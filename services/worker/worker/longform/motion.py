"""Plans des vidéos longues en 16:9 (docs/63 §5) : une image fixe animée par un mouvement de caméra lent (zoom,
travelling), calculé image par image en Pillow (sous-pixel : pas les saccades du filtre zoompan), ou un clip d'IA mis à
la taille ; l'écran de chapitre se pose par-dessus. Chaque plan devient un segment MP4 sans son, tous encodés pareil
(1920 × 1080, 30 i/s, yuv420p) pour être mis bout à bout sans réencodage (worker/longform/render.py).

Les durées se comptent en IMAGES, jamais en secondes arrondies : sur 220 plans, un arrondi d'une demi-image par plan
décalerait l'image de la voix de près de 4 s à la fin de la vidéo."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Any

W, H, FPS = 1920, 1080, 30
ZOOM_MAX = 1.12  # zoom total d'un plan : lent, presque imperceptible à l'échelle d'une seconde
CLIP_SLOW_MAX = 1.25  # un clip se ralentit au plus de 25 % ; au-delà, son dernier instant continue en image fixe animée
CARD_IN, CARD_HOLD, CARD_OUT = 0.5, 2.6, 0.6  # écran de chapitre : apparition, tenue, disparition (secondes)


def encode_args(nvenc: bool) -> list[str]:
    if nvenc:
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "20", "-b:v", "0", "-profile:v", "high"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high"]


def segment_tail(out: Path, nvenc: bool) -> list[str]:
    return [*encode_args(nvenc), "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", str(out)]


def cover(img: Any, size: tuple[int, int]) -> Any:
    """L'image agrandie pour couvrir `size`, recadrée au centre."""
    from PIL import Image

    tw, th = size
    scale = max(tw / img.width, th / img.height)
    resized = img.resize((math.ceil(img.width * scale), math.ceil(img.height * scale)), Image.Resampling.LANCZOS)
    left, top = (resized.width - tw) // 2, (resized.height - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def ease(t: float) -> float:
    """Départ et arrivée en douceur : la caméra ne démarre ni ne s'arrête d'un coup."""
    t = min(1.0, max(0.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def window(t: float, move: str, base: tuple[int, int]) -> tuple[float, float, float, float]:
    """Fenêtre (x0, y0, x1, y1) découpée dans l'image agrandie `base` (taille W·ZOOM_MAX × H·ZOOM_MAX) à l'instant
    t ∈ [0, 1]. in : de l'image entière au centre agrandi ; out : l'inverse ; left/right/up/down : léger zoom fixe,
    l'image glisse lentement dans ce sens."""
    bw, bh = base
    e = ease(t)
    if move in ("in", "out"):
        z = 1 + (ZOOM_MAX - 1) * (e if move == "in" else 1 - e)
        ww, wh = bw / z, bh / z
        cx, cy = bw / 2, bh / 2
    else:
        z = ZOOM_MAX
        ww, wh = bw / z, bh / z
        span_x, span_y = (bw - ww) / 2, (bh - wh) / 2
        k = 2 * e - 1  # -1 → +1
        cx = bw / 2 + (span_x * k if move == "right" else -span_x * k if move == "left" else 0.0)
        cy = bh / 2 + (span_y * k if move == "down" else -span_y * k if move == "up" else 0.0)
    return (cx - ww / 2, cy - wh / 2, cx + ww / 2, cy + wh / 2)


def card_alpha(t_s: float) -> float:
    """Opacité de l'écran de chapitre à l'instant t_s (secondes depuis le début du plan)."""
    if t_s < CARD_IN:
        return t_s / CARD_IN
    if t_s < CARD_IN + CARD_HOLD:
        return 1.0
    if t_s < CARD_IN + CARD_HOLD + CARD_OUT:
        return 1.0 - (t_s - CARD_IN - CARD_HOLD) / CARD_OUT
    return 0.0


def _faded(overlay: Any, a: float) -> Any:
    from PIL import Image

    r, g, b, alpha = overlay.split()
    return Image.merge("RGBA", (r, g, b, alpha.point(lambda v: int(v * a))))


def _writer(out: Path, nvenc: bool) -> subprocess.Popen:
    out.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{W}x{H}",
            "-r",
            str(FPS),
            "-i",
            "-",
            *segment_tail(out, nvenc),
        ],  # fmt: skip
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def render_still(
    image: Path, out: Path, frames: int, move: str, *, card: Path | None = None, card_from: int = 0, nvenc: bool = False
) -> int:
    """Segment de `frames` images d'une image fixe animée. `card_from` : l'écran de chapitre commence à cette image du
    segment (0 = tout de suite)."""
    from PIL import Image

    src = Image.open(image).convert("RGB")
    base = cover(src, (round(W * ZOOM_MAX) + 2, round(H * ZOOM_MAX) + 2))
    overlay = Image.open(card).convert("RGBA") if card else None
    n = max(1, frames)
    proc = _writer(out, nvenc)
    assert proc.stdin is not None
    try:
        for i in range(n):
            frame = base.resize((W, H), Image.Resampling.BICUBIC, box=window(i / max(1, n - 1), move, base.size))
            if overlay is not None and i >= card_from:
                a = card_alpha((i - card_from) / FPS)
                if a > 0:
                    layer = overlay if a >= 1 else _faded(overlay, a)
                    frame = Image.alpha_composite(frame.convert("RGBA"), layer).convert("RGB")
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        code = proc.wait()
    if code != 0:
        raise RuntimeError(f"ffmpeg a échoué sur l'image animée {image.name} : {err[-400:]}")
    return n


def clip_frames(native_s: float, frames: int) -> int:
    """Images du segment jouées par le clip (ralenti au plus de CLIP_SLOW_MAX) ; le reste continue en image fixe."""
    if native_s <= 0:
        return frames
    return min(frames, int(native_s * CLIP_SLOW_MAX * FPS))


def clip_command(clip: Path, out: Path, frames: int, native_s: float, *, card: Path | None, nvenc: bool) -> list[str]:
    """Le clip mis en 1920 × 1080 (recadré pour couvrir), ralenti juste assez pour durer `frames` images (au plus
    CLIP_SLOW_MAX), `frames` images exactement."""
    want_s = frames / FPS
    slow = min(CLIP_SLOW_MAX, max(1.0, want_s / native_s)) if native_s > 0 else 1.0
    chain = (
        f"[0:v]setpts={slow:.4f}*PTS,fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={W}:{H},setsar=1,format=yuv420p"
    )
    inputs = ["-i", str(clip)]
    if card:
        inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(card)]
        fade_out = CARD_IN + CARD_HOLD
        chain += (
            f"[v0];[1:v]format=rgba,fade=t=in:st=0:d={CARD_IN}:alpha=1,fade=t=out:st={fade_out}:d={CARD_OUT}:alpha=1[c];"
            f"[v0][c]overlay=0:0:shortest=1,format=yuv420p"
        )
    chain += ",tpad=stop_mode=clone:stop=-1[v]"  # garde-fou : jamais une image de moins que demandé
    return [
        "ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", chain, "-map", "[v]",
        "-frames:v", str(frames), *segment_tail(out, nvenc),
    ]  # fmt: skip


