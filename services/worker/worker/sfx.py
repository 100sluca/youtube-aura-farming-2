"""Bruitages : vocabulaire d'étiquettes, bibliothèque locale, placement sur la timeline.

Le script choisit pour chaque scène 1 à 3 étiquettes (ScriptScene.sfx, « excavator, birds ») dans TAGS ;
le montage place les fichiers correspondants sous l'image :
- un « fond » (bed : engin, outil qui travaille, ambiance) couvre toute la scène, bouclé, avec fondus ;
- un « coup » (hit : whoosh, impact, porte) part au début de la scène ;
- chaque transition « whip » reçoit un whoosh centré sur le passage d'une pièce à l'autre ; la dernière
  scène d'une révélation peut recevoir un « shimmer ».

Bibliothèque : DATA_DIR/sfx/<étiquette>/*.wav|flac|mp3|ogg — des sons libres (CC0) déposés à la main, ou
générés une fois pour toutes par `yt2 sfx generate` (Stable Audio Open dans ComfyUI, prompts de TAGS). Un
même son est réutilisé d'une vidéo à l'autre : choix stable par vidéo (hash), comme pick_music.
Fonctions pures (plan_cues) testables sans audio.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .media import AUDIO_EXT


@dataclass(frozen=True)
class SfxTag:
    kind: str  # bed (couvre la scène, bouclé) | hit (ponctuel)
    volume: float  # gain avant normalisation finale (la musique vise −20 LUFS en format B : worker/music.py)
    prompt: str  # prompt de génération (anglais, Stable Audio Open)
    seconds: float  # durée générée
    label: str  # description courte pour l'agent script


def _bed(prompt: str, label: str, volume: float = 0.55, seconds: float = 12.0) -> SfxTag:
    return SfxTag("bed", volume, prompt, seconds, label)


def _hit(prompt: str, label: str, volume: float = 0.8, seconds: float = 3.0) -> SfxTag:
    return SfxTag("hit", volume, prompt, seconds, label)


TAGS: dict[str, SfxTag] = {
    # Chantier : engins et outils (fonds bouclés)
    "excavator": _bed(
        "heavy excavator engine rumbling and hydraulic arm digging soil, construction site, field recording", "pelleteuse"
    ),
    "bulldozer": _bed("bulldozer diesel engine pushing earth and rocks, tracks clanking, construction site", "bulldozer"),
    "chainsaw": _bed("chainsaw cutting branches in overgrown garden, bursts of revving, outdoor", "tronçonneuse"),
    "lawn_mower": _bed("petrol lawn mower and brush cutter clearing tall grass, outdoor", "débroussailleuse"),
    "hammer": _bed("several workers hammering nails into wooden beams, construction site, irregular hits", "marteaux"),
    "drill": _bed("cordless drill and impact driver screwing into wood and concrete, workshop, bursts", "perceuse, visseuse"),
    "saw": _bed("circular saw cutting wooden planks, bursts with pauses, construction site", "scie circulaire"),
    "grinder": _bed("angle grinder cutting metal, sparks, bursts, workshop", "meuleuse"),
    "jackhammer": _bed("jackhammer breaking concrete, demolition, bursts, outdoor", "marteau-piqueur"),
    "concrete_mixer": _bed("concrete mixer truck drum rotating and pouring wet concrete, construction site", "toupie à béton"),
    "scaffolding": _bed("metal scaffolding poles clanking, workers assembling scaffolding, outdoor", "échafaudage"),
    "debris": _bed("demolition debris, bricks and rubble falling into a skip, shovels scraping", "gravats"),
    "shovel": _bed("shovels digging and scraping gravel, wheelbarrow rolling, outdoor", "pelles, brouette"),
    "crane": _bed("tower crane motor whirring, steel cables, distant construction site ambience", "grue"),
    "truck": _bed("heavy truck engine idling and driving on gravel, construction site", "camion"),
    "sanding": _bed("electric orbital sander on wood, steady, interior", "ponceuse"),
    "paint_roller": _bed("paint roller rolling on a wall, soft wet sound, interior", "rouleau de peinture", 0.45),
    "tiles": _bed("ceramic tiles being laid and tapped with a rubber mallet, trowel scraping mortar", "carrelage"),
    "nail_gun": _bed("pneumatic nail gun firing into wood, compressor, construction site", "cloueuse"),
    "power_washer": _bed("pressure washer spraying water on stone and concrete, outdoor", "nettoyeur haute pression"),
    "welding": _bed("arc welding crackling and buzzing, workshop", "soudure"),
    "workers": _bed("construction workers busy, tools, distant voices unintelligible, site ambience", "ouvriers au travail", 0.4),
    # Ambiances (fonds)
    "birds": _bed("birds chirping in a quiet garden, morning, gentle breeze", "oiseaux", 0.4, 20.0),
    "wind": _bed("soft wind blowing outdoors, open landscape", "vent", 0.35, 20.0),
    "rain": _bed("steady rain falling on a roof and garden", "pluie", 0.4, 20.0),
    "night": _bed("night ambience, crickets and cicadas, calm", "nuit, grillons", 0.35, 20.0),
    "forest": _bed("forest ambience, leaves rustling, distant birds", "forêt", 0.35, 20.0),
    "ocean": _bed("gentle ocean waves on the shore, seaside", "mer, vagues", 0.4, 20.0),
    "river": _bed("small river stream flowing over rocks", "rivière", 0.35, 20.0),
    "city": _bed("distant city traffic ambience seen from a high floor, muffled", "ville au loin", 0.3, 20.0),
    "room_tone": _bed("quiet luxury interior room tone, very soft air", "silence d'intérieur", 0.25, 20.0),
    "fireplace": _bed("wood fire crackling in a fireplace, cozy interior", "cheminée", 0.4, 20.0),
    "pool_water": _bed("swimming pool water gently lapping, infinity pool overflow trickling", "piscine", 0.4, 20.0),
    "fountain": _bed("small garden fountain water trickling", "fontaine", 0.35, 20.0),
    "wind_chimes": _bed("soft wind chimes in a gentle breeze", "carillon", 0.3, 20.0),
    "footsteps_wood": _bed("slow footsteps on a wooden floor, interior, one person", "pas sur parquet", 0.35, 8.0),
    "footsteps_stone": _bed("slow footsteps on stone tiles, interior, one person", "pas sur pierre", 0.35, 8.0),
    # Coups
    "whoosh": _hit("fast cinematic whoosh swipe transition, airy, short", "whoosh (transition)", 0.7, 1.5),
    "impact": _hit("deep cinematic impact boom with short tail", "impact", 0.7, 3.0),
    "riser": _hit("cinematic tension riser building up then stopping", "montée de tension", 0.5, 4.0),
    "shimmer": _hit("magical sparkle shimmer, bright chimes, reveal", "scintillement (révélation)", 0.5, 3.0),
    "door_open": _hit("heavy wooden front door opening slowly, creak and latch", "porte qui s'ouvre", 0.7, 3.0),
    "light_switch": _hit("light switch click and lights humming on", "lumières qui s'allument", 0.6, 2.0),
    "curtains": _hit("motorized curtains sliding open", "rideaux qui s'ouvrent", 0.6, 4.0),
    "glass_clink": _hit("two champagne glasses clinking", "verres", 0.6, 2.0),
    "splash": _hit("person diving into a swimming pool, big splash", "plongeon", 0.6, 3.0),
}
ALIASES = {
    "digger": "excavator",
    "mower": "lawn_mower",
    "brush_cutter": "lawn_mower",
    "hammering": "hammer",
    "saw_cut": "saw",
    "circular_saw": "saw",
    "mixer": "concrete_mixer",
    "concrete": "concrete_mixer",
    "footsteps": "footsteps_stone",
    "water": "pool_water",
    "waves": "ocean",
    "crickets": "night",
    "door": "door_open",
    "boom": "impact",
    "sparkle": "shimmer",
    "swoosh": "whoosh",
    "transition": "whoosh",
}
TRANSITION_TAG = "whoosh"
WHOOSH_TRANSITIONS = frozenset({"whip", "push"})  # passages qui « déplacent » la caméra : un whoosh les accompagne
FADE_S = 0.35


def parse_tags(text: str | None) -> list[str]:
    """« Excavator, birds » → ["excavator", "birds"] ; alias rabattus, inconnus ignorés, 3 au plus."""
    out: list[str] = []
    for raw in (text or "").replace(";", ",").replace("/", ",").split(","):
        key = raw.strip().lower().replace(" ", "_").replace("-", "_")
        key = ALIASES.get(key, key)
        if key in TAGS and key not in out:
            out.append(key)
    return out[:3]


def vocabulary_text() -> str:
    """Le vocabulaire donné à l'agent script."""
    beds = ", ".join(f"{k} ({v.label})" for k, v in TAGS.items() if v.kind == "bed")
    hits = ", ".join(f"{k} ({v.label})" for k, v in TAGS.items() if v.kind == "hit")
    return f"Fonds (couvrent la scène) : {beds}\nCoups (ponctuels) : {hits}"


