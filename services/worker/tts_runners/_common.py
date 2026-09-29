"""Outils communs aux scripts des moteurs de voix. Ils tournent dans l'environnement Python du moteur
(<YT2_HOME>/tts/<moteur>/venv), jamais dans celui du worker : seulement la bibliothèque standard et numpy ici.

Protocole (worker/providers/tts.py, VenvTTS) : le worker écrit request.json puis lance
`<venv>/Scripts/python.exe tts_runners/<moteur>.py <dossier>/request.json` ; le script écrit « PROGRESS <fait> <total> »
sur sa sortie standard, un .wav par texte dans le dossier, puis result.json {"rate", "files", "speed_applied"}.
Code de sortie non nul ou result.json absent = échec (le worker affiche la fin de la sortie d'erreur).
"""

from __future__ import annotations

import json
import re
import sys
import traceback
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np


def load_request() -> dict[str, Any]:
    return json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))


def progress(done: int, total: int) -> None:
    print(f"PROGRESS {done} {total}", flush=True)


def to_mono_float(samples: Any) -> np.ndarray:
    a = np.asarray(samples, dtype=np.float32)
    if a.ndim > 1:  # (canaux, n) ou (n, canaux)
        a = a.mean(axis=0 if a.shape[0] < a.shape[-1] else -1)
    return a.reshape(-1)


def write_wav(path: Path, samples: Any, rate: int) -> None:
    a = np.clip(to_mono_float(samples), -1.0, 1.0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes((a * 32767.0).astype("<i2").tobytes())


def split_text(text: str, max_chars: int) -> list[str]:
    """Découpe aux fins de phrase (puis aux virgules) pour les modèles qui dérivent sur les textes longs."""
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return [text] if text else []
    parts: list[str] = []
    for sentence in re.split(r"(?<=[.!?…])\s+", text):
        pieces = [sentence] if len(sentence) <= max_chars else re.split(r"(?<=[,;:])\s+", sentence)
        for piece in pieces:
            if parts and len(parts[-1]) + 1 + len(piece) <= max_chars:
                parts[-1] = f"{parts[-1]} {piece}"
            else:
                parts.append(piece)
    return [p for p in parts if p.strip()]


def join_audio(chunks: list[np.ndarray], rate: int, pause_s: float = 0.18) -> np.ndarray:
    gap = np.zeros(int(rate * pause_s), dtype=np.float32)
    out: list[np.ndarray] = []
    for i, c in enumerate(chunks):
        if i:
            out.append(gap)
        out.append(to_mono_float(c))
    return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)


def run(
    synthesize: Callable[[dict[str, Any], str], tuple[np.ndarray, int]],
    *,
    speed_applied: bool = False,
    prepare: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Boucle commune : `prepare(req)` charge le modèle une fois, `synthesize(req, texte)` → (échantillons, fréquence)."""
    try:
        req = load_request()
        out_dir = Path(req["out_dir"])
        texts = req["texts"]
        progress(0, len(texts))
        if prepare:
            prepare(req)
        files, rate = [], 24000
        for i, text in enumerate(texts):
            samples, rate = synthesize(req, text)
            name = f"{i:04d}.wav"
            write_wav(out_dir / name, samples, rate)
            files.append(name)
            progress(i + 1, len(texts))
        (out_dir / "result.json").write_text(
            json.dumps({"rate": rate, "files": files, "speed_applied": speed_applied}), encoding="utf-8"
        )
    except Exception:  # noqa: BLE001 — le worker lit la sortie d'erreur
        traceback.print_exc()
        sys.exit(1)
