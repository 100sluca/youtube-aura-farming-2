"""Agent script : concept → ScriptV1, puis création du DAG de jobs de la production."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from ..models import ScriptV1
from ..providers.llm import get_llm
from .base import Context, Step

SCENE_JOB_PRIORITY = 100


class ScriptStep(Step):
    type = "script"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        pid = ctx.job.production_id
        assert pid, "script: production_id requis"
        prod = ctx.db.fetch_one(
            """select p.*, c.title, c.hook, c.premise, c.visual_beats, c.category
               from productions p left join concepts c on c.id = p.concept_id where p.id = %s""",
            (pid,),
        )
        assert prod, "production introuvable"
        ctx.db.set_status("productions", pid, "scripting")

        if prod["script"]:  # idempotence : script déjà produit → on ne fait que (re)créer le DAG
            script = ScriptV1.model_validate(prod["script"])
        else:
            tpl = ctx.db.fetch_one("select id, content from prompt_templates where agent = 'script' and is_active")
            examples = ctx.db.fetch_all(
                """select p.script from v_video_overview v join productions p on p.id = v.production_id
                   where v.status = 'published' and p.script is not null
                   order by v.average_view_pct desc nulls last limit 5"""
            )
            system = tpl["content"] if tpl else DEFAULT_PROMPT
            user = (
                f"Concept : {prod['title']}\nHook : {prod['hook']}\nPrémisse : {prod['premise']}\n"
                f"Beats : {prod['visual_beats']}\nFormat : {prod['format']}\n"
                f"Durée cible : {prod['target_duration_s']} s\nStyle : {prod['style_preset']}\n"
                f"Exemples performants : {[e['script'] for e in examples]}"
            )
            ctx.progress(20, "Appel LLM")
            script = get_llm(ctx.settings).complete_json(system, user, ScriptV1)
            ctx.db.execute(
                "update productions set script = %s, prompt_template_id = %s where id = %s",
                (Jsonb(script.model_dump()), tpl["id"] if tpl else None, pid),
            )

        ctx.progress(60, "Création des jobs")
        self._build_dag(ctx, pid, prod["format"], script)
        ctx.db.set_status("productions", pid, "generating")
        return {"scenes": len(script.scenes), "duration_s": script.duration_s}

    def _build_dag(self, ctx: Context, pid: UUID, fmt: str, script: ScriptV1) -> None:
        clip_jobs = [
            ctx.enqueue("generate_clip", production_id=pid, priority=SCENE_JOB_PRIORITY, payload={"scene_index": s.index})
            for s in script.scenes
        ]
        channels = ctx.db.fetch_all("select id, lang from channels where is_active")
        for ch in channels:
            lang = ch["lang"]
            meta = script.metadata.get(lang)
            narration = " ".join(s.narration.get(lang, "") for s in script.scenes).strip() or None
            row = ctx.db.fetch_one(
                """insert into videos (production_id, channel_id, lang, format, title, description, tags, narration_text)
                   values (%s, %s, %s, %s, %s, %s, %s, %s)
                   on conflict (production_id, channel_id) do update set title = excluded.title
                   returning id""",
                (
                    pid,
                    ch["id"],
                    lang,
                    fmt,
                    meta.title if meta else None,
                    meta.description if meta else None,
                    meta.tags if meta else [],
                    narration,
                ),
            )
            vid = row["id"]
            deps = list(clip_jobs)
            if fmt == "A_voiceover":
                deps.append(ctx.enqueue("tts", video_id=vid, production_id=pid, payload={"lang": lang}))
            asm = ctx.enqueue("assemble", video_id=vid, production_id=pid, depends_on=deps)
            qa = ctx.enqueue("qa", video_id=vid, production_id=pid, depends_on=[asm])
            ctx.log("dag.video", video_id=str(vid), lang=lang, jobs=len(deps) + 2, qa=str(qa))


DEFAULT_PROMPT = """Tu écris des scripts de YouTube Shorts (9:16, 20-35 s) pour une chaîne construction /
design / DIY. Règles : hook visuel dans les 3 premières secondes (résultat final ou mécanisme), un
événement visuel ou sonore toutes les 3-4 s, 6-10 scènes de 3-5 s, dernière scène qui reboucle sur la
première (loop_note). Chaque scène a un visual_prompt en anglais (caméra, lumière, matière, mouvement,
style photoréaliste), une narration courte FR et EN (format A) ou un champ sfx (format B), et un texte
à l'écran optionnel (≤ 5 mots). metadata : titre ≤ 60 caractères, description avec 2-3 hashtags,
10 tags. Réponds uniquement en JSON conforme à ScriptV1."""
