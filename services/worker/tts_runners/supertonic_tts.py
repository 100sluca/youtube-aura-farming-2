"""Supertonic 3 (Supertone, licence OpenRAIL-M) : 10 voix prêtes (F1-F5, M1-M5), ONNX sur le processeur, 44,1 kHz
(docs/18-voix.md). La licence impose d'indiquer clairement qu'une voix est générée par IA (Attachment A, e) et
interdit l'usurpation d'identité. Dépôt archivé le 09/09/2026 : plus de correctifs, les voix n'évolueront plus.

Paramètres de voix : name (F1…M5). Options du moteur : steps (qualité, 8 par défaut chez Supertone).
La vitesse est réglée par le modèle lui-même.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from _common import run

STATE: dict[str, Any] = {}


def prepare(req: dict[str, Any]) -> None:
    from supertonic import TTS

    opts = req.get("options") or {}
    model_dir = Path(req["engine_dir"]) / "models" / "supertonic-3"
    tts = TTS(model="supertonic-3", model_dir=model_dir, auto_download=not (model_dir / "onnx").is_dir())
    name = (req.get("voice_params") or {}).get("name") or req["voice"]
    STATE.update(tts=tts, style=tts.get_voice_style(voice_name=name), steps=int(opts.get("steps", 16)))


def synthesize(req: dict[str, Any], text: str) -> tuple[np.ndarray, int]:
    tts = STATE["tts"]
    speed = min(2.0, max(0.7, float(req.get("speed") or 1.0)))
    wav, _duration = tts.synthesize(text, voice_style=STATE["style"], lang=req["lang"], total_steps=STATE["steps"], speed=speed)
    return np.asarray(wav, dtype=np.float32), int(tts.sample_rate)


if __name__ == "__main__":
    run(synthesize, prepare=prepare, speed_applied=True)
