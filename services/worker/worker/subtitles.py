"""Sous-titres personnalisables : profils, découpage en légendes, fichier ASS gravé par FFmpeg (libass).

Reprend les réglages de l'écran « Customize Subtitles » (police, taille, graisse, couleurs, contour,
ombre portée orientée et floutée, espacement, casse, position, fond, animation, profils enregistrés)
et le principe du karaoké mot à mot de MJClipIt.

Tout est calculé ici à partir d'une liste de mots horodatés (WordTiming) : aucune dépendance au
reste du pipeline, ce qui permet de prévisualiser un profil sans base de données
(`yt2 subtitles preview`).

Rendu en couches ASS, de bas en haut : 1 = ombre portée, 2 = texte (et sa boîte), 3 = titres.
Positionnement absolu (\\an5\\pos) sur une scène de 1080×1920 : les tailles sont en pixels du final.
Au montage, le profil, la position et le style des textes à l'écran (TitleStyle) viennent du modèle de montage
réglé dans l'onglet Montage du dashboard (worker/montage.py, docs/23-montage.md).
"""

from __future__ import annotations

import math
import re
import struct
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .models import WordTiming
from .numbers import spoken, tokens

W, H = 1080, 1920
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


# ---------------------------------------------------------------------------
# Profil
# ---------------------------------------------------------------------------


class SubtitleProfile(BaseModel):
    """Un profil de sous-titres. Tailles en pixels sur un final 1080×1920."""

    name: str = "personnalise"
    # Texte
    font_family: str = "Montserrat"
    font_size: int = Field(88, ge=24, le=220)
    bold: bool = True
    italic: bool = False
    text_transform: Literal["none", "uppercase", "lowercase", "capitalize"] = "uppercase"
    letter_spacing: float = Field(0, ge=-5, le=30)
    text_color: str = "#FFFFFF"
    # Mot actif : none = texte uni, word = mot prononcé coloré, karaoke = remplissage progressif
    highlight_mode: Literal["none", "word", "karaoke"] = "word"
    highlight_color: str = "#FFD400"
    # Contour
    outline_color: str = "#000000"
    outline_width: float = Field(6, ge=0, le=20)
    # Ombre portée (angle façon logiciel de retouche : direction de la lumière, 135° = ombre en bas à droite)
    shadow_color: str = "#000000"
    shadow_opacity: float = Field(0.6, ge=0, le=1)
    shadow_distance: float = Field(6, ge=0, le=40)
    shadow_angle: int = Field(135, ge=0, le=359)
    shadow_blur: float = Field(4, ge=0, le=20)
    # Fond derrière la légende
    background: Literal["none", "box"] = "none"
    background_color: str = "#000000"
    background_opacity: float = Field(0.55, ge=0, le=1)
    background_padding: int = Field(0, ge=0, le=80, description="marge de la boîte autour de la légende, en px")
    # Position et découpage
    position: Literal["top", "center", "bottom"] = "center"
    offset_y: int = Field(0, ge=-800, le=800)
    # Centre de la légende en px (modèle de montage, worker/montage.py) : remplace position + offset_y s'il est donné
    x: int | None = Field(None, ge=0, le=1080)
    y: int | None = Field(None, ge=0, le=1920)
    max_words: int = Field(3, ge=1, le=8)
    max_chars: int = Field(18, ge=6, le=60, description="caractères par ligne, deux lignes au plus")
    animation: Literal["none", "pop", "bounce", "fade", "slide_up"] = "pop"
    # Texte à l'écran des scènes (on_screen_text du script), dessiné avec la même police
    title_font_size: int = Field(76, ge=24, le=220)
    title_text_color: str = "#FFFFFF"
    title_box_color: str = "#000000"
    title_box_opacity: float = Field(0.6, ge=0, le=1)
    title_y: int = Field(330, ge=80, le=1400, description="centre vertical du titre, en px depuis le haut")

    @field_validator(
        "text_color", "highlight_color", "outline_color", "shadow_color", "background_color", "title_text_color", "title_box_color"
    )
    @classmethod
    def _hex(cls, v: str) -> str:
        if not HEX_COLOR.match(v):
            raise ValueError(f"couleur attendue au format #RRGGBB, reçu {v!r}")
        return v.upper()


