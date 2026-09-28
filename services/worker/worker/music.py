"""Musiques de fond : la bibliothèque de Luca, le choix d'une piste pour chaque vidéo et les niveaux du mixage
(docs/26-musique.md).

Bibliothèque : les fichiers du dossier « music » du dépôt (MUSIC_LIBRARY_DIR), une ligne par fichier dans music_tracks
(migration 0018) : description, ambiances (MOODS), formats où elle sert (récit, chantier, visite), préférence, volume
et début. Un fichier ajouté au dossier apparaît seul (sync_library) mais ne sert qu'une fois un format coché dans
l'onglet Montage. Chaque piste est mesurée (sonie intégrée EBU R128, en LUFS) pour les mettre toutes au même niveau
avant les réglages de Luca : le 28/09, de −18,1 LUFS (music_5) à −6,7 (music_9), 11 dB d'écart.

Choix (choose_track) : le scénariste donne une ambiance (ScriptV1.music_mood, liste lue dans mood_brief) ; on tire
parmi les pistes actives du format qui la portent, selon leur préférence, le même tirage pour une même production. Une
ambiance sans piste passe à ses voisines (RELATED), puis aux ambiances conseillées par la série, puis à toutes les
pistes du format. Les ambiances anglaises des anciens scripts et des séries (mysterious, epic, luxury…) sont traduites
(ALIASES).

Niveaux (mix_levels) : la voix est ramenée à VOICE_REF_LUFS ; sous une voix, la musique vise VOICE_REF_LUFS +
music_db et baisse de duck_db pendant que la voix parle (duck_expression : rampes de DUCK_ATTACK_S et DUCK_RELEASE_S
autour de chaque passage parlé) ; sans voix, elle vise SOLO_REF_LUFS + solo_db, sous les bruitages ; plus le volume
propre de la piste. Le mixage final est ramené à −14 LUFS (loudnorm, le niveau de YouTube) : ces réglages font
l'équilibre entre voix, musique et bruitages. L'écoute de l'onglet Montage refait le même calcul
(apps/dashboard/src/lib/audio-mix.ts) avec les constantes recopiées dans assets/montage/defaults.json (« audio ») ;
tests/test_music.py vérifie qu'elles suivent ce fichier.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from .media import AUDIO_EXT, measure_loudness

log = structlog.get_logger(__name__)

VOICE_REF_LUFS = -18.0  # voix égalisée (les moteurs de voix sortent vers −18,8 LUFS, mesuré le 28/09)
SOLO_REF_LUFS = -20.0  # musique d'une vidéo sans voix, sous les bruitages (≈ le mixage des chantiers et visites d'avant)
UNKNOWN_LUFS = -14.0  # piste pas encore mesurée : niveau courant d'une musique masterisée
MAX_LEVELING_DB = 30.0  # garde-fou : une mesure aberrante (fichier presque muet) ne pousse pas le gain au-delà
DUCK_MERGE_GAP_S = 0.7  # deux mots séparés de moins que ça : même passage parlé, la musique ne remonte pas entre eux
DUCK_ATTACK_S = 0.12  # la musique descend en 0,12 s juste avant que la voix parle
DUCK_RELEASE_S = 0.45  # et remonte en 0,45 s après
FADE_IN_S, FADE_OUT_S = 0.6, 1.2  # fondus de la musique au début et à la fin de la vidéo
OUTPUT_LUFS = -14.0  # mixage final (loudnorm) : le niveau auquel YouTube ramène les vidéos

# Ambiances des pistes : (libellé, ce qu'elle raconte) ; l'identifiant est ce que le scénariste écrit dans music_mood
MOODS: dict[str, tuple[str, str]] = {
    "mystere": ("Mystère", "enquête, énigme, intrigue, histoire à comprendre"),
    "epique": ("Épique", "exploit, tour de force, spectaculaire, puissant, qui a de l'aura"),
    "majestueux": ("Majestueux", "monument, grandeur, épopée, médiéval"),
    "sentimental": ("Sentimental", "émotion, tendresse, amour, souvenir"),
    "tragique": ("Tragique", "amour qui finit mal, drame, destin"),
    "triste": ("Triste", "perte, deuil, mélancolie"),
    "voyage": ("Voyage", "évasion, nostalgie, solitude, grands espaces"),
    "decouverte": ("Découverte", "visite d'un lieu, émerveillement, luxe"),
    "joyeux": ("Joyeux", "léger, positif, entraînant"),
    "pose": ("Posé", "récit calme, documentaire, neutre"),
}
# Ambiance sans piste pour ce format : ses voisines, dans l'ordre
RELATED: dict[str, tuple[str, ...]] = {
    "mystere": ("pose",),
    "epique": ("majestueux",),
    "majestueux": ("epique",),
    "sentimental": ("tragique", "voyage"),
    "tragique": ("triste", "sentimental"),
    "triste": ("tragique", "sentimental"),
    "voyage": ("decouverte", "sentimental"),
    "decouverte": ("voyage", "pose"),
    "joyeux": ("decouverte", "pose"),
    "pose": ("decouverte",),
}
# Mots des anciens prompts, des séries (series.music_moods) et de la bibliothèque ACE-Step, et variantes françaises
ALIASES: dict[str, tuple[str, ...]] = {
    "mysterious": ("mystere",), "mystery": ("mystere",), "suspense": ("mystere",), "investigation": ("mystere",),
    "intriguing": ("mystere",), "tension": ("mystere",), "dark": ("mystere",), "mysterieux": ("mystere",),
    "mysterieuse": ("mystere",), "enquete": ("mystere",), "intrigant": ("mystere",), "intrigante": ("mystere",),
    "epic": ("epique",), "heroic": ("epique",), "powerful": ("epique",), "triumphant": ("epique",),
    "badass": ("epique",), "inspiring": ("epique", "joyeux"), "epopee": ("epique",),
    "majestic": ("majestueux",), "grand": ("majestueux",), "medieval": ("majestueux",), "solemn": ("majestueux",),
    "majestueuse": ("majestueux",),
    "emotional": ("sentimental",), "romantic": ("sentimental",), "tender": ("sentimental",), "love": ("sentimental",),
    "romantique": ("sentimental",), "sentimentale": ("sentimental",), "emouvant": ("sentimental",),
    "tragic": ("tragique",), "dramatic": ("tragique",), "drama": ("tragique",), "dramatique": ("tragique",),
    "sad": ("triste",), "melancholic": ("triste",), "melancholy": ("triste",), "melancolique": ("triste",),
    "travel": ("voyage",), "journey": ("voyage",), "nostalgic": ("voyage", "sentimental"), "lonely": ("voyage",),
    "adventure": ("voyage", "epique"), "nostalgique": ("voyage", "sentimental"), "nostalgie": ("voyage", "sentimental"),
    "luxury": ("decouverte",), "elegant": ("decouverte",), "chill": ("decouverte", "pose"), "discovery": ("decouverte",),
    "wonder": ("decouverte",), "luxe": ("decouverte",), "visite": ("decouverte",), "elegante": ("decouverte",),
    "upbeat": ("joyeux",), "happy": ("joyeux",), "joyful": ("joyeux",), "cheerful": ("joyeux",), "fun": ("joyeux",),
    "joyeuse": ("joyeux",), "gai": ("joyeux",),
    "calm": ("pose",), "neutral": ("pose",), "documentary": ("pose",), "ambient": ("pose",), "peaceful": ("pose",),
    "calme": ("pose",), "narratif": ("pose",), "neutre": ("pose",), "posee": ("pose",),
}
FORMATS = ("story", "timelapse", "tour")


def _words(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]+", " ", plain).split()


def mood_ids(value: str | None) -> list[str]:
    """Ambiances de la bibliothèque pour ce qu'écrit un agent ou une série (« mystere », « Mystère », « mysterious »,
    « epic, emotional ») : dans l'ordre, sans doublon ; [] si rien n'est reconnu."""
    out: list[str] = []
    for word in _words(value or ""):
        for mood in (word,) if word in MOODS else ALIASES.get(word, ()):
            if mood not in out:
                out.append(mood)
    return out


# ---- Bibliothèque ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Track:
    id: str
    file: str
    title: str = ""
    description: str = ""
    moods: tuple[str, ...] = ()
    formats: tuple[str, ...] = ()
    weight: float = 1.0
    enabled: bool = True
    gain_db: float = 0.0
    start_s: float = 0.0
    note: str = ""
    lufs: float | None = None
    duration_s: float | None = None
    path: Path | None = None  # None : fichier absent du dossier

    @property
    def usable(self) -> bool:
        return self.enabled and self.path is not None and self.weight > 0

    @classmethod
    def from_row(cls, row: dict[str, Any], path: Path | None) -> Track:
        return cls(
            id=row["id"], file=row["file"], title=row.get("title") or row["id"], description=row.get("description") or "",
            moods=tuple(m for m in row.get("moods") or () if m in MOODS),
            formats=tuple(f for f in row.get("formats") or () if f in FORMATS),
            weight=float(row["weight"] if row.get("weight") is not None else 1.0), enabled=bool(row.get("enabled", True)),
            gain_db=float(row.get("gain_db") or 0.0), start_s=float(row.get("start_s") or 0.0), note=row.get("note") or "",
            lufs=float(row["lufs"]) if row.get("lufs") is not None else None,
            duration_s=float(row["duration_s"]) if row.get("duration_s") is not None else None,
            path=path,
        )


def library_files(folder: Path) -> dict[str, Path]:
    """Fichiers audio du dossier par identifiant (nom sans extension) ; un nom en double garde le premier."""
    out: dict[str, Path] = {}
    if folder.is_dir():
        for p in sorted(folder.iterdir(), key=lambda f: f.name.lower()):
            if p.is_file() and p.suffix.lower() in AUDIO_EXT:
                out.setdefault(p.stem.strip()[:120], p)
    return out


def _same_file(row: dict[str, Any], path: Path) -> bool:
    """Le fichier mesuré est-il toujours le même (nom, taille, date à la seconde près : le dashboard écrit la date en
    millisecondes, le worker en microsecondes) ?"""
    st = path.stat()
    mtime = row.get("file_mtime")
    return (row.get("file") == path.name and row.get("file_size") == st.st_size and mtime is not None
            and abs(mtime.timestamp() - st.st_mtime) < 1.0)


def load_library(db: Any, folder: Path) -> list[Track]:
    """La bibliothèque telle qu'enregistrée, sans rien écrire en base (le scénariste ne lit que les pistes décrites) ;
    liste vide si la table manque ou ne se lit pas."""
    files = library_files(folder)
    try:
        rows = db.fetch_all("select * from music_tracks")
        return [Track.from_row(r, files.get(r["id"])) for r in sorted(rows, key=lambda r: r["id"])]
    except Exception as exc:  # noqa: BLE001 — migration 0018 absente
        log.warning("music.table_absente", error=str(exc)[:200])
        return []


def sync_library(db: Any, folder: Path, *, measure: bool = True) -> list[Track]:
    """Met music_tracks à jour avec le dossier et renvoie la bibliothèque : un nouveau fichier est ajouté (sans format
    coché : à décrire dans l'onglet Montage), un fichier retiré est marqué absent (la ligne reste pour les
    statistiques), un fichier nouveau ou remplacé est mesuré. Base sans la migration 0018 : liste vide."""
    files = library_files(folder)
    try:
        rows = {r["id"]: r for r in db.fetch_all("select * from music_tracks")}
    except Exception as exc:  # noqa: BLE001 — migration 0018 absente : le montage garde l'ancienne bibliothèque
        log.warning("music.table_absente", error=str(exc)[:200])
        return []
    changed = False
    for tid, path in files.items():
        row = rows.get(tid)
        if row is None:
            db.execute("insert into music_tracks (id, file, title) values (%s, %s, %s) on conflict (id) do nothing",
                       (tid, path.name, tid.replace("_", " ").strip().capitalize()))
            row, changed = {"id": tid, "missing": False, "lufs": None}, True
        if measure and (row.get("lufs") is None or not _same_file(row, path)):
            loud = measure_loudness(path)
            st = path.stat()
            db.execute(
                """update music_tracks set file = %s, lufs = %s, peak_db = %s, duration_s = %s, file_size = %s,
                     file_mtime = %s, missing = false where id = %s""",
                (path.name, loud.lufs, loud.peak_db, loud.duration_s, st.st_size,
                 datetime.fromtimestamp(int(st.st_mtime), UTC), tid),
            )
            log.info("music.mesure", piste=tid, lufs=loud.lufs, duree_s=loud.duration_s)
            changed = True
        elif row.get("missing"):
            db.execute("update music_tracks set missing = false, file = %s where id = %s", (path.name, tid))
            changed = True
    for tid, row in rows.items():
        if tid not in files and not row.get("missing"):
            db.execute("update music_tracks set missing = true where id = %s", (tid,))
            changed = True
    if changed:
        rows = {r["id"]: r for r in db.fetch_all("select * from music_tracks")}
    return [Track.from_row(r, files.get(tid)) for tid, r in sorted(rows.items())]


# ---- Choix d'une piste -------------------------------------------------------------------------------------------------


def weighted_pick(pool: Sequence[Track], key: str) -> Track:
    """Tirage selon la préférence (weight) de chaque piste, toujours le même pour une même clé (la production)."""
    total = sum(t.weight for t in pool)
    u = int(hashlib.sha1(key.encode()).hexdigest()[:13], 16) / 16**13 * total
    acc = 0.0
    for t in pool:
        acc += t.weight
        if u < acc:
            return t
    return pool[-1]


def choose_track(
    tracks: Sequence[Track], recipe: str, mood: str | None, key: str, series_moods: Iterable[str] = ()
) -> tuple[Track | None, str | None]:
    """Piste d'une vidéo (None : aucune piste active pour ce format) et l'ambiance qui l'a fait choisir (None : aucune
    ambiance ne correspondait, tirage parmi toutes les pistes du format)."""
    usable = sorted((t for t in tracks if t.usable and recipe in t.formats), key=lambda t: t.id)
    if not usable:
        return None, None
    wanted = mood_ids(mood)
    order = [*wanted, *(r for m in wanted for r in RELATED.get(m, ())), *(m for s in series_moods for m in mood_ids(s))]
    for m in dict.fromkeys(order):
        pool = [t for t in usable if m in t.moods]
        if pool:
            return weighted_pick(pool, key), m
    return weighted_pick(usable, key), None


def mood_brief(tracks: Sequence[Track], recipe: str, series_moods: Iterable[str] = ()) -> str:
    """Consigne du scénariste pour music_mood : les ambiances qui ont au moins une piste active pour ce format, et
    celles que conseille la série. Vide si la bibliothèque n'a rien pour ce format."""
    usable = [t for t in tracks if t.usable and recipe in t.formats]
    moods = [m for m in MOODS if any(m in t.moods for t in usable)]
    if not moods:
        return ""
    advised = [m for m in dict.fromkeys(m for s in series_moods for m in mood_ids(s)) if m in moods]
    named = {m: f"{m} ({MOODS[m][0].lower()})" if MOODS[m][0].lower() != m else m for m in moods}  # « epique (épique) »
    lines = "\n".join(f"- {named[m]} : {MOODS[m][1]}" for m in moods)
    return (
        "MUSIQUE DE FOND (champ music_mood) : l'ambiance de la musique, choisie pour l'émotion de l'histoire ; écris "
        f"l'identifiant tel quel :\n{lines}" + (f"\nConseillées pour cette série : {', '.join(advised)}." if advised else "")
    )


