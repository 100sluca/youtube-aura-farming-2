"""Recettes de fabrication : ce qui change d'un format de Short à l'autre, de l'agent script au montage.

- story (défaut) : récit narré par Kokoro, règles du storytelling addictif (worker/storytelling.py), une image
  par scène puis image → vidéo, sous-titres.
- timelapse : chantier en accéléré (docs/15). Point de vue fixe, 8 à 12 étapes rapides. Le chantier se construit
  À REBOURS (docs/15 §10) : l'image du bâtiment FINI est générée (Z-Image), chaque étape antérieure est une
  RETOUCHE de l'étape suivante (Qwen-Image-Edit-2511 : on enlève ce qui n'est pas encore construit) ; le
  bâtiment, son échelle et le cadre restent donc identiques d'un bout à l'autre. Chaque clip va de l'image clé
  de son étape à celle de la suivante (première + dernière image, Wan 2.2 14B), puis le montage l'accélère
  (×3 à ×4, traînées des silhouettes, compteur de jours qui défile). Fin : le jour tombe, les lumières
  s'allument. Pas de voix : bruitages d'engins et d'outils, musique, titre d'accroche façon MJClipIt.
- tour : visite de maison de luxe (docs/15). La visite suit un PLAN : une pièce par scène dans l'ordre du
  parcours (arrivée, entrée, rez-de-chaussée, étage, clou), chaque image montre l'ouverture vers la pièce
  suivante (leads_to), les mêmes matériaux (design_bible) et la même vue par les fenêtres (view) ; pièces
  intérieures marquées comme telles. Mouvement de caméra stabilisée lent vers l'ouverture, passage « poussé »
  d'une pièce à la suivante, images interpolées à 30 i/s, musique élégante, ambiances, titre d'accroche.

La recette vient de la série (series.recipe, migration 0006). Le script est normalisé en code (normalize_script)
pour que la mécanique (retouches, première + dernière image, transitions, durées) ne dépende pas du LLM, puis
vérifié (lint_recipe_script) ; un script en défaut repart une fois au LLM, comme pour les récits.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from . import drama
from .hooktitle import clean_hook, lint_hook_title
from .models import ScriptScene, ScriptV1
from .numbers import script_to_digits
from .sfx import parse_tags, vocabulary_text
from .storytelling import DURATION_TOLERANCE, ON_SCREEN_WORDS_MAX, words


@dataclass(frozen=True)
class RecipeSpec:
    name: str
    narration: bool  # False : format B, ni voix ni sous-titres
    hook_title: bool
    hook_duration_s: float | None  # None : titre affiché toute la vidéo (défaut MJClipIt)
    scenes: tuple[int, int]
    scene_s: tuple[float, float]  # durée d'une scène, bornes appliquées par normalize_script
    interpolate: bool  # images intermédiaires calculées (minterpolate) : caméra fluide à 30 i/s
    music_volume: float  # ne sert plus : niveaux du modèle de montage (onglet Montage → Son, worker/music.py)
    title_y: int  # centre vertical des textes à l'écran (on_screen_text), en px sur 1920
    transition_s: dict[str, float] = field(default_factory=lambda: {"whip": 0.35, "fade": 0.6, "zoom": 0.45, "push": 0.4})
    max_speedup: float = 2.0  # accélération maximale d'un clip « première + dernière image »
    trails: bool = False  # traînées des silhouettes (images fusionnées) : la signature d'un vrai time-lapse
    counter: bool = False  # compteur de jours qui défile (« Jour 1 » → « Jour 120 »)
    title_size: int = 58  # taille des textes à l'écran (px sur 1920)
    passages: bool = False  # visite : un passage filmé relie chaque pièce à la suivante (au lieu d'une transition)
    # Variante du modèle vidéo à prendre à la place des 4 passes (« hybrid » : 2 passes avec CFG 3,5 puis la LoRA, le
    # négatif agit) et ce que le négatif doit exclure en plus pour cette recette (worker/providers/video.py)
    video_variant: str | None = None
    video_negative: str = ""


RECIPES: dict[str, RecipeSpec] = {
    # Récit : 60 à 90 s découpés phrase par phrase (worker/storycraft.py, docs/37), jusqu'à 24 scènes
    "story": RecipeSpec("story", True, False, None, (4, 24), (2.0, 8.0), False, 0.12, 330),
    "timelapse": RecipeSpec(
        "timelapse",
        False,
        True,
        None,
        (8, 14),
        (1.2, 5.0),
        False,
        0.35,
        1330,
        max_speedup=4.5,
        trails=True,
        counter=True,
        title_size=76,
        video_negative="giant person, person close to the camera, close-up of a person, face, hand in the "
        "foreground, camera, tripod",
    ),
    # Visite : en 4 passes, Wan fait entrer des passants par les portes (essais du 25/09 : bibliothèque, salle de bain) ;
    # le mélange avec négatif les supprime (même salle de bain : pièce vide), pour ≈ 2 fois plus de calcul (10 min/clip)
    "tour": RecipeSpec(
        "tour",
        False,
        True,
        None,
        (6, 10),
        (2.5, 6.0),
        True,
        0.45,
        1330,
        max_speedup=4.5,
        passages=True,
        video_variant="hybrid",
        video_negative="person, people, human, man, woman, child, figure, silhouette, someone walking, hand, "
        "face, camera, tripod, crane, gimbal",
    ),
    # Drame (worker/drama.py, docs/35) : une réplique par plan, dite par le modèle vidéo ; coupes franches
    "drama": RecipeSpec("drama", True, True, None, drama.SCENES_RANGE, drama.SCENE_S, False, 0.12, 1330),
}

# Durées d'une scène de chantier selon sa place (normalize_script) : étapes rapides, le fini, la révélation.
# Un clip première + dernière image fait 81 images (5,06 s) : à 1,2 s il est accéléré ×4,2 (≤ max_speedup).
STAGE_S, DONE_S, REVEAL_S = (1.2, 2.5), (1.5, 3.0), (3.0, 5.0)
# Visite : une pièce se montre 2,5 à 4 s (le clou 5 s), le passage vers la suivante dure 1,2 s (clip de 5 s accéléré)
ROOM_S, PASSAGE_S = (2.5, 4.0), 1.2


def spec(recipe: str | None) -> RecipeSpec:
    return RECIPES.get(recipe or "story", RECIPES["story"])


def recipe_for_production(db: Any, production_id: UUID | str) -> str:
    row = db.fetch_one(
        "select coalesce(s.recipe, 'story') as recipe from productions p left join series s on s.id = p.series_id where p.id = %s",
        (production_id,),
    )
    return row["recipe"] if row else "story"


def is_visual(recipe: str | None) -> bool:
    return recipe in ("timelapse", "tour")


def has_prompt(recipe: str | None) -> bool:
    """Recette qui a son propre scénariste (clé script_<recette>), sa normalisation et son correcteur : les formats
    visuels et le drame ; un récit narré passe par l'agent script et les règles du storytelling."""
    return recipe in SCRIPT_PROMPTS


