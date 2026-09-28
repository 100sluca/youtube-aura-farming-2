"""Kyutai Pocket TTS (poids CC BY 4.0, créditer Kyutai) : modèle français de 100 M de paramètres, sur le processeur
(docs/18-voix.md). Aucune concurrence avec ComfyUI pour la carte graphique.

Voix : les « états » précalculés du modèle français (dépôt sans clonage, kyutai/pocket-tts-without-voice-cloning) ;
seule « estelle » est une voix française native (enregistrement CC0 de Kyutai). Paramètres de voix : name.
Options du moteur : language (french, ou french_24l, plus gros), temp.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from _common import run

STATE: dict[str, Any] = {}


def prepare(req: dict[str, Any]) -> None:
    from pocket_tts import TTSModel

    opts = req.get("options") or {}
    language = opts.get("language", "french" if req["lang"] == "fr" else "english")
    model = TTSModel.load_model(language=language, temp=opts.get("temp"))
    name = (req.get("voice_params") or {}).get("name") or req["voice"]
    STATE.update(model=model, voice=model.get_state_for_audio_prompt(name))


def synthesize(req: dict[str, Any], text: str) -> tuple[np.ndarray, int]:
    model = STATE["model"]
    audio = model.generate_audio(STATE["voice"], text)  # [canaux, n] ; textes longs gérés par le modèle
    return audio.detach().cpu().numpy(), int(model.sample_rate)


if __name__ == "__main__":
    run(synthesize, prepare=prepare)
