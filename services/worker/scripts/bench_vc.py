"""Banc « voix fixes » des drames (docs/49 §12) : chaque réplique jouée par MiniMax H3, avec le timbre de référence de
son personnage, pour deux références :
- « dessinée » : la voix Qwen du personnage (catalog.json → params.ref, « garçon timide »…), la même d'un épisode à
  l'autre ;
- « h3 » : la voix H3 du meilleur clip du personnage (réplique la mieux entendue, la plus longue).
Puis une vidéo par référence, sur les mêmes clips (copie de la production, voix des clips, les répliques converties à la
place du son des clips), à comparer dans la Bibliothèque avec l'originale. Les fichiers restent dans
C:\\YouTube2\\bench\\<date>-voix-fixes (Bibliothèque → Démos et essais).

    .venv\\Scripts\\python.exe scripts\\bench_vc.py <vidéo> [--refs dessinee,h3] [--no-videos]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from worker.cli import _full_id  # noqa: E402
from worker.config import Settings  # noqa: E402
from worker.db import Db  # noqa: E402
from worker.drama import assign_voices, character_voices, line_text  # noqa: E402
from worker.hookvariant import clone, source_of  # noqa: E402
from worker.models import ScriptV1  # noqa: E402
from worker.providers.tts import tts_catalog, voice_entry  # noqa: E402

LABELS = {"dessinee": "voix dessinées", "h3": "voix H3 de référence"}


def speech_s(dialogue: dict) -> float:
    return sum(float(b) - float(a) for a, b in (dialogue.get("speech") or []))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--refs", default="dessinee,h3")
    ap.add_argument("--no-videos", action="store_true")
    args = ap.parse_args()
    settings = Settings()
    db = Db(settings.database_url, max_size=1)
    vid = _full_id(db, "videos", args.video)
    v, p = source_of(db, vid, voiced=False)
    script = ScriptV1.model_validate(p["script"])
    clips = {
        int(r["scene_index"]): r
        for r in db.fetch_all(
            """select distinct on (scene_index) id, scene_index, local_path, meta->'dialogue' as dialogue from assets
               where production_id = %s and kind = 'clip' order by scene_index, created_at desc""",
            (p["id"],),
        )
    }
    catalog = tts_catalog(settings)
    voices = assign_voices(script.cast, list(character_voices(catalog, v["lang"])))
    qwen_root = Path(settings.yt2_home) / "tts" / "qwen3"
    drawn, best = {}, {}
    for m in script.cast:
        entry = voice_entry(catalog, voices.get(m.key) or "") or {}
        ref = (entry.get("params") or {}).get("ref")
        if ref:
            drawn[m.key] = str(qwen_root / ref)
        lines = [
            (float((clips[s.index]["dialogue"] or {}).get("ratio") or 0), speech_s(clips[s.index]["dialogue"] or {}), s.index)
            for s in script.scenes
            if s.lines and s.lines[0].who == m.key and s.index in clips
        ]
        if lines:
            best[m.key] = clips[max(lines)[2]]["local_path"]
    out = Path(settings.yt2_home) / "bench" / f"{date.today()}-voix-fixes"
    modes = [m.strip() for m in args.refs.split(",") if m.strip()]
    items = []
    for mode in modes:
        for s in script.scenes:
            if not line_text(s) or s.index not in clips:
                continue
            who = s.lines[0].who
            ref = drawn.get(who) if mode == "dessinee" else None
            if mode == "dessinee" and not ref:
                continue
            items.append(
                {
                    "clip": clips[s.index]["local_path"],
                    "out": str(out / mode / f"plan_{s.index + 1:02d}.wav"),
                    "reference": ref,
                    "reference_clip": best.get(who) if mode == "h3" else None,
                    "scene": s.index,
                    "mode": mode,
                }
            )
    out.mkdir(parents=True, exist_ok=True)
    req = out / "request.json"
    req.write_text(json.dumps({"items": items, "work": str(out / "work")}, ensure_ascii=False, indent=1), encoding="utf-8")
    python = Path(settings.yt2_home) / "tts" / "vc" / "venv" / "Scripts" / "python.exe"
    runner = ROOT / "tts_runners" / "voice_convert.py"
    print(f"{len(items)} répliques à convertir ({', '.join(modes)}) → {out}")
    subprocess.run([str(python), str(runner), str(req)], check=True)
    (out / "demo.json").write_text(
        json.dumps(
            {
                "title": f"Voix fixes par personnage · {v['title']}",
                "description": "Banc du "
                + date.today().strftime("%d/%m")
                + " (docs/49 §12) : chaque réplique jouée par MiniMax H3, convertie (Demucs + Chatterbox VC) vers une voix de "
                "référence par personnage. Dossiers : dessinee (voix Qwen du personnage), h3 (voix H3 de son meilleur clip) ; "
                "*.voix.wav = la voix seule.",
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    if args.no_videos:
        return
    for mode in modes:
        lines = {}
        for it in (i for i in items if i["mode"] == mode):
            asset = db.add_asset(
                production_id=p["id"],
                kind="take",
                scene_index=it["scene"],
                local_path=it["out"],
                meta={"source": "vc", "reference": mode, "note": f"voix convertie ({LABELS[mode]})"},
            )
            lines[str(it["scene"])] = str(asset)
        title = f"{v['title']} · {LABELS[mode]}"[:100]
        made = clone(db, settings.data_dir, v, p, script, title, None, [], clip_voices=True, extra_retouch={"lines": lines})
        print(f"{LABELS[mode]} : vidéo {made.video_id} (montage → contrôle en file)")


if __name__ == "__main__":
    main()
