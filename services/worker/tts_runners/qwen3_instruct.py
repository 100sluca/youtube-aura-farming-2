"""Qwen3-TTS VoiceDesign 1.7B dit chaque texte d'après une consigne : l'identité de la voix + le ton de la réplique
(docs/41-voix-emotion.md).

Le modèle Base (qwen3.py) garde le timbre de sa référence mais lit tout sur le même ton, celui de la référence.
VoiceDesign, lui, suit une consigne en langage naturel (« whispering, trembling », « shouts furiously ») ; en échange,
il tire le timbre de la description à chaque appel : une graine fixe par voix le garde proche d'une réplique à l'autre,
ce que le banc d'essai mesure (ressemblance des timbres). Sans ton, la description entière de la voix sert de consigne.

Paramètres de voix : ceux des voix « qwen3:<nom> » du catalogue (design.instruct, design.seed), repris par l'entrée
« voices_from » du moteur. Options : model (dossier sous models/), max_chars.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
from _common import join_audio, run, split_text

LANGS = {"fr": "French", "en": "English"}
STATE: dict[str, Any] = {}


def identity(description: str) -> str:
    """La première phrase d'une description de voix dit qui parle (âge, timbre, accent) ; la suite, sa manière
    habituelle (« Calm, confident narrator »), que le ton de la réplique remplace."""
    first = re.split(r"(?<=\.)\s+", description.strip(), maxsplit=1)[0]
    return first if first.endswith(".") else f"{first}."


def instruction(description: str, tone: str) -> str:
    tone = " ".join((tone or "").split()).rstrip(".")
    if not tone:
        return description.strip()
    return f"{identity(description)} Delivery of this line: {tone}. Stay natural, with the emotion clearly audible."


def prepare(req: dict[str, Any]) -> None:
    import torch
    from qwen_tts import Qwen3TTSModel

    opts = req.get("options") or {}
    engine_dir = Path(req["engine_dir"])
    device = opts.get("device") or ("cuda:0" if torch.cuda.is_available() else "cpu")
    model = Qwen3TTSModel.from_pretrained(
        str(engine_dir / "models" / opts.get("model", "Qwen3-TTS-12Hz-1.7B-VoiceDesign")),
        device_map=device,
        dtype=torch.bfloat16 if device.startswith("cuda") else torch.float32,
        attn_implementation="sdpa",
    )
    design = (req.get("voice_params") or {}).get("design") or {}
    if not design.get("instruct"):
        raise ValueError(f"voix {req['voice']} : description absente du catalogue (params.design.instruct)")
    STATE.update(
        torch=torch,
        model=model,
        description=design["instruct"],
        seed=int(opts.get("seed", design.get("seed", 1234))),
        max_chars=int(opts.get("max_chars", 140)),
        language=LANGS.get(req["lang"], "French"),
    )


def synthesize(req: dict[str, Any], text: str, tone: str) -> tuple[np.ndarray, int]:
    torch, model = STATE["torch"], STATE["model"]
    instruct = instruction(STATE["description"], tone)
    chunks, rate = [], 24000
    for i, sentence in enumerate(split_text(text, STATE["max_chars"])):
        torch.manual_seed(STATE["seed"] + i)
        wavs, rate = model.generate_voice_design(text=sentence, instruct=instruct, language=STATE["language"])
        chunks.append(np.asarray(wavs[0], dtype=np.float32))
    return join_audio(chunks, rate), rate


if __name__ == "__main__":
    run(synthesize, prepare=prepare)
