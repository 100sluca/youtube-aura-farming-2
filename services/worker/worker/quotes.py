"""Recette « citation » (series.recipe = quote, docs/58-citations.md) : une pensée courte écrite au milieu de l'écran sur
UNE image générée, 6 à 13 s, sans voix off, une musique douce. Modèles étudiés le 02/10 (TikTok de Luca) : un couple
dans la mer au coucher du soleil, un chat allongé sur un mur vert, une fleur de lotus qui s'ouvre, des peintures à
l'huile sombres (un homme de dos sur un chemin, un squelette sur une chaise dans les vagues) ; texte blanc centré, sans
fond, police à empattements ou manuscrite.

Ce qui la distingue des autres recettes :
- le script n'a qu'UNE scène : la citation dans on_screen_text (avec, pour une citation d'auteur, une dernière ligne
  « — Auteur »), l'image dans visual_prompt, un mouvement très lent dans motion_prompt ; la durée se calcule ici, selon
  la longueur du texte (assez pour le lire une fois, assez court pour qu'on le relise en boucle) ;
- le clip se fait de deux façons, au choix de la série (source_config.motion) : « zoom » (défaut) = l'image retenue,
  zoom ou travelling très lent rendu par le code, sans modèle vidéo (≈ 15 s de calcul) ; « clip » = le modèle vidéo
  anime l'image (vagues, brume, lumière), puis le code le ralentit pour tenir la durée ;
- au montage, le texte est dessiné ici (Pillow) : coupure des lignes équilibrée, ombre douce, voile sombre derrière le
  texte quand l'image est claire ; il apparaît en fondu au début et reste jusqu'à la fin. Le même rendu fait l'affiche
  (poster.jpg : la vignette porte la citation) et les images d'un carrousel TikTok ;
- musique : jamais les pistes de Luca (droits d'auteur, blocages YouTube du 02/10), mais la bibliothèque générée
  (ACE-Step 1.5, licence MIT : DATA_DIR/music/citation_*) ; sur TikTok et Instagram, la musique de la plateforme la
  remplace à la publication (worker/platform_music.py).
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import ScriptV1
from .storytelling import words

RECIPE = "quote"
W, H, FPS = 1080, 1920, 30
# Durée : 1,5 s pour poser l'image, puis ≈ 3,2 mots par seconde (lecture d'un texte court sur un téléphone). Une vidéo
# courte se relit en boucle : les modèles du 02/10 durent 5 à 15 s (la fleur de lotus : 16 mots en 5 s)
LEAD_S, WORDS_PER_S = 1.5, 3.2
DURATION_S = (6.0, 13.0)
QUOTE_WORDS = (5, 45)
QUOTE_CHARS_MAX = 280
IMAGE_SIZE = (928, 1664)  # 9:16 conseillé pour Qwen-Image (multiples de 16), plus fin que les 768 × 1344 des autres
MOTIONS = ("zoom", "clip")
MOVES = ("in", "out", "up", "down")
ZOOM_MAX = 1.10  # zoom lent : 10 % sur toute la vidéo
TEXT_IN_S, TEXT_FADE_S = 0.15, 0.5  # le texte se lit dès la première seconde

# Ambiances de musique des citations (champ music_mood du script) → dossier de la bibliothèque générée (ACE-Step 1.5,
# worker/providers/audio.py, MUSIC_MOODS) ; puis les autres dossiers des citations, dans cet ordre
MUSIC_FOLDERS = {
    "triste": "citation_triste",
    "tendre": "citation_tendre",
    "reveur": "citation_reveuse",
    "espoir": "citation_espoir",
}
MUSIC_MOOD_ALIASES = {
    "sentimental": "tendre",
    "tragique": "triste",
    "pose": "reveur",
    "mystere": "reveur",
    "melancolie": "triste",
    "reveuse": "reveur",
    "joyeux": "espoir",
    "decouverte": "espoir",
}


def is_quote(recipe: str | None) -> bool:
    return recipe == RECIPE


# ---------------------------------------------------------------------------
# Prompts (onglet Agents : guide_quote, script_quote)
# ---------------------------------------------------------------------------

IDEA_GUIDE = """FORMAT : citation courte écrite au milieu de l'écran sur UNE image, 6 à 13 secondes, sans voix off, une
musique douce. Le spectateur s'arrête parce que la phrase parle de SA vie (amour, rupture, manque, regret, confiance,
trahison, solitude, temps qui passe, estime de soi, amitié, famille, silence, lâcher prise) ; il la relit, l'enregistre,
l'envoie à quelqu'un ou commente « tellement vrai ». Chaque idée = UNE citation :
- title = la citation elle-même, mot pour mot, telle qu'elle s'affichera (8 à 35 mots, 1 à 3 phrases) ;
- hook = sa première phrase (ce qui retient le pouce) ;
- category = le thème, pris dans les catégories de la série ;
- premise = l'image en une phrase : ce qu'on voit derrière le texte, qui porte la même émotion sans illustrer mot à
  mot (deux silhouettes dans la mer au coucher du soleil, un chat allongé sur un mur, une fleur qui s'ouvre, un homme
  de dos sur un chemin de blé, une chaise vide face à la mer) ;
