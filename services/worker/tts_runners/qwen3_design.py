"""Crée les voix de référence de Qwen3-TTS avec le modèle VoiceDesign 1.7B, d'après leur description (docs/18-voix.md).

Une voix « dessinée » n'imite personne : c'est ce qui la rend utilisable sans l'accord de qui que ce soit (la voix est
un attribut de la personnalité, Cour de cassation, 24/06/2026). Chaque voix « qwen3:<nom> » du catalogue porte dans
params : design.instruct (description, en anglais), design.seed, ref_text (la phrase que la voix prononce) et ref (wav
de sortie, relatif au dossier du moteur). Pour chacune, 3 essais (graines seed, seed+1, seed+2) ; on garde celui
dont le débit est le plus proche de design.cps caractères par seconde (17 par défaut : narration posée ; Kokoro dit
≈ 21 car./s à vitesse 1) : un essai raté saute ou répète des mots, ce qui se voit à la durée. Les essais restent dans
voices/_essais/ pour en choisir un autre à l'oreille.

    C:\\YouTube2\\tts\\qwen3\\venv\\Scripts\\python.exe tts_runners\\qwen3_design.py services\\worker\\workflows\\catalog.json
        [--force] [--only narrateur,narratrice] [--engine-dir C:\\YouTube2\\tts\\qwen3] [--free-comfy URL]

À lancer quand la carte graphique est libre (≈ 5 Go de VRAM) ; --free-comfy vide d'abord la mémoire de ComfyUI.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from _common import write_wav  # noqa: E402

TARGET_CPS = 17.0  # caractères par seconde d'une narration française posée (design.cps le change voix par voix)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("catalog")
    ap.add_argument("--engine-dir", default="C:/YouTube2/tts/qwen3")
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--free-comfy", default="")
    args = ap.parse_args()

    engine_dir = Path(args.engine_dir)
    only = {n for n in args.only.split(",") if n}
    catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    todo = []
    for lang, voices in catalog.get("voices", {}).items():
        for v in voices:
            engine, _, name = v["id"].partition(":")
            params = v.get("params") or {}
            if engine != "qwen3" or not params.get("design") or (only and name not in only):
                continue
            if (engine_dir / params["ref"]).exists() and not args.force:
                print(f"déjà là : {name}")
                continue
            todo.append((lang, name, params))
    if not todo:
        print("rien à faire")
        return

    if args.free_comfy:
        req = urllib.request.Request(
            f"{args.free_comfy.rstrip('/')}/free",
            data=b'{"unload_models": true, "free_memory": true}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=30)
            time.sleep(3)
        except OSError as exc:
            print(f"ComfyUI injoignable ({exc}) : on continue")

    import torch
    from qwen_tts import Qwen3TTSModel

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    t0 = time.monotonic()
    model = Qwen3TTSModel.from_pretrained(
        str(engine_dir / "models" / "Qwen3-TTS-12Hz-1.7B-VoiceDesign"),
        device_map=device,
        dtype=torch.bfloat16 if device.startswith("cuda") else torch.float32,
        attn_implementation="sdpa",
    )
    print(f"VoiceDesign chargé sur {device} en {time.monotonic() - t0:.0f} s", flush=True)
    trials_dir = engine_dir / "voices" / "_essais"
    trials_dir.mkdir(parents=True, exist_ok=True)
    language = {"fr": "French", "en": "English"}
    for lang, name, params in todo:
        text, design = params["ref_text"], params["design"]
        best = None
        for k in range(args.tries):
            seed = int(design.get("seed", 1234)) + k
            torch.manual_seed(seed)
            t1 = time.monotonic()
            wavs, rate = model.generate_voice_design(
                text=text, instruct=design["instruct"], language=language.get(lang, "French")
            )
            audio = np.asarray(wavs[0], dtype=np.float32)
            seconds = len(audio) / rate
            cps = len(text) / max(seconds, 0.1)
            write_wav(trials_dir / f"{name}_{seed}.wav", audio, rate)
            print(
                f"{name} graine {seed} : {seconds:.1f} s, {cps:.1f} car./s, calculé en {time.monotonic() - t1:.0f} s", flush=True
            )
            score = abs(cps - float(design.get("cps", TARGET_CPS)))
            if best is None or score < best[0]:
                best = (score, audio, rate, seed)
        _, audio, rate, seed = best
        out = engine_dir / params["ref"]
        out.parent.mkdir(parents=True, exist_ok=True)
        write_wav(out, audio, rate)
        print(f"→ {name} : graine {seed} retenue ({out})", flush=True)
    if device.startswith("cuda"):
        print(f"VRAM max : {torch.cuda.max_memory_allocated() / 2**30:.1f} Go")


if __name__ == "__main__":
    main()
