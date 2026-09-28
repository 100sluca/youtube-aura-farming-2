"""Titre d'accroche (« hook title ») gravé en haut de l'écran, repris de MJClipIt.

Même rendu que MJClipIt (Projet2FOU, backend/app/services/hook_overlay.py) : le texte est dessiné par Pillow
dans un PNG transparent, une plaque arrondie sombre par ligne, puis incrusté par FFmpeg (`overlay`). libass
ne sait ni régler l'interligne ni arrondir les coins d'une boîte : le PNG donne exactement le style TikTok.
Réglages par défaut identiques à MJClipIt (HookTitle) : Arial Black 64 px sur 1080 de large, plaque #111111,
texte blanc, 90 % de la largeur, interligne 1,1, rayon 16, haut du titre à 150 px (hors du centre de l'image
et des boutons Shorts). Les émojis sont retirés du rendu (la police n'en a pas), ils restent dans les métadonnées.
Tout se règle dans l'onglet Montage du dashboard (worker/montage.py → HookStyle) : police, taille, couleurs, fond
(une plaque par ligne, une seule plaque, ou texte contouré), opacité, marges, alignement et position.

Le texte vient du script (ScriptV1.hook_title, une langue par chaîne) ; clean_hook() et lint_hook_title()
appliquent les règles d'écriture de MJClipIt : 3 à 8 mots, parlé, sans point final, sans guillemets ni hashtag.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .subtitles import strip_emojis

FONT_CANDIDATES = (
    r"C:\Windows\Fonts\ariblk.ttf",  # Arial Black, défaut de MJClipIt
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
)
WORDS_MIN, WORDS_MAX, CHARS_MAX = 3, 8, 70


@dataclass(frozen=True)
class HookStyle:
    size: int = 64  # px, sur un final de 1080 de large
    width_pct: float = 0.9
    bg: bool = True  # False : texte contouré, sans plaque
    bg_color: str = "111111"
    text_color: str = "FFFFFF"
    line_spacing: float = 1.1
    radius: int = 16
    y: int = 150  # haut du titre, en px depuis le haut du final 1080×1920
    duration_s: float | None = None  # None = toute la vidéo (défaut de MJClipIt)
    font_path: str | None = None  # .ttf à utiliser ; None = Arial Black puis repli
    # Réglages de l'onglet Montage (docs/23-montage.md)
    x: int = 540  # centre horizontal du bloc de texte
    align: str = "center"  # lignes alignées dans le bloc : left | center | right
    bg_mode: str = "plate"  # plate : une plaque par ligne (MJClipIt) ; block : une seule plaque pour tout le titre
    bg_opacity: float = 1.0
    pad_x: int | None = None  # marges intérieures de la plaque ; None = 0,35 et 0,16 × la taille (MJClipIt)
    pad_y: int | None = None
    outline_color: str = "111111"  # contour du texte sans plaque
    outline_width: int | None = None  # None = taille / 14 (au moins 2)
    uppercase: bool = False
    fake_bold: bool = False  # gras demandé à une police sans graisse grasse : épaissi par un contour de sa couleur


DEFAULT_STYLE = HookStyle()


def clean_hook(text: str) -> str:
    """Nettoyage sans perte de sens : guillemets, hashtags, émojis, espaces et point final retirés."""
    t = strip_emojis(text or "")
    t = re.sub(r"#\w+", "", t)
    t = t.replace("«", "").replace("»", "").replace('"', "").replace("“", "").replace("”", "")
    t = re.sub(r"[ \t\r\n]+", " ", t).strip().strip("'’ ")  # l'espace insécable reste : « 1 350 » ne se coupe pas
    t = re.sub(r"(?<![.!?])\.$", "", t).strip()  # le point final saute, pas « … » ni « ?! »
    return t[:1].upper() + t[1:]  # une phrase commence par une majuscule (« construire au bord du vide »)


def lint_hook_title(text: str, lang: str = "fr") -> list[str]:
    """Problèmes d'un titre d'accroche (après clean_hook) ; liste vide = conforme."""
    t = clean_hook(text)
    if not t:
        return [f"[{lang}] hook_title manquant : titre d'accroche de {WORDS_MIN} à {WORDS_MAX} mots"]
    n = len(re.findall(r"[\w'’-]+", t))
    issues = []
    if n < WORDS_MIN or n > WORDS_MAX + 1:
        issues.append(f"[{lang}] hook_title de {n} mots : {WORDS_MIN} à {WORDS_MAX}")
    if len(t) > CHARS_MAX:
        issues.append(f"[{lang}] hook_title de {len(t)} caractères : {CHARS_MAX} au plus")
    if t.isupper() and len(t) > 12:
        issues.append(f"[{lang}] hook_title tout en majuscules : écrire normalement")
    return issues


def _load_font(size: int, font_path: str | None):  # noqa: ANN202
    from PIL import ImageFont

    for path in ([font_path] if font_path else []) + list(FONT_CANDIDATES):
        if path and Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:  # noqa: ANN001
    lines: list[str] = []
    cur: list[str] = []
    for word in (w for w in text.split(" ") if w):  # pas split() : il couperait « 10 000 » à l'espace insécable
        trial = " ".join(cur + [word])
        if cur and draw.textlength(trial, font=font) > max_w:
            lines.append(" ".join(cur))
            cur = [word]
        else:
            cur.append(word)
    if cur:
        lines.append(" ".join(cur))
    return lines or [text]


def _rgba(hex_color: str, opacity: float = 1.0) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), round(255 * max(0.0, min(1.0, opacity)))


def render_image(text: str, style: HookStyle = DEFAULT_STYLE, canvas_w: int = 1080):  # noqa: ANN201
    """Image RGBA transparente de canvas_w de large : une plaque arrondie par ligne (ou une seule plaque pour tout le
    bloc), ou texte contouré (fond désactivé). Même algorithme que MJClipIt (_render_image) ; le bloc est centré sur
    style.x et gardé dans l'image, ses lignes alignées à gauche, au centre ou à droite."""
    from PIL import Image, ImageDraw

    text = clean_hook(text)
    if style.uppercase:
        text = text.upper()
    font = _load_font(style.size, style.font_path)
    pad_x = style.pad_x if style.pad_x is not None else int(style.size * 0.35)
    pad_y = style.pad_y if style.pad_y is not None else int(style.size * 0.16)
    stroke = 0 if style.bg else (style.outline_width if style.outline_width is not None else max(2, style.size // 14))
    embolden = max(1, style.size // 36) if style.fake_bold else 0
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    lines = _wrap(probe, text, font, max(50, int(canvas_w * style.width_pct) - 2 * pad_x))
    ascent, descent = font.getmetrics()
    box_h = ascent + descent + 2 * pad_y
    step = max(1, int(box_h * style.line_spacing))
    block_h = step * (len(lines) - 1) + box_h
    total_h = block_h + 2 * stroke
    widths = [int(probe.textlength(line, font=font)) for line in lines]
    block_w = max(widths) + 2 * pad_x
    left = min(max(0, style.x - block_w // 2), canvas_w - block_w) if block_w <= canvas_w else (canvas_w - block_w) // 2
    img = Image.new("RGBA", (canvas_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fill = _rgba(style.bg_color, style.bg_opacity)
    text_fill = _rgba(style.text_color)
    if style.bg and style.bg_mode == "block":
        draw.rounded_rectangle((left, stroke, left + block_w, stroke + block_h), radius=min(style.radius, block_h // 2), fill=fill)
    y = stroke
    for line, w in zip(lines, widths, strict=True):
        line_w = w + 2 * pad_x
        x0 = left + {"left": 0, "right": block_w - line_w}.get(style.align, (block_w - line_w) // 2)
        if style.bg and style.bg_mode != "block":
            draw.rounded_rectangle((x0, y, x0 + line_w, y + box_h), radius=min(style.radius, box_h // 2), fill=fill)
        at = (x0 + pad_x, y + pad_y)
        if stroke:
            draw.text(at, line, font=font, fill=text_fill, stroke_width=stroke + embolden, stroke_fill=_rgba(style.outline_color))
        if embolden or not stroke:
            draw.text(at, line, font=font, fill=text_fill, stroke_width=embolden, stroke_fill=text_fill if embolden else None)
        y += step
    return img


def build_png(text: str, dst: Path, style: HookStyle = DEFAULT_STYLE, canvas_w: int = 1080) -> Path | None:
    """Écrit le PNG du titre ; None si le texte est vide ou si Pillow manque (le montage s'en passe)."""
    if not clean_hook(text):
        return None
    try:
        img = render_image(text, style, canvas_w)
    except ImportError:
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "PNG")
    return dst


def overlay_filter(style: HookStyle, total_s: float | None = None) -> str:
    """Arguments du filtre FFmpeg `overlay` : PNG de toute la largeur (le bloc y est déjà placé à style.x), haut à
    style.y, affiché style.duration_s secondes (toute la vidéo si None)."""
    expr = f"overlay=(W-w)/2:{style.y}"
    if style.duration_s and (total_s is None or style.duration_s < total_s):
        expr += f":enable='between(t,0,{style.duration_s:.3f})'"
    return expr