# ---- Niveaux du mixage -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MixLevels:
    voice_gain_db: float  # gain de la narration (égalisation + réglage « Voix IA »)
    music_gain_db: float  # gain de la piste (égalisation + niveau du modèle + volume de la piste)
    duck_db: float  # baisse de la musique pendant que la voix parle
    sfx_gain_db: float  # gain des bruitages


def _leveling(target: float, measured: float | None, unknown: float) -> float:
    level = measured if measured is not None else unknown
    return max(-MAX_LEVELING_DB, min(MAX_LEVELING_DB, target - level))


def mix_levels(
    audio: Any, *, with_voice: bool, track_lufs: float | None = None, track_gain_db: float = 0.0,
    narration_lufs: float | None = None,
) -> MixLevels:
    """Gains du mixage d'une vidéo : `audio` est la couche AudioLayer du modèle de montage (worker/montage.py). Une
    voix non mesurée garde son niveau ; une piste non mesurée est supposée à UNKNOWN_LUFS."""
    voice = (_leveling(VOICE_REF_LUFS, narration_lufs, VOICE_REF_LUFS) if narration_lufs is not None else 0.0) + audio.voice_db
    target = VOICE_REF_LUFS + audio.music_db if with_voice else SOLO_REF_LUFS + audio.solo_db
    music = _leveling(target, track_lufs, UNKNOWN_LUFS) + track_gain_db
    return MixLevels(round(voice, 2), round(music, 2), float(audio.duck_db) if with_voice else 0.0, float(audio.sfx_db))


