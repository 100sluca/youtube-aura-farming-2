"""Essai de voix (Réglages → Modèles de génération, bouton « Écouter ») : une phrase dite par la voix choisie, hors de
toute production. Le fichier va dans DATA_DIR/previews/voices/<job>.wav, son chemin dans jobs.result.path, que la route
/api/voice-preview/<job> du dashboard sert au lecteur audio (docs/18-voix.md)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..providers.tts import get_engine, split_voice
from ..timeline import trim_silence
from .base import Context, Step

# Phrase par défaut : ton des séries narrées (accroche, chiffres, liaisons)
SAMPLES = {
    "fr": "Derrière ce miroir se cache une pièce que personne n'avait vue depuis 120 ans. "
          "Regardez bien ce qui se passe quand on l'ouvre.",
    "en": "Behind this mirror hides a room nobody had seen for 120 years. "
          "Watch closely what happens when we open it.",
}
MAX_CHARS = 600
KEEP = 40  # essais gardés sur le disque, les plus récents


class VoicePreviewStep(Step):
    type = "voice_preview"
    lane = "gpu"  # même voie que la narration (moteurs PyTorch) ; le dashboard le met en tête de file (priorité 5)

    def run(self, ctx: Context) -> dict[str, Any]:
        p = ctx.job.payload or {}
        lang = p.get("lang") if p.get("lang") in SAMPLES else "fr"
        engine_name, voice = split_voice(str(p.get("voice") or ""))
        text = " ".join(str(p.get("text") or "").split())[:MAX_CHARS] or SAMPLES[lang]
        speed = float(p.get("speed") or ctx.settings.kokoro_speed)
        out_dir = ctx.settings.data_dir / "previews" / "voices"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{ctx.job.id}.wav"

        tts = get_engine(ctx.settings, engine_name)
        started = time.monotonic()
        ctx.progress(5, f"{tts.name} · chargement du modèle")
        if ctx.settings.dry_run:
            out.write_bytes(b"")
            duration = 0.0
        else:
            import soundfile as sf

            [speech] = tts.speak_many([text], voice=voice, lang=lang, speed=speed,
                                      on_progress=lambda pct, label: ctx.progress(5 + int(0.9 * pct), label))
            samples = trim_silence(speech.samples, speech.rate)
            sf.write(str(out), samples, speech.rate)
            duration = len(samples) / speech.rate
        _prune(out_dir)
        return {
            "path": str(out), "voice": f"{engine_name}:{voice}", "engine": tts.name, "lang": lang, "text": text,
            "speed": speed, "duration_s": round(duration, 2), "elapsed_s": round(time.monotonic() - started, 1),
        }


def _prune(folder: Path) -> None:
    files = sorted(folder.glob("*.wav"), key=lambda f: f.stat().st_mtime, reverse=True)
    for old in files[KEEP:]:
        old.unlink(missing_ok=True)
