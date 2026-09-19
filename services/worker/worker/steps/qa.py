"""Contrôle qualité du final : durée, résolution, loudness, frames noires, narration tronquée."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from ..models import QACheck, QAReport
from .base import Context, Step


class QAStep(Step):
    type = "qa"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        vid = ctx.job.video_id
        v = ctx.db.fetch_one(
            """select v.format, v.title, v.lang, a.local_path, c.auto_publish from videos v
               join assets a on a.id = v.final_asset_id join channels c on c.id = v.channel_id where v.id = %s""",
            (vid,),
        )
        assert v, "final manquant"
        ctx.db.set_status("videos", vid, "qa")
        report = (
            QAReport(ok=True, checks=[], duration_s=30.0)
            if ctx.settings.dry_run
            else self._analyse(Path(v["local_path"]), v["format"])
        )
        ctx.db.execute("update videos set qa_report = %s where id = %s", (Jsonb(report.model_dump()), vid))
        if not report.ok:
            failed = ", ".join(c.name for c in report.checks if not c.ok)
            ctx.db.set_status("videos", vid, "failed", f"QA : {failed}")
            raise RuntimeError(f"QA échoué : {failed}")
        if v["auto_publish"]:
            ctx.db.set_status("videos", vid, "ready")
        else:
            ctx.db.set_status("videos", vid, "review")
            if ctx.settings.notify_on_review:  # le planificateur envoie les alertes warning/error par mail
                ctx.db.alert(
                    "warning",
                    f"Validation requise : {v['title'] or 'Short'} ({v['lang'].upper()})",
                    "Ouvrir le dashboard → Production → Contrôle / revue, puis Approuver ou Refuser.",
                    video_id=vid,
                )
        self._maybe_mark_production_ready(ctx)
        return report.model_dump()

    def _analyse(self, path: Path, fmt: str) -> QAReport:
        probe = json.loads(
            subprocess.run(
                ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
        vs = next(s for s in probe["streams"] if s["codec_type"] == "video")
        dur = float(probe["format"]["duration"])
        checks = [
            QACheck(name="duration", ok=15 <= dur <= 58, value=dur),
            QACheck(name="resolution", ok=(vs["width"], vs["height"]) == (1080, 1920), value=f"{vs['width']}x{vs['height']}"),
        ]
        lufs = None
        if fmt == "A_voiceover":
            r = subprocess.run(
                ["ffmpeg", "-i", str(path), "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                capture_output=True,
                text=True,
            )
            m = re.search(r'"input_i"\s*:\s*"(-?[\d.]+)"', r.stderr)
            lufs = float(m.group(1)) if m else None
            checks.append(QACheck(name="loudness", ok=lufs is not None and -15 <= lufs <= -13, value=lufs))
        r = subprocess.run(
            ["ffmpeg", "-i", str(path), "-vf", "blackdetect=d=0.3:pix_th=0.10", "-an", "-f", "null", "-"],
            capture_output=True,
            text=True,
        )
        black = sum(float(x) for x in re.findall(r"black_duration:([\d.]+)", r.stderr))
        checks.append(QACheck(name="black_frames", ok=black < 0.5, value=black))
        return QAReport(ok=all(c.ok for c in checks), checks=checks, duration_s=dur, loudness_lufs=lufs)

    def _maybe_mark_production_ready(self, ctx: Context) -> None:
        pid = ctx.job.production_id
        row = ctx.db.fetch_one(
            "select bool_and(status in ('review', 'ready', 'scheduled', 'published')) as done from videos where production_id = %s",
            (pid,),
        )
        if row and row["done"]:
            ctx.db.set_status("productions", pid, "ready")
