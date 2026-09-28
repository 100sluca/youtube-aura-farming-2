"""Planches d'images des vidéos pour l'agent analyste (docs/25-dashboard-statistiques.md) : ce que le spectateur voit.

Une planche par vidéo, quatre images 9:16 côte à côte (768 px de large, la taille qu'envoie encode_image) :
- vidéo de l'appli encore sur le PC : images tirées du fichier final à 0,5 s et 2,5 s (l'accroche), au milieu et à 90 % ;
- sinon (mise en ligne à la main, fichiers effacés) : les images que YouTube publie pour chaque vidéo à 25, 50 et 75 %
  de sa durée (sd1-3.jpg, 4:3 avec la vidéo verticale au centre : on garde le centre).
Les planches sont gardées dans DATA_DIR/analysis/<vidéo>.jpg : une vidéo publiée ne change plus.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import httpx
import structlog

from .media import probe_duration, run

log = structlog.get_logger(__name__)

CELL_W, CELL_H = 192, 341
YOUTUBE_FRAMES = ("1", "2", "3")  # 25 %, 50 %, 75 % de la vidéo


def frame_times(duration: float | None) -> list[float]:
    """Instants des images d'une vidéo de l'appli : l'accroche (0,5 s, 2,5 s), le milieu, la fin (90 %)."""
    d = duration or 20.0
    times = [0.5, 2.5, d * 0.5, d * 0.9]
    return sorted({round(min(max(t, 0.0), max(d - 0.1, 0.0)), 2) for t in times})


def local_frames(video: Path, work: Path) -> list[Path]:
    """Images du fichier final, recadrées en 9:16 à la taille d'une case."""
    work.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for i, t in enumerate(frame_times(probe_duration(video))):
        target = work / f"{i}.jpg"
        run([
            "ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
            "-vf", f"scale={CELL_W}:{CELL_H}:force_original_aspect_ratio=increase,crop={CELL_W}:{CELL_H}",
            str(target),
        ], timeout=120)
        if target.exists():
            out.append(target)
    return out


def center_crop_916(image: Any) -> Any:
    """Le centre 9:16 d'une image YouTube 4:3 (la vidéo verticale est au milieu, les bords sont du remplissage)."""
    w, h = image.size
    cw = min(w, round(h * 9 / 16))
    left = (w - cw) // 2
    return image.crop((left, 0, left + cw, h))


def youtube_frames(youtube_id: str, work: Path) -> list[Path]:
    """Les images publiées par YouTube (25, 50, 75 %), recadrées en 9:16 à la taille d'une case."""
    from PIL import Image

    work.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for n in YOUTUBE_FRAMES:
        for size in ("sd", "hq"):  # 640×480, sinon 480×360
            try:
                r = httpx.get(f"https://i.ytimg.com/vi/{youtube_id}/{size}{n}.jpg", timeout=20)
            except httpx.HTTPError:
                continue
            if r.status_code != 200 or len(r.content) < 2000:  # image absente : YouTube renvoie une vignette grise
                continue
            with Image.open(io.BytesIO(r.content)) as im:
                frame = center_crop_916(im.convert("RGB")).resize((CELL_W, CELL_H))
            target = work / f"yt{n}.jpg"
            frame.save(target, "JPEG", quality=88)
            out.append(target)
            break
    return out


def strip(frames: list[Path], out: Path) -> Path:
    from PIL import Image

    sheet = Image.new("RGB", (CELL_W * len(frames), CELL_H), (0, 0, 0))
    for i, f in enumerate(frames):
        with Image.open(f) as im:
            sheet.paste(im.convert("RGB").resize((CELL_W, CELL_H)), (i * CELL_W, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, "JPEG", quality=85)
    return out


def video_sheet(db: Any, data_dir: Path, video_id: str) -> Path | None:
    """Planche d'une vidéo publiée (en cache) ; None si ni le fichier ni YouTube ne donnent d'image."""
    out = data_dir / "analysis" / f"{video_id}.jpg"
    if out.exists():
        return out
    v = db.fetch_one(
        """select v.youtube_video_id, v.files_deleted_at,
                  (select a.local_path from assets a where a.video_id = v.id and a.kind = 'final'
                   order by a.created_at desc limit 1) as final_path
           from videos v where v.id = %s""",
        (video_id,),
    )
    if not v:
        return None
    work = data_dir / "analysis" / f"{video_id}.work"
    try:
        final = Path(v["final_path"]) if v.get("final_path") and not v.get("files_deleted_at") else None
        frames = local_frames(final, work) if final and final.exists() else []
        if not frames and v.get("youtube_video_id"):
            frames = youtube_frames(v["youtube_video_id"], work)
        return strip(frames, out) if frames else None
    except Exception as exc:  # noqa: BLE001 — une planche manquante ne bloque pas l'analyse
        log.warning("analyse.planche_impossible", video=video_id, error=str(exc)[:200])
        return None
    finally:
        for f in work.glob("*.jpg") if work.exists() else []:
            f.unlink(missing_ok=True)
        if work.exists():
            work.rmdir()