def montage_format(recipe: str | None) -> str:
    """Format du modèle de montage (onglet Montage : récit, chantier, visite) : un drame se monte comme un récit
    (titre d'accroche, sous-titres de ses répliques, musique qui baisse sous les voix)."""
    return "story" if recipe in (None, "", "drama") else recipe


# ---------------------------------------------------------------------------
# Ordre de fabrication des images clés : une retouche part de l'image d'une autre scène
# ---------------------------------------------------------------------------


def edit_source(script: ScriptV1, pos: int) -> int | None:
    """Position (dans script.scenes) de la scène dont l'image est retouchée pour faire celle de la scène `pos` ;
    None = image générée. Sans edit_from, c'est la scène précédente (visite : variante d'une pièce)."""
    sc = script.scenes[pos]
    if not (sc.edit_prompt or "").strip():
        return None
    if sc.edit_from is None:
        return pos - 1 if pos > 0 else None
    src = next((k for k, s in enumerate(script.scenes) if s.index == sc.edit_from), None)
    return src if src is not None and src != pos else None


def keyframe_order(script: ScriptV1) -> list[int]:
    """Positions des scènes dans l'ordre où fabriquer leurs images : chaque retouche après l'image qu'elle
    retouche (chantier : le fini d'abord, puis on remonte le temps). Une boucle de retouches est une erreur."""
    order: list[int] = []
    done: set[int] = set()

    def visit(pos: int, stack: frozenset[int]) -> None:
        if pos in done:
            return
        if pos in stack:
            raise ValueError(f"retouches en boucle autour de la scène {script.scenes[pos].index}")
        src = edit_source(script, pos)
        if src is not None:
            visit(src, stack | {pos})
        done.add(pos)
        order.append(pos)

    for pos in range(len(script.scenes)):
        visit(pos, frozenset())
    return order


def edit_dependents(script: ScriptV1, indices: set[int]) -> set[int]:
    """Index des scènes à refaire quand on refait `indices` : toutes les retouches qui en dérivent, de proche en
    proche (refaire le bâtiment fini d'un chantier refait tout le chantier)."""
    out = set(indices)
    changed = True
    while changed:
        changed = False
        for pos, sc in enumerate(script.scenes):
            src = edit_source(script, pos)
            if src is not None and script.scenes[src].index in out and sc.index not in out:
                out.add(sc.index)
                changed = True
    return out


# ---------------------------------------------------------------------------
# Normalisation : la mécanique de la recette ne dépend pas du LLM
# ---------------------------------------------------------------------------

KEEP_FRAME = (
    "Keep exactly the same camera position, angle, lens and framing, the same surroundings, sky and light; "
    "only change what is described."
)
EARLIER = "Show the same place at an EARLIER stage of the construction: "
DUSK = (
    "Change the time of day to dusk: deep blue evening sky with a warm glow on the horizon, warm lights glow inside "
    "and outside the building, no worker, no machine, no tool left on site."
)


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return round(min(bounds[1], max(bounds[0], value)), 2)


def normalize_script(script: ScriptV1, recipe: str) -> ScriptV1:
    """Copie du script avec les champs imposés par la recette (retouches et leur source, modes d'animation,
    transitions, durées bornées, titre d'accroche nettoyé). Un récit (story) est rendu tel quel ; un drame suit
    drama.normalize (personnages, une réplique par plan, durées tirées des répliques)."""
    if recipe == "drama":
        return drama.normalize(script)
    if not is_visual(recipe):
        return script
    rs = spec(recipe)
    s = script.model_copy(deep=True)
    s.scenes = [sc for sc in s.scenes if not sc.passage]  # idempotent : les passages sont recalculés plus bas
    for i, sc in enumerate(s.scenes):
        sc.index = i
        sc.continues_previous = False  # les images clés assurent la continuité (docs/12 §4 ne s'applique pas)
        sc.duration_s = _clamp(sc.duration_s, rs.scene_s)
        sc.narration = {}
    if recipe == "timelapse":
        _normalize_timelapse(s)
    else:
        _normalize_tour(s, rs.passages)
    for i, sc in enumerate(s.scenes):
        sc.index = i
    s.scenes[-1].transition = "cut"
    s.hook_title = {lang: _question_mark(clean_hook(t), lang) for lang, t in s.hook_title.items() if clean_hook(t)}  # type: ignore[misc]
    return script_to_digits(s)  # « Jour quatorze » → « Jour 14 » : le compteur de jours ne lit que des chiffres