BUILTIN_PROFILES: dict[str, SubtitleProfile] = {
    # Gros mots en capitales, mot prononcé en jaune, apparition « pop » : le style des Shorts viraux
    "impact": SubtitleProfile(name="impact"),
    # Remplissage progressif mot à mot, plus bas dans l'image
    "karaoke": SubtitleProfile(
        name="karaoke",
        font_family="Poppins",
        font_size=80,
        text_transform="none",
        highlight_mode="karaoke",
        highlight_color="#FFD400",
        outline_width=5,
        position="bottom",
        max_words=4,
        max_chars=22,
        animation="fade",
    ),
    # Sobre : phrase courte sur fond sombre, sans mot actif
    "sobre": SubtitleProfile(
        name="sobre",
        font_family="Poppins",
        font_size=66,
        bold=False,
        text_transform="none",
        highlight_mode="none",
        outline_width=0,
        shadow_opacity=0,
        background="box",
        background_opacity=0.55,
        position="bottom",
        max_words=6,
        max_chars=26,
        animation="fade",
    ),
    # Affiche : très grands caractères condensés, un ou deux mots, accent vert
    "affiche": SubtitleProfile(
        name="affiche",
        font_family="Bebas Neue",
        font_size=132,
        bold=False,
        highlight_color="#00E676",
        outline_width=6,
        max_words=2,
        max_chars=16,
        animation="bounce",
    ),
    # Bande dessinée : police ronde, contour épais, mot actif orange
    "bd": SubtitleProfile(
        name="bd",
        font_family="Luckiest Guy",
        font_size=96,
        bold=False,
        highlight_color="#FF8A00",
        outline_width=9,
        shadow_distance=8,
        shadow_blur=0,
        shadow_opacity=0.9,
        max_words=2,
        max_chars=15,
        animation="bounce",
    ),
}


def resolve_profile(name: str | None, saved: dict[str, dict] | None = None) -> SubtitleProfile:
    """Profil enregistré (base) en priorité, puis profil intégré, sinon « impact »."""
    if name and saved and name in saved:
        return SubtitleProfile.model_validate({**saved[name], "name": name})
    if name and name in BUILTIN_PROFILES:
        return BUILTIN_PROFILES[name]
    return BUILTIN_PROFILES["impact"]


# ---------------------------------------------------------------------------
# Polices : lecture du nom de famille dans les fichiers, pour que libass les trouve
# ---------------------------------------------------------------------------

BOLD_WORDS = ("black", "heavy", "extrabold", "ultrabold", "bold", "semibold", "demibold")


@dataclass(frozen=True)
class FontFace:
    path: Path
    family: str  # nameID 1 : ce que libass reconnaît dans le champ Fontname
    typographic_family: str  # nameID 16 (ou 1) : le nom affiché à l'utilisateur
    subfamily: str  # nameID 17 (ou 2)
    weight: int = 400  # OS/2 usWeightClass (400 normal, 700 gras, 900 noir)
    italic: bool = False
    # Métriques verticales (unités de la police) : libass fait tenir usWinAscent + usWinDescent dans la taille ASS
    units_per_em: int = 1000
    win_ascent: int = 0
    win_descent: int = 0

    @property
    def is_bold(self) -> bool:
        s = (self.subfamily + " " + self.family).lower().replace(" ", "").replace("-", "")
        return self.weight >= 600 or any(w in s for w in BOLD_WORDS)

    def em_px(self, ass_size: float) -> float:
        """Taille du cadratin en px pour une taille ASS : libass ramène la hauteur Windows de la police à la taille."""
        height = self.win_ascent + self.win_descent
        return ass_size * self.units_per_em / height if height > 0 else ass_size


