"""Benchmark local des fournisseurs vidéo : mêmes prompts, temps par clip, VRAM, sorties à comparer.

Usage (depuis services/worker, ComfyUI lancé sur COMFY_BASE_URL) :
    uv run python scripts/bench_video.py --providers comfy_wan22_i2v_4step,comfy_wan22_t2v_4step --duration 5
    uv run python scripts/bench_video.py --providers comfy_wan22_i2v_4step --prompts 1 --dry-run   # test du script

Un workflow image → vidéo (nœud IMAGE) passe d'abord par l'image de storyboard (COMFY_IMAGE_WORKFLOW,
Flux schnell GGUF par défaut) : son temps est mesuré à part (colonne image_seconds).

Sorties dans bench/<horodatage>/ : les clips (<provider>_<prompt>_<run>.mp4), results.csv et README.md
(tableau à compléter avec une note qualité 1-5 par clip après visionnage).
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from worker.config import Settings, utf8_console
from worker.providers.video import ComfyImage, get_video_provider

# (clé, prompt de l'image de départ, prompt de mouvement pour l'animation) : comme dans le pipeline, l'image
# décrit une photo, le mouvement décrit UNE action lente et lisible (docs/12 §4).
PROMPTS = [
    (
        "bookshelf_door",
        "A modern living room, a tall oak slatted bookshelf standing slightly ajar, revealing the first steps of a "
        "hidden staircase lit by warm LED strips, wide shot, photorealistic, cinematic",
        "The camera slowly pushes in toward the bookshelf while it swings open like a door on hinges, revealing "
        "the hidden staircase with warm LED light; smooth rigid motion, everything else stays still",
    ),
    (
        "pool_reveal",
        "Backyard at dusk, a luxury infinity pool with a wooden deck and underwater lights, wide static shot, photorealistic",
        "Slow rising crane shot over the pool at dusk, water gently rippling, underwater lights glowing, steady motion",
    ),
    (
        "slat_wall_led",
        "Close-up of a walnut acoustic slat wall with diffused LED strips glowing between the slats, minimalist "
        "interior, soft evening light, photorealistic",
        "Slow lateral tracking shot sliding along the slat wall, LED glow softly pulsing, shallow depth of field",
    ),
]


def gpu_mem_mb() -> int | None:
    if shutil.which("nvidia-smi") is None:
        return None
    out = (
        subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
        )
        .stdout.strip()
        .splitlines()
    )
    return int(out[0]) if out else None


class VramSampler:
    def __init__(self) -> None:
        self.peak, self._stop = 0, threading.Event()

    def __enter__(self) -> VramSampler:
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def _run(self) -> None:
        while not self._stop.wait(1):
            m = gpu_mem_mb()
            if m:
                self.peak = max(self.peak, m)

    def __exit__(self, *exc: object) -> None:
        self._stop.set()


def probe(path: Path) -> dict:
    if shutil.which("ffprobe") is None or not path.exists() or path.stat().st_size == 0:
        return {}
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True,
        text=True,
    )
    if r.returncode:
        return {}
    d = json.loads(r.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), {})
    return {"width": v.get("width"), "height": v.get("height"), "duration_s": float(d["format"].get("duration", 0))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--providers", default="comfy_wan22_i2v_4step,comfy_wan22_t2v_4step", help="liste séparée par des virgules")
    ap.add_argument("--duration", type=float, default=4.0, help="durée cible du clip (s)")
    ap.add_argument("--prompts", type=int, default=len(PROMPTS), help="nombre de prompts (1-3)")
    ap.add_argument("--runs", type=int, default=1, help="répétitions par prompt (seed différente)")
    ap.add_argument("--dry-run", action="store_true", help="ne génère rien, valide le script")
    ap.add_argument("--size", help="résolution des clips, ex. 704x1280 (défaut : VIDEO_SIZE ou la valeur native du modèle)")
    ap.add_argument("--out", help="dossier des sorties (défaut : bench/ dans le dossier courant)")
    args = ap.parse_args()
    utf8_console()

    settings = Settings()
    if args.size:
        settings.video_size = args.size
    out_dir = Path(args.out or "bench") / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    for name in [p.strip() for p in args.providers.split(",") if p.strip()]:
        provider = get_video_provider(settings, name)
        for key, image_prompt, motion_prompt in PROMPTS[: args.prompts]:
            for run in range(1, args.runs + 1):
                out = out_dir / f"{name}_{key}_{run}.mp4"
                print(f"→ {name} · {key} · run {run} · {provider.width}×{provider.height}", flush=True)
                error, image, image_s = "", None, ""
                prompt = image_prompt
                t0 = time.perf_counter()
                with VramSampler() as vram:
                    try:
                        if provider.image_to_video:  # route image → vidéo : l'image d'abord, chronométrée à part
                            image = ComfyImage(settings).generate(
                                prompt=image_prompt,
                                style_preset="modern_minimal",
                                out_path=out.with_suffix(".png"),
                                seed=run * 1000 + len(key),
                                dry_run=args.dry_run,
                            )
                            image_s = round(time.perf_counter() - t0, 1)
                            t0 = time.perf_counter()
                            prompt = motion_prompt
                        info = provider.generate(
                            prompt=prompt,
                            style_preset="modern_minimal",
                            duration_s=args.duration,
                            out_path=out,
                            on_progress=lambda p: None,
                            dry_run=args.dry_run,
                            image_path=image,
                        )
                    except Exception as exc:  # noqa: BLE001
                        info, error = None, f"{type(exc).__name__}: {exc}"[:300]
                elapsed = round(time.perf_counter() - t0, 1)
                meta = probe(out)
                rows.append(
                    {
                        "provider": name,
                        "prompt": key,
                        "run": run,
                        "image_seconds": image_s,
                        "seconds": elapsed,
                        "vram_peak_mb": vram.peak or "",
                        "width": meta.get("width", getattr(info, "width", "")),
                        "height": meta.get("height", getattr(info, "height", "")),
                        "clip_s": meta.get("duration_s", getattr(info, "duration_s", "")),
                        "file": out.name,
                        "error": error,
                        "quality_1_5": "",
                    }
                )
                print(f"   {elapsed}s · VRAM max {vram.peak} Mo · {error or 'ok'}", flush=True)

    with (out_dir / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    lines = [
        f"# Benchmark vidéo · {out_dir.name}",
        "",
        "Noter chaque clip de 1 à 5 (netteté, cohérence, respect du prompt) dans results.csv, colonne quality_1_5.",
        "",
        "| Fournisseur | Prompt | Run | Temps (s) | VRAM max (Mo) | Résolution | Durée (s) | Fichier | Erreur |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['provider']} | {r['prompt']} | {r['run']} | {r['seconds']} | {r['vram_peak_mb']} | "
            f"{r['width']}×{r['height']} | {r['clip_s']} | {r['file']} | {r['error']} |"
        )
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nRésultats : {out_dir / 'README.md'}")


if __name__ == "__main__":
    main()
