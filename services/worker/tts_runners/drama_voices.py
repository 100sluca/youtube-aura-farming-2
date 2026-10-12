"""Voix des clips d'un drame, au montage (docs/70 §6) : une voix fixe par personnage et des plans muets vraiment muets,
sans toucher au jeu de MiniMax H3 (rythme, émotion, calage sur les lèvres) ni à l'ambiance de ses clips.

Demandé par Luca le 12/10 : garder les voix faites avec la vidéo (tout est cohérent : voix, bruitages, ambiance), mais
la voix d'un personnage ne doit pas changer d'un plan à l'autre, et les plans sans réplique ne doivent pas parler
anglais. Deux actions, dans une même requête :
- `split` : Demucs (htdemucs) sépare la voix (mono) de l'ambiance (stéréo) d'un clip ;
- `convert` : Chatterbox VC donne à une voix séparée le timbre d'une référence (les meilleures répliques H3 du
  personnage mises bout à bout : `reference_parts`, construite une fois par `reference_key`), la ramène à la longueur
  et au niveau d'origine, puis la remélange à l'ambiance du clip.

Tourne dans C:\\YouTube2\\tts\\vc\\venv (install_tts.ps1 -Engine vc), comme voice_convert.py dont il reprend le
séparateur. request.json :
{"split": [{"clip": mp4, "voice": wav, "rest": wav}], "convert": [{"voice": wav, "rest": wav, "reference": wav |
 "reference_parts": [{"file": wav, "spans": [[début, fin], …]}], "reference_key": str, "out": wav}],
 "reference_max_s": 15, "work": dossier, "device": "auto" | "cuda" | "cpu"}
→ result.json : {"split": [voice…], "convert": [out…], "device": …, "seconds": s}.
`auto` : la carte graphique si elle a au moins 3 Go libres (ComfyUI y fait souvent tourner H3), sinon le processeur.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from voice_convert import SR, Separator, read_audio, rms

FREE_GPU_MIN = 3 * 1024**3
GAP_S = 0.25  # silence entre deux répliques de la référence


def build_reference(parts: list[dict], out: Path, max_s: float) -> Path:
    """Référence d'un personnage : les passages parlés de ses répliques (voix séparées), bout à bout, `max_s` au plus."""
    chunks, total = [], 0.0
    for part in parts:
        v, sr = sf.read(part["file"], dtype="float32")
        v = v if v.ndim == 1 else v.mean(1)
        for a, b in part.get("spans") or [[0.0, len(v) / sr]]:
            seg = v[int(a * sr) : int(b * sr)]
            if len(seg) == 0:
                continue
            chunks += [seg, np.zeros(int(GAP_S * sr), np.float32)]
            total += len(seg) / sr
        if total >= max_s:
            break
    sf.write(str(out), np.concatenate(chunks) if chunks else np.zeros(SR, np.float32), SR)
    return out


def pick_device(wanted: str | None) -> str:
    if wanted in ("cuda", "cpu"):
        return wanted if wanted == "cpu" or torch.cuda.is_available() else "cpu"
    if not torch.cuda.is_available():
        return "cpu"
    try:
        free, _total = torch.cuda.mem_get_info()
    except Exception:  # noqa: BLE001
        return "cpu"
    return "cuda" if free >= FREE_GPU_MIN else "cpu"


def main(request: Path) -> None:
    req = json.loads(request.read_text(encoding="utf-8"))
    work = Path(req["work"])
    work.mkdir(parents=True, exist_ok=True)
    device = pick_device(req.get("device"))
    started = time.perf_counter()
    split_done, convert_done = [], []
    if req.get("split"):
        sep = Separator(device)
        for k, item in enumerate(req["split"], start=1):
            voc, rest = sep.split(read_audio(Path(item["clip"]), work))
            for key, data in (("voice", voc.mean(0)), ("rest", rest.T)):
                Path(item[key]).parent.mkdir(parents=True, exist_ok=True)
                sf.write(item[key], data, SR)
            split_done.append(item["voice"])
            print(f"[séparation {k}/{len(req['split'])}] {Path(item['clip']).name}", file=sys.stderr, flush=True)
        del sep
    if req.get("convert"):
        from chatterbox.vc import ChatterboxVC

        vc = ChatterboxVC.from_pretrained(device)
        built: dict[str, str] = {}
        for k, item in enumerate(req["convert"], start=1):
            ref = item.get("reference")
            if not ref:
                key = item["reference_key"]
                if key not in built:
                    built[key] = str(
                        build_reference(item["reference_parts"], work / f"ref_{key}.wav", float(req.get("reference_max_s", 15)))
                    )
                ref = built[key]
            voc, _ = sf.read(item["voice"], dtype="float32")
            rest, _ = sf.read(item["rest"], dtype="float32", always_2d=True)
            voc = voc if voc.ndim == 1 else voc.mean(1)
            wav = vc.generate(item["voice"], target_voice_path=ref)
            conv = wav.squeeze(0).cpu().numpy().astype(np.float32)
            conv = np.interp(np.linspace(0, len(conv) - 1, int(len(conv) * SR / vc.sr)), np.arange(len(conv)), conv)
            n = len(voc)
            conv = np.pad(conv, (0, max(0, n - len(conv))))[:n]
            conv = (conv * (rms(voc) / max(rms(conv), 1e-6))).astype(np.float32)  # même niveau que la voix d'origine
            rest = np.pad(rest, ((0, max(0, n - len(rest))), (0, 0)))[:n]
            mixed = np.clip(rest + conv[:, None], -1.0, 1.0)
            Path(item["out"]).parent.mkdir(parents=True, exist_ok=True)
            sf.write(item["out"], mixed, SR)
            convert_done.append(item["out"])
            print(f"[conversion {k}/{len(req['convert'])}] {Path(item['voice']).name}", file=sys.stderr, flush=True)
    (request.parent / "result.json").write_text(
        json.dumps(
            {
                "split": split_done,
                "convert": convert_done,
                "device": device,
                "seconds": round(time.perf_counter() - started, 1),
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