@dataclass
class FontRegistry:
    faces: list[FontFace] = field(default_factory=list)

    @classmethod
    def scan(cls, *sources: Path | None) -> FontRegistry:
        """Polices (.ttf, .otf) des dossiers ou fichiers donnés, dans cet ordre ; un fichier n'est lu qu'une fois."""
        faces: list[FontFace] = []
        seen: set[Path] = set()
        for src in sources:
            if not src:
                continue
            files = sorted(src.iterdir()) if src.is_dir() else [src] if src.is_file() else []
            for p in files:
                if p.suffix.lower() not in (".ttf", ".otf") or p.resolve() in seen:
                    continue
                seen.add(p.resolve())
                face = read_face(p)
                if face:
                    faces.append(face)
        return cls(faces)

    def families(self) -> list[str]:
        return sorted({f.typographic_family for f in self.faces})

    def pick(self, wanted: str, bold: bool) -> FontChoice:
        """Choisit la police : nom ASS, gras synthétique éventuel, fichier à fournir à libass.
        Le nom de famille exact (nameID 1 : « Arial Black », « Segoe UI Black ») passe avant la famille typographique
        (« Arial », « Segoe UI ») ; parmi les graisses, la plus proche de 700 (gras) ou de 400 (normal).
        Une famille absente du dossier est demandée telle quelle (police système)."""
        key = _norm(wanted)
        cands = [f for f in self.faces if _norm(f.family) == key] or [f for f in self.faces if _norm(f.typographic_family) == key]
        if not cands:
            return FontChoice(wanted, bold, None)
        upright = [f for f in cands if not f.italic] or cands
        if bold:
            bolds = [f for f in upright if f.is_bold]
            if bolds:  # la graisse est dans la police : pas de gras synthétique
                best = min(bolds, key=lambda f: abs(f.weight - 700))
                return FontChoice(best.family, False, best.path, best)
            return FontChoice(upright[0].family, True, upright[0].path, upright[0])
        regular = [f for f in upright if not f.is_bold] or upright
        best = min(regular, key=lambda f: abs(f.weight - 400))
        return FontChoice(best.family, False, best.path, best)


@dataclass(frozen=True)
class FontChoice:
    fontname: str  # champ Fontname du style ASS
    synthetic_bold: bool
    path: Path | None  # fichier à copier dans fontsdir (None = police système)
    face: FontFace | None = None

    def text_width(self, text: str, ass_size: float, spacing: float = 0.0) -> float:
        """Largeur approximative (px) d'un texte que libass dessine à cette taille ASS : mesurée avec la police (Pillow),
        sinon estimée (0,6 cadratin par caractère)."""
        em = self.face.em_px(ass_size) if self.face else ass_size * 0.8
        width = None
        if self.path:
            try:
                from PIL import ImageFont

                width = ImageFont.truetype(str(self.path), max(1, round(em))).getlength(text) * em / max(1, round(em))
            except (ImportError, OSError):
                width = None
        if width is None:
            width = 0.6 * em * len(text)
        if self.synthetic_bold:
            width *= 1.04
        return width + spacing * max(0, len(text) - 1)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _tables(data: bytes) -> dict[bytes, int]:
    """Répertoire des tables d'un fichier TrueType/OpenType : étiquette → position."""
    num_tables = struct.unpack(">H", data[4:6])[0]
    out = {}
    for i in range(num_tables):
        tag, _, offset, _ = struct.unpack(">4sLLL", data[12 + 16 * i : 28 + 16 * i])
        out[tag] = offset
    return out


def read_face(path: Path) -> FontFace | None:
    """Noms, graisse, italique et métriques d'un fichier de police ; None s'il est illisible."""
    names = read_font_names(path)
    if not names.get(1):
        return None
    weight, italic, upm, win_asc, win_desc = 400, False, 1000, 0, 0
    try:
        data = path.read_bytes()
        tables = _tables(data)
        if b"head" in tables:
            upm = struct.unpack(">H", data[tables[b"head"] + 18 : tables[b"head"] + 20])[0] or 1000
        if b"OS/2" in tables:
            o = tables[b"OS/2"]
            weight = struct.unpack(">H", data[o + 4 : o + 6])[0] or 400
            italic = bool(struct.unpack(">H", data[o + 62 : o + 64])[0] & 1)
            win_asc, win_desc = struct.unpack(">HH", data[o + 74 : o + 78])
        if not win_asc and b"hhea" in tables:
            asc, desc = struct.unpack(">hh", data[tables[b"hhea"] + 4 : tables[b"hhea"] + 8])
            win_asc, win_desc = asc, -desc
    except (struct.error, IndexError, OSError):
        pass
    subfamily = names.get(17) or names.get(2) or "Regular"
    return FontFace(
        path=path, family=names[1], typographic_family=names.get(16) or names[1], subfamily=subfamily, weight=weight,
        italic=italic or "italic" in subfamily.lower() or "oblique" in subfamily.lower(), units_per_em=upm,
        win_ascent=win_asc, win_descent=win_desc,
    )


