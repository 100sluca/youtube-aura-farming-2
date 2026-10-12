"""Miniatures des vidéos longues (docs/63 §6) : l'image est générée SANS texte (les modèles d'image écrivent mal), puis
le code pose 0 à 4 mots en lettres grasses (Anton), jaunes ou blanches à contour noir épais, dans la zone que l'image
laisse libre, avec un léger dégradé sombre derrière pour la lecture en petit. 1280 × 720, JPEG (2 Mo au plus pour
YouTube). Trois concepts différents par vidéo : Luca choisit, YouTube peut les tester (Test & Compare)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .motion import cover

TW, TH = 1280, 720
YELLOW, WHITE, BLACK = (255, 214, 0), (255, 255, 255), (0, 0, 0)
STROKE = 9
MARGIN = 54
NBSP = " "


def wrap(text: str, font: Any, max_w: float, draw: Any) -> list[str]:
    """Le texte en lignes de largeur max_w au plus (mots entiers), 3 lignes au plus."""
    lines: list[str] = []
    cur = ""
    for w in text.split(" "):  # espaces ordinaires seulement : l'insécable garde « 7 000 » entier
        if not w:
            continue
        trial = f"{cur} {w}".strip(" ")
        if cur and draw.textlength(trial, font=font) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def fit_text(text: str, zone_w: float, zone_h: float, font_path: Path, draw: Any) -> tuple[Any, list[str]]:
    """La plus grande police (de 180 à 60 px) où le texte tient dans la zone en 3 lignes au plus."""
    from PIL import ImageFont

    for size in range(180, 58, -6):
        font = ImageFont.truetype(str(font_path), size)
        lines = wrap(text, font, zone_w, draw)
        height = len(lines) * size * 1.02
        if len(lines) <= 3 and height <= zone_h and all(draw.textlength(line, font=font) <= zone_w for line in lines):
            return font, lines
    font = ImageFont.truetype(str(font_path), 60)
    return font, wrap(text, font, zone_w, draw)[:3]


def shade_mask(side: str, strength: int = 150) -> Any:
    """Masque du dégradé sombre posé du côté du texte (lisible en petit sans cacher l'image) : continu, sans bandes."""
    from PIL import Image

    ramp = [int(strength * (1 - i / 255) ** 1.6) for i in range(256)]
    if side in ("left", "right"):
        strip = Image.new("L", (256, 1))
        strip.putdata(ramp if side == "left" else ramp[::-1])
        band = strip.resize((round(TW * 0.62), TH), Image.Resampling.BILINEAR)
        mask = Image.new("L", (TW, TH), 0)
        mask.paste(band, (0 if side == "left" else TW - band.width, 0))
        return mask
    strip = Image.new("L", (1, 256))
    strip.putdata(ramp)
    band = strip.resize((TW, round(TH * 0.5)), Image.Resampling.BILINEAR)
    mask = Image.new("L", (TW, TH), 0)
    mask.paste(band, (0, 0))
    return mask


def compose(image: Path, text: str, side: str, out: Path, fonts_dir: Path, *, color: tuple[int, int, int] = YELLOW) -> Path:
    from PIL import Image, ImageDraw, ImageEnhance

    img = cover(Image.open(image).convert("RGB"), (TW, TH))
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Color(img).enhance(1.12)
    # un nombre ne se coupe jamais (« 7 000 » reste sur une ligne) : espace insécable entre ses groupes de chiffres
    text = re.sub(r"(?<=\d)[   ](?=\d{3}\b)", NBSP, " ".join(text.upper().split()))
    if text:
        if side in ("left", "right"):
            zone_w, zone_h = TW * 0.46, TH * 0.70
        else:
            zone_w, zone_h = TW - 2 * MARGIN, TH * 0.36
        img = Image.composite(Image.new("RGB", (TW, TH), BLACK), img, shade_mask(side))
        draw = ImageDraw.Draw(img)
        font, lines = fit_text(text, zone_w, zone_h, fonts_dir / "Anton-Regular.ttf", draw)
        size = font.size
        block_h = len(lines) * size * 1.02
        top = (TH * 0.42 - block_h / 2) if side in ("left", "right") else MARGIN * 0.8
        top = max(MARGIN * 0.6, min(top, TH * 0.82 - block_h))  # jamais dans les 15 % du bas (barre de lecture, durée)
        for k, line in enumerate(lines):
            w = draw.textlength(line, font=font)
            x = MARGIN if side == "left" else TW - MARGIN - w if side == "right" else (TW - w) / 2
            y = top + k * size * 1.02
            draw.text((x, y), line, font=font, fill=color, stroke_width=STROKE, stroke_fill=BLACK)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=90, optimize=True)
    if out.stat().st_size > 1_900_000:
        img.save(out, "JPEG", quality=80, optimize=True)
    return out


def small(path: Path, out: Path, width: int = 320) -> Path:
    """Aperçu en petit (le contrôle juge la lisibilité à la taille d'un téléphone)."""
    from PIL import Image

    img = Image.open(path)
    img.thumbnail((width, round(width * TH / TW)))
    img.save(out, "JPEG", quality=88)
    return out
