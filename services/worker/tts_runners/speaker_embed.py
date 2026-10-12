"""Empreinte de voix de chaque réplique d'un drame (docs/70 §6) : un vecteur par fichier (WeSpeaker ResNet34 de
sherpa-onnx, celui du banc docs/49 §12), sur les seuls passages parlés, pour savoir si la voix d'un personnage change
d'un plan à l'autre (worker/clip_voices.py).

Tourne dans l'environnement d'évaluation (<YT2_HOME>/tts/eval/venv : faster-whisper, sherpa-onnx ; modèle
<YT2_HOME>/tts/eval/models/speaker.onnx). request.json : {"items": [{"file": wav ou mp4, "spans": [[début, fin], …]}],
"model": chemin du modèle, "out": chemin du résultat} → {"embeddings": [[…] | null, …]} (vecteurs normés ; null si le
fichier n'a pas assez de voix).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

SR = 16000
MIN_S = 0.6  # moins de voix que ça : l'empreinte ne veut rien dire


def main(request: Path) -> None:
    req = json.loads(request.read_text(encoding="utf-8"))
    import sherpa_onnx
    from faster_whisper.audio import decode_audio

    ext = sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(req["model"]), num_threads=4)
    )
    out = []
    for item in req["items"]:
        try:
            audio = decode_audio(item["file"], sampling_rate=SR)
        except Exception:  # noqa: BLE001
            out.append(None)
            continue
        spans = item.get("spans") or []
        parts = [audio[int(a * SR) : int(b * SR)] for a, b in spans if b > a]
        x = np.concatenate(parts) if parts else audio
        if len(x) < MIN_S * SR:
            x = audio
        if len(x) < MIN_S * SR:
            out.append(None)
            continue
        st = ext.create_stream()
        st.accept_waveform(SR, x.astype(np.float32))
        st.input_finished()
        v = np.array(ext.compute(st), dtype=np.float64)
        out.append((v / (np.linalg.norm(v) + 1e-9)).round(6).tolist())
    Path(req["out"]).write_text(json.dumps({"embeddings": out}), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