def read_font_names(path: Path) -> dict[int, str]:
    """Lit la table « name » d'un fichier TrueType/OpenType (IDs 1, 2, 4, 16, 17)."""
    data = path.read_bytes()
    try:
        tables = _tables(data)
        if b"name" not in tables:
            return {}
        offset = tables[b"name"]
        _, count, str_off = struct.unpack(">HHH", data[offset : offset + 6])
        out: dict[int, str] = {}
        for j in range(count):
            pid, eid, lid, nid, length, noff = struct.unpack(">HHHHHH", data[offset + 6 + 12 * j : offset + 18 + 12 * j])
            if nid not in (1, 2, 4, 16, 17):
                continue
            raw = data[offset + str_off + noff : offset + str_off + noff + length]
            if pid == 3 and eid in (0, 1, 10):  # Windows, UTF-16BE ; anglais US prioritaire
                if nid not in out or lid == 0x409:
                    out[nid] = raw.decode("utf-16-be", errors="ignore")
            elif pid == 1 and nid not in out:
                out[nid] = raw.decode("mac_roman", errors="ignore")
        return out
    except (struct.error, IndexError):
        return {}


# ---------------------------------------------------------------------------
# Texte : casse, émojis, échappement, retour à la ligne
# ---------------------------------------------------------------------------

_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff\U0000fe0f\U0000200d\U00002b00-\U00002bff]",
    flags=re.UNICODE,
)


def strip_emojis(s: str) -> str:
    """libass n'affiche pas les émojis en couleur : on les retire du rendu (ils restent dans les métadonnées)."""
    return _EMOJI.sub("", s)


def transform(s: str, mode: str) -> str:
    if mode == "uppercase":
        return s.upper()
    if mode == "lowercase":
        return s.lower()
    if mode == "capitalize":
        return " ".join(w[:1].upper() + w[1:] for w in s.split(" "))
    return s


def escape_ass(s: str) -> str:
    """Neutralise les accolades (blocs de surcharge ASS) et les antislashs (\\N, \\h…)."""
    return s.replace("\\", "⧵").replace("{", "(").replace("}", ")").replace("\n", " ")


def display_word(text: str, profile: SubtitleProfile) -> str:
    return escape_ass(transform(strip_emojis(text).strip(), profile.text_transform))


def split_lines(words: Sequence[str], max_chars: int) -> list[list[str]]:
    """Une ligne si elle tient, sinon deux lignes coupées au plus près du milieu."""
    if len(" ".join(words)) <= max_chars or len(words) < 2:
        return [list(words)]
    best, best_cost = 1, math.inf
    for k in range(1, len(words)):
        a, b = len(" ".join(words[:k])), len(" ".join(words[k:]))
        cost = max(a, b) * 10 + abs(a - b)
        if cost < best_cost:
            best, best_cost = k, cost
    return [list(words[:best]), list(words[best:])]


# ---------------------------------------------------------------------------
# Minutage : répartition proportionnelle des mots dans un segment de parole
# ---------------------------------------------------------------------------

_PAUSE_SHORT = re.compile(r"[,;:–—]$")
_PAUSE_LONG = re.compile(r"[.!?…]+[»\"')\]]*$")


def distribute_words(text: str, start: float, end: float, lang: str = "fr") -> list[WordTiming]:
    """Horodate les mots d'une phrase lue entre start et end.

    Chaque mot reçoit un temps proportionnel à sa longueur ; la ponctuation ajoute une pause après
    le mot (virgule courte, point longue), comme le fait une voix de synthèse. Précision typique
    sur une voix TTS : ± 0,15 s, suffisant pour colorer le mot prononcé. Un nombre en chiffres reste un seul mot
    (« 1 350 ») et dure le temps des mots qui le disent (« mille trois cent cinquante », worker/numbers.py).
    """
    words = [w for w in tokens(text) if strip_emojis(w).strip()]
    if not words or end <= start:
        return []
    weights, pauses = [], []
    for w in words:
        said = spoken(w, lang)
        letters = sum(ch.isalnum() for ch in said)
        weights.append(max(1, letters) + 1.5 * max(1, len(said.split())))
        pauses.append(5.0 if _PAUSE_LONG.search(w) else 2.5 if _PAUSE_SHORT.search(w) else 0.0)
    pauses[-1] = 0.0
    unit = (end - start) / (sum(weights) + sum(pauses))
    out, t = [], start
    for w, wt, p in zip(words, weights, pauses, strict=True):
        out.append(WordTiming(text=w, start=round(t, 3), end=round(t + wt * unit, 3)))
        t += (wt + p) * unit
    return out


# ---------------------------------------------------------------------------
# Légendes : groupes de mots affichés ensemble
# ---------------------------------------------------------------------------