_QUESTION = {
    "fr": re.compile(
        r"^(combien|qui |quoi|pourquoi|comment|est-ce|où |quel|tu \w+rais\b|vous \w+riez\b|tu devines|"
        r"tu crois|t'as déjà|as-tu|aurais-tu|oserais-tu)",
        re.I,
    ),
    "en": re.compile(r"^(would|how|what|who|why|could|can|do|did|is|are|where|which|will)\b", re.I),
}


def _question_mark(text: str, lang: str) -> str:
    """« Tu paierais combien pour cette villa » → « … ? » : Gemini oublie parfois le point d'interrogation (25/09)."""
    rx = _QUESTION.get(lang)
    if not rx or not rx.search(text) or text.endswith(("?", "!", "…")):
        return text
    return f"{text} ?" if lang == "fr" else f"{text}?"


def _normalize_timelapse(s: ScriptV1) -> None:
    """Chantier à rebours : l'avant-dernière scène (le fini, en plein jour) est la seule image générée ; chaque
    étape antérieure retouche la suivante ; la dernière (crépuscule) retouche le fini."""
    n = len(s.scenes)
    done = n - 2
    for i, sc in enumerate(s.scenes):
        sc.transition = "cut"  # chaque clip finit sur l'image clé où commence le suivant : coupe invisible
        if i < done:
            sc.edit_from = i + 1
            sc.edit_prompt = (sc.edit_prompt or "").strip() or sc.visual_prompt
            sc.clip_mode = "flf"
            sc.duration_s = _clamp(sc.duration_s, STAGE_S)
        elif i == done:
            sc.edit_prompt, sc.edit_from, sc.clip_mode = None, None, "flf"
            sc.duration_s = _clamp(sc.duration_s, DONE_S)
        else:
            sc.edit_from = s.scenes[done].index
            sc.edit_prompt = (sc.edit_prompt or "").strip() or DUSK
            sc.clip_mode = "i2v"
            sc.duration_s = _clamp(sc.duration_s, REVEAL_S)


def _normalize_tour(s: ScriptV1, passages: bool) -> None:
    """Visite : chaque pièce est une image générée animée lentement ; entre deux pièces, un PASSAGE (inséré ici)
    part de l'image où s'arrête la pièce et finit sur l'image clé de la suivante (première + dernière image) : la
    caméra traverse l'ouverture, la visite est continue (essai du 25/09 : entrée → séjour, séjour → cuisine)."""
    n = len(s.scenes)
    for i, sc in enumerate(s.scenes):
        sc.clip_mode = "i2v"
        if sc.interior is None:  # l'arrivée et le clou sont dehors, sauf avis contraire du script
            sc.interior = 0 < i < n - 1
        if not (sc.edit_prompt or "").strip():
            sc.edit_prompt, sc.edit_from = None, None
        if i < n - 1:
            sc.duration_s = _clamp(sc.duration_s, ROOM_S)
    if n < 2:
        return
    if not passages:
        # d'une pièce à la suivante : on avance à travers l'ouverture (zoom avant flou + whoosh), sauf choix du script
        if all(sc.transition in ("cut", "whip", "push") for sc in s.scenes[:-1]):
            for sc in s.scenes[:-1]:
                sc.transition = "push"
        return
    rooms, out = list(s.scenes), []
    for i, room in enumerate(rooms):
        room.transition = "cut"
        out.append(room)
        if i + 1 < len(rooms):
            nxt = rooms[i + 1]
            lead = (room.leads_to or "").strip().rstrip(".") or "through the opening into the next room"
            out.append(
                ScriptScene(
                    index=0,
                    duration_s=PASSAGE_S,
                    passage=True,
                    continues_previous=True,
                    clip_mode="flf",
                    transition="cut",
                    visual_prompt=f"Passage from scene {i + 1} to scene {i + 2}: {lead}",
                    motion_prompt=f"smooth steady shot walking forward through the opening into the next room, {lead}",
                    interior=room.interior if room.interior is not None else nxt.interior,
                    floor=nxt.floor,
                    sfx="whoosh",
                )
            )
    # une variante d'une pièce (edit_prompt, rare) retouche la PIÈCE précédente, pas le passage qui les sépare
    last_room: int | None = None
    for k, sc in enumerate(out):
        sc.index = k
        if sc.passage:
            continue
        if sc.edit_prompt:
            sc.edit_from = last_room
            if last_room is None:
                sc.edit_prompt = None
        last_room = k
    s.scenes = out


