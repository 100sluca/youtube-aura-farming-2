"""Musique et bruitages générés en local par ComfyUI : bibliothèques DATA_DIR/music/<ambiance>/ et DATA_DIR/sfx/<étiquette>/.

- Musique : ACE-Step 1.5 (MIT, sorties utilisables commercialement ; nœuds natifs de ComfyUI 0.37,
  workflows/audio/ace_step_15_music.json), instrumentale, une ambiance = un style décrit en anglais (MUSIC_MOODS) ;
  `yt2 music generate --mood luxury`.
- Bruitages : Stable Audio 3 « small-sfx » (workflows/audio/stable_audio_3_sfx.json ; licence communautaire de
  Stability : gratuite sous 1 M$ de chiffre d'affaires, inscription gratuite obligatoire), un prompt par étiquette
  de worker/sfx.py ; `yt2 sfx generate`.
On génère une bibliothèque une fois (quelques minutes de GPU), puis le montage y pioche (pick_music, pick_sfx) :
une vidéo ne relance aucune génération audio. Licences et tailles : docs/15.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Settings
from .video import ComfyClient, WorkflowError, nodes_titled, output_node_id

MUSIC_WORKFLOW = "ace_step_15_music"
SFX_WORKFLOW = "stable_audio_3_sfx"
SFX_NEGATIVE = ""  # modèle distillé, CFG 1 : le négatif n'agit pas (gabarit officiel)


def sfx_prompt(prompt: str, seconds: float) -> str:
    """Forme attendue par Stable Audio 3 (réécriture du gabarit officiel) : description dense, puis la durée."""
    return f"{prompt.rstrip('. ')}. Length: {max(1, round(seconds))} seconds"


@dataclass(frozen=True)
class MusicMood:
    tags: str  # description du style (anglais), champ « tags » d'ACE-Step
    bpm: int
    key: str  # tonalité (keyscale d'ACE-Step)


INSTRUMENTAL = "instrumental, no vocals, loopable background music for a short video, clean modern mix"
MUSIC_MOODS: dict[str, MusicMood] = {
    # Visites de luxe
    "luxury": MusicMood("Luxury real estate video music: chill deep house, smooth Rhodes electric piano chords, warm sub "
                        f"bass, soft four-on-the-floor kick, crisp shakers, shimmering pads, elegant and aspirational, {INSTRUMENTAL}", 118, "A minor"),
    "chill": MusicMood(f"Chill lounge house, mellow piano, soft guitar licks, relaxed groove, warm bass, sunny, {INSTRUMENTAL}", 102, "D major"),
    "elegant": MusicMood(f"Elegant cinematic piano with light strings and pizzicato, sophisticated, calm, luxurious, {INSTRUMENTAL}", 88, "C major"),
    # Chantiers en accéléré
    "inspiring": MusicMood("Inspiring cinematic build-up for a construction time-lapse: steady piano ostinato, rising strings, "
                           f"light percussion and claps, uplifting and positive, grows in intensity, {INSTRUMENTAL}", 110, "G major"),
    "upbeat": MusicMood(f"Upbeat energetic pop instrumental, punchy drums, bright synth plucks, claps, positive, fast-paced, {INSTRUMENTAL}", 124, "C major"),
    "epic": MusicMood(f"Epic cinematic trailer music, big drums, powerful strings and brass, heroic build-up, {INSTRUMENTAL}", 100, "D minor"),
    # Récits (séries narrées)
    "calm": MusicMood(f"Calm ambient piano, soft pads, gentle and warm, {INSTRUMENTAL}", 80, "F major"),
    "suspense": MusicMood(f"Suspense documentary underscore, pulsing low synth, ticking percussion, tension, {INSTRUMENTAL}", 95, "E minor"),
    "emotional": MusicMood(f"Emotional cinematic piano and cello, tender, hopeful, {INSTRUMENTAL}", 76, "A minor"),
    "mysterious": MusicMood(f"Mysterious ambient soundtrack, airy pads, subtle bells, low drones, curious, {INSTRUMENTAL}", 85, "B minor"),
}


def load_audio_workflow(settings: Settings, name: str) -> dict[str, Any]:
    p = settings.comfy_workflow_dir / "audio" / f"{name}.json"
    if not p.exists():
        raise WorkflowError(f"workflow audio {name!r} introuvable ({p})")
    return json.loads(p.read_text(encoding="utf-8"))


def patch_audio_workflow(
    wf: dict[str, Any], *, prompt: str, seed: int, seconds: float, negative: str = "",
    bpm: int | None = None, key: str | None = None, prefix: str | None = None,
) -> dict[str, Any]:
    """Copie du workflow audio avec les entrées remplacées (titres PROMPT, NEGATIVE, SIZE, DURATION, SEED, OUTPUT).
    Le nœud PROMPT est soit un encodeur ACE-Step (tags, durée, tempo, tonalité, graine), soit un CLIPTextEncode."""
    w = copy.deepcopy(wf)
    for title in ("PROMPT", "SEED", "SIZE", "OUTPUT"):
        if not nodes_titled(w, title):
            raise WorkflowError(f"le workflow audio n'a pas de nœud titré {title}")
    for n in nodes_titled(w, "PROMPT"):
        inp = n["inputs"]
        if "tags" in inp:  # ACE-Step 1.5
            inp["tags"] = prompt
            inp["duration"] = float(seconds)
            inp["seed"] = seed
            if bpm:
                inp["bpm"] = int(bpm)
            if key:
                inp["keyscale"] = key
        else:
            inp["text"] = prompt
    for n in nodes_titled(w, "NEGATIVE"):
        n["inputs"]["text"] = negative
    for n in nodes_titled(w, "SIZE"):
        n["inputs"]["seconds"] = float(seconds)
    for n in nodes_titled(w, "DURATION"):
        n["inputs"]["seconds_total"] = float(seconds)
    for n in nodes_titled(w, "SEED"):
        n["inputs"]["seed"] = seed
    if prefix:
        for n in nodes_titled(w, "OUTPUT"):
            n["inputs"]["filename_prefix"] = prefix
    return w


class ComfyAudio:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = ComfyClient(settings.comfy_base_url, settings.comfy_timeout_s)

    def _run(self, wf: dict[str, Any], out: Path) -> Path:
        entry = self.client.wait(self.client.submit(wf), lambda _p: None)
        return self.client.download_output(entry, output_node_id(wf), out)

    def music(self, mood: str, out_dir: Path, *, seed: int, seconds: float = 90.0) -> Path:
        m = MUSIC_MOODS[mood]
        wf = patch_audio_workflow(load_audio_workflow(self.settings, MUSIC_WORKFLOW), prompt=m.tags, seed=seed,
                                  seconds=seconds, bpm=m.bpm, key=m.key, prefix=f"yt2/music_{mood}")
        return self._run(wf, out_dir / f"ace15_{mood}_{seed}.mp3")

    def sfx(self, tag: str, prompt: str, out_dir: Path, *, seed: int, seconds: float) -> Path:
        wf = patch_audio_workflow(load_audio_workflow(self.settings, SFX_WORKFLOW), prompt=sfx_prompt(prompt, seconds),
                                  negative=SFX_NEGATIVE, seed=seed, seconds=seconds, prefix=f"yt2/sfx_{tag}")
        return self._run(wf, out_dir / f"sa3_{tag}_{seed}.flac")
