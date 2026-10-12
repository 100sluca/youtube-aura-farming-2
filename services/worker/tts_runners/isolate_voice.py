"""Voix seule d'un clip de drame (Retoucher → Plans → « Couper le son », docs/49 §13) : Demucs (htdemucs) sépare la
réplique dite par MiniMax H3 de l'ambiance et des bruits du clip ; seule la voix est gardée.

Tourne dans C:\\YouTube2\\tts\\vc\\venv (install_tts.ps1 -Engine vc), comme la conversion de voix (voice_convert.py,
dont il reprend le séparateur). request.json : {"items": [{"clip": mp4, "out": wav}], "work": dossier, "device": "cpu"}
→ chaque `out` (44,1 kHz mono, durée du clip) ; result.json : {"done": [out…], "seconds": s}.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import soundfile as sf
from voice_convert import SR, Separator, read_audio


def main(request: Path) -> None:
    req = json.loads(request.read_text(encoding="utf-8"))
    work = Path(req["work"])
    work.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    sep = Separator(req.get("device") or "cpu")
    done = []
    for k, item in enumerate(req["items"], start=1):
        clip, out = Path(item["clip"]), Path(item["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        voc, _ = sep.split(read_audio(clip, work))
        sf.write(str(out), voc.mean(0), SR)
        done.append(str(out))
        print(f"[{k}/{len(req['items'])}] {clip.name} → {out.name}", file=sys.stderr, flush=True)
    (request.parent / "result.json").write_text(
        json.dumps({"done": done, "seconds": round(time.perf_counter() - started, 1)}), encoding="utf-8"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
