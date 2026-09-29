"""Rendu exact d'un modèle de montage (onglet Montage du dashboard, bouton « Rendu exact ») : quelques secondes montées
par le vrai code du montage (fichier ASS des sous-titres et des textes à l'écran, titre d'accroche en PNG, même FFmpeg)
sur un clip ou une image d'une production, sans son. Le modèle vient du payload (réglages en cours, pas forcément
enregistrés). Fichiers : DATA_DIR/previews/montage/<job>.mp4 et .jpg, chemins dans jobs.result, servis par la route
/api/montage-preview/<job> du dashboard (docs/23-montage.md).

Mode « sound » (onglet Montage → Son, docs/26-musique.md) : une vidéo déjà montée, avec la musique choisie et les
niveaux du modèle en cours ; l'image est copiée telle quelle, le son est recalculé par le code du montage (voix,
musique baissée sous la voix, bruitages, −14 LUFS). Quelques secondes."""

from __future__ import annotations

import dataclasses
import shutil
import time
from pathlib import Path
from typing import Any

from ..media import probe_duration, run
from ..montage import FORMATS, MontageTemplate, font_registry
from ..music import sync_library
from ..numbers import to_digits
from ..recipes import montage_format
from ..subtitles import distribute_words
from .assemble import (
    FPS,
    H,
    RenderPlan,
    W,
    apply_audio,
    apply_template,
    narration_loudness,
    prepare_video,
    render,
    sound_command,
)
from .base import Context, Step

# Textes d'essai quand le dashboard n'en envoie pas (ton des séries)
SAMPLES = {
    "hook": "Personne ne voulait de ce terrain",
    "subtitle": "Derrière ce miroir se cache une pièce que personne n'avait vue depuis 120 ans.",
    "title": "Salon · 60 m²",
}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
KEEP = 20  # rendus gardés sur le disque, les plus récents


