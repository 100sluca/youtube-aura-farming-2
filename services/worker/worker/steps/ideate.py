"""Agent idée : produit N concepts scorés à partir des catégories et des top performers."""

from __future__ import annotations

from typing import Any

from ..models import IdeaBatch
from ..providers.llm import get_llm
from .base import Context, Step

CATEGORIES = [
    "secret_passages",
    "space_optimization",
    "pool",
    "container",
    "hidden_cinema",
    "slat_wall",
    "smart_furniture",
    "office_pod",
    "concrete_epoxy",
    "under_stairs",
    "ceiling_storage",
    "zen_bathroom",
]


class IdeateStep(Step):
    type = "ideate"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        count = int(ctx.job.payload.get("count", 10))
        tpl = ctx.db.fetch_one("select id, content from prompt_templates where agent = 'idea' and is_active")
        top = ctx.db.fetch_all(
            """select title, category, average_view_pct, views from v_video_overview
               where status = 'published' order by average_view_pct desc nulls last, views desc limit 20"""
        )
        recent = ctx.db.fetch_all(
            "select category, count(*) as n from concepts where created_at > now() - interval '30 days' group by 1"
        )
        existing = [
            r["title"]
            for r in ctx.db.fetch_all(
                "select title from concepts where status in ('proposed', 'approved') order by created_at desc limit 100"
            )
        ]
        system = tpl["content"] if tpl else DEFAULT_PROMPT
        user = (
            f"Catégories : {CATEGORIES}\nRépartition 30 j : {recent}\nTop 20 : {top}\n"
            f"Déjà proposées (éviter) : {existing}\nProduis {count} idées."
        )
        ctx.progress(20, "Appel LLM")
        batch = get_llm(ctx.settings).complete_json(system, user, IdeaBatch)
        for i, idea in enumerate(batch.ideas):
            ctx.db.execute(
                """insert into concepts (title, hook, category, premise, visual_beats, source, score, prompt_template_id)
                   values (%s, %s, %s, %s, %s, 'agent', %s, %s)""",
                (
                    idea.title,
                    idea.hook,
                    idea.category,
                    idea.premise,
                    _jsonb(idea.visual_beats),
                    idea.score,
                    tpl["id"] if tpl else None,
                ),
            )
            ctx.progress(20 + int(80 * (i + 1) / len(batch.ideas)), f"Idée {i + 1}/{len(batch.ideas)}")
        return {"created": len(batch.ideas)}


def _jsonb(v: Any):  # noqa: ANN202
    from psycopg.types.json import Jsonb

    return Jsonb(v)


DEFAULT_PROMPT = """Tu es le stratège d'une chaîne YouTube Shorts (construction, design d'intérieur, DIY
spectaculaire : passages secrets, rangements cachés, piscines, containers enterrés, cinéma caché…).
Propose des concepts universels (compréhensibles en FR et EN), visuels, avec un hook fort dans les
3 premières secondes et une révélation. Réponds en JSON : {"ideas":[{title, hook, category, premise,
visual_beats[], score}]}. score = potentiel 0-100 (viralité × faisabilité en vidéo IA)."""
