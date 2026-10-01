"""Graphe de jobs d'une production, après le script.

    script ──► seo (par vidéo)
          └──► storyboard ──► [validation humaine des images] ──► rendu
          └──────────────────────────────────────────────────────► rendu (sans storyboard)

    rendu = generate_clip (par scène) ─┬─► assemble ──► qa (par vidéo)
            tts (par vidéo, format A) ──┘

Le rendu n'est mis en file qu'une fois les images validées (`yt2 storyboard approve`), ou tout de
suite si STORYBOARD_REVIEW=false. Un job ne démarre que quand tous ses `depends_on` sont terminés.

Continuité (docs/12 §4) : un clip qui prolonge le précédent (continuity_plan) part de sa dernière
image ; son job dépend donc du clip précédent. Les autres clips partent de leur image de storyboard.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from .db import Db
from .models import ScriptV1
from .recipes import is_visual, recipe_for_production

SCENE_JOB_PRIORITY = 100


def continuity_plan(script: ScriptV1, mode: str = "script", max_chain: int = 3) -> list[bool]:
    """Pour chaque scène : True si son clip part de la dernière image du clip précédent.
    mode : "script" (champ continues_previous de la scène), "chain" (toujours), "cut" (jamais).
    Après `max_chain` clips enchaînés, la scène suivante repart d'une image de storyboard (dérive).
    Une scène carte (rendue par le code, worker/maps.py) est toujours une coupe, et la scène qui la suit aussi."""
    plan: list[bool] = []
    run = 0
    for i, s in enumerate(script.scenes):
        mapped = s.is_map or (i > 0 and script.scenes[i - 1].is_map)
        wants = i > 0 and not mapped and (mode == "chain" or (mode == "script" and s.continues_previous))
        if wants and run < max_chain:
            run += 1
            plan.append(True)
        else:
            run = 0
            plan.append(False)
    return plan


def enqueue_render_dag(db: Db, production_id: UUID, continuity: str = "script", max_chain: int = 3) -> dict[str, Any]:
    """Met en file clips, narration, montage et contrôle qualité. Idempotent."""
    prod = db.fetch_one("select format, script from productions where id = %s", (production_id,))
    assert prod and prod["script"], "script manquant"
    if db.fetch_one(
        "select 1 from jobs where production_id = %s and type = 'generate_clip' and status in ('queued', 'running', 'done')",
        (production_id,),
    ):
        return {"skipped": True}
    script = ScriptV1.model_validate(prod["script"])
    if is_visual(recipe_for_production(db, production_id)):
        # formats visuels : chaque scène part de son image clé, sauf les passages d'une visite qui prolongent la pièce
        # précédente (continues_previous posé par recipes.normalize_script, jamais par le LLM)
        continuity = "script"
    plan = continuity_plan(script, continuity, max_chain)
    clip_jobs: list[UUID] = []
    prev: UUID | None = None
    for s, cont in zip(script.scenes, plan, strict=True):
        prev = db.enqueue(
            "generate_clip",
            production_id=production_id,
            priority=SCENE_JOB_PRIORITY,
            payload={"scene_index": s.index, "continues": cont},
            depends_on=[prev] if cont and prev else (),
        )
        clip_jobs.append(prev)
    videos = db.fetch_all("select id, lang from videos where production_id = %s and archived_at is null", (production_id,))
    for v in videos:
        deps = list(clip_jobs)
        if prod["format"] == "A_voiceover":
            deps.append(db.enqueue("tts", video_id=v["id"], production_id=production_id, payload={"lang": v["lang"]}))
        asm = db.enqueue("assemble", video_id=v["id"], production_id=production_id, depends_on=deps)
        db.enqueue("qa", video_id=v["id"], production_id=production_id, depends_on=[asm])
    db.set_status("productions", production_id, "generating")
    return {"clips": len(clip_jobs), "chained": sum(plan), "videos": len(videos)}