@dataclass
class Caption:
    words: list[WordTiming]
    start: float
    end: float


def group_words(
    words_by_scene: Sequence[Sequence[WordTiming]], profile: SubtitleProfile, *, max_gap: float = 0.6, hold: float = 0.25
) -> list[Caption]:
    """Regroupe les mots en légendes : au plus max_words mots et deux lignes, coupe aux fins de phrase,
    aux silences et aux changements de scène. Chaque légende reste affichée jusqu'à la suivante
    (au plus `hold` secondes après le dernier mot) pour éviter le clignotement."""
    captions: list[Caption] = []
    for scene_words in words_by_scene:
        current: list[WordTiming] = []
        for w in scene_words:
            if not display_word(w.text, profile):
                continue
            if current:
                texts = [display_word(x.text, profile) for x in current + [w]]
                too_long = len(split_lines(texts, profile.max_chars)) > 1 and any(
                    len(" ".join(line)) > profile.max_chars for line in split_lines(texts, profile.max_chars)
                )
                if (
                    len(current) >= profile.max_words
                    or too_long
                    or _PAUSE_LONG.search(current[-1].text)
                    or w.start - current[-1].end > max_gap
                ):
                    captions.append(Caption(current, current[0].start, current[-1].end))
                    current = []
            current.append(w)
        if current:
            captions.append(Caption(current, current[0].start, current[-1].end))
    for a, b in zip(captions, captions[1:], strict=False):
        a.end = min(b.start, a.end + hold) if b.start > a.end else b.start
    if captions:
        captions[-1].end += hold
    return [c for c in captions if c.end - c.start >= 0.04]


# ---------------------------------------------------------------------------
# ASS
# ---------------------------------------------------------------------------


def ass_color(hex_color: str, opacity: float = 1.0) -> str:
    """#RRGGBB + opacité → &HAABBGGRR (alpha 00 = opaque, FF = transparent)."""
    r, g, b = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    alpha = round((1 - max(0.0, min(1.0, opacity))) * 255)
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_tag_color(hex_color: str) -> str:
    """Couleur pour une balise \\c : &HBBGGRR&."""
    return f"&H{hex_color[5:7]}{hex_color[3:5]}{hex_color[1:3]}&".upper()


def ass_time(t: float) -> str:
    t = max(0.0, t)
    cs = round(t * 100)
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _anchor_y(profile: SubtitleProfile, height: int) -> int:
    if profile.y is not None:
        return max(40, min(height - 40, profile.y))
    base = {"top": 0.24, "center": 0.52, "bottom": 0.70}[profile.position]
    return max(80, min(height - 80, round(base * height) + profile.offset_y))


def _anchor_x(profile: SubtitleProfile, width: int) -> int:
    return width // 2 if profile.x is None else max(40, min(width - 40, profile.x))


@dataclass(frozen=True)
class TitleStyle:
    """Textes à l'écran des scènes (on_screen_text) et compteur de jours. Taille en taille ASS, comme les sous-titres ;
    position = centre du texte en px. Sans modèle de montage : les réglages title_* du profil (TitleStyle.from_profile)."""

    font_family: str | None = None  # None : la police des sous-titres
    bold: bool | None = None  # None : comme les sous-titres
    size: int = 76
    text_color: str = "#FFFFFF"
    transform: str = "uppercase"  # none | uppercase | lowercase | capitalize
    style: str = "box"  # box : boîte derrière le texte ; outline : texte contouré ; none : texte seul
    box_color: str = "#000000"
    box_opacity: float = 0.6
    padding: int = 16  # marge de la boîte
    outline_color: str = "#000000"
    outline_width: float = 4
    x: int | None = None  # None : centre de l'image
    y: int = 330
    max_width: int = 1000  # un texte plus large rapetisse (au plus de 45 %) au lieu de sortir de l'image

    @classmethod
    def from_profile(cls, p: SubtitleProfile) -> TitleStyle:
        return cls(size=p.title_font_size, text_color=p.title_text_color, box_color=p.title_box_color,
                   box_opacity=p.title_box_opacity, y=p.title_y)


