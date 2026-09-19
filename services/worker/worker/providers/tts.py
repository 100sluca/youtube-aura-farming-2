"""TTS : Kokoro (local, CPU) par défaut. Sortie wav 24 kHz mono."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..config import Settings


@dataclass
class AudioInfo:
    duration_s: float
    voice: str


class TTS(Protocol):
    name: str

    def synthesize(self, text: str, *, lang: str, out_path: Path, dry_run: bool = False) -> AudioInfo: ...


class KokoroTTS:
    name = "kokoro"

    def __init__(self, settings: Settings) -> None:
        self.voices = {"fr": settings.kokoro_voice_fr, "en": settings.kokoro_voice_en}

    def synthesize(self, text: str, *, lang: str, out_path: Path, dry_run: bool = False) -> AudioInfo:
        voice = self.voices[lang]
        if dry_run:
            out_path.write_bytes(b"")
            return AudioInfo(duration_s=len(text.split()) / 2.6, voice=voice)
        import soundfile as sf
        from kokoro_onnx import Kokoro

        kokoro = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")  # fichiers dans services/worker/models/
        samples, rate = kokoro.create(text, voice=voice, speed=1.05, lang="fr-fr" if lang == "fr" else "en-us")
        sf.write(str(out_path), samples, rate)
        return AudioInfo(duration_s=len(samples) / rate, voice=voice)


def get_tts(settings: Settings) -> TTS:
    if settings.tts_provider == "kokoro":
        return KokoroTTS(settings)
    raise NotImplementedError(f"TTS {settings.tts_provider} non implémenté (chatterbox, elevenlabs : phase 3)")
