"""Produire une vidéo des formats visuels (docs/15) à partir d'un script écrit à la main, EN PASSANT PAR L'APP :
le script (même forme que la sortie de l'agent script, scripts/demo/*.json) devient une vraie production de la
série (concept + production + job script), que le worker fabrique comme les autres. Elle apparaît dans le
dashboard (Production : storyboard à valider, puis vidéo à autoriser), comme demandé par Luca le 25/09 : plus
aucune vidéo fabriquée hors de la base.

Usage (depuis services/worker, .env exporté, worker lancé) :
    uv run python scripts/demo_formats.py scripts/demo/timelapse_refuge.json
    uv run python scripts/demo_formats.py scripts/demo/visite_chalet.json --series visites_luxe
    uv run python scripts/demo_formats.py scripts/demo/drama_valise_madame_figue.json --series karma_fruits
La série par défaut est celle de la recette (chantiers_timelapse, visites_luxe ou karma_fruits, d'après --recipe ou la
forme du script : un script avec une distribution `cast` est un drame, docs/35). Le script est normalisé
(normalize_script) et vérifié (lint_recipe_script) avant d'être enregistré.

Reprendre un essai déjà calculé (images clés, clips) : --keyframes "<motif>" et --clips "<motif>" (motifs de
fichiers, triés par nom = ordre des scènes). Les images sont rattachées à la production comme storyboard retenu,
contrôlées par le modèle de vision (assets.meta.qc), les clips comme clips des scènes : le worker ne les refait pas,
la production attend la validation du storyboard dans l'app, puis le montage part tout de suite.
"""

from __future__ import annotations

import argparse
import glob
import json
import shutil
from pathlib import Path

from psycopg.types.json import Jsonb

from worker.config import Settings, utf8_console
from worker.db import Db
from worker.keyframe_qc import check_keyframe
from worker.media import probe_duration
from worker.models import ScriptV1
from worker.providers.llm import get_vision_llm
from worker.recipes import edit_source, lint_recipe_script, normalize_script

SERIES = {"timelapse": "chantiers_timelapse", "tour": "visites_luxe", "drama": "karma_fruits"}


def _files(pattern: str | None, n: int, what: str) -> list[Path]:
    if not pattern:
        return []
    files = sorted(Path(p) for p in glob.glob(pattern))
    if len(files) != n:
        raise SystemExit(f"{what} : {len(files)} fichiers pour {n} scènes ({pattern})")
    return files


def main() -> None:
    utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--recipe", choices=["timelapse", "tour", "drama"],
                    help="défaut : drama si le script a une distribution (cast), tour s'il a une vue (view), sinon timelapse")
    ap.add_argument("--series", help="slug de la série (défaut : celle de la recette)")
    ap.add_argument("--lang", default="fr")
    ap.add_argument("--keyframes", help="motif des images clés d'un essai à reprendre (une par scène, passages exceptés)")
    ap.add_argument("--clips", help="motif des clips d'un essai à reprendre (un par scène, passages compris, dans l'ordre)")
    args = ap.parse_args()

    raw = ScriptV1.model_validate(json.loads(Path(args.script).read_text(encoding="utf-8")))
    recipe = args.recipe or ("drama" if raw.cast else "tour" if raw.view else "timelapse")
    script = normalize_script(raw, recipe)
    issues = lint_recipe_script(script, recipe, [args.lang])
    print("Script :", "conforme" if not issues else "; ".join(issues))
    with_image = [i for i, sc in enumerate(script.scenes) if not sc.passage]  # un passage n'a pas d'image clé
    keys = _files(args.keyframes, len(with_image), "images clés")
    clips = _files(args.clips, len(script.scenes), "clips")

    settings = Settings()
    db = Db(settings.database_url)
    series = db.fetch_one("select id, slug, recipe, format, target_duration_s, style_preset from series where slug = %s",
                          (args.series or SERIES[recipe],))
    if not series:
        raise SystemExit(f"série introuvable : {args.series or SERIES[recipe]}")
    if series["recipe"] != recipe:
        raise SystemExit(f"la série {series['slug']} suit la recette {series['recipe']}, pas {recipe}")
    meta = script.metadata.get(args.lang)  # type: ignore[call-overload]
    title = meta.title if meta else Path(args.script).stem
    # Drame : la prémisse est la description de la vidéo, les temps visuels sont les répliques (« Kiwi : … »)
    premise = (meta.description if meta else None) if recipe == "drama" else script.design_bible
    beats = [sc.narration.get(args.lang, "") if recipe == "drama" else sc.on_screen_text.get(args.lang, "")  # type: ignore[call-overload]
             for sc in script.scenes]
    concept = db.fetch_one(
        """insert into concepts (title, hook, premise, visual_beats, source, status, series_id)
           values (%s, %s, %s, %s, 'manual', 'used', %s) returning id""",
        (title, script.hook_title.get(args.lang), premise, Jsonb(beats), series["id"]),  # type: ignore[call-overload]
    )
    prod = db.fetch_one(
        """insert into productions (concept_id, series_id, channel_id, format, target_duration_s, style_preset, status, script, lint)
           values (%s, %s, (select id from channels where is_active order by created_at limit 1), %s, %s, %s, 'draft', %s, %s)
           returning id""",
        (concept["id"], series["id"], series["format"], round(script.duration_s), series["style_preset"],
         Jsonb(script.model_dump()), Jsonb(issues)),
    )
    pdir = settings.data_dir / "productions" / str(prod["id"])
    if keys:  # storyboard repris : chaque image contrôlée comme le ferait le worker
        (pdir / "storyboard").mkdir(parents=True, exist_ok=True)
        qc = get_vision_llm(settings, db)
        copied: dict[int, Path] = {}
        for i, src in zip(with_image, keys, strict=True):
            dst = pdir / "storyboard" / f"scene_{i:02d}_essai{src.suffix}"
            shutil.copy2(src, dst)
            copied[i] = dst
        for i, dst in copied.items():
            s_pos = edit_source(script, i)
            verdict = check_keyframe(qc, dst, script, i, recipe, copied.get(s_pos) if s_pos is not None else None) if qc else None
            db.add_asset(production_id=prod["id"], kind="storyboard", scene_index=i, local_path=str(dst), width=768,
                         height=1344, selected=True,
                         meta={"provider": "essai", "source": str(keys[with_image.index(i)]),
                               **({"qc": verdict.model_dump()} if verdict else {})})
            print(f"image {i} :", "contrôle OK" if verdict and verdict.ok else verdict.problems if verdict else "non contrôlée")
    if clips:
        (pdir / "clips").mkdir(parents=True, exist_ok=True)
        for i, src in enumerate(clips):
            dst = pdir / "clips" / f"scene_{i:02d}.mp4"
            shutil.copy2(src, dst)
            db.add_asset(production_id=prod["id"], kind="clip", scene_index=i, local_path=str(dst), width=480, height=832,
                         duration_s=probe_duration(dst), meta={"provider": "essai", "source": str(src)})
    db.enqueue("script", production_id=prod["id"], priority=50)  # le script existe : le job crée la vidéo et le storyboard
    print(f"Production {prod['id']} ({series['slug']}) : en file. Storyboard à valider dans le dashboard (Création).")


if __name__ == "__main__":
    main()