class MontagePreviewStep(Step):
    type = "montage_preview"
    # Voie des aperçus (worker/main.py : preview_lane) : pris dans la seconde, même pendant un clip de 10 min. Encodé sur le
    # processeur (libx264) : NVENC pourrait manquer de mémoire vidéo à côté de ComfyUI ; l'habillage est le même.
    lane = "preview"

    def run(self, ctx: Context) -> dict[str, Any]:
        p = ctx.job.payload or {}
        if p.get("mode") == "sound":
            return self._sound(ctx, p)
        template = MontageTemplate.model_validate(p.get("template") or {})
        recipe = p.get("recipe") if p.get("recipe") in FORMATS else "story"
        given = p.get("texts") or {}
        # nombres en chiffres, comme au vrai montage (worker/numbers.py)
        texts = {k: to_digits(" ".join(str(given.get(k) or "").split())[:300] or v) for k, v in SAMPLES.items()}
        duration = min(10.0, max(3.0, float(p.get("duration_s") or 5.0)))
        root = ctx.settings.data_dir / "previews" / "montage"
        work = root / str(ctx.job.id)
        work.mkdir(parents=True, exist_ok=True)
        video, poster = root / f"{ctx.job.id}.mp4", root / f"{ctx.job.id}.jpg"
        started = time.monotonic()
        try:
            ctx.progress(10, "Fond de l'aperçu")
            clip, native = self._background(ctx, p.get("asset_id"), work, duration)
            fonts = font_registry(ctx.settings)
            plan = RenderPlan(clips=[clip], clip_durations=[native], scene_durations=[duration])
            if recipe == "story":  # récit narré : les sous-titres suivent la voix, mot à mot
                plan.words_by_scene = [distribute_words(texts["subtitle"], 0.3, duration - 0.3)]
            if recipe == "timelapse":  # chantier : le compteur de jours défile
                step = duration / 4
                plan.ticks = [(round(i * step, 3), round((i + 1) * step, 3), f"Jour {1 + 30 * i}") for i in range(4)]
            else:
                plan.titles = [(0.0, duration, texts["title"])]
            report = apply_template(plan, template, recipe, hook=texts["hook"], workdir=work, fonts=fonts)
            ctx.progress(40, "Montage de l'aperçu")
            out = work / "apercu.mp4"
            if ctx.settings.dry_run:
                out.write_bytes(b"")
                (work / "apercu.jpg").write_bytes(b"")
            else:
                render(plan, out, fonts=fonts, encoder="cpu")
                run(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "error",
                        "-ss",
                        f"{min(1.5, duration / 2):.2f}",
                        "-i",
                        str(out),
                        "-frames:v",
                        "1",
                        "-q:v",
                        "3",
                        str(work / "apercu.jpg"),
                    ]
                )
            shutil.move(str(out), video)
            shutil.move(str(work / "apercu.jpg"), poster)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        _prune(root)
        return {
            "path": str(video),
            "poster": str(poster),
            "recipe": recipe,
            "duration_s": duration,
            "elapsed_s": round(time.monotonic() - started, 1),
            **report,
        }

    def _sound(self, ctx: Context, p: dict[str, Any]) -> dict[str, Any]:
        """Essai du son : la vidéo `video_id` avec la musique `music_track` (volume et début envoyés par l'éditeur, pas
        forcément encore enregistrés) aux niveaux du modèle en cours ; null = sans musique."""
        started = time.monotonic()
        template = MontageTemplate.model_validate(p.get("template") or {})
        vid = str(p.get("video_id") or "")
        row = ctx.db.fetch_one(
            """select v.production_id, (select local_path from assets a where a.video_id = v.id and a.kind = 'final'
                 order by a.created_at desc limit 1) as final from videos v where v.id = %s""",
            (vid,),
        )
        if not row or not row["production_id"]:
            raise RuntimeError("vidéo d'essai introuvable")
        source = Path(row["final"]) if row["final"] else None
        if not source or not source.is_file():
            raise RuntimeError("vidéo d'essai sans fichier final (effacé ?) : choisis-en une autre")
        ctx.progress(10, "Préparation du son")
        m = prepare_video(ctx.db, ctx.settings, vid, row["production_id"])
        wanted = p.get("music_track")
        track = None
        if wanted and template.plays_music(montage_format(m.recipe)):  # un drame a la musique des récits
            tracks = {t.id: t for t in sync_library(ctx.db, ctx.settings.effective_music_library_dir)}
            track = tracks.get(str(wanted))
            if not track or track.path is None:
                raise RuntimeError(f"musique « {wanted} » absente du dossier des musiques")
            overrides = {k: float(p[f"track_{k}"]) for k in ("gain_db", "start_s") if p.get(f"track_{k}") is not None}
            track = dataclasses.replace(track, **overrides)
        mix = apply_audio(
            m.plan,
            template.audio,
            track,
            narration_lufs=narration_loudness(m.plan, ctx.settings.dry_run),
            words=m.timeline.words if m.timeline else (),
        )
        root = ctx.settings.data_dir / "previews" / "montage"
        root.mkdir(parents=True, exist_ok=True)
        video, poster = root / f"{ctx.job.id}.mp4", root / f"{ctx.job.id}.jpg"
        ctx.progress(40, "Mixage du son" + (f" · « {track.title} »" if track else " · sans musique"))
        if ctx.settings.dry_run:
            video.write_bytes(b"")
            poster.write_bytes(b"")
        else:
            tmp = root / f"{ctx.job.id}.tmp.mp4"
            run(sound_command(m.plan, source, tmp))
            run(["ffmpeg", "-y", "-v", "error", "-ss", "1.5", "-i", str(tmp), "-frames:v", "1", "-q:v", "3", str(poster)])
            shutil.move(str(tmp), video)
        _prune(root)
        return {
            "path": str(video),
            "poster": str(poster),
            "mode": "sound",
            "video_id": vid,
            "recipe": m.recipe,
            "music_track": track.id if track else None,
            "duration_s": m.plan.total_s,
            "elapsed_s": round(time.monotonic() - started, 1),
            "mix": mix,
        }

    def _background(self, ctx: Context, asset_id: Any, work: Path, duration: float) -> tuple[Path, float | None]:
        """Clip choisi tel quel ; une image devient un plan fixe ; sans fond, un dégradé neutre."""
        row = ctx.db.fetch_one("select local_path, duration_s from assets where id = %s", (str(asset_id),)) if asset_id else None
        src = Path(row["local_path"]) if row and row["local_path"] else None
        if src and src.is_file() and src.suffix.lower() not in IMAGE_EXT:
            native = float(row["duration_s"]) if row and row["duration_s"] else probe_duration(src)
            return src, native
        out = work / "fond.mp4"
        geom = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=yuv420p"
        if src and src.is_file():
            source = ["-loop", "1", "-i", str(src)]
        else:
            source = ["-f", "lavfi", "-i", f"gradients=s={W}x{H}:c0=0x2B3A55:c1=0xC9A66B:x0=0:y0=0:x1={W}:y1={H}:speed=0.02"]
        if not ctx.settings.dry_run:
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-v",
                    "error",
                    *source,
                    "-t",
                    f"{duration:.2f}",
                    "-r",
                    str(FPS),
                    "-vf",
                    geom,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "20",
                    str(out),
                ]
            )
        return out, duration


def _prune(folder: Path) -> None:
    for ext in ("*.mp4", "*.jpg"):
        files = sorted(folder.glob(ext), key=lambda f: f.stat().st_mtime, reverse=True)
        for old in files[KEEP:]:
            old.unlink(missing_ok=True)
