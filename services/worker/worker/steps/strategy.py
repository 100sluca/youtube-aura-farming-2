"""Agent stratégie (hebdomadaire, par chaîne) : lit les statistiques et propose des ajustements à valider.

Ajuste ce qui se pilote vraiment : poids des catégories pour l'agent idée, consignes d'accroche et
durée cible pour l'agent script, modèles de titres pour l'agent SEO, créneaux de publication.
Rien n'est appliqué sans validation humaine (`yt2 strategy accept`), dans l'esprit « human in the loop ».
"""

from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb

from ..models import StrategyProposal
from ..prompts import prompt_text
from ..providers.llm import get_llm
from ..strategy import VideoPerf, active_strategies, compute_stats, guidance_text, validate_proposal
from .base import Context, Step
from .ideate import CATEGORIES


class StrategyStep(Step):
    type = "strategy"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        channel_id = ctx.job.channel_id
        assert channel_id, "strategy : channel_id requis"
        ch = ctx.db.fetch_one("select slug, name, publish_slots from channels where id = %s", (channel_id,))
        assert ch, "chaîne introuvable"
        days = int(ctx.job.payload.get("window_days", ctx.settings.strategy_window_days))
        rows = ctx.db.fetch_all(
            """select * from v_video_performance
               where channel_id = %s and age_days >= 3 and published_at > now() - make_interval(days => %s)""",
            (channel_id, days),
        )
        stats = compute_stats([VideoPerf.from_row(r) for r in rows])
        version_row = ctx.db.fetch_one(
            "select coalesce(max(version), 0) + 1 as v from strategies where channel_id = %s", (channel_id,)
        )
        version = version_row["v"] if version_row else 1

        proposal: StrategyProposal | None = None
        if stats["n"] >= ctx.settings.strategy_min_videos:
            current = active_strategies(ctx.db).get(ch["slug"])
            system = prompt_text(ctx.db, "strategy", DEFAULT_PROMPT)  # version active (onglet Agents, worker/prompts.py)
            slots = [s.strftime("%H:%M") for s in ch["publish_slots"]]
            user = (
                f"Chaîne : {ch['name']} ({ch['slug']}). Fenêtre : {days} jours. Créneaux actuels : {slots}.\n"
                f"Catégories disponibles : {CATEGORIES}\n"
                f"Stratégie actuellement validée :\n{guidance_text({ch['slug']: current} if current else {})}\n"
                f"Statistiques (calculées, fiables ; « confidence » indique si l'échantillon suffit) :\n"
                f"{json.dumps(stats, ensure_ascii=False, default=str)}"
            )
            ctx.progress(40, "Appel LLM")
            raw = get_llm(ctx.settings, ctx.db).complete_json(system, user, StrategyProposal)
            proposal = validate_proposal(raw, stats, slots)

        ctx.db.execute(
            """insert into strategies (channel_id, version, window_days, stats, proposal, status)
               values (%s, %s, %s, %s, %s, 'proposed')""",
            (channel_id, version, days, Jsonb(stats), Jsonb(proposal.model_dump()) if proposal else None),
        )
        if proposal:
            ctx.db.alert(
                "warning",
                f"Stratégie v{version} à valider ({ch['slug']})",
                f"{proposal.summary}\nValider : yt2 strategy show {ch['slug']} puis yt2 strategy accept {ch['slug']} {version}",
            )
        else:
            ctx.db.alert(
                "info",
                f"Stratégie ({ch['slug']}) : données insuffisantes",
                f"{stats['n']} vidéo(s) publiée(s) depuis au moins 3 jours, minimum {ctx.settings.strategy_min_videos}.",
            )
        return {"version": version, "videos": stats["n"], "proposal": bool(proposal)}


DEFAULT_PROMPT = """Tu es le stratège d'une chaîne YouTube Shorts de construction, rénovation et aménagement
spectaculaires. Tu reçois des statistiques DÉJÀ CALCULÉES sur les vidéos publiées (vues à J+7,
rétention, abonnés pour 1 000 vues, engagement), ventilées par catégorie, format, durée, créneau,
heure et caractéristiques du titre, avec une confiance par groupe.

Propose des ajustements concrets pour la semaine suivante :
- category_weights : un poids par catégorie concernée (1 = inchangé, 0 = arrêter, 2 = doubler), avec
  la raison chiffrée ; ne dépasse 2 que si la confiance du groupe est « bonne » ;
- hook_guidelines : consignes d'accroche tirées des vidéos qui retiennent le mieux ;
- title_patterns : modèles de titres qui marchent, avec un exemple ;
- avoid : ce qui décroche ;
- publish_slots : seulement si les données par heure le justifient (confiance au moins moyenne),
  même nombre de créneaux qu'aujourd'hui, format HH:MM ; sinon null ;
- target_duration_s : seulement si la ventilation par durée le justifie ; sinon null ;
- experiments : au plus 3 tests à mener, pour les questions que les données ne tranchent pas ;
- confidence : ta confiance globale.
Règles : appuie chaque recommandation sur un chiffre fourni ; n'invente aucune statistique ;
une différence sur un groupe de confiance « faible » est une piste d'expérience, pas une règle.
Réponds uniquement en JSON conforme au schéma StrategyProposal."""
