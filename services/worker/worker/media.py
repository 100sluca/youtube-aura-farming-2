"""Outils FFmpeg partagés : encodeur (NVENC ou CPU), musique d'ambiance, sonie et durée d'un média.

Encodeur et test NVENC repris de MJClipIt (services/media.py) : un encodage d'une image est le seul test
honnête (pilote, mémoire), et NVENC divise environ par deux le temps de montage sur une RTX 3070.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}
_ENCODER: dict[str, list[str]] = {}


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 1800) -> None:
    if shutil.which(cmd[0]) is None:
        raise RuntimeError(f"{cmd[0]} introuvable dans le PATH (winget install Gyan.FFmpeg)")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} a échoué : {r.stderr[-2000:]}")


def _nvenc_works() -> bool:
    try:
        listed = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20).stdout
        if "h264_nvenc" not in listed:
            return False
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
             "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True, timeout=60,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def video_encode_args(mode: str = "auto") -> list[str]:
    """Arguments de codec vidéo : NVENC (qualité constante 19) si disponible, sinon libx264 CRF 18."""
    if mode not in _ENCODER:
        if mode == "nvenc" or (mode == "auto" and _nvenc_works()):
            _ENCODER[mode] = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0",
                              "-profile:v", "high"]
        else:
            _ENCODER[mode] = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high"]
    return list(_ENCODER[mode])


# Ancienne bibliothèque DATA_DIR/music/<ambiance>/ (pistes ACE-Step) : ne sert plus qu'à défaut de la bibliothèque de
# Luca (worker/music.py, dossier « music » du dépôt). Ambiance sans piste : une ambiance voisine plutôt qu'une vidéo
# sans musique (le récit du canal Rhin-Main-Danube, le 28/09, demandait « mysterious », dossier vide : aucune musique).
MOOD_FALLBACKS: dict[str, tuple[str, ...]] = {
    "mysterious": ("suspense", "emotional"),
    "suspense": ("mysterious",),
    "emotional": ("calm", "mysterious"),
    "calm": ("emotional",),
    "epic": ("inspiring",),
    "inspiring": ("epic", "upbeat"),
    "upbeat": ("inspiring",),
    "luxury": ("elegant", "chill"),
    "elegant": ("luxury", "calm"),
    "chill": ("luxury",),
}


def pick_music(music_dir: Path, mood: str | None, key: str) -> Path | None:
    """Choisit une piste dans music_dir/<ambiance>/, puis dans une ambiance voisine (MOOD_FALLBACKS), puis dans
    music_dir/default/ ; stable pour une même clé."""
    moods = [mood, *MOOD_FALLBACKS.get(mood, ())] if mood else []
    for folder in [music_dir / m for m in moods] + [music_dir / "default"]:
        if folder.is_dir():
            tracks = sorted(p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXT)
            if tracks:
                h = int(hashlib.sha1(key.encode()).hexdigest(), 16)
                return tracks[h % len(tracks)]
    return None


@dataclass(frozen=True)
class Loudness:
    lufs: float | None  # sonie intégrée EBU R128 ; None : fichier muet ou illisible
    peak_db: float | None  # crête vraie (dBTP)
    duration_s: float | None


_SUMMARY_I = re.compile(r"I:\s+(-?\d+(?:\.\d+)?) LUFS")
_SUMMARY_PEAK = re.compile(r"Peak:\s+(-?\d+(?:\.\d+)?|-inf) dBFS")
_DURATION = re.compile(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)")
SILENT_LUFS = -60.0  # en dessous, fichier presque muet : pas de niveau fiable


def parse_ebur128(stderr: str) -> Loudness:
    """Résumé du filtre ebur128 de FFmpeg (« I: -15.8 LUFS », « Peak: -2.6 dBFS ») et durée de l'entrée."""
    summary = stderr.rsplit("Summary:", 1)[-1] if "Summary:" in stderr else ""
    i, peak, dur = _SUMMARY_I.search(summary), _SUMMARY_PEAK.search(summary), _DURATION.search(stderr)
    lufs = float(i.group(1)) if i else None
    return Loudness(
        lufs=lufs if lufs is not None and lufs > SILENT_LUFS else None,
        peak_db=float(peak.group(1)) if peak and peak.group(1) != "-inf" else None,
        duration_s=round(int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3)), 3) if dur else None,
    )


def measure_loudness(path: Path, timeout: int = 180) -> Loudness:
    """Sonie intégrée (EBU R128), crête et durée d'un fichier audio, en une lecture : ce qui permet de mettre toutes les
    musiques et toutes les voix au même niveau avant les réglages du modèle de montage (worker/music.py). Environ 1 s
    pour une piste de 4 min."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=framelog=quiet:peak=true", "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return Loudness(None, None, None)
    return parse_ebur128(r.stderr)


def contact_sheet(rows: list[list[Path]], selected: list[int | None], out: Path, cell_w: int = 216, cell_h: int = 384) -> Path:
    """Planche du storyboard : une ligne par scène, une colonne par image candidate ; la retenue est cadrée en vert."""
    cells, layout, n = [], [], 0
    inputs: list[str] = []
    for r, row in enumerate(rows):
        for c, img in enumerate(row):
            inputs += ["-i", str(img)]
            box = ",drawbox=x=0:y=0:w=iw:h=ih:color=0x00E676:t=10" if selected[r] == c else ""
            cells.append(f"[{n}:v]scale={cell_w}:{cell_h}:force_original_aspect_ratio=increase,crop={cell_w}:{cell_h},setsar=1{box}[c{n}]")
            layout.append(f"{c * cell_w}_{r * cell_h}")
            n += 1
    if n == 0:
        raise ValueError("storyboard vide")
    if n == 1:
        graph = cells[0].replace("[c0]", "[out]")
    else:
        graph = ";".join(cells) + ";" + "".join(f"[c{i}]" for i in range(n)) + f"xstack=inputs={n}:layout={'|'.join(layout)}:fill=0x202020[out]"
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "[out]", "-frames:v", "1", str(out)])
    return out


def last_frame(video: Path, out: Path, offset_s: float = 0.05) -> Path:
    """Dernière image d'un clip en PNG : point de départ du clip suivant quand la scène le prolonge."""
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-v", "error", "-sseof", f"-{max(0.02, offset_s):.3f}", "-i", str(video),
         "-frames:v", "1", "-update", "1", str(out)])
    if not out.exists() or out.stat().st_size == 0:  # clip trop court pour le seek : on inverse et on prend la première
        run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", "reverse", "-frames:v", "1", "-update", "1", str(out)])
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"dernière image introuvable : {video}")
    return out


def probe_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout
        return float(json.loads(out)["format"]["duration"])
    except (OSError, subprocess.SubprocessError, KeyError, ValueError):
        return None
