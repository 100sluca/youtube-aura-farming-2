"""Mots horodatés de ce que disent des clips (recette drame, docs/35 ; worker/drama.py, transcribe). Tourne dans
l'environnement d'évaluation du banc des voix (<YT2_HOME>/tts/eval/venv : faster-whisper, install_tts.ps1 -Engine eval),
jamais dans celui du worker : Whisper large-v3-turbo sur le processeur (int8, ≈ 1,6 Go de RAM).

Entrée : request.json {"files": [clips .mp4 ou .wav], "lang": "fr", "out": chemin du résultat, "model"?, "threads"?}.
Sortie : {"results": [{"file", "text", "words": [{"w", "start", "end", "p"}], "speech": [[début, fin], …]}]} ;
« PROGRESS <fait> <total> » sur la sortie standard. Les fichiers vidéo sont lus directement (PyAV, inclus dans
faster-whisper). `speech` : les passages parlés d'après le détecteur de voix Silero livré avec faster-whisper, plus
justes que les mots de Whisper au début d'une phrase (le premier mot part souvent de 0 s) ; ils calent la voix des
personnages sur la bouche des clips (worker/lipsync.py).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SR = 16000


def main() -> None:
    req = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    model = WhisperModel(req.get("model", "large-v3-turbo"), device="cpu", compute_type="int8",
                         cpu_threads=int(req.get("threads", 8)))
    # une pause de 0,2 s sépare deux phrases ; 30 ms de marge ; un souffle de moins de 0,12 s n'est pas une phrase
    vad = VadOptions(threshold=0.5, min_silence_duration_ms=200, speech_pad_ms=30, min_speech_duration_ms=120)
    files = list(req["files"])
    results = []
    for i, path in enumerate(files):
        segments, _info = model.transcribe(path, language=req.get("lang", "fr"), word_timestamps=True, vad_filter=False,
                                           beam_size=5, condition_on_previous_text=False)
        words = [{"w": w.word.strip(), "start": round(float(w.start), 3), "end": round(float(w.end), 3),
                  "p": round(float(w.probability), 3)}
                 for seg in segments for w in (seg.words or []) if w.word.strip()]
        try:
            audio = decode_audio(path, sampling_rate=SR)
            speech = [[round(r["start"] / SR, 3), round(r["end"] / SR, 3)] for r in get_speech_timestamps(audio, vad)]
        except Exception:  # noqa: BLE001  un clip sans son : aucun passage parlé
            speech = []
        results.append({"file": path, "text": " ".join(w["w"] for w in words).strip(), "words": words, "speech": speech})
        print(f"PROGRESS {i + 1} {len(files)}", flush=True)
    Path(req["out"]).write_text(json.dumps({"results": results}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