def lint_recipe_script(script: ScriptV1, recipe: str, langs: Sequence[str], target_duration_s: float | None = None) -> list[str]:
    """Problèmes mesurables d'un script de recette visuelle ou d'un drame (après normalize_script) ; liste vide =
    conforme."""
    if recipe == "drama":
        return drama.lint(script, langs, target_duration_s)
    rs = spec(recipe)
    issues: list[str] = []
    total_s = script.duration_s  # passages compris : c'est la durée de la vidéo
    if any(sc.passage for sc in script.scenes):  # le reste se vérifie sur les scènes écrites par le LLM (les pièces)
        script = script.model_copy(update={"scenes": [sc for sc in script.scenes if not sc.passage]})
    n = len(script.scenes)
    if not rs.scenes[0] <= n <= rs.scenes[1]:
        issues.append(f"{n} scènes : {rs.scenes[0]} à {rs.scenes[1]} pour ce format")
    for lang in langs:
        issues += lint_hook_title(script.hook_title.get(lang, ""), lang)  # type: ignore[call-overload]
    if not (script.design_bible or "").strip():
        issues.append("design_bible manquant : décrire le lieu en une phrase (anglais), répétée dans chaque image")
    raw = {t.strip() for sc in script.scenes for t in (sc.sfx or "").replace(";", ",").split(",") if t.strip()}
    unknown = sorted(t for t in raw if not parse_tags(t))  # alias compris (« digger » = excavator)
    known = [sc for sc in script.scenes if parse_tags(sc.sfx)]
    if unknown and len(unknown) > len(known):
        issues.append(f"bruitages inconnus {unknown} : utiliser les étiquettes de la liste fournie")
    if len(known) < (n + 1) // 2:
        issues.append(f"bruitages sur {len(known)} scènes sur {n} : au moins une étiquette sfx pour la moitié des scènes")
    for i, sc in enumerate(script.scenes):
        tag = f"scène {i + 1}"
        if not (sc.motion_prompt or "").strip():
            issues.append(f"{tag} : motion_prompt manquant (le mouvement pendant la scène)")
        for lang in langs:
            ost = sc.on_screen_text.get(lang, "").strip()  # type: ignore[call-overload]
            if ost and len(words(ost)) > ON_SCREEN_WORDS_MAX + 1:
                issues.append(f"[{lang}] {tag} : texte à l'écran de {len(words(ost))} mots, {ON_SCREEN_WORDS_MAX + 1} au plus")
    if recipe == "timelapse":
        issues += _lint_timelapse(script, langs)
    elif recipe == "tour":
        issues += _lint_tour(script)
    if target_duration_s and abs(total_s - target_duration_s) > DURATION_TOLERANCE * target_duration_s:
        issues.append(f"durée {total_s:g} s, cible {target_duration_s:g} s (± {int(DURATION_TOLERANCE * 100)} %)")
    return issues


_REMOVAL = re.compile(r"\b(remove|removed|take away|without|strip|clear|bare|empty|earlier|before|not yet|replace)\b", re.I)
# L'état initial d'un chantier : ce qu'on s'attend à lire dans la scène 1 (Gemini y a mis deux fois le résultat fini)
_INITIAL = re.compile(
    r"\b(abandon\w*|ruin\w*|overgrown|derelict|bare|empty|untouched|wild|vacant|collaps\w*|dilapidated|old|rusty|"
    r"weeds?|rubble|raw|virgin|neglected|decay\w*|crumbl\w*|disused|flooded|muddy|barren|unbuilt|plot|wasteland)\b",
    re.I,
)


def _overlap(a: str, b: str, ignore: str = "") -> float:
    """Part des mots (≥ 4 lettres) de `a` qu'on retrouve dans `b`, sans compter ceux de `ignore` (le paysage)."""
    skip = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", ignore)}
    wa = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", a)} - skip
    wb = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", b)} - skip
    return len(wa & wb) / len(wa) if wa else 0.0


def _lint_timelapse(script: ScriptV1, langs: Sequence[str]) -> list[str]:
    issues: list[str] = []
    n = len(script.scenes)
    if n < 3:
        return issues
    done = script.scenes[n - 2]
    if len(words(done.visual_prompt)) < 25:
        issues.append(
            f"scène {n - 1} (le résultat fini, seule image générée) : visual_prompt trop court, décrire le "
            "bâtiment terminé en détail (matériaux, portes, fenêtres, garde-corps) et le paysage"
        )
    first = script.scenes[0].visual_prompt
    if not _INITIAL.search(first) or _overlap(first, done.visual_prompt, script.design_bible or "") > 0.8:
        issues.append(
            "scène 1 : c'est l'ÉTAT INITIAL, avant tout travaux (ruine, terrain nu, lieu abandonné ou "
            "vierge), jamais le résultat ; l'ordre des scènes est chronologique"
        )
    forward = [i + 1 for i, sc in enumerate(script.scenes[: n - 2]) if not _REMOVAL.search(sc.edit_prompt or "")]
    if len(forward) > (n - 2) // 2:
        issues.append(
            f"scènes {forward} : edit_prompt doit ENLEVER ce qui n'est pas encore construit (« Remove the "
            "roof and the windows… ») : l'image d'une étape est une retouche de l'étape SUIVANTE"
        )
    for lang in langs:
        days = [_day(sc.on_screen_text.get(lang, "")) for sc in script.scenes[: n - 1]]  # type: ignore[call-overload]
        got = [d for d in days if d is not None]
        if len(got) < (n - 1) // 2:
            issues.append(f"[{lang}] compteur de jours manquant : on_screen_text « Jour 1 », « Jour 14 »… sur chaque étape")
        elif any(b < a for a, b in zip(got, got[1:], strict=False)):
            issues.append(f"[{lang}] compteur de jours qui recule : {got}")
    return issues


def _lint_tour(script: ScriptV1) -> list[str]:
    issues: list[str] = []
    if not (script.view or "").strip():
        issues.append("view manquant : le paysage vu par toutes les fenêtres, en une phrase (anglais), le même partout")
    missing = [i + 1 for i, sc in enumerate(script.scenes[:-1]) if not (sc.leads_to or "").strip()]
    if len(missing) > 1:
        issues.append(f"scènes {missing} : leads_to manquant (l'ouverture visible vers la pièce suivante du parcours)")
    floors = [(i, sc.floor) for i, sc in enumerate(script.scenes) if sc.floor is not None]
    inside = [(i, f) for i, f in floors if script.scenes[i].interior]
    back = [inside[k + 1][0] + 1 for k in range(len(inside) - 1) if inside[k + 1][1] < inside[k][1]]  # type: ignore[operator]
    if back:
        issues.append(f"scènes {back} : la visite redescend d'un niveau ; parcourir un niveau entier avant de monter")
    return issues


_DAY = re.compile(r"(\d{1,4})")


def _day(text: str) -> int | None:
    m = _DAY.search(text or "")
    return int(m.group(1)) if m else None


