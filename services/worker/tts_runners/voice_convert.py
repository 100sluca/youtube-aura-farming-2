"""Conversion de voix des drames (docs/49 §12) : la réplique que MiniMax H3 a jouée dans un clip, avec le timbre de
référence du personnage, sans toucher à son jeu (rythme, émotion, et donc le calage sur les lèvres).

Demandé par Luca le 01/10 : les voix des clips sont excellentes, mais H3 change la voix d'un même personnage d'un clip à
l'autre. Pour chaque clip :
1. Demucs (htdemucs) sépare la voix de l'ambiance ;
2. Chatterbox VC (Resemble AI, MIT) donne à la voix le timbre de la référence : une voix dessinée (Qwen, « garçon
   timide ») ou la voix H3 du meilleur clip du personnage (séparée elle aussi) ;
3. la voix convertie, ramenée à la longueur et au niveau de la voix d'origine, est remélangée à l'ambiance.

Tourne dans C:\\YouTube2\\tts\\vc\\venv (install_tts.ps1 -Engine vc). request.json :
{"items": [{"clip": mp4, "out": wav, "reference": wav | null, "reference_clip": mp4 | null, "clean": bool}],
 "work": dossier, "device": "cuda"} → chaque `out` (44,1 kHz stéréo, durée du clip), plus <out>.voix.wav (la voix
convertie seule) ; result.json : {"done": [out…], "seconds": s}.
`clean` : voix enregistrée seule (Studio voix des vidéos longues, docs/63 §4) : pas de séparation par Demucs, qui
n'a rien à retirer et abîmerait le timbre.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

SR = 44100


def read_audio(path: Path, work: Path) -> np.ndarray:
    """Le son d'un fichier (clip mp4 ou wav), 44,1 kHz stéréo, (2, N) float32."""
    wav = work / f"{path.stem}.src.wav"
    if not wav.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-vn", "-ac", "2", "-ar", str(SR), str(wav)], check=True)
    x, _ = sf.read(str(wav), dtype="float32", always_2d=True)
    return x.T.copy()


class Separator:
    def __init__(self, device: str) -> None:
        from demucs.pretrained import get_model

        self.model = get_model("htdemucs").to(device).eval()
        self.device = device
        self.vocals = self.model.sources.index("vocals")

    def split(self, audio: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(voix, reste) d'un son (2, N)."""
        from demucs.apply import apply_model

        mix = torch.from_numpy(audio)[None].to(self.device)
        ref = mix.mean(1)  # normalisation comme demucs.separate
        mean, std = ref.mean(), ref.std() + 1e-8
        with torch.no_grad():
            out = apply_model(self.model, (mix - mean) / std, device=self.device, split=True, overlap=0.25)[0]
        out = out * std + mean
        voc = out[self.vocals].cpu().numpy()
        rest = (out.sum(0) - out[self.vocals]).cpu().numpy()
        return voc, rest


def rms(x: np.ndarray) -> float:
    v = x[np.abs(x) > 1e-4]
    return float(np.sqrt(np.mean(v**2))) if v.size else 0.0


def main(request: Path) -> None:
    req = json.loads(request.read_text(encoding="utf-8"))
    work = Path(req["work"])
    work.mkdir(parents=True, exist_ok=True)
    device = req.get("device") or ("cuda" if torch.cuda.is_available() else "cpu")
    started = time.perf_counter()
    seps: list[Separator] = []

    def sep() -> Separator:  # chargé au premier clip à séparer seulement
        if not seps:
            seps.append(Separator(device))
        return seps[0]

    from chatterbox.vc import ChatterboxVC

    vc = ChatterboxVC.from_pretrained(device)
    refs: dict[str, Path] = {}
    done = []
    for k, item in enumerate(req["items"], start=1):
        clip, out = Path(item["clip"]), Path(item["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        ref = item.get("reference")
        if not ref:  # la voix H3 du meilleur clip du personnage, séparée de son ambiance
            src = str(item["reference_clip"])
            if src not in refs:
                voc, _ = sep().split(read_audio(Path(src), work))
                refs[src] = work / f"{Path(src).stem}.ref.wav"
                sf.write(str(refs[src]), voc.mean(0), SR)
            ref = str(refs[src])
        audio = read_audio(clip, work)
        if item.get("clean"):
            voc, rest = audio, np.zeros_like(audio)
        else:
            voc, rest = sep().split(audio)
        voc_path = work / f"{clip.stem}.voc.wav"
        sf.write(str(voc_path), voc.mean(0), SR)
        wav = vc.generate(str(voc_path), target_voice_path=str(ref))
        conv = wav.squeeze(0).cpu().numpy().astype(np.float32)
        conv = np.interp(np.linspace(0, len(conv) - 1, int(len(conv) * SR / vc.sr)), np.arange(len(conv)), conv)
        n = voc.shape[1]
        conv = np.pad(conv, (0, max(0, n - len(conv))))[:n]
        gain = rms(voc.mean(0)) / max(rms(conv), 1e-6)  # même niveau que la voix d'origine
        conv = (conv * gain).astype(np.float32)
        sf.write(str(out.with_suffix(".voix.wav")), conv, SR)
        mixed = np.clip(rest + conv[None, :], -1.0, 1.0)
        sf.write(str(out), mixed.T, SR)
        done.append(str(out))
        print(f"[{k}/{len(req['items'])}] {clip.name} → {out.name}", file=sys.stderr, flush=True)
    (request.parent / "result.json").write_text(
        json.dumps({"done": done, "seconds": round(time.perf_counter() - started, 1)}), encoding="utf-8"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
