"""Assemblage FFmpeg : clips → final 1080×1920 (+ narration / SFX, textes, loudnorm), preview 480p, poster."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..models import ScriptV1
from ..youtube.storage import upload_preview
from .base import Context, Step

W, H, FPS = 1080, 1920, 30


class AssembleStep(Step):
    type = "assemble"
    lane = "io"  # CPU (FFmpeg) ; passer en "gpu" si upscale Real-ESRGAN sur GPU

    def run(self, ctx: Context) -> dict[str, Any]:
        vid, pid = ctx.job.video_id, ctx.job.production_id
        v = ctx.db.fetch_one("select lang, format from videos where id = %s", (vid,))
        prod = ctx.db.fetch_one("select script from productions where id = %s", (pid,))
        assert v and prod and prod["script"]
        script = ScriptV1.model_validate(prod["script"])
        ctx.db.set_status("videos", vid, "rendering")
        ctx.db.set_status("productions", pid, "assembling")

        clips = ctx.db.fetch_all(
            "select scene_index, local_path from assets where production_id = %s and kind = 'clip' order by scene_index",
            (pid,),
        )
        assert len(clips) == len(script.scenes), f"{len(clips)} clips pour {len(script.scenes)} scènes"
        vdir = ctx.video_dir(vid)
        final, preview, poster = vdir / "final.mp4", vdir / "preview.mp4", vdir / "poster.jpg"
        narration = vdir / "narration.wav" if v["format"] == "A_voiceover" else None

        if ctx.settings.dry_run:
            for p in (final, preview):
                p.write_bytes(b"")
            poster.write_bytes(b"")
        else:
            ctx.progress(10, "Concat + upscale")
            self._render(script, v["lang"], [Path(c["local_path"]) for c in clips], narration, final)
            ctx.progress(70, "Preview + poster")
            _run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(final),
                    "-vf",
                    "scale=480:-2",
                    "-c:v",
                    "libx264",
                    "-crf",
                    "28",
                    "-preset",
                    "veryfast",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "96k",
                    "-movflags",
                    "+faststart",
                    str(preview),
                ]
            )
            _run(["ffmpeg", "-y", "-ss", "0.5", "-i", str(final), "-frames:v", "1", "-q:v", "3", str(poster)])

        ctx.progress(85, "Envoi de l'aperçu")
        preview_path = upload_preview(ctx.settings, preview, f"{vid}/preview.mp4", "video/mp4")
        poster_path = upload_preview(ctx.settings, poster, f"{vid}/poster.jpg", "image/jpeg")
        final_id = ctx.db.add_asset(
            video_id=vid,
            kind="final",
            local_path=str(final),
            width=W,
            height=H,
            duration_s=script.duration_s,
            bytes=final.stat().st_size,
        )
        preview_id = ctx.db.add_asset(
            video_id=vid, kind="preview", local_path=str(preview), storage_bucket="previews", storage_path=preview_path
        )
        poster_id = ctx.db.add_asset(
            video_id=vid, kind="poster", local_path=str(poster), storage_bucket="previews", storage_path=poster_path
        )
        ctx.db.execute(
            "update videos set final_asset_id = %s, preview_asset_id = %s, poster_asset_id = %s, duration_s = %s where id = %s",
            (final_id, preview_id, poster_id, script.duration_s, vid),
        )
        return {"final": str(final), "preview": preview_path}

    def _render(self, script: ScriptV1, lang: str, clips: list[Path], narration: Path | None, out: Path) -> None:
        """Construit le filtre FFmpeg : scale/pad 9:16, fondus, textes, mixage, loudnorm."""
        inputs: list[str] = []
        for c in clips:
            inputs += ["-i", str(c)]
        if narration:
            inputs += ["-i", str(narration)]
        parts, names = [], []
        for i, scene in enumerate(script.scenes):
            font = (
                ""
                if not scene.on_screen_text.get(lang)
                else (
                    f",drawtext=text='{_esc(scene.on_screen_text[lang])}':fontsize=64:fontcolor=white:"
                    f"borderw=3:x=(w-text_w)/2:y=h*0.18"
                )
            )
            parts.append(
                f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"fps={FPS},setsar=1,trim=duration={scene.duration_s},setpts=PTS-STARTPTS{font}[v{i}]"
            )
            names.append(f"[v{i}]")
        parts.append(f"{''.join(names)}concat=n={len(names)}:v=1:a=0[vout]")
        cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(parts), "-map", "[vout]"]
        if narration:
            cmd += ["-map", f"{len(clips)}:a", "-af", "loudnorm=I=-14:TP=-1:LRA=11", "-c:a", "aac", "-b:a", "192k"]
        else:
            # TODO(format B) : lit d'ambiance + SFX par scène depuis data/sfx (amix), loudnorm
            cmd += ["-an"]
        cmd += [
            "-c:v",
            "libx264",
            "-profile:v",
            "high",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-shortest",
            str(out),
        ]
        _run(cmd)


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")


def _run(cmd: list[str]) -> None:
    if shutil.which(cmd[0]) is None:
        raise RuntimeError(f"{cmd[0]} introuvable dans le PATH")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} a échoué : {r.stderr[-2000:]}")
