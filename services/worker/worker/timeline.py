"""Timeline de narration : place la voix scène par scène et horodate chaque mot.

Le step tts synthétise la narration de chaque scène séparément (au lieu d'un seul bloc) : on connaît
ainsi exactement où commence chaque scène, et la voix reste synchronisée avec l'image. Si une phrase
est plus longue que la scène prévue, la scène est allongée (le montage ralentit légèrement le clip).

Fonctions pures, testables sans audio : plan_timeline() calcule durées et mots ; mix_speech() et
trim_silence() manipulent les échantillons (numpy, présent avec l'extra « tts »).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .models import NarrationTimeline, SceneTiming
from .numbers import spoken
from .subtitles import distribute_words

LEAD_IN = 0.15  # silence avant la voix, au début de chaque scène
TAIL = 0.30  # respiration après la voix, avant la coupe
# Débit de la voix : estimation hors audio (mode DRY_RUN) et plafond de mots par scène du correcteur. Mesuré le 28/09 :
# 3,2 mots/s pour Qwen3-TTS « mystère » à 1,05 (canal Rhin-Main-Danube) ; à 2,6, les scènes de 5 s gardaient 1,4 s de
# blanc chacune et le récit manquait de rythme.
WORDS_PER_SECOND = 3.0


@dataclass(frozen=True)
class SceneSpeech:
    index: int
    planned_s: float  # durée prévue par le script
    text: str  # narration de la scène dans la langue de la vidéo ("" = pas de voix)
    speech_s: float | None  # durée de la voix, silences retirés (None = pas de voix)


def estimate_speech_s(text: str, lang: str = "fr") -> float | None:
    words = len(spoken(text, lang).split())  # « 1992 » se dit en 5 mots (worker/numbers.py)
    return round(words / WORDS_PER_SECOND, 3) if words else None


def plan_timeline(scenes: Sequence[SceneSpeech], lang: str, aligner: str = "proportional") -> NarrationTimeline:
    """Durées effectives des scènes et mots horodatés (temps absolus sur la vidéo)."""
    out: list[SceneTiming] = []
    t = 0.0
    for s in scenes:
        if s.speech_s and s.text.strip():
            duration = max(s.planned_s, LEAD_IN + s.speech_s + TAIL)
            a, b = t + LEAD_IN, t + LEAD_IN + s.speech_s
            out.append(
                SceneTiming(
                    index=s.index,
                    start=round(t, 3),
                    duration=round(duration, 3),
                    speech_start=round(a, 3),
                    speech_end=round(b, 3),
                    words=distribute_words(s.text, a, b, lang),
                )
            )
        else:
            duration = s.planned_s
            out.append(SceneTiming(index=s.index, start=round(t, 3), duration=round(duration, 3)))
        t += duration
    return NarrationTimeline(lang=lang, aligner=aligner, scenes=out)  # type: ignore[arg-type]


def trim_silence(samples: Any, rate: int, threshold: float = 0.012, pad_s: float = 0.02) -> Any:
    """Retire les silences de début et de fin (énergie RMS sur des fenêtres de 10 ms)."""
    import numpy as np

    x = np.asarray(samples, dtype=np.float32).reshape(-1)
    win = max(1, rate // 100)
    n = len(x) // win
    if n == 0:
        return x
    rms = np.sqrt(np.mean(x[: n * win].reshape(n, win) ** 2, axis=1))
    voiced = np.nonzero(rms > threshold)[0]
    if len(voiced) == 0:
        return x
    pad = int(pad_s * rate)
    a = max(0, voiced[0] * win - pad)
    b = min(len(x), (voiced[-1] + 1) * win + pad)
    return x[a:b]


def mix_speech(timeline: NarrationTimeline, speeches: dict[int, Any], rate: int) -> Any:
    """Construit la piste de narration complète : chaque voix posée au début de sa scène (+ LEAD_IN)."""
    import numpy as np

    total = int(round(timeline.duration_s * rate)) + 1
    track = np.zeros(total, dtype=np.float32)
    for sc in timeline.scenes:
        x = speeches.get(sc.index)
        if x is None or sc.speech_start is None:
            continue
        a = int(round(sc.speech_start * rate))
        x = np.asarray(x, dtype=np.float32)[: max(0, total - a)]
        track[a : a + len(x)] += x
    return np.clip(track, -1.0, 1.0)
