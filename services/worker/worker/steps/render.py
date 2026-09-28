"""Job `render` : demandé par le dashboard (ou `yt2 storyboard approve`) une fois le storyboard validé.

Le graphe de rendu (clips, voix, montage, contrôle) dépend du plan de continuité, calculé en Python
(dag.continuity_plan) : le dashboard ne l'écrit donc pas lui-même, il met ce job en file.
"""

from __future__ import annotations

from typing import Any

from ..dag import enqueue_render_dag
from .base import Context, Step


class RenderStep(Step):
    type = "render"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        pid = ctx.job.production_id
        assert pid, "render : production_id requis"
        missing = ctx.db.fetch_all(
            """select distinct a.scene_index from assets a where a.production_id = %s and a.kind = 'storyboard'
               and not exists (select 1 from assets b where b.production_id = a.production_id and b.kind = 'storyboard'
                               and b.scene_index = a.scene_index and b.selected)""",
            (pid,),
        )
        if missing:
            raise RuntimeError(f"scènes sans image retenue : {[m['scene_index'] for m in missing]}")
        return enqueue_render_dag(ctx.db, pid, ctx.settings.clip_continuity, ctx.settings.continuity_max_chain)
