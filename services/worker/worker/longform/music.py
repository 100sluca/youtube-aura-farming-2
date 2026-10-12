"""Musique des vidéos longues (docs/63 §5) : une bibliothèque à part, générée en local par ACE-Step 1.5 (licence MIT,
sans droits d'auteur tiers : rien que Content ID puisse réclamer, contrairement à music_7 bloquée dans 249 pays,
docs/58), des fonds de documentaire discrets, sans percussions brusques, faits pour durer sous une voix. Rangée dans
DATA_DIR/music/long_<ambiance>/ ; trois pistes de 3 min par ambiance, générées la première fois qu'une vidéo en a
besoin (environ 2 min de carte graphique par piste)."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from ..media import AUDIO_EXT
from ..providers.audio import MUSIC_WORKFLOW, MusicMood, load_audio_workflow, patch_audio_workflow
from ..providers.video import ComfyClient, output_node_id

SCORE = "instrumental, no vocals, background score for a long documentary video, clean balanced mix, no sudden loud hits"
LONG_MOODS: dict[str, tuple[str, MusicMood]] = {
    "mystere": (
        "Mystère : énigme, enquête, lieux anciens",
        MusicMood(
            "Dark ambient mystery documentary underscore, low sustained strings, deep warm drones, sparse felt piano "
            f"notes, distant airy choir pad, soft ticking pulse, slow and suspenseful, {SCORE}",
            70,
            "D minor",
        ),
    ),
    "tension": (
        "Tension : la découverte approche, le danger monte",
        MusicMood(
            "Tense investigative documentary underscore, pulsing low synth ostinato, dark cello and strings, subtle "
            f"taiko hits far away, slowly building suspense, cinematic, {SCORE}",
            92,
            "E minor",
        ),
    ),
    "epique": (
        "Épique : grandeur, empire, exploit",
        MusicMood(
            "Epic but restrained historical documentary score, warm strings and french horns, slow timpani, "
            f"majestic and noble, builds slowly then settles, {SCORE}",
            80,
            "C minor",
        ),
    ),
    "emotion": (
        "Émotion : perte, destin, souvenir",
        MusicMood(
            f"Melancholic documentary piano with soft cello and warm strings, intimate, reflective, slow, {SCORE}",
            66,
            "A minor",
        ),
    ),
    "epoque": (
        "Époque : antiquité, moyen âge, vie d'autrefois",
        MusicMood(
            "Ancient world ambient documentary music, duduk and wooden flute melody over soft drones, frame drum "
            f"heartbeat, antique and medieval atmosphere, calm and immersive, {SCORE}",
            72,
            "D minor",
        ),
    ),
}
RELATED = {
    "mystere": ("tension", "epoque"),
    "tension": ("mystere",),
    "epique": ("epoque", "tension"),
    "emotion": ("mystere",),
    "epoque": ("mystere", "epique"),
}
TRACKS_PER_MOOD = 3
TRACK_S = 180.0


def mood_list() -> str:
    return ", ".join(f"{k} ({v[0]})" for k, v in LONG_MOODS.items())


def folder(data_dir: Path, mood: str) -> Path:
    return Path(data_dir) / "music" / f"long_{mood}"


def tracks(data_dir: Path, mood: str) -> list[Path]:
    f = folder(data_dir, mood)
    return sorted(p for p in f.iterdir() if p.suffix.lower() in AUDIO_EXT) if f.is_dir() else []


def pick_moods(mood: str | None) -> list[str]:
    m = mood if mood in LONG_MOODS else "mystere"
    return [m, *RELATED.get(m, ())]


def generate(settings: Any, mood: str, count: int, log: Any = None) -> list[Path]:
    """`count` pistes de plus pour cette ambiance (ACE-Step 1.5 dans ComfyUI)."""
    _, m = LONG_MOODS[mood]
    client = ComfyClient(settings.comfy_base_url, settings.comfy_timeout_s)
    out_dir = folder(settings.data_dir, mood)
    out_dir.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    for _ in range(count):
        seed = random.randint(0, 2**31)
        wf = patch_audio_workflow(
            load_audio_workflow(settings, MUSIC_WORKFLOW), prompt=m.tags, seed=seed, seconds=TRACK_S, bpm=m.bpm, key=m.key,
            prefix=f"yt2/music_long_{mood}",
        )  # fmt: skip
        entry = client.wait(client.submit(wf), lambda _p: None)
        made.append(client.download_output(entry, output_node_id(wf), out_dir / f"ace15_long_{mood}_{seed}.mp3"))
        if log:
            log(f"Musique « {mood} » générée : {made[-1].name}")
    return made
