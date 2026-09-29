"""Modèle de montage : où et comment s'affichent le titre d'accroche, les sous-titres et les textes à l'écran, et les
niveaux du son (voix, musique de fond, bruitages : docs/26-musique.md), pour toutes les vidéos (onglet Montage du
dashboard, docs/23-montage.md).

Le modèle « par défaut » de la table montage_templates (migration 0013) est lu à chaque montage : le changer dans le
dashboard change les montages suivants, pas les vidéos déjà montées (« Refaire le montage » les remonte). Sans modèle
en base, le modèle d'origine ci-dessous garde le style d'avant l'onglet : titre d'accroche de MJClipIt (Arial Black 64
sur plaque #111111, haut à 150 px), désormais sur toutes les vidéos ; sous-titres du profil « impact » au milieu de
l'image ; textes à l'écran en capitales sur boîte noire à 60 %, centrés à 1 330 px, sur les chantiers et les visites.

Positions en pixels du final 1080×1920, comme dans l'éditeur : x = centre horizontal ; y = haut du titre d'accroche,
centre des sous-titres et des textes à l'écran. Tailles : px pour le titre d'accroche (Pillow), taille ASS pour les
sous-titres et les textes à l'écran (libass : la hauteur de ligne de la police vaut la taille).

Chaque couche s'affiche sur les formats choisis (récits narrés, chantiers, visites) ; les sous-titres n'existent que
sur les vidéos narrées. Les valeurs par défaut sont recopiées dans services/worker/assets/montage/defaults.json, que
lit le dashboard (un test vérifie qu'elles restent identiques).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal

import structlog
from pydantic import AfterValidator, BaseModel, Field, ValidationError

from .config import WORKER_ROOT
from .hooktitle import HookStyle, clean_hook
from .models import ScriptV1
from .numbers import to_digits
from .subtitles import BUILTIN_PROFILES, FontRegistry, SubtitleProfile, TitleStyle

log = structlog.get_logger(__name__)

DEFAULTS_FILE = WORKER_ROOT / "assets" / "montage" / "defaults.json"
FORMATS = ("story", "timelapse", "tour")  # recettes (worker/recipes.py) : récit narré, chantier, visite
ORIGIN_NAME = "Modèle d'origine"

Format = Literal["story", "timelapse", "tour"]


def _hex(v: str) -> str:
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
        raise ValueError(f"couleur attendue au format #RRGGBB, reçu {v!r}")
    return v.upper()


HexColor = Annotated[str, AfterValidator(_hex)]


class HookLayer(BaseModel):
    """Titre d'accroche : PNG dessiné par Pillow puis incrusté (worker/hooktitle.py). Sur toutes les vidéos par défaut
    (demande de Luca, 28/09 : « titre d'accroche, il y en aura toujours »)."""

    formats: list[Format] = Field(default_factory=lambda: list(FORMATS))
    duration_s: float | None = Field(None, ge=0.5, le=60)  # None : toute la vidéo
    font_family: str = "Arial Black"
    bold: bool = True
    size: int = Field(64, ge=24, le=200)
    uppercase: bool = False
    text_color: HexColor = "#FFFFFF"
    background: Literal["plate", "block", "none"] = "plate"  # une plaque par ligne, une seule plaque, aucune
    background_color: HexColor = "#111111"
    background_opacity: float = Field(1.0, ge=0, le=1)
    radius: int = Field(16, ge=0, le=120)
    padding_x: int = Field(22, ge=0, le=160)
    padding_y: int = Field(10, ge=0, le=160)
    outline_color: HexColor = "#111111"  # contour du texte sans plaque
    outline_width: int = Field(4, ge=0, le=24)
    width_pct: float = Field(0.9, ge=0.3, le=1.0)  # largeur maximale d'une ligne, plaque comprise
    line_spacing: float = Field(1.1, ge=0.8, le=2.0)
    align: Literal["left", "center", "right"] = "center"
    x: int = Field(540, ge=0, le=1080)
    y: int = Field(150, ge=0, le=1800)


class SubtitleLayer(BaseModel):
    """Sous-titres mot à mot des vidéos narrées (fichier ASS, worker/subtitles.py) ; défaut : le profil « impact »."""

    enabled: bool = True
    font_family: str = "Montserrat"
    bold: bool = True
    italic: bool = False
    font_size: int = Field(88, ge=24, le=220)
    text_transform: Literal["none", "uppercase", "lowercase", "capitalize"] = "uppercase"
    letter_spacing: float = Field(0, ge=-5, le=30)
    text_color: HexColor = "#FFFFFF"
    highlight_mode: Literal["none", "word", "karaoke"] = "word"
    highlight_color: HexColor = "#FFD400"
    outline_color: HexColor = "#000000"
    outline_width: float = Field(6, ge=0, le=20)
    shadow_color: HexColor = "#000000"
    shadow_opacity: float = Field(0.6, ge=0, le=1)
    shadow_distance: float = Field(6, ge=0, le=40)
    shadow_angle: int = Field(135, ge=0, le=359)
    shadow_blur: float = Field(4, ge=0, le=20)
    background: Literal["none", "box"] = "none"
    background_color: HexColor = "#000000"
    background_opacity: float = Field(0.55, ge=0, le=1)
    background_padding: int = Field(0, ge=0, le=80)
    max_words: int = Field(3, ge=1, le=8)
    max_chars: int = Field(18, ge=6, le=60)
    animation: Literal["none", "pop", "bounce", "fade", "slide_up"] = "pop"
    x: int = Field(540, ge=0, le=1080)
    y: int = Field(998, ge=40, le=1880)  # « center » du profil impact : 52 % de 1920


class TitleLayer(BaseModel):
    """Textes à l'écran des scènes (on_screen_text) et compteur de jours des chantiers (fichier ASS). Par défaut sur les
    chantiers (jours qui défilent) et les visites (nom des pièces) seulement : sur un récit narré, les sous-titres
    suffisent (demande de Luca, 28/09 : pas de texte en plus qui encombre l'image)."""

    formats: list[Format] = Field(default_factory=lambda: ["timelapse", "tour"])
    font_family: str = "Montserrat"
    bold: bool = True
    size: int = Field(76, ge=24, le=220)
    uppercase: bool = True
    text_color: HexColor = "#FFFFFF"
    background: Literal["box", "outline", "none"] = "box"
    box_color: HexColor = "#000000"
    box_opacity: float = Field(0.6, ge=0, le=1)
    padding: int = Field(16, ge=0, le=80)
    outline_color: HexColor = "#000000"
    outline_width: float = Field(4, ge=0, le=20)
    x: int = Field(540, ge=0, le=1080)
    y: int = Field(1330, ge=40, le=1880)  # sous le centre de l'image, au-dessus des boutons Shorts


class AudioLayer(BaseModel):
    """Son : niveaux de la voix, de la musique de fond et des bruitages (worker/music.py, docs/26-musique.md). Voix et
    musiques sont d'abord ramenées au même niveau (sonie mesurée) ; ces réglages font ensuite l'équilibre, le mixage
    final étant toujours ramené à −14 LUFS. Le volume propre de chaque piste se règle dans la bibliothèque
    (music_tracks.gain_db), pour tous les modèles."""

    formats: list[Format] = Field(default_factory=lambda: list(FORMATS))  # musique de fond sur ces formats
    voice_db: float = Field(0.0, ge=-12, le=12)  # voix IA, après égalisation
    music_db: float = Field(-10.0, ge=-40, le=0)  # musique sous la voix, par rapport à la voix
    duck_db: float = Field(4.0, ge=0, le=20)  # baisse de la musique pendant que la voix parle (remontée entre les phrases)
    solo_db: float = Field(0.0, ge=-20, le=12)  # musique des vidéos sans voix (chantiers, visites), sous les bruitages
    sfx_db: float = Field(0.0, ge=-20, le=12)  # bruitages


class MontageTemplate(BaseModel):
    version: Literal[1] = 1
    hook: HookLayer = Field(default_factory=HookLayer)
    subtitles: SubtitleLayer = Field(default_factory=SubtitleLayer)
    titles: TitleLayer = Field(default_factory=TitleLayer)
    audio: AudioLayer = Field(default_factory=AudioLayer)

    def shows_hook(self, recipe: str) -> bool:
        return recipe in self.hook.formats

    def shows_titles(self, recipe: str) -> bool:
        return recipe in self.titles.formats

    def plays_music(self, recipe: str) -> bool:
        return recipe in self.audio.formats

    def profile(self) -> SubtitleProfile:
        return SubtitleProfile.model_validate({**self.subtitles.model_dump(exclude={"enabled"}), "name": "modele"})

    def title_style(self) -> TitleStyle:
        t = self.titles
        return TitleStyle(
            font_family=t.font_family,
            bold=t.bold,
            size=t.size,
            text_color=t.text_color,
            transform="uppercase" if t.uppercase else "none",
            style=t.background,
            box_color=t.box_color,
            box_opacity=t.box_opacity,
            padding=t.padding,
            outline_color=t.outline_color,
            outline_width=t.outline_width,
            x=t.x,
            y=t.y,
        )

    def hook_style(self, fonts: FontRegistry) -> HookStyle:
        h = self.hook
        choice = fonts.pick(h.font_family, h.bold)
        return HookStyle(
            size=h.size,
            width_pct=h.width_pct,
            bg=h.background != "none",
            bg_color=h.background_color,
            text_color=h.text_color,
            line_spacing=h.line_spacing,
            radius=h.radius,
            y=h.y,
            duration_s=h.duration_s,
            font_path=str(choice.path) if choice.path else None,
            x=h.x,
            align=h.align,
            bg_mode="block" if h.background == "block" else "plate",
            bg_opacity=h.background_opacity,
            pad_x=h.padding_x,
            pad_y=h.padding_y,
            outline_color=h.outline_color,
            outline_width=h.outline_width,
            uppercase=h.uppercase,
            fake_bold=choice.synthetic_bold and choice.path is not None,
        )


def subtitle_presets() -> dict[str, dict[str, Any]]:
    """Styles de départ des sous-titres proposés dans l'onglet Montage : les profils intégrés (impact, karaoké, sobre,
    affiche, bd), sans leur position (le style s'applique, la légende reste où on l'a placée)."""
    keep = set(SubtitleLayer.model_fields) - {"enabled", "x", "y"}
    return {
        name: SubtitleLayer.model_validate(p.model_dump(include=keep)).model_dump(mode="json", include=keep)
        for name, p in BUILTIN_PROFILES.items()
    }


def load_template(db: Any) -> tuple[MontageTemplate, str]:
    """Modèle de montage par défaut (table montage_templates) ; le modèle d'origine s'il n'y en a pas, si la migration
    0013 manque, ou s'il est illisible (le montage ne doit jamais échouer pour ça : on le journalise)."""
    try:
        row = db.fetch_one("select name, template from montage_templates where is_default limit 1")
    except Exception as exc:  # noqa: BLE001 — table absente (migration 0013 pas encore appliquée)
        log.warning("montage.modele_illisible", error=str(exc)[:200])
        return MontageTemplate(), ORIGIN_NAME
    if not row:
        return MontageTemplate(), ORIGIN_NAME
    try:
        return MontageTemplate.model_validate(row["template"]), row["name"]
    except ValidationError as exc:
        log.warning("montage.modele_invalide", name=row["name"], error=str(exc)[:300])
        return MontageTemplate(), ORIGIN_NAME


def _defaults() -> dict[str, Any]:
    try:
        return json.loads(DEFAULTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def windows_font_files() -> list[Path]:
    """Polices de Windows proposées dans l'onglet Montage (liste de defaults.json), celles présentes sur ce PC."""
    folder = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    return [folder / name for name in _defaults().get("windows_fonts", []) if (folder / name).is_file()]


def font_registry(settings: Any) -> FontRegistry:
    """Polices du montage : celles livrées avec le worker (assets/fonts), celles ajoutées depuis l'onglet Montage
    (DATA_DIR/fonts) et une sélection de polices de Windows (Arial Black, Impact, Segoe UI…)."""
    return FontRegistry.scan(settings.fonts_dir, settings.data_dir / "fonts", *windows_font_files())


def hook_text(script: ScriptV1, lang: str) -> str:
    """Texte du titre d'accroche : celui du script, sinon (anciens récits écrits sans) le titre de la vidéo ; nombres en
    chiffres (« Huit cent cinquante-deux morts » → « 852 morts », worker/numbers.py)."""
    text = clean_hook(script.hook_title.get(lang) or "")  # type: ignore[call-overload]
    if not text and lang in script.metadata:
        text = clean_hook(script.metadata[lang].title)  # type: ignore[index]
    return to_digits(text, lang)