def music_start(track: Track, total_s: float) -> float:
    """Départ de la musique dans le fichier : le « Début » de la piste, avancé si la vidéo dépasserait la fin du fichier
    (la piste repartirait de zéro en pleine vidéo) ; 0 pour une piste plus courte que la vidéo (elle boucle)."""
    start = max(0.0, track.start_s)
    if track.duration_s:
        start = min(start, max(0.0, track.duration_s - total_s))
    return round(start, 3)


def speech_segments(words: Iterable[Any], merge_gap: float = DUCK_MERGE_GAP_S) -> list[tuple[float, float]]:
    """Passages parlés (début, fin en s) d'après les mots horodatés de la narration (videos.timeline) : deux mots
    séparés de moins de `merge_gap` secondes sont dans le même passage."""
    out: list[list[float]] = []
    for w in sorted(words, key=lambda w: w.start):
        if w.end <= w.start:
            continue
        if out and w.start - out[-1][1] < merge_gap:
            out[-1][1] = max(out[-1][1], w.end)
        else:
            out.append([w.start, w.end])
    return [(round(a, 3), round(b, 3)) for a, b in out]


def duck_amount(t: float, segments: Sequence[tuple[float, float]], attack: float = DUCK_ATTACK_S,
                release: float = DUCK_RELEASE_S) -> float:
    """Part de la baisse à l'instant t (0 : musique à son niveau, 1 : baissée de duck_db) : rampe de `attack` s avant
    chaque passage parlé, palier, rampe de `release` s après. Même courbe que duck_expression et que l'écoute du
    dashboard."""
    level = 0.0
    for a, b in segments:
        level = max(level, min(1.0, max(0.0, min((t - (a - attack)) / attack, ((b + release) - t) / release))))
    return level


def _max_tree(terms: list[str]) -> str:
    """max() de FFmpeg ne prend que deux arguments : arbre équilibré (l'analyseur limite la profondeur à 100)."""
    while len(terms) > 1:
        terms = [f"max({terms[i]},{terms[i + 1]})" if i + 1 < len(terms) else terms[i] for i in range(0, len(terms), 2)]
    return terms[0]


def duck_expression(segments: Sequence[tuple[float, float]], duck_db: float, attack: float = DUCK_ATTACK_S,
                    release: float = DUCK_RELEASE_S) -> str | None:
    """Gain de la musique à l'instant t, pour le filtre volume de FFmpeg (eval=frame) : 1 hors de la voix,
    10^(-duck_db/20) pendant ; None s'il n'y a rien à baisser."""
    if duck_db <= 0 or not segments:
        return None
    depth = 1 - 10 ** (-duck_db / 20)
    terms = [
        f"clip(min((t-({a - attack:.3f}))*{1 / attack:.4f},({b + release:.3f}-t)*{1 / release:.4f}),0,1)"
        for a, b in segments
    ]
    return f"1-{depth:.4f}*{_max_tree(terms)}"