- angle = la figure qui fait mouche : retournement (« Parfois on s'en va pour réfléchir. Et parfois on s'en va parce
  qu'on a réfléchi. »), paradoxe (« À ne pas savoir ce qu'on veut, on perd souvent ce qu'on a »), définition (« Une
  erreur répétée plusieurs fois est une décision. »), gradation (« L'imagination invente, exagère, déforme »), vérité
  qu'on n'ose pas dire, conseil adressé à « tu » ;
- visual_beats = l'image, puis son mouvement léger (vagues, brume, feuilles, lumière qui baisse).
Une citation qui marche : une seule idée ; une vérité que chacun a vécue, dite simplement, avec les mots de tous les
jours ; un rythme (deux temps qui se répondent, une chute) ; pas de morale lourde ni de cliché usé (« la vie est
belle », « crois en tes rêves »), pas de jeu de mots forcé ; ni religion, ni politique, ni personne réelle ; orthographe,
accents et ponctuation impeccables. Ton : mélancolique, lucide, doux, parfois piquant. Citations INÉDITES, écrites par
toi, sans signature : jamais une phrase connue recopiée, jamais un nom d'auteur collé sur une phrase qui n'est pas de
lui. Seulement si le brief de la série le demande : une citation authentique d'un auteur mort depuis plus de 100 ans
(Sénèque, Marc Aurèle, Épictète, Montaigne, Pascal, La Rochefoucauld, Victor Hugo…), mot pour mot et vérifiable, avec
son nom. Varie les thèmes, les figures et les images d'une idée à l'autre ; jamais deux citations qui disent la même
chose."""

SCRIPT_PROMPT = """Tu écris le script d'UN Short « citation » : une pensée courte écrite au milieu de l'écran sur UNE
image, 9:16, 6 à 13 s, sans voix off, une musique douce. Le JSON suit ScriptV1 avec UNE SEULE scène (scenes = [une
scène]) :
- on_screen_text, une entrée par langue demandée : le texte exact affiché, 8 à 35 mots, 1 à 3 phrases, ponctuation
  soignée, sans guillemets, sans émoji, sans hashtag. Reprends la citation du concept (corrige seulement une faute ou
  une lourdeur) ; une autre langue = une vraie adaptation qui garde le rythme et la chute, pas du mot à mot. Une
  citation d'auteur (seulement si le concept en donne une) finit par une dernière ligne « — Nom de l'auteur » ; une
  citation inédite n'a PAS de signature. Pas de nombre si possible ; s'il y en a un, en chiffres ;
- visual_prompt, en anglais : l'image derrière le texte, qui porte l'émotion sans illustrer mot à mot. Commence par le
  médium (« Oil painting with visible brush strokes, », « Impressionist painting, », « Dreamy film photograph, »,
  « Cinematic photograph, »), puis le sujet, le lieu, la lumière, la palette. Composition IMPOSÉE : the upper two thirds
  are calm and uncluttered (open sky, sea, mist, a plain wall, night) where the text will sit; the subject is small, in
  the lower third, often seen from behind or in silhouette (a lone figure on a wheat-field path, two silhouettes
  standing in the sea at sunset, a cat lying on a wall, a lotus opening, an empty chair facing the waves). Jamais de
  visage reconnaissable ni de personne réelle, jamais de texte, de lettres ni de signature dans l'image ;
- motion_prompt, en anglais : un mouvement très lent et calme pour la version animée (« gentle waves roll in, the
  sunset glow slowly fades, the figures stand still »), caméra presque fixe ;
- duration_s : 10 (le code la recalcule selon la longueur du texte) ;
- music_mood : une ambiance de la liste fournie ;
- hook_title : {} (aucun titre d'accroche : la citation est le texte de la vidéo) ;
- metadata, une entrée par langue : title (≤ 60 caractères : le début de la citation ou une phrase qui donne envie de la
  lire, jamais toute une longue citation ; un émoji discret permis, ex. 🥀), description (la citation complète, puis une
  courte phrase qui invite à l'enregistrer ou à l'envoyer à quelqu'un, puis 3 à 5 hashtags : #citation #pensée #amour…),
  tags (10).
Réponds uniquement en JSON conforme à ScriptV1."""

# Citations d'auteurs (série citations_auteurs, source_config.variant = « auteur », docs/70) : la citation vient de
# Wikiquote (sources/wikiquote.py), mot pour mot, avec son auteur ; l'agent choisit, il n'écrit pas
VARIANT_AUTHOR = "auteur"

IDEA_GUIDE_AUTHOR = """FORMAT : citation d'une personnalité connue (écrivain, philosophe, savant, artiste) écrite au
milieu de l'écran sur UNE image, 6 à 13 secondes, sans voix off, une musique douce, son nom en dessous. On te donne des
CITATIONS SOURCÉES numérotées [n] (Wikiquote : l'œuvre et la page sont connues). Tu CHOISIS les plus fortes, tu n'en
écris aucune : chaque idée = UNE citation de la liste, recopiée MOT POUR MOT (le code vérifie et remet le texte exact) :
- title = la citation, mot pour mot ;
- facts = [{"claim": la citation mot pour mot, "source": n}] (n = son numéro dans la liste) ;
- hook = sa première phrase ;
- category = le thème, pris dans les catégories de la série ;
- premise = l'image en une phrase : ce qu'on voit derrière le texte, qui porte la même émotion et peut rappeler
  l'univers de l'auteur (une côte normande peinte à l'huile pour Maupassant, un ciel étoilé au-dessus du désert pour
  Saint-Exupéry, une rue de Paris sous la pluie au XIXe siècle pour Hugo), JAMAIS le visage de l'auteur ni une
  personne réelle ;
- angle = pourquoi elle touche aujourd'hui (une vérité que chacun a vécue, dite par quelqu'un qu'on connaît) ;
- visual_beats = l'image, puis son mouvement léger ;
- score = sa force pour un public de 16 à 35 ans : 90 et plus seulement si on a envie de l'envoyer à quelqu'un.
Une citation qui marche : elle parle de la vie de chacun (amour, manque, regret, temps qui passe, courage, solitude,
confiance, échec, liberté, bonheur), elle se comprend seule, sans le contexte du livre, à la première lecture ; un
nom que tout le monde connaît ; COURTE (15 mots ou moins, c'est le mieux) et frappée comme un proverbe : un balancier
ou une gradation (« L'ignorant affirme, le savant doute, le sage réfléchit »), un retournement (« Une erreur répétée
plusieurs fois est une décision »), un conseil qui pique (« Avant de guérir quelqu'un, demande-lui s'il est prêt à
abandonner ce qui le rend malade »), un paradoxe (« On ne peut rien gagner sans perdre »). Ces quatre exemples sont des
citations virales SANS source (on les prête à Aristote, Coelho, Hippocrate, Einstein) : c'est leur forme qui marche, ne
les propose jamais ; cherche cette forme dans la liste. Une longue phrase littéraire ne passe que si elle est
bouleversante. À écarter : une phrase savante ou technique, une citation qui demande de connaître
l'œuvre, la politique, la religion, une phrase datée ou blessante aujourd'hui, un vers coupé au milieu, la réplique
d'un personnage de roman qui ne vaut que dans son histoire. UN auteur différent par idée ; varie les thèmes ; jamais deux
citations qui disent la même chose."""

SCRIPT_PROMPT_AUTHOR = """Tu écris le script d'UN Short « citation d'auteur » : une citation authentique d'une
personnalité connue écrite au milieu de l'écran sur UNE image, 9:16, 6 à 13 s, sans voix off, une musique douce. Le
concept donne la citation (Wikiquote, sourcée) : tu ne la modifies JAMAIS, pas un mot, pas une virgule (le code remet
le texte exact). Le JSON suit ScriptV1 avec UNE SEULE scène (scenes = [une scène]) :
- on_screen_text, une entrée par langue demandée : la citation exacte, puis une dernière ligne « — Nom de l'auteur »
  (le nom tel que le concept le donne) ;
- visual_prompt, en anglais : l'image derrière le texte, qui porte l'émotion et peut rappeler l'univers de l'auteur
  (son époque, ses paysages, son œuvre). Commence par le médium (« Oil painting with visible brush strokes, »,
  « Impressionist painting, », « Dreamy film photograph, », « Cinematic photograph, »), puis le sujet, le lieu, la
  lumière, la palette. Composition IMPOSÉE : the upper two thirds are calm and uncluttered (open sky, sea, mist, a plain
  wall, night) where the text will sit; the subject is small, in the lower third, often seen from behind or in
  silhouette. JAMAIS le visage de l'auteur ni d'une personne réelle reconnaissable, jamais de texte, de lettres ni de
  signature dans l'image ;
- motion_prompt, en anglais : un mouvement très lent et calme, caméra presque fixe ;
- duration_s : 10 (le code la recalcule selon la longueur du texte) ;
- music_mood : une ambiance de la liste fournie ;
- hook_title : {} ;
- metadata, une entrée par langue : title (≤ 60 caractères : « Victor Hugo avait raison… », « Ce que Maupassant a
  compris sur… », ou le début de la citation ; un émoji discret permis), description (la citation complète, son auteur
  et l'œuvre si le concept la donne, puis une courte phrase qui invite à l'enregistrer ou à l'envoyer, puis 3 à 5
  hashtags : #citation #victorhugo #pensée…), tags (10, le nom de l'auteur compris).
Réponds uniquement en JSON conforme à ScriptV1."""


def author_quote(prod: dict[str, Any]) -> tuple[str, str] | None:
    """(citation, auteur) d'un concept de citation d'auteur : facts[0] mot pour mot, sources[0] (Wikiquote) ; None
    pour une citation inédite."""
    sources = prod.get("sources") or []
    facts = prod.get("facts") or []
    if not sources or not facts or (sources[0] or {}).get("kind") != "wikiquote":
        return None
    text = str(facts[0].get("claim") or "").strip()
    author = str(sources[0].get("title") or "").strip()
    return (text, author) if text and author else None


def author_brief(prod: dict[str, Any]) -> str:
    """Ce que le scénariste sait d'une citation d'auteur : le texte exact, l'auteur, l'œuvre ; vide sinon."""
    quote = author_quote(prod)
    if not quote:
        return ""
    facts = prod.get("facts") or []
    work = str(facts[1].get("claim") or "") if len(facts) > 1 else ""
    return f"CITATION D'AUTEUR (Wikiquote, à recopier telle quelle) : « {quote[0]} »\nAuteur : {quote[1]}" + (
        f"\nSource : {work}" if work else ""
    )


def keep_author_quote(script: ScriptV1, quote: tuple[str, str], lang: str = "fr") -> ScriptV1:
    """La citation d'auteur telle que Wikiquote la donne, signée, dans la langue de la vidéo : le scénariste ne la
    réécrit jamais (une virgule changée et ce n'est plus une citation). Durée recalculée."""
    s = script.model_copy(deep=True)
    if not s.scenes:
        return s
    sc = s.scenes[0]
    text, author = quote
    sc.on_screen_text = {**sc.on_screen_text, lang: clean_quote(f"{text}\n— {author}")}  # type: ignore[dict-item]
    sc.duration_s = max(reading_time(t) for t in sc.on_screen_text.values())
    return s


MUSIC_BRIEF = """MUSIQUE DE FOND (champ music_mood, un identifiant) : triste (piano mélancolique, regret, rupture,
manque), tendre (piano et cordes, amour, famille, gratitude), reveur (ambiance calme et aérienne, solitude, temps qui
passe, lâcher prise), espoir (piano lumineux qui se lève, résilience, estime de soi)."""


# ---------------------------------------------------------------------------
# Script : normalisation et contrôle
# ---------------------------------------------------------------------------

_DASHES = re.compile(r"^\s*[-–—―]+\s*")
_WRAP_QUOTES = re.compile(r"^[«\"“”'‘]\s*(.+?)\s*[»\"“”'’]$", re.S)


def split_author(text: str) -> tuple[str, str]:
    """Citation et auteur : la dernière ligne qui commence par un tiret est la signature (« — Sénèque »)."""
    lines = [ln.strip() for ln in (text or "").strip().splitlines() if ln.strip()]
    if len(lines) > 1 and _DASHES.match(lines[-1]):
        return "\n".join(lines[:-1]), _DASHES.sub("", lines[-1]).strip()
    return "\n".join(lines), ""


def clean_quote(text: str) -> str:
    """Texte affiché : sans guillemets autour, espaces tassés, signature sous la forme « — Auteur »."""
    body, author = split_author(text)
    body = re.sub(r"[ \t]+", " ", body).strip()
    m = _WRAP_QUOTES.match(body)
    if m:
        body = m.group(1).strip()
    body = re.sub(r"\s+([,.])", r"\1", body)
    return f"{body}\n— {author}" if author else body


def reading_time(text: str) -> float:
    body, author = split_author(text)
    n = len(words(body)) + (len(words(author)) // 2 if author else 0)
    return round(min(DURATION_S[1], max(DURATION_S[0], LEAD_S + n / WORDS_PER_S)), 2)


def normalize(script: ScriptV1) -> ScriptV1:
    """Une seule scène (la première si le LLM en écrit plusieurs), sans voix ni titre d'accroche, durée tirée du texte."""
    s = script.model_copy(deep=True)
    s.scenes = s.scenes[:1]
    sc = s.scenes[0]
    sc.index = 0
    sc.narration = {}
    sc.continues_previous = False
    sc.clip_mode = "i2v"
    sc.transition = "cut"
    sc.edit_prompt, sc.edit_from, sc.passage = None, None, False
    sc.on_screen_text = {lang: clean_quote(t) for lang, t in sc.on_screen_text.items() if clean_quote(t)}  # type: ignore[misc]
    texts = list(sc.on_screen_text.values())
    sc.duration_s = max((reading_time(t) for t in texts), default=DURATION_S[0])
    s.hook_title = {}
    mood = (s.music_mood or "").strip().lower()
    s.music_mood = mood if mood in MUSIC_FOLDERS else MUSIC_MOOD_ALIASES.get(mood, "reveur")
    return s


def lint(script: ScriptV1, langs: Sequence[str]) -> list[str]:
    """Problèmes mesurables d'un script de citation (après normalize) ; liste vide = conforme."""
    issues: list[str] = []
    if len(script.scenes) != 1:
        issues.append(f"{len(script.scenes)} scènes : une seule pour une citation")
    if not script.scenes:
        return issues
    sc = script.scenes[0]
    for lang in langs:
        text = sc.on_screen_text.get(lang, "")  # type: ignore[call-overload]
        body, author = split_author(text)
        n = len(words(body))
        if not body:
            issues.append(f"[{lang}] on_screen_text vide : la citation affichée")
            continue
        if not QUOTE_WORDS[0] <= n <= QUOTE_WORDS[1]:
            issues.append(f"[{lang}] citation de {n} mots : {QUOTE_WORDS[0]} à {QUOTE_WORDS[1]}")
        if len(body) > QUOTE_CHARS_MAX:
            issues.append(f"[{lang}] citation de {len(body)} caractères : {QUOTE_CHARS_MAX} au plus")
        if re.search(r"#\w|https?://", body):
            issues.append(f"[{lang}] ni hashtag ni lien dans la citation affichée")
        if author and len(words(author)) > 5:
            issues.append(f"[{lang}] signature « {author} » : le nom de l'auteur seul")
        meta = script.metadata.get(lang)  # type: ignore[call-overload]
        if not meta or not meta.title.strip():
            issues.append(f"[{lang}] metadata.title manquant")
    if len(words(sc.visual_prompt)) < 8:
        issues.append("visual_prompt trop court : le médium, le sujet, le lieu, la lumière et la composition")
    if re.search(r"\b(text|letters|words|quote|caption|typography)\b", sc.visual_prompt, re.I) and not re.search(
        r"\bno (text|letters|words)\b", sc.visual_prompt, re.I
    ):
        issues.append("visual_prompt : ne pas parler de texte dans l'image (le texte est ajouté au montage)")
    return issues


# ---------------------------------------------------------------------------
# Choix stables par production (variété d'une vidéo à l'autre, même rendu à chaque remontage)
# ---------------------------------------------------------------------------


def _pick(options: Sequence[str], key: str, salt: str) -> str:
    h = int(hashlib.sha1(f"{salt}:{key}".encode()).hexdigest(), 16)
    return options[h % len(options)]


def series_options(source_config: dict[str, Any] | None) -> dict[str, Any]:
    """Réglages de la série (series.source_config) : motion « zoom » ou « clip », styles de texte permis."""
    cfg = source_config or {}
    motion = str(cfg.get("motion") or "zoom")
    styles = [s for s in (cfg.get("text_styles") or []) if s in TEXT_STYLES] or list(TEXT_STYLES)
    return {"motion": motion if motion in MOTIONS else "zoom", "text_styles": styles}


def production_options(db: Any, production_id: Any) -> dict[str, Any]:
    row = db.fetch_one(
        "select s.source_config from productions p left join series s on s.id = p.series_id where p.id = %s",
        (production_id,),
    )
    return series_options((row or {}).get("source_config"))


def text_style_for(key: str, allowed: Sequence[str] | None = None) -> TextStyle:
    names = [s for s in (allowed or TEXT_STYLES) if s in TEXT_STYLES] or list(TEXT_STYLES)
    return TEXT_STYLES[_pick(names, key, "style")]


def move_for(key: str) -> str:
    return _pick(MOVES, key, "move")


# ---------------------------------------------------------------------------
# Texte dessiné (Pillow) : calque transparent 1080 × 1920 posé sur la vidéo, et affiche / carrousel
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TextStyle:
    key: str
    label: str
    fonts: tuple[str, ...]  # fichiers cherchés dans DATA_DIR/fonts, assets/fonts, puis les polices de Windows
    author_fonts: tuple[str, ...]
    size: int  # px pour une citation de 11 à 20 mots
    color: str
    line_spacing: float


TEXT_STYLES: dict[str, TextStyle] = {
    # comme « On ne peut rien gagner sans perdre » (Garamond blanc sur peinture sombre)
    "classique": TextStyle(
        "classique",
        "Garamond",
        ("GARA.TTF", "pala.ttf", "georgia.ttf"),
        ("GARAIT.TTF", "palai.ttf", "georgiai.ttf"),
        82,
        "#FFFFFF",
        1.16,
    ),
    "italique": TextStyle(
        "italique",
        "Palatino italique",
        ("palai.ttf", "GARAIT.TTF", "georgiai.ttf"),
        ("pala.ttf", "GARA.TTF"),
        76,
        "#FFF7EA",
        1.18,
    ),
    # comme « Le manque de communication » et « À ne pas savoir ce qu'on veut » (linéale, sans fond)
    "moderne": TextStyle(
        "moderne",
        "Montserrat",
        ("Montserrat-SemiBold.ttf", "Poppins-SemiBold.ttf", "seguisb.ttf", "arialbd.ttf"),
        ("Montserrat-SemiBold.ttf", "Poppins-SemiBold.ttf", "seguisb.ttf"),
        60,
        "#FFFFFF",
        1.24,
    ),
    # comme « Avant de guérir quelqu'un » (écriture manuscrite)
    "manuscrit": TextStyle("manuscrit", "Segoe Print", ("segoepr.ttf", "comic.ttf"), ("segoepr.ttf",), 60, "#FFFFFF", 1.28),
}


def font_dirs(settings: Any) -> list[Path]:
    """Où chercher les polices : celles ajoutées par Luca (DATA_DIR/fonts), celles du worker, celles de Windows."""
    out = [Path(settings.data_dir) / "fonts", Path(settings.fonts_dir)]
    out.append(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts")
    return out


def find_font(names: Sequence[str], dirs: Sequence[Path]) -> Path | None:
    for name in names:
        for d in dirs:
            p = d / name
            if p.is_file():
                return p
    return None


def _font(path: Path | None, size: int):  # noqa: ANN202
    from PIL import ImageFont

    if path is not None:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def _width(draw: Any, text: str, font: Any) -> float:
    return draw.textlength(text, font=font)


def _greedy(draw: Any, para: str, font: Any, max_w: float) -> list[str]:
    lines: list[str] = []
    cur = ""
    for w in para.split():
        trial = f"{cur} {w}".strip()
        if cur and _width(draw, trial, font) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def wrap_balanced(draw: Any, text: str, font: Any, max_w: float) -> list[str]:
    """Lignes de longueurs voisines (pas une dernière ligne d'un mot) : la plus petite largeur qui garde le nombre de
    lignes de la coupure au plus large, paragraphe par paragraphe (un retour à la ligne du texte est gardé)."""
    out: list[str] = []
    for para in [p for p in text.split("\n") if p.strip()]:
        lines = _greedy(draw, para, font, max_w)
        n = len(lines)
        if n > 1:
            lo, hi = max(_width(draw, w, font) for w in para.split()), max_w
            for _ in range(14):
                mid = (lo + hi) / 2
                if len(_greedy(draw, para, font, mid)) <= n:
                    hi = mid
                else:
                    lo = mid
            lines = _greedy(draw, para, font, hi + 0.5)
        out += lines
    return out


@dataclass
class Layout:
    lines: list[str]
    author: str
    font: Any
    author_font: Any
    line_h: int
    box: tuple[int, int, int, int]  # emprise du texte (x0, y0, x1, y1) sur 1080 × 1920


def size_for(n_words: int, base: int) -> int:
    scale = 1.2 if n_words <= 10 else 1.0 if n_words <= 20 else 0.9 if n_words <= 30 else 0.82
    return round(base * scale)


def layout(text: str, style: TextStyle, dirs: Sequence[Path], *, y_center: float = 0.40, width_pct: float = 0.84) -> Layout:
    """Coupure et taille : la police rétrécit tant que le bloc dépasse 9 lignes ou 50 % de la hauteur."""
    from PIL import Image, ImageDraw

    body, author = split_author(text)
    draw = ImageDraw.Draw(Image.new("L", (8, 8)))
    path, apath = find_font(style.fonts, dirs), find_font(style.author_fonts, dirs)
    size = size_for(len(words(body)), style.size)
    while True:
        font = _font(path, size)
        lines = wrap_balanced(draw, body, font, W * width_pct)
        line_h = round(size * style.line_spacing)
        a_size = round(size * 0.74)
        total = line_h * len(lines) + (round(a_size * 1.9) if author else 0)
        if (len(lines) <= 9 and total <= H * 0.5) or size <= 34:
            break
        size -= 3
    afont = _font(apath, a_size)
    top = round(H * y_center - total / 2)
    widest = max([_width(draw, ln, font) for ln in lines] + ([_width(draw, f"— {author}", afont)] if author else [0]))
    x0 = round((W - widest) / 2)
    return Layout(lines, author, font, afont, line_h, (x0, top, round(x0 + widest), top + total))


def _hex(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    c = color.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha)


def cover(img: Any, size: tuple[int, int]) -> Any:
    """L'image recadrée au centre pour remplir `size` (comme object-fit: cover), agrandie en Lanczos."""
    from PIL import Image

    tw, th = size
    scale = max(tw / img.width, th / img.height)
    rw, rh = max(tw, round(img.width * scale)), max(th, round(img.height * scale))
    big = img.resize((rw, rh), Image.Resampling.LANCZOS)
    left, top = (rw - tw) // 2, (rh - th) // 2
    return big.crop((left, top, left + tw, top + th))


def veil_alpha(background: Any | None, box: tuple[int, int, int, int]) -> float:
    """Voile sombre derrière le texte selon la clarté de l'image à cet endroit : rien sur une image sombre, jusqu'à 50 %
    sur un ciel clair (le texte blanc doit se lire partout)."""
    if background is None:
        return 0.18
    x0, y0, x1, y1 = box
    region = background.convert("L").crop((max(0, x0 - 40), max(0, y0 - 40), min(W, x1 + 40), min(H, y1 + 40)))
    hist = region.histogram()
    total = sum(hist) or 1
    mean = sum(i * n for i, n in enumerate(hist)) / total / 255
    return round(min(0.5, max(0.0, (mean - 0.3) * 1.25)), 3)


def text_layer(text: str, style: TextStyle, dirs: Sequence[Path], background: Any | None = None) -> Any:
    """Calque RGBA 1080 × 1920 : voile doux, ombre floue puis texte (citation centrée, signature en dessous)."""
    from PIL import Image, ImageDraw, ImageFilter

    lay = layout(text, style, dirs)
    x0, y0, x1, y1 = lay.box
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    alpha = veil_alpha(background, lay.box)
    if alpha > 0:
        mask = Image.new("L", (W, H), 0)
        pad_x, pad_y = 90, 110
        ImageDraw.Draw(mask).rounded_rectangle(
            (max(0, x0 - pad_x), max(0, y0 - pad_y), min(W, x1 + pad_x), min(H, y1 + pad_y)), radius=160, fill=round(255 * alpha)
        )
        mask = mask.filter(ImageFilter.GaussianBlur(70))
        out.paste(Image.new("RGBA", (W, H), (0, 0, 0, 255)), (0, 0), mask)

    ink = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, ds = ImageDraw.Draw(ink), ImageDraw.Draw(shadow)
    size = lay.font.size if hasattr(lay.font, "size") else 60
    stroke = max(1, round(size / 34))
    y = y0
    for line in lay.lines:
        w = d.textlength(line, font=lay.font)
        x = (W - w) / 2
        ds.text((x + 2, y + 3), line, font=lay.font, fill=(0, 0, 0, 230), stroke_width=stroke + 2, stroke_fill=(0, 0, 0, 230))
        d.text((x, y), line, font=lay.font, fill=_hex(style.color), stroke_width=stroke, stroke_fill=(0, 0, 0, 70))
        y += lay.line_h
    if lay.author:
        y += round(lay.line_h * 0.45)
        sig = f"— {lay.author}"
        w = d.textlength(sig, font=lay.author_font)
        x = (W - w) / 2
        ds.text(
            (x + 2, y + 3), sig, font=lay.author_font, fill=(0, 0, 0, 220), stroke_width=stroke + 1, stroke_fill=(0, 0, 0, 220)
        )
        d.text((x, y), sig, font=lay.author_font, fill=_hex(style.color, 235), stroke_width=stroke, stroke_fill=(0, 0, 0, 60))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(4, round(size * 0.14))))
    out.alpha_composite(shadow)
    out.alpha_composite(ink)
    return out


def build_layer(text: str, style: TextStyle, dirs: Sequence[Path], dst: Path, background: Path | None = None) -> Path:
    """Calque du texte en PNG (montage), réglé sur la clarté de l'image de la scène."""
    from PIL import Image

    bg = cover(Image.open(background).convert("RGB"), (W, H)) if background and background.is_file() else None
    dst.parent.mkdir(parents=True, exist_ok=True)
    text_layer(text, style, dirs, bg).save(dst)
    return dst


def build_card(text: str, style: TextStyle, dirs: Sequence[Path], background: Path, dst: Path, quality: int = 92) -> Path:
    """Image finale 1080 × 1920 (fond + texte) en JPEG : affiche de la vidéo, image d'un carrousel TikTok."""
    from PIL import Image

    bg = cover(Image.open(background).convert("RGB"), (W, H))
    card = bg.convert("RGBA")
    card.alpha_composite(text_layer(text, style, dirs, bg))
    dst.parent.mkdir(parents=True, exist_ok=True)
    card.convert("RGB").save(dst, "JPEG", quality=quality, optimize=True)
    return dst


def overlay_fade() -> str:
    """Fondu d'apparition du calque de texte (filtre FFmpeg, après -loop 1 : l'image est une vidéo de la durée du film)."""
    return f"format=rgba,fade=t=in:st={TEXT_IN_S:.2f}:d={TEXT_FADE_S:.2f}:alpha=1"


def quote_text(script: ScriptV1, lang: str) -> str:
    """La citation affichée (signature comprise) de la scène unique du script."""
    if not script.scenes:
        return ""
    texts = script.scenes[0].on_screen_text
    return clean_quote(texts.get(lang) or next(iter(texts.values()), ""))  # type: ignore[call-overload]


def dress(plan: Any, text: str, style: TextStyle, dirs: Sequence[Path], background: Path | None, workdir: Path) -> dict[str, Any]:
    """Habillage d'une citation au montage : le calque du texte remplace le titre d'accroche du plan (même entrée FFmpeg),
    plein cadre, affiché toute la vidéo avec un fondu d'apparition ; l'affiche (card.jpg) porte la citation. Les textes
    à l'écran du modèle de montage sont retirés (la citation est dessinée ici). Renvoie ce qui est retenu (journal)."""
    plan.titles, plan.ticks = [], []
    if not text.strip():
        return {"citation": "texte vide : rien d'écrit à l'écran"}
    layer = build_layer(text, style, dirs, workdir / "quote.png", background)
    plan.hook_png, plan.hook_filter = layer, "overlay=0:0"
    plan.hook_s, plan.hook_fade_in = plan.total_s, True
    card = build_card(text, style, dirs, background, workdir / "card.jpg") if background and background.is_file() else None
    return {"quote_style": style.key, "quote_card": str(card) if card else None}


# ---------------------------------------------------------------------------
# Clips : zoom lent rendu par le code, ou clip du modèle vidéo ralenti pour tenir la durée
# ---------------------------------------------------------------------------


def _ffmpeg_writer(out: Path, size: tuple[int, int], fps: int, crf: int = 16) -> subprocess.Popen[bytes]:
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
            f"{size[0]}x{size[1]}",
            "-r",
            str(fps),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out),
        ],  # fmt: skip
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def window(t: float, move: str, base: tuple[int, int]) -> tuple[float, float, float, float]:
    """Fenêtre (x0, y0, x1, y1) découpée dans l'image agrandie `base` à l'instant t ∈ [0, 1]. « in » : de toute l'image
    au centre agrandi de 10 % ; « out » : l'inverse ; « up » / « down » : léger zoom fixe, l'image glisse lentement."""
    bw, bh = base
    t = min(1.0, max(0.0, t))
    if move in ("in", "out"):
        z = 1 + (ZOOM_MAX - 1) * (t if move == "in" else 1 - t)
        ww, wh = bw / z, bh / z
        cx, cy = bw / 2, bh / 2
    else:
        z = 1 + (ZOOM_MAX - 1) * 0.6
        ww, wh = bw / z, bh / z
        cx = bw / 2
        span = (bh - wh) / 2
        cy = bh / 2 + span * ((1 - 2 * t) if move == "up" else (2 * t - 1))
    return (cx - ww / 2, cy - wh / 2, cx + ww / 2, cy + wh / 2)


def render_still_clip(image: Path, out: Path, duration_s: float, *, move: str = "in", fps: int = FPS) -> float:
    """Clip d'une image fixe animée par un zoom (ou un glissement) très lent, image par image en Pillow (sous-pixel :
    pas les saccades du filtre zoompan), encodé par FFmpeg. Renvoie la durée du clip."""
    from PIL import Image

    src = Image.open(image).convert("RGB")
    base = cover(src, (round(W * ZOOM_MAX) + 2, round(H * ZOOM_MAX) + 2))
    n = max(2, round(duration_s * fps))
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = _ffmpeg_writer(out, (W, H), fps)
    assert proc.stdin is not None
    try:
        for i in range(n):
            box = window(i / (n - 1), move, base.size)
            frame = base.resize((W, H), Image.Resampling.BICUBIC, box=box)
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        code = proc.wait()
    if code != 0:
        raise RuntimeError(f"ffmpeg a échoué pour le zoom de la citation : {err[-400:]}")
    return round(n / fps, 3)


SLOW_MAX = 2.0  # ralenti maximal d'un clip animé (images intermédiaires calculées) ; au-delà, aller-retour


def fit_command(src: Path, out: Path, duration_s: float, native_s: float) -> list[str] | None:
    """Commande FFmpeg qui amène un clip animé à la durée de la citation : ralenti (≤ ×2, images intermédiaires
    compensées en mouvement), et aller-retour (boomerang) s'il reste trop court. None : le clip est déjà assez long."""
    if native_s <= 0 or native_s >= duration_s - 0.05:
        return None
    interp = f"minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
    if duration_s / native_s <= SLOW_MAX:
        vf = f"[0:v]setpts={duration_s / native_s:.4f}*PTS,{interp}[v]"
    else:
        slow = min(SLOW_MAX, duration_s / (2 * native_s))
        vf = f"[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0[bo];[bo]setpts={max(1.0, slow):.4f}*PTS,{interp}[v]"
    return [
        "ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", vf, "-map", "[v]", "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-t", f"{duration_s:.3f}", str(out),
    ]  # fmt: skip


# ---------------------------------------------------------------------------
# Musique : bibliothèque générée seulement (sans droits d'auteur tiers)
# ---------------------------------------------------------------------------

AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}


def music_folders(mood: str | None) -> list[str]:
    first = MUSIC_FOLDERS.get(MUSIC_MOOD_ALIASES.get(mood or "", mood or ""), "")
    return [f for f in [first, *MUSIC_FOLDERS.values()] if f]


_SHORT_TERM = re.compile(r"t:\s*([\d.]+)\s+.*?S:\s*(-?[\d.]+|-inf)")


def short_term_loudness(path: Path) -> list[tuple[float, float]]:
    """Sonie à court terme (fenêtres de 3 s, EBU R128) tous les dixièmes de seconde : (t, LUFS)."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    out = []
    for m in _SHORT_TERM.finditer(r.stderr):
        value = m.group(2)
        out.append((float(m.group(1)), -120.0 if value == "-inf" else float(value)))
    return out


def music_window(points: Sequence[tuple[float, float]], total_s: float) -> tuple[float, float] | None:
    """Départ (s) et sonie moyenne du passage de `total_s` secondes où la musique est la plus présente : une citation
    dure 6 à 13 s, une intro presque muette la laisserait sans musique. None si la piste est trop courte."""
    if not points:
        return None
    end = points[-1][0]
    best: tuple[float, float] | None = None
    start = 0.0
    while start + total_s <= end + 0.05:
        vals = [v for t, v in points if start + 3.0 <= t <= start + total_s]  # S couvre les 3 s précédentes
        if vals:
            mean = sum(vals) / len(vals)
            if best is None or mean > best[1] + 0.5:  # à 0,5 dB près, le passage le plus tôt
                best = (start, mean)
        start += 1.0
    return (round(best[0], 1), round(best[1], 1)) if best else None


def pick_track(music_dir: Path, mood: str | None, key: str) -> Path | None:
    """Une piste de la bibliothèque générée des citations (DATA_DIR/music/citation_*), stable pour une même clé :
    l'ambiance du script d'abord, puis les autres dossiers des citations ; None si aucune n'est générée."""
    seen: set[str] = set()
    for folder in music_folders(mood):
        if folder in seen:
            continue
        seen.add(folder)
        d = music_dir / folder
        if d.is_dir():
            tracks = sorted(p for p in d.iterdir() if p.suffix.lower() in AUDIO_EXT)
            if tracks:
                return tracks[int(hashlib.sha1(key.encode()).hexdigest(), 16) % len(tracks)]
    return None