def day_counter(
    script: ScriptV1, lang: str, starts: Sequence[float], durations: Sequence[float], per_s: float = 10.0
) -> list[tuple[float, float, str]]:
    """Compteur de jours d'un chantier (« Jour 1 » → « Jour 120 ») : pendant chaque étape, le nombre défile de
    son jour à celui de l'étape suivante (au plus `per_s` changements par seconde) ; la fin reste sur le dernier
    jour. Vide si le script n'a pas de compteur (moins de la moitié des étapes numérotées)."""
    texts = [sc.on_screen_text.get(lang, "").strip() for sc in script.scenes]  # type: ignore[call-overload]
    days = [_day(t) for t in texts]
    if sum(d is not None for d in days) < max(2, len(days) // 2):
        return []
    pattern = next(_DAY.sub("{n}", t, count=1) for t, d in zip(texts, days, strict=True) if d is not None)
    filled: list[int] = []
    for d in days:  # étape sans jour : garde le précédent ; le compteur ne recule jamais
        filled.append(max(d if d is not None else (filled[-1] if filled else 1), filled[-1] if filled else 0))
    out: list[tuple[float, float, str]] = []
    for i, (start, dur) in enumerate(zip(starts, durations, strict=True)):
        a, b = filled[i], filled[i + 1] if i + 1 < len(filled) else filled[i]
        steps = max(1, min(abs(b - a), int(dur * per_s)))
        for k in range(steps):
            t0, t1 = start + dur * k / steps, start + dur * (k + 1) / steps
            value = a + round((b - a) * k / steps)
            if out and out[-1][2] == pattern.format(n=value) and abs(out[-1][1] - t0) < 1e-6:
                out[-1] = (out[-1][0], round(t1, 3), out[-1][2])
            else:
                out.append((round(t0, 3), round(t1, 3), pattern.format(n=value)))
    return out


# ---------------------------------------------------------------------------
# Prompts des agents
# ---------------------------------------------------------------------------

HOOK_RULES = """TITRE D'ACCROCHE (hook_title, une entrée par langue) : gravé en haut de l'écran pendant toute la
vidéo, comme sur TikTok ; c'est lui qui retient le pouce dans la première seconde. 3 à 8 mots, écrit comme on
parle (tutoiement en français), qui déclenche la curiosité, la surprise ou l'envie ; il promet sans tout dire.
Jamais descriptif plat, jamais de point final, de guillemets, de hashtag, d'émoji ni de MAJUSCULES criardes.
Varier les formes : question, affirmation choc, « POV : » (au plus une fois sur trois), chiffre, défi.
Histoires vraies : il dit vrai, sans contresens ni exagération fausse, et il pose l'enjeu de l'histoire plutôt
qu'un détail (« 1 200 ans pour relier 2 fleuves », pas « un chantier secret » s'il n'y a pas de secret).
Nombres et années toujours en chiffres, jamais en toutes lettres (« 852 morts en pleine mer », « En 1994 »).
Format JSON : "hook_title": {"fr": "…", "en": "…"} (une entrée par langue demandée), comme on_screen_text.
La bible du lieu (design_bible) est ajoutée automatiquement à chaque image : ne la recopie pas dans les visual_prompt."""

IDEA_GUIDES = {
    "timelapse": """FORMAT : chantier en accéléré (time-lapse), sans voix off : un lieu vu d'un point fixe passe
d'un état saisissant (abandonné, envahi par la végétation, en ruine, terrain vague, falaise nue) à un résultat
spectaculaire, en 8 à 12 étapes rapides. Chaque concept : le lieu et son état initial (premise), le résultat
final précis (ce qui est construit, ses matériaux), les étapes visibles du chantier dans l'ordre (visual_beats :
nettoyage, démolition, terrassement, structure, toiture et façades, finitions, révélation au crépuscule), et
l'accroche (hook) = un titre d'accroche de 3 à 8 mots, parlé, qui donne envie de voir la fin. Lieux variés et
universels : maison abandonnée, grange, piscine, stade, cabane dans une falaise, bunker, container, jardin,
rooftop, château en ruine, tiny house, sous-sol, garage, ponton… Un bâtiment à l'échelle humaine lisible
(portes, fenêtres, escaliers), entièrement visible depuis le point de vue.""",
    "tour": """FORMAT : visite de maison ou d'appartement de luxe imaginaire (générée par IA), sans voix off : la
caméra suit un PARCOURS logique dans une seule maison, comme dans la vidéo d'un agent immobilier haut de gamme :
arrivée devant la maison, entrée, pièces du rez-de-chaussée, escalier, étage, jusqu'au clou. Chaque concept : une
propriété d'exception (lieu, style architectural, matériaux, lumière, vue), 6 à 9 pièces dans l'ordre de la
visite (visual_beats : arrivée, entrée, séjour, cuisine, suite, salle de bain, pièce surprise, clou final :
piscine, terrasse, rooftop…), le détail qui fait parler (pièce secrète, vue folle, prix), et l'accroche (hook) =
un titre d'accroche de 3 à 8 mots, parlé (« Tu paierais combien pour cette villa ? »). Styles et lieux variés :
villa méditerranéenne, chalet, penthouse parisien, maison de falaise, désert, tropiques, japonais minimaliste…""",
}

SCRIPT_PROMPTS = {
    "timelapse": """Tu écris le script d'UN YouTube Short « chantier en accéléré » (time-lapse de construction ou de
rénovation), 9:16, 20 à 30 s, SANS voix off : bruitages, musique, un titre d'accroche et un compteur de jours. Un
seul lieu, vu d'un point FIXE (même position, même objectif, même cadrage du début à la fin), passe d'un état
saisissant à un résultat spectaculaire en 8 à 12 étapes rapides (1,5 s chacune à l'écran).

ORDRE DES SCÈNES : CHRONOLOGIQUE, comme le spectateur les voit (N scènes en tout, 10 à 14) :
- scène 1 : l'ÉTAT INITIAL, avant tout travaux (ruine envahie, terrain nu, falaise vierge, bâtiment abandonné) ;
- scènes 2 à N-2 : les étapes du chantier, de la plus ancienne à la plus récente ;
- scène N-1 : le RÉSULTAT FINI, en plein jour ;
- scène N : la révélation, le même résultat au crépuscule, lumières allumées.
FABRICATION (pour écrire edit_prompt) : le code génère d'abord l'image de la scène N-1 (le résultat fini), puis
obtient chaque étape antérieure en RETOUCHANT l'image de l'étape qui la SUIT : N-2 depuis N-1, N-3 depuis N-2…
jusqu'à la scène 1. On remonte le temps en enlevant ce qui n'est pas encore construit : c'est ce qui garde le même
bâtiment, la même échelle et le même cadre du début à la fin.
Chaque scène :
- visual_prompt, en anglais : ce que montre l'image de CETTE étape (scène 1 : le lieu avant travaux, jamais le
  résultat). Scène N-1 : c'est l'image générée, décris le résultat terminé EN DÉTAIL (forme, matériaux, portes,
  fenêtres, garde-corps, escaliers : ce qui donne l'échelle humaine), ENTIER et au centre de l'image avec de
  l'espace autour, et le paysage ; personne. Jamais les mots « camera », « tripod » ni « time-lapse » ;
- edit_prompt, en anglais, scènes 1 à N-2 : la RETOUCHE qui transforme l'image de l'étape SUIVANTE (plus avancée)
  en celle de cette scène : ce qu'il faut ENLEVER (pas encore construit) et ce qu'il faut ajouter à ce moment
  (échafaudages, bâches, matériaux empilés, engins, ouvriers en gilet orange et casque blanc) ; scène 1 : enlever
  tout le chantier pour retrouver le lieu intact ; scène N-1 : aucun edit_prompt ; scène N : « Change the time of
  day to dusk, warm lights on inside… ». Exemple pour une grange (extrait) :
  scène 1 : visual_prompt « An overgrown ruined stone barn with a collapsed roof in a wheat field »,
            edit_prompt « Remove the excavator and the workers; cover the ground again with tall weeds, brambles
            and fallen roof timbers: the untouched ruined barn »
  scène 2 : visual_prompt « The barn cleared of vegetation, an excavator levelling the ground »,
            edit_prompt « Remove the new concrete slab and the formwork: bare levelled soil, one excavator and two
            workers »
  scène N-1 : visual_prompt « A contemporary glass and dark-timber house on the old stone base of the barn… »,
            pas d'edit_prompt ;
- motion_prompt, en anglais : ce qui se construit pendant le passage à l'étape suivante (« steel beams are lifted
  and bolted into the rock ») ; le style time-lapse (ouvriers minuscules et rapides, nuages qui filent) est
  ajouté par le code ; scène N : un mouvement de caméra lent (« slow push-in toward the glowing cabin ») ;
- sfx : 1 à 2 étiquettes de la liste (engins et outils de l'étape ; ambiance pour la fin) ;
- on_screen_text FR et EN : le compteur « Jour 1 », « Jour 14 »… croissant, du premier au dernier jour du
  chantier (il défile à l'écran) ; la révélation garde le dernier jour ;
- duration_s : 1.5 par étape (1.2 à 2.5), 2 pour la scène N-1, 4 pour la révélation.
Progression type : lieu intact → préparation (débroussaillage, démolition, piquetage) → terrassement et
fondations → structure (béton, acier ou bois) → charpente et toiture → murs, bardage, vitrages → finitions
extérieures (terrasse, garde-corps, allée, jardin, piscine) → fini → crépuscule. Chaque étape change UNE chose bien
visible par rapport à la suivante (un étage entier d'écart, et la retouche échoue) ; le paysage, le ciel et le point
de vue ne changent pas. Les ouvriers sont petits, à l'échelle du bâtiment ; personne ne pose ni ne regarde l'objectif.
design_bible, en anglais : ce qui NE CHANGE PAS, en une phrase : le paysage et le point de vue (« a sheer granite
sea cliff seen from the opposite side of a narrow cove, the open sea behind ») ; jamais le résultat.
music_mood : prise dans la liste MUSIQUE DE FOND. loop_note : comment la fin renvoie au début. metadata : par langue,
titre YouTube ≤ 60 caractères (différent du hook_title, un émoji permis), description, 10 tags ; affiné par
l'agent SEO. Réponds uniquement en JSON conforme à ScriptV1.""",
    "tour": """Tu écris le script d'UN YouTube Short « visite de maison de luxe », 9:16, 25 à 35 s, SANS voix off :
musique élégante, bruitages d'ambiance, titre d'accroche. Une propriété d'exception imaginaire, visitée comme
dans la vidéo d'un vidéaste immobilier : caméra stabilisée (gimbal) qui glisse lentement, une pièce par scène.
La maison est vide : personne à l'image.

LE PLAN D'ABORD : imagine la maison (ses niveaux, l'enchaînement de ses pièces), puis fais-la parcourir dans
l'ordre, sans jamais revenir en arrière : on arrive devant, on entre, on traverse le rez-de-chaussée, on monte,
on finit sur le clou (terrasse, piscine, rooftop, vue). Chaque pièce donne sur la suivante : on doit comprendre
qu'on est dans la même maison et comment les pièces s'enchaînent.
- design_bible, en anglais : les MATÉRIAUX et la lumière de toute la maison, précis, en liste (murs, sols,
  plafonds, pierre, métal, bois, textiles, cadres des fenêtres, éclairage) ; répétés mot pour mot dans chaque
  image ;
- view, en anglais : le paysage vu par TOUTES les fenêtres (« a single snow-covered pyramid-shaped peak above a
  larch forest », « the turquoise bay with one rocky islet ») : le même dans chaque pièce ;
Chaque scène = une pièce du parcours :
- visual_prompt, en anglais : la pièce vue depuis l'endroit où l'on entre (type de pièce, mobilier, détail fort,
  grand angle, à hauteur d'œil) ; jamais de personnes ;
- interior : true pour une pièce intérieure (murs et plafond visibles), false pour l'arrivée devant la maison et
  un extérieur (terrasse, jardin, piscine extérieure) ; une bibliothèque, une cave, un spa, un cinéma, une pièce
  secrète sont des pièces INTÉRIEURES ;
- floor : 0 rez-de-chaussée, 1 étage, -1 sous-sol ; on visite un niveau entier avant de changer de niveau ;
- leads_to, en anglais : l'ouverture VISIBLE dans l'image qui mène à la pièce suivante (« at the far end, a wide
  opening reveals the living room and its huge window », « on the right, an oak staircase climbs to the upper
  floor ») ; vide pour la dernière scène ;
- motion_prompt, en anglais : UN mouvement de caméra lent qui avance vers cette ouverture (« smooth steady shot
  gliding forward toward the opening at the far end », « slow lateral tracking move along the island toward the
  staircase », « the view rises slowly above the pool ») ; rien d'autre ne bouge que la lumière, l'eau, les
  flammes, les rideaux ; ne parle jamais de personnes dans le mouvement (même pour dire « personne ») ni d'appareil
  de tournage (crane, gimbal, drone, dolly, tripod) : le modèle vidéo les ferait apparaître ;
- transition : laisser vide (le passage d'une pièce à l'autre est imposé par le montage) ;
- sfx : 1 à 2 étiquettes d'ambiance de la liste (birds, pool_water, fireplace, ocean, footsteps_stone…) ;
- on_screen_text FR et EN, optionnel : nom de la pièce et un chiffre (« Suite parentale · 60 m² ») ; la
  dernière scène peut révéler un prix, toujours comme une estimation fictive (« Estimée à 14,5 M€ ») si le titre
  d'accroche pose la question ; jamais d'adresse, d'agence ni de « à vendre » : ce n'est pas une annonce ;
- edit_prompt : vide (chaque pièce est une image générée) ;
- duration_s : 3 à 4 s, 5 s pour le clou final.
music_mood : prise dans la liste MUSIQUE DE FOND. loop_note : comment la fin renvoie au début. metadata : par langue,
titre YouTube ≤ 60 caractères (différent du hook_title, un émoji permis), description, 10 tags ; affiné par
l'agent SEO. Réponds uniquement en JSON conforme à ScriptV1.""",
}

# Drame (worker/drama.py, docs/35) : son scénariste et son guide d'idées, modifiables dans l'onglet Agents (clés
# script_drama et guide_drama)
SCRIPT_PROMPTS["drama"] = drama.SCRIPT_PROMPT
IDEA_GUIDES["drama"] = drama.IDEA_GUIDE


def script_context(recipe: str, hook_rules: str = HOOK_RULES) -> str:
    """Parties du message utilisateur propres à la recette : titre d'accroche (`hook_rules` : la version active de la
    consigne rules_hook_title, worker/prompts.py) et vocabulaire des bruitages (formats visuels : un drame n'en a pas,
    le son vient des clips)."""
    if recipe == "drama":
        return hook_rules
    return f"{hook_rules}\n\nBRUITAGES DISPONIBLES (champ sfx, étiquettes séparées par des virgules) :\n{vocabulary_text()}"


# ---------------------------------------------------------------------------
# Prompts d'image : ce que la recette ajoute au prompt du script
# ---------------------------------------------------------------------------


_CAMERA_WORDS = re.compile(r"[^,.;]*\b(tripod|camera|time-?lapse)\b[^,.;]*[,.;]?", re.I)


def _no_camera(text: str) -> str:
    """Retire d'un prompt d'image les membres de phrase qui parlent de caméra ou de trépied : un modèle d'image les
    dessine (trépied planté dans la falaise, essai du 25/09). Ils restent dans les prompts de mouvement."""
    return re.sub(r"\s{2,}", " ", _CAMERA_WORDS.sub("", text)).strip(" ,;")


# Chantier : le résultat fini est la seule image générée, il fixe le cadre et l'échelle de toutes les étapes
# (essai du 25/09 : bâtiment coupé par le bord de l'image, aucune porte ni fenêtre → Wan a fait un ouvrier géant).
FINISHED_FRAMING = (
    "the whole construction is fully visible in the middle of the frame with open space around it, realistic human "
    "scale with doors, windows and railings, nobody"
)
WORKER_SCALE = "Workers are small, at the true scale of the building, never close to the viewer."
_WORKERS = re.compile(r"\b(workers?|crew|builders?|people|men|climbers?|labou?rers?|masons?|carpenters?)\b", re.I)


def image_prompt(script: ScriptV1, index: int, recipe: str) -> str:
    """Prompt de l'image clé générée : la scène + la bible du lieu (même maison, même chantier). Drame : la scène et ses
    personnages décrits en entier (le storyboard préfère leurs fiches en références, drama.scene_prompt)."""
    if recipe == "drama":
        return drama.scene_prompt(script, index)
    sc = script.scenes[index]
    bible = _no_camera((script.design_bible or "").strip())
    prompt = _no_camera(sc.visual_prompt.strip()).rstrip(".")
    if bible and bible[:40].lower() in prompt.lower():  # le LLM l'a déjà recopiée : pas deux fois
        bible = ""
    if recipe == "tour":
        return _tour_prompt(script, sc, prompt, bible)
    extra = ""
    if recipe == "timelapse":  # jamais « tripod » ni « camera » dans une image : le modèle les dessine
        extra = f", {FINISHED_FRAMING}, static wide shot, vertical framing"
    return f"{prompt}{extra}" + (f". {bible}" if bible else "")


def _tour_prompt(script: ScriptV1, sc: Any, prompt: str, bible: str) -> str:
    """Une pièce de la visite : intérieur ou extérieur dit en premier (essai du 25/09 : la « pièce secrète » est
    sortie en façade de chalet), l'ouverture vers la pièce suivante, les matériaux et la vue de toute la maison."""
    inside = sc.interior is not False
    parts = [
        (
            "Interior photograph taken inside the house, walls and ceiling visible: "
            if inside
            else "Exterior photograph of the house: "
        )
        + prompt
    ]
    if (sc.leads_to or "").strip():
        lead = _no_camera(sc.leads_to.strip()).rstrip(".")
        parts.append(lead[:1].upper() + lead[1:])
    if bible:
        parts.append(f"Materials of the whole house: {bible.rstrip('.')}")
    view = _no_camera((script.view or "").strip()).rstrip(".")
    if view:
        parts.append(f"Seen through the windows: {view}" if inside else f"Surroundings: {view}")
    return ". ".join(parts) + ", empty, nobody, no people"


def edit_instruction(script: ScriptV1, index: int, recipe: str) -> str:
    """Instruction de retouche d'une image clé (depuis l'image de sa scène source, edit_source)."""
    sc = script.scenes[index]
    bible = (script.design_bible or "").strip()
    text = (sc.edit_prompt or sc.visual_prompt).strip()
    if recipe == "timelapse":
        src = edit_source(script, index)
        backwards = src is not None and src > index  # on remonte le temps
        if backwards and not text.lower().startswith("show"):
            text = EARLIER + text
        target = _no_camera(sc.visual_prompt.strip()).rstrip(".")
        if backwards and len(words(target)) >= 5 and target[:30].lower() not in text.lower():
            text = f"{text.rstrip('.')}. The result shows: {target}."  # la cible, en plus de ce qu'il faut enlever
        if _WORKERS.search(text):
            text = f"{text.rstrip('.')}. {WORKER_SCALE}"
        return f"{text} {KEEP_FRAME}"
    return f"{text} Same house and same style: {bible}" if bible else text


# Visite : Wan en 4 passes ignore le négatif et fait entrer des passants (essais du 25/09). Nommer les personnes dans
# le prompt positif, même pour les exclure (« nobody », « no person »), les suggère : on décrit seulement une scène
# figée où seule la caméra bouge, et l'on retire du prompt de mouvement toute mention de personnes.
EMPTY_HOUSE = "static scene, everything stays exactly as in the first frame, only the camera moves slowly and smoothly"
WALK_THROUGH = "the rooms stay still, only the camera moves forward smoothly from one room into the next"  # passage
_PEOPLE = re.compile(r",?\s*\b(empty (house|room)s?|nobody|no (one|people|person)|without (people|anyone))\b[^,.;]*", re.I)
# Chantier : ce qui fait « accéléré » (ouvriers minuscules et rapides, nuages qui filent, ombres qui tournent)
TIMELAPSE_MOTION = (
    "fast construction time-lapse, fixed camera, tiny workers bustle quickly around the structure, clouds race "
    "across the sky, shadows sweep quickly"
)
DUSK_MOTION = (
    "time-lapse, fixed camera, the sun sets quickly, the sky turns deep blue, warm lights turn on inside the building, "
    "clouds race across the sky"
)


# Vocabulaire de tournage que Wan dessine au lieu de l'exécuter (essai du chalet, 25/09 soir) : « slow crane up » a
# fait descendre une grue de chantier au-dessus du jacuzzi, « gimbal move » a planté un pied de stabilisateur dans la
# salle de bain. On garde le mouvement, sans nommer l'appareil.
_RIG_WORDS = (
    (re.compile(r"\bcrane(?:[- ]shot)?\s+up\b|\bcrane[- ]shot\b|\bcrane\b", re.I), "rising view"),
    (re.compile(r"\b(?:gimbal|steadicam|tripod|slider)\b", re.I), "steady"),
    (re.compile(r"\bdolly\b", re.I), "tracking"),
    (re.compile(r"\bdrone\b", re.I), "aerial"),
)


def _no_rig(text: str) -> str:
    for rx, repl in _RIG_WORDS:
        text = rx.sub(repl, text)
    return re.sub(r"\bsteady\s+steady\b", "steady", text)


def motion_prompt(script: ScriptV1, index: int, recipe: str) -> str:
    sc = script.scenes[index]
    text = (sc.motion_prompt or sc.visual_prompt).strip().rstrip(".")
    if recipe == "tour":
        text = _no_rig(_PEOPLE.sub("", text).strip(" ,;"))
        return f"{text}, {WALK_THROUGH if sc.passage else EMPTY_HOUSE}"
    if recipe == "timelapse":
        n = len(script.scenes)
        if index == n - 2 and sc.clip_mode == "flf":  # le fini → le crépuscule
            return DUSK_MOTION
        if sc.clip_mode == "flf":  # une grue de chantier est ici voulue : pas de _no_rig
            return f"{TIMELAPSE_MOTION}, {text}"
        return f"{_no_rig(_PEOPLE.sub('', text).strip(' ,;'))}, {EMPTY_HOUSE}"  # révélation : seule la caméra bouge
    return text
