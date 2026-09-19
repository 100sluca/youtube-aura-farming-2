"""Boucle d'amélioration : propose une nouvelle version de prompt (inactive, à valider dans le dashboard)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..providers.llm import get_llm
from .base import Context, Step


class PromptProposal(BaseModel):
    agent: str
    content: str
    rationale: str


class Proposals(BaseModel):
    proposals: list[PromptProposal]


class ImproveStep(Step):
    type = "improve"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        days = int(ctx.job.payload.get("window_days", 14))
        perf = ctx.db.fetch_all(
            """select t.agent, t.version, t.content, count(v.*) as videos,
                      round(avg(v.average_view_pct), 1) as avg_view_pct, round(avg(v.views)) as views
               from prompt_templates t
               join productions p on p.prompt_template_id = t.id
               join v_video_overview v on v.production_id = p.id and v.status = 'published'
               where v.published_at > now() - make_interval(days => %s)
               group by t.id order by t.agent, t.version""",
            (days,),
        )
        best = ctx.db.fetch_all(
            "select title, category, average_view_pct, views from v_video_overview where status = 'published' "
            "and published_at > now() - make_interval(days => %s) order by average_view_pct desc nulls last limit 10",
            (days,),
        )
        worst = ctx.db.fetch_all(
            "select title, category, average_view_pct, views from v_video_overview where status = 'published' "
            "and published_at > now() - make_interval(days => %s) order by average_view_pct asc nulls last limit 10",
            (days,),
        )
        active = ctx.db.fetch_all("select agent, version, content from prompt_templates where is_active")
        if not perf:
            ctx.log("improve.skip", reason="pas assez de données")
            return {"proposals": 0}
        ctx.progress(30, "Appel LLM")
        out = get_llm(ctx.settings).complete_json(
            IMPROVE_PROMPT,
            f"Performance par prompt : {perf}\nMeilleures : {best}\nPires : {worst}\nPrompts actifs : {active}",
            Proposals,
        )
        created = 0
        for p in out.proposals:
            parent = next((a for a in active if a["agent"] == p.agent), None)
            if not parent:
                continue
            ctx.db.execute(
                """insert into prompt_templates (agent, version, content, notes, parent_id, is_active, created_by)
                   values (%s, (select coalesce(max(version), 0) + 1 from prompt_templates where agent = %s), %s, %s,
                           (select id from prompt_templates where agent = %s and is_active), false, 'improve_agent')""",
                (p.agent, p.agent, p.content, p.rationale, p.agent),
            )
            created += 1
        if created:
            ctx.db.alert("info", f"{created} proposition(s) de prompt à valider", "Voir Réglages → Prompts des agents")
        return {"proposals": created}


IMPROVE_PROMPT = """Tu optimises les prompts d'une fabrique de YouTube Shorts. À partir des performances par
version de prompt, des meilleures et des pires vidéos (rétention, vues), propose au plus une nouvelle
version par agent (idea, script) : garde la structure, change ce qui explique les écarts (hooks, rythme,
catégories, longueur). Réponds en JSON : {"proposals":[{agent, content, rationale}]}."""