def _bold_flag(choice: FontChoice) -> int:
    """Champ Bold du style ASS : -1 (gras demandé) pour un gras synthétique, et aussi quand la graisse est dans la police
    (« Arial Bold ») pour que libass prenne ce fichier plutôt qu'un « Arial » normal du même nom. Une police déjà grasse
    n'est pas épaissie une seconde fois (mesuré le 28/09 : Montserrat SemiBold identique avec Bold 0 ou -1)."""
    return -1 if choice.synthetic_bold or (choice.face is not None and choice.face.is_bold) else 0


def _fit_size(choice: FontChoice, ts: TitleStyle, text: str, spacing: float) -> int | None:
    """Taille réduite qui fait tenir le texte dans ts.max_width (boîte et contour compris) ; None s'il tient déjà."""
    border = ts.padding if ts.style == "box" else ts.outline_width if ts.style == "outline" else 0
    room = ts.max_width - 2 * border
    width = choice.text_width(text, ts.size, spacing)
    if width <= room or width <= 0:
        return None
    return max(round(ts.size * 0.55), math.floor(ts.size * room / width))


def _animation(profile: SubtitleProfile, x: int, y: int) -> str:
    """Balises de position + animation d'entrée d'une légende."""
    a = profile.animation
    if a == "slide_up":
        return f"\\an5\\move({x},{y + 60},{x},{y},0,160)"
    tags = f"\\an5\\pos({x},{y})"
    if a == "pop":
        tags += "\\fscx80\\fscy80\\t(0,90,\\fscx108\\fscy108)\\t(90,160,\\fscx100\\fscy100)"
    elif a == "bounce":
        tags += "\\fscx60\\fscy60\\t(0,110,\\fscx118\\fscy118)\\t(110,190,\\fscx94\\fscy94)\\t(190,250,\\fscx100\\fscy100)"
    elif a == "fade":
        tags += "\\fad(120,0)"
    return tags


def _still(x: int, y: int) -> str:
    return f"\\an5\\pos({x},{y})"


def _shadow_offset(profile: SubtitleProfile) -> tuple[int, int]:
    a = math.radians(profile.shadow_angle)
    return round(-math.cos(a) * profile.shadow_distance), round(math.sin(a) * profile.shadow_distance)


def _lines_text(words: Sequence[str], profile: SubtitleProfile, active: int | None = None) -> str:
    """Assemble les mots en une ou deux lignes ; colore le mot `active` avec la couleur d'accent."""
    lines = split_lines(words, profile.max_chars)
    out, k = [], 0
    for line in lines:
        parts = []
        for w in line:
            if active is not None and k == active:
                parts.append(f"{{\\c{ass_tag_color(profile.highlight_color)}}}{w}{{\\c{ass_tag_color(profile.text_color)}}}")
            else:
                parts.append(w)
            k += 1
        out.append(" ".join(parts))
    return "\\N".join(out)


def _karaoke_text(caption: Caption, words: Sequence[str], profile: SubtitleProfile) -> str:
    """Balises \\kf mot à mot (remplissage progressif). Comme dans MJClipIt : chaque mot dure jusqu'au
    début du suivant (les pauses sont absorbées, pas de clignotement) et les centièmes sont émis par
    différence avec un cumul exact, pour qu'aucun arrondi ne dérive sur la légende."""
    acc, emitted = 0.0, 0

    def take(seconds: float) -> int:
        nonlocal acc, emitted
        acc += max(0.0, seconds) * 100
        k = max(0, round(acc) - emitted)
        emitted += k
        return k

    lead = caption.words[0].start - caption.start
    prefix = f"{{\\k{take(lead)}}}" if lead > 0.01 else ""
    lines = split_lines(words, profile.max_chars)
    out, k = [], 0
    for line in lines:
        parts = []
        for w in line:
            nxt = caption.words[k + 1].start if k + 1 < len(caption.words) else caption.end
            parts.append(f"{{\\kf{take(nxt - caption.words[k].start)}}}{w}")
            k += 1
        out.append(" ".join(parts))
    return prefix + "\\N".join(out)