def last_frame(clip: Path, out: Path) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-sseof", "-0.1", "-i", str(clip), "-frames:v", "1", "-update", "1", str(out)],
        check=True,
        capture_output=True,
    )
    return out


def render_clip(
    clip: Path, out: Path, frames: int, native_s: float, *, card: Path | None = None, nvenc: bool = False
) -> list[Path]:
    """Segment(s) d'un plan clip, `frames` images en tout : le clip (ralenti au besoin), puis, s'il reste du temps, son
    dernier instant en image fixe animée (même image : le raccord ne se voit pas). Renvoie les segments dans l'ordre."""
    played = clip_frames(native_s, frames)
    rest = frames - played
    if rest < 3:  # moins de 3 images de reste : le clip couvre tout (tpad tient la dernière image)
        played, rest = frames, 0
    proc = subprocess.run(clip_command(clip, out, played, native_s, card=card, nvenc=nvenc), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg a échoué sur le clip {clip.name} : {(proc.stderr or '')[-400:]}")
    if not rest:
        return [out]
    still = last_frame(clip, out.with_suffix(".fin.png"))
    tail = out.with_name(out.stem + "_suite.mp4")
    render_still(still, tail, rest, "in", nvenc=nvenc)
    return [out, tail]


def chapter_card(number: int, title: str, out: Path, fonts_dir: Path) -> Path:
    """Écran de chapitre (calque transparent 1920 × 1080) : un bandeau sombre en bas à gauche, « CHAPITRE 2 » en petit,
    le titre en grand. Posé au début du premier plan du chapitre (CARD_IN + CARD_HOLD + CARD_OUT secondes)."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    big = ImageFont.truetype(str(fonts_dir / "BebasNeue-Regular.ttf"), 112)
    small = ImageFont.truetype(str(fonts_dir / "Montserrat-SemiBold.ttf"), 34)
    label = f"CHAPITRE {number}"
    text = title.strip().upper()
    probe = ImageDraw.Draw(img)
    while probe.textlength(text, font=big) > W - 360 and big.size > 60:
        big = ImageFont.truetype(str(fonts_dir / "BebasNeue-Regular.ttf"), big.size - 6)
    x, y = 120, H - 450  # le bandeau s'arrête à 820 px : les sous-titres (captions.py, centrés à 950 px) restent libres
    tw = max(probe.textlength(text, font=big), probe.textlength(label, font=small))
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shade).rounded_rectangle((x - 50, y - 40, x + tw + 60, y + 190), radius=18, fill=(0, 0, 0, 150))
    img = Image.alpha_composite(img, shade.filter(ImageFilter.GaussianBlur(6)))
    d = ImageDraw.Draw(img)
    d.text((x, y), label, font=small, fill=(232, 196, 120, 255))
    d.line((x, y + 52, x + 90, y + 52), fill=(232, 196, 120, 255), width=4)
    d.text((x, y + 66), text, font=big, fill=(255, 255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out
