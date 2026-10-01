"""Outils communs aux scripts des moteurs de voix. Ils tournent dans l'environnement Python du moteur
(<YT2_HOME>/tts/<moteur>/venv), jamais dans celui du worker : seulement la bibliothèque standard et numpy ici.

Protocole (worker/providers/tts.py, VenvTTS) : le worker écrit request.json puis lance
`<venv>/Scripts/python.exe tts_runners/<moteur>.py <dossier>/request.json` ; le script écrit « PROGRESS <fait> <total> »
sur sa sortie standard, un .wav par texte dans le dossier, puis result.json {"rate", "files", "speed_applied", "load_s",
"times"} (chargement du modèle et calcul de chaque texte, en secondes : le banc d'essai les lit).
Code de sortie non nul ou result.json absent = échec (le worker affiche la fin de la sortie d'erreur).
request.json → tones (facultatif, docs/41) : comment dire chaque texte, en anglais, écrit par le scénariste d'un drame
(« whispers, trembling », « shouts furiously ») ; seul un moteur qui sait jouer une émotion s'en sert.
request.json → targets (facultatif, docs/41 §8) : durée visée de chaque texte en secondes de voix (le temps où la bouche
du clip dit la réplique), null si inconnue ; seul un moteur qui sait régler son débit s'en sert (Gemini).
"""

from __future__ import annotations

import json
import re
import sys
import time
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


# Ton d'une réplique (anglais libre, écrit par le scénariste) → émotion d'une voix de référence (docs/41). Règles dans
# l'ordre, la première qui trouve un de ses mots l'emporte : les larmes et le chuchotement s'entendent avant tout le reste
# (« desperate, crying » est d'abord en larmes, « whispering, furious » d'abord chuchoté).
EMOTION_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("tristesse", ("cry", "crying", "tears", "sob", "weep")),
    ("chuchote", ("whisper", "murmur", "barely audible", "hushed")),
    ("joie", ("overjoyed", "joy", "happy", "excited", "delighted", "laugh", "thrilled")),
    ("colere", ("furious", "angry", "anger", "rage", "shout", "yell", "scream")),
    ("peur", ("terrified", "scared", "afraid", "fear", "trembling", "panic", "nervous", "desperate", "shaking")),
    ("froid", ("cold", "icy", "contempt", "disdain", "threat", "stern", "disgust", "haughty")),
    ("moqueur", ("mocking", "sarcas", "smug", "sly", "mischiev", "fake", "falsely", "greedy", "jealous", "teasing")),
    ("surprise", ("surprised", "stunned", "shocked", "disbelief", "gasp")),
    ("tristesse", ("sad", "broken", "nostalgic", "weak", "ashamed", "sorrow", "grief")),
    ("tendre", ("kind", "gentle", "tender", "moved", "emotional", "warm", "proud", "loving", "amused", "shy")),
]


def plausible(text: str, samples: Any, rate: int, lo: float = 6.0, hi: float = 28.0) -> bool:
    """Débit plausible (caractères par seconde de voix) : un modèle qui clone parfois ajoute des mots, répète la phrase
    de sa référence ou s'arrête net ; la durée le trahit. Une réplique en larmes ou chuchotée reste au-dessus de 6."""
    seconds = len(to_mono_float(samples)) / max(1, int(rate))
    return lo <= len(text.strip()) / max(seconds, 0.05) <= hi


def voiced_seconds(samples: Any, rate: int, rel: float = 0.05) -> float:
    """Durée de la voix, du premier au dernier son audible (les blancs du début et de la fin ne comptent pas : l'étape
    voix les retire avant de caler la réplique)."""
    x = to_mono_float(samples)
    hop = max(1, int(rate * 0.01))
    if len(x) < hop * 3:
        return len(x) / max(1, rate)
    frames = x[: len(x) // hop * hop].reshape(-1, hop)
    rms = np.sqrt((frames**2).mean(axis=1))
    loud = np.nonzero(rms >= rel * max(float(rms.max()), 1e-6))[0]
    return float((loud[-1] - loud[0] + 1) * hop / rate) if len(loud) else 0.0


def emotion_of(tone: str) -> str:
    """« whispering, greedy » → « chuchote » ; un ton vide ou calme (« calm, certain ») → « neutre »."""
    t = (tone or "").lower()
    for label, words in EMOTION_RULES:
        if any(w in t for w in words):
            return label
    return "neutre"


def run(
    synthesize: Callable[..., tuple[np.ndarray, int]],
    *,
    speed_applied: bool = False,
    prepare: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Boucle commune : `prepare(req)` charge le modèle une fois, `synthesize(req, texte)` → (échantillons, fréquence).
    Un `synthesize(req, texte, ton)` à trois paramètres reçoit en plus le ton du texte (request.json → tones, "" sinon) ;
    à quatre, `synthesize(req, texte, ton, visée)` reçoit aussi la durée visée (request.json → targets, None sinon)."""
    try:
        req = load_request()
        out_dir = Path(req["out_dir"])
        texts = req["texts"]
        tones = [str(t or "") for t in (req.get("tones") or [])][: len(texts)]
        tones += [""] * (len(texts) - len(tones))
        targets = [float(t) if isinstance(t, int | float) and t > 0 else None for t in (req.get("targets") or [])][: len(texts)]
        targets += [None] * (len(texts) - len(targets))
        argc = synthesize.__code__.co_argcount
        progress(0, len(texts))
        started = time.perf_counter()
        if prepare:
            prepare(req)
        load_s = time.perf_counter() - started
        files, times, rate = [], [], 24000
        for i, text in enumerate(texts):
            started = time.perf_counter()
            if argc >= 4:
                samples, rate = synthesize(req, text, tones[i], targets[i])
            elif argc == 3:
                samples, rate = synthesize(req, text, tones[i])
            else:
                samples, rate = synthesize(req, text)
            times.append(round(time.perf_counter() - started, 2))
            name = f"{i:04d}.wav"
            write_wav(out_dir / name, samples, rate)
            files.append(name)
            progress(i + 1, len(texts))
        result = {"rate": rate, "files": files, "speed_applied": speed_applied, "load_s": round(load_s, 2), "times": times}
        (out_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    except Exception:  # noqa: BLE001 — le worker lit la sortie d'erreur
        traceback.print_exc()
        sys.exit(1)