def build_ass(
    words_by_scene: Sequence[Sequence[WordTiming]],
    profile: SubtitleProfile,
    titles: Iterable[tuple[float, float, str]] = (),
    *,
    fonts: FontRegistry | None = None,
    width: int = W,
    height: int = H,
    ticks: Sequence[tuple[float, float, str]] = (),
    title_style: TitleStyle | None = None,
) -> str:
    """Construit le fichier ASS complet (en-tête, styles, événements). `ticks` : un compteur qui défile (« Jour 12 »,
    « Jour 13 »…), au style des titres mais sans fondu entre deux valeurs (fondu à l'entrée et à la sortie seulement).
    `title_style` : police, fond et position des textes à l'écran (modèle de montage) ; défaut = réglages title_* du profil."""
    fonts = fonts or FontRegistry()
    choice = fonts.pick(profile.font_family, profile.bold)
    fontname = choice.fontname
    bold = _bold_flag(choice)
    italic = -1 if profile.italic else 0
    ts = title_style or TitleStyle.from_profile(profile)
    tchoice = fonts.pick(ts.font_family or profile.font_family, profile.bold if ts.bold is None else ts.bold)
    tbold = _bold_flag(tchoice)
    shadow_on = profile.shadow_opacity > 0 and (profile.shadow_distance > 0 or profile.shadow_blur > 0)
    karaoke = profile.highlight_mode == "karaoke"
    primary = profile.highlight_color if karaoke else profile.text_color  # en karaoké : couleur une fois « chanté »
    secondary = profile.text_color

    # Fond : BorderStyle 4 (extension libass ≥ 0.17) dessine UNE boîte autour de toute la légende,
    # couleur BackColour, sans empêcher le contour du texte. Le BorderStyle 3 classique fait une boîte
    # par ligne, qui se chevauchent entre deux lignes (bande plus sombre au milieu). En BorderStyle 4, libass prend la
    # valeur Shadow comme marge de la boîte (mesuré le 28/09 : boîte = lignes + contour + Shadow de chaque côté).
    box = profile.background == "box"
    main_border = 4 if box else 1
    main_back = ass_color(profile.background_color, profile.background_opacity) if box else "&H00000000"
    main_shadow = profile.background_padding if box else 0
    # Textes à l'écran : une ligne courte (≤ 5 mots), donc BorderStyle 3 suffit et donne une vraie marge intérieure
    # (Outline = marge ; la boîte prend la couleur de contour) ; sans boîte, un contour classique ou rien
    if ts.style == "box":
        t_border, t_outline, t_outline_color = 3, ts.padding, ass_color(ts.box_color, ts.box_opacity)
    else:
        t_border, t_outline_color = 1, ass_color(ts.outline_color)
        t_outline = ts.outline_width if ts.style == "outline" else 0
    styles = [
        # Texte : contour, pas d'ombre native (l'ombre est une couche à part, orientable et floutable)
        f"Style: Main,{fontname},{profile.font_size},{ass_color(primary)},{ass_color(secondary)},"
        f"{ass_color(profile.outline_color)},{main_back},{bold},{italic},0,0,100,100,{profile.letter_spacing:g},0,"
        f"{main_border},{profile.outline_width:g},{main_shadow},5,40,40,0,1",
        # Ombre : même dessin, couleur et opacité de l'ombre partout
        f"Style: Shadow,{fontname},{profile.font_size},{ass_color(profile.shadow_color, profile.shadow_opacity)},"
        f"{ass_color(profile.shadow_color, profile.shadow_opacity)},{ass_color(profile.shadow_color, profile.shadow_opacity)},"
        f"&H00000000,{bold},{italic},0,0,100,100,{profile.letter_spacing:g},0,1,{profile.outline_width:g},0,5,40,40,0,1",
        f"Style: Title,{tchoice.fontname},{ts.size},{ass_color(ts.text_color)},{ass_color(ts.text_color)},{t_outline_color},"
        f"&HFF000000,{tbold},0,0,0,100,100,{profile.letter_spacing:g},0,{t_border},{t_outline:g},0,5,40,40,0,1",
    ]
    events: list[str] = []
    x, y = _anchor_x(profile, width), _anchor_y(profile, height)
    dx, dy = _shadow_offset(profile)

    def dialogue(layer: int, start: float, end: float, style: str, text: str) -> None:
        events.append(f"Dialogue: {layer},{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{text}")

    shadow_on = shadow_on and not box  # la boîte recouvrirait l'ombre : inutile de la dessiner
    for cap in group_words(words_by_scene, profile):
        words = [display_word(w.text, profile) for w in cap.words]
        plain = _lines_text(words, profile)
        if karaoke or profile.highlight_mode == "none":
            body = _karaoke_text(cap, words, profile) if karaoke else plain
            if shadow_on:
                dialogue(1, cap.start, cap.end, "Shadow", f"{{{_animation(profile, x + dx, y + dy)}\\blur{profile.shadow_blur:g}}}{plain}")
            dialogue(2, cap.start, cap.end, "Main", f"{{{_animation(profile, x, y)}}}{body}")
            continue
        # Mode « word » : une tranche par mot prononcé ; l'animation d'entrée ne joue que sur la première
        for k, w in enumerate(cap.words):
            t0 = cap.start if k == 0 else w.start
            t1 = cap.words[k + 1].start if k + 1 < len(cap.words) else cap.end
            if t1 - t0 < 0.02:
                continue
            place = _animation(profile, x, y) if k == 0 else _still(x, y)
            if shadow_on:
                sp = _animation(profile, x + dx, y + dy) if k == 0 else _still(x + dx, y + dy)
                dialogue(1, t0, t1, "Shadow", f"{{{sp}\\blur{profile.shadow_blur:g}}}{plain}")
            dialogue(2, t0, t1, "Main", f"{{{place}}}{_lines_text(words, profile, active=k)}")

    tx = width // 2 if ts.x is None else max(40, min(width - 40, ts.x))
    ty = max(40, min(height - 40, ts.y))

    def title_text(text: str) -> tuple[str, str]:
        """Texte du titre ; trop large pour l'image, il rapetisse (\\fs) plutôt que d'en sortir."""
        shown = transform(strip_emojis(text).strip(), ts.transform)
        size = _fit_size(tchoice, ts, shown, profile.letter_spacing) if shown else None
        return (f"\\fs{size}" if size else "", escape_ass(shown))

    for start, end, text in titles:
        fs, shown = title_text(text)
        if shown and end > start:
            dialogue(3, start, end, "Title", f"{{\\an5\\pos({tx},{ty})\\fad(150,150){fs}}}{shown}")
    last = len(ticks) - 1
    for k, (start, end, text) in enumerate(ticks):
        fs, shown = title_text(text)
        if shown and end > start:
            fad = f"\\fad({150 if k == 0 else 0},{150 if k == last else 0})"
            dialogue(3, start, end, "Title", f"{{\\an5\\pos({tx},{ty}){fad}{fs}}}{shown}")

    header = [
        "[Script Info]",
        "; Généré par YouTube 2.0 (worker/subtitles.py)",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 2",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        *styles,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    return "\n".join(header + events) + "\n"


# ---------------------------------------------------------------------------
# FFmpeg
# ---------------------------------------------------------------------------


ASS_NAME = "subtitles.ass"
FONTS_SUBDIR = "fonts"


def write_subtitles(
    workdir: Path, ass_text: str, profile: SubtitleProfile, fonts: FontRegistry, title_style: TitleStyle | None = None
) -> str:
    """Écrit subtitles.ass et les polices (sous-titres, textes à l'écran) dans `workdir`, renvoie le filtre FFmpeg.

    Méthode reprise de MJClipIt : sous Windows, un chemin absolu (C:\\…) casse l'analyse du graphe de
    filtres. FFmpeg doit donc tourner avec cwd = workdir ; le filtre ne cite que des noms relatifs, et la
    police est copiée à côté pour que libass la trouve par son nom de famille (y compris une police de Windows :
    le FFmpeg utilisé ne voit pas toujours les polices du système)."""
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / ASS_NAME).write_text(ass_text, encoding="utf-8")
    ts = title_style or TitleStyle.from_profile(profile)
    choices = [
        fonts.pick(profile.font_family, profile.bold),
        fonts.pick(ts.font_family or profile.font_family, profile.bold if ts.bold is None else ts.bold),
    ]
    flt = f"subtitles={ASS_NAME}"
    paths = list(dict.fromkeys(c.path for c in choices if c.path))
    fdir = workdir / FONTS_SUBDIR
    if fdir.is_dir():  # polices d'un montage précédent (autre modèle) : libass pourrait prendre la mauvaise graisse
        for old in fdir.iterdir():
            if old.is_file() and old.name not in {p.name for p in paths}:
                old.unlink(missing_ok=True)
    if paths:
        fdir.mkdir(exist_ok=True)
        for path in paths:
            target = fdir / path.name
            if not target.exists():
                target.write_bytes(path.read_bytes())
        flt += f":fontsdir={FONTS_SUBDIR}"
    return flt


def normalize_text(s: str) -> str:
    """Compare deux textes sans tenir compte de la casse, des accents ni de la ponctuation (tests, alignement)."""
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"[^a-z0-9 ]", "", "".join(c for c in s if not unicodedata.combining(c)).lower()).strip()
