"""Qwen3-TTS 12 Hz (Alibaba, Apache 2.0) : voix françaises « dessinées », dites par le modèle Base (docs/18-voix.md).

Chaque voix du catalogue a une référence de quelques secondes, créée une fois par le modèle VoiceDesign d'après une
description (qwen3_design.py) : aucune personne réelle n'est clonée. En production, le modèle Base (0,6B par défaut)
reprend ce timbre à partir de la référence et de son texte exact. Le texte est dit phrase par phrase (le débit
accélère sur les textes de plus de ≈ 100 caractères, issue #239 du dépôt), avec une graine fixe par voix.

Paramètres de voix (catalog.json → voices → params) : ref (wav relatif au dossier du moteur), ref_text.
Options du moteur : model (dossier sous models/), max_chars, seed, device.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from _common import join_audio, run, split_text

LANGS = {"fr": "French", "en": "English"}
STATE: dict[str, Any] = {}


def prepare(req: dict[str, Any]) -> None:
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    opts = req.get("options") or {}
    engine_dir = Path(req["engine_dir"])
    device = opts.get("device") or ("cuda:0" if torch.cuda.is_available() else "cpu")
    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
    model = Qwen3TTSModel.from_pretrained(
        str(engine_dir / "models" / opts.get("model", "Qwen3-TTS-12Hz-0.6B-Base")),
        device_map=device,
        dtype=dtype,
        attn_implementation="sdpa",
    )
    params = req.get("voice_params") or {}
    if not params.get("ref") or not params.get("ref_text"):
        raise ValueError(f"voix {req['voice']} : référence absente du catalogue (params.ref, params.ref_text)")
    ref_path = engine_dir / params["ref"]
    if not ref_path.exists():
        raise FileNotFoundError(f"référence de voix absente : {ref_path} (lancer tts_runners/qwen3_design.py)")
    ref, ref_sr = sf.read(str(ref_path), dtype="float32")
    STATE.update(
        torch=torch,
        model=model,
        seed=int(opts.get("seed", params.get("seed", 1234))),
        max_chars=int(opts.get("max_chars", 140)),
        language=LANGS.get(req["lang"], "French"),
        prompt=model.create_voice_clone_prompt(ref_audio=(ref, ref_sr), ref_text=params["ref_text"]),
    )


def synthesize(req: dict[str, Any], text: str) -> tuple[np.ndarray, int]:
    torch, model = STATE["torch"], STATE["model"]
    chunks, rate = [], 24000
    for i, sentence in enumerate(split_text(text, STATE["max_chars"])):
        torch.manual_seed(STATE["seed"] + i)
        wavs, rate = model.generate_voice_clone(text=sentence, language=STATE["language"], voice_clone_prompt=STATE["prompt"])
        chunks.append(np.asarray(wavs[0], dtype=np.float32))
    return join_audio(chunks, rate), rate


if __name__ == "__main__":
    run(synthesize, prepare=prepare)