def library_files(sfx_dir: Path, tag: str) -> list[Path]:
    folder = sfx_dir / tag
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXT)


def pick_sfx(sfx_dir: Path, tag: str, key: str) -> Path | None:
    files = library_files(sfx_dir, tag)
    if not files:
        return None
    return files[int(hashlib.sha1(f"{tag}:{key}".encode()).hexdigest(), 16) % len(files)]


@dataclass(frozen=True)
class SfxCue:
    path: Path
    start: float  # secondes, sur la vidéo finale
    duration: float
    volume: float
    loop: bool  # bouclé pour couvrir la durée (fond)
    fade: float = FADE_S


def plan_cues(
    scene_tags: Sequence[Sequence[str]],
    starts: Sequence[float],
    durations: Sequence[float],
    transitions: Sequence[tuple[str, float]],
    resolve: Callable[[str, str], Path | None],  # (étiquette, clé) → fichier de la bibliothèque
    *,
    key: str = "",
) -> list[SfxCue]:
    """Place les bruitages : fonds sur leurs scènes, coups au début de la scène, whoosh à chaque passage whip ou
    push. Un fond présent sur plusieurs scènes consécutives devient UN seul fond continu : un chantier accéléré
    change d'étape toutes les 1,5 s, le son hacherait sinon.
    `transitions[i]` = (type, durée) du passage de la scène i à la suivante ; `resolve` choisit le fichier."""
    cues: list[SfxCue] = []
    runs: list[tuple[str, int, int]] = []  # (étiquette, première scène, dernière scène) d'un fond continu
    open_runs: dict[str, list[int]] = {}
    for i, tags in enumerate(scene_tags):
        for tag in tags:
            spec = TAGS.get(tag)
            if not spec:
                continue
            if spec.kind == "hit":
                path = resolve(tag, f"{key}:{i}")
                if path:
                    cues.append(
                        SfxCue(path, round(starts[i] + 0.05, 3), min(spec.seconds, durations[i]), spec.volume, False, 0.05)
                    )
                continue
            run = open_runs.get(tag)
            if run and run[1] == i - 1:
                run[1] = i
            else:
                if run:
                    runs.append((tag, run[0], run[1]))
                open_runs[tag] = [i, i]
    runs += [(tag, a, b) for tag, (a, b) in open_runs.items()]
    for tag, a, b in runs:
        path = resolve(tag, f"{key}:{a}")
        if path:
            start, end = starts[a], starts[b] + durations[b]
            cues.append(
                SfxCue(path, round(start, 3), round(end - start, 3), TAGS[tag].volume, True, min(FADE_S, (end - start) / 4))
            )
    whoosh = TAGS[TRANSITION_TAG]
    for i, (kind, dur) in enumerate(transitions):
        if kind not in WHOOSH_TRANSITIONS or i + 1 >= len(starts):
            continue
        path = resolve(TRANSITION_TAG, f"{key}:t{i}")
        if path:
            mid = starts[i + 1] + dur / 2  # la scène suivante commence au début du fondu
            cues.append(SfxCue(path, round(max(0.0, mid - 0.45), 3), whoosh.seconds, whoosh.volume, False, 0.05))
    return sorted(cues, key=lambda c: c.start)
