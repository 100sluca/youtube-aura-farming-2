"""Agent idée : N concepts scorés par série, à partir du brief de la série, de ses catégories, des vidéos qui
marchent, de la stratégie validée et, pour une série documentaire, de la matière du jour (Wikipédia).

Payload : {"count": 10} répartit les idées entre séries actives selon leurs poids ;
          {"series": "animaux_etranges", "count": 6} ne sert qu'une série ;
          "channel_id" (écran Création) : chaîne pour laquelle les idées sont demandées (concepts.channel_id).
Une idée d'une série documentaire n'est gardée que si au moins deux de ses faits citent une source fournie.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from ..lessons import lessons_text
from ..models import IdeaBatch
from ..prompts import active_prompt, prompt_text
from ..providers.llm import get_llm
from ..recipes import IDEA_GUIDES
from ..series import Series, active_series, get_series, weighted_counts
from ..sources.wikipedia import (
    SourceDoc,
    WikipediaClient,
    cached_material,
    daily_material,
    material_text,
    sources_for,
)
from ..storytelling import RULES, lint_hook
from ..strategy import active_strategies, guidance_text
from .base import Context, Step

# Catégories de la série d'origine (maisons de rêve), gardées pour l'agent stratégie et comme repli quand
# un concept n'a pas de série. La liste vivante est dans series.categories.
CATEGORIES = [
    # Intérieur caché
    "secret_passages",
    "under_stairs",
    "hidden_cinema",
    "smart_furniture",
    "space_optimization",
    "ceiling_storage",
    # Extérieur et terrain
    "pool",
    "container",
    "underground",
    "garden_shed",
    "treehouse",
    "landscaping",
    "rooftop",
    # Pièces et usages
    "home_gym",
    "office_pod",
    "zen_bathroom",
    "slat_wall",
    # Chantier et matière
    "renovation",
    "concrete_epoxy",
    "building_extension",
]


class IdeateStep(Step):
    type = "ideate"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        count = int(ctx.job.payload.get("count", 10))
        slug = ctx.job.payload.get("series")
        if slug:
            plan: list[tuple[Series, int]] = [(get_series(ctx.db, slug), count)]
        else:
            series = active_series(ctx.db)
            counts = weighted_counts(series, count)
            plan = [(s, counts[s.slug]) for s in series if counts.get(s.slug)]
        if not plan:
            ctx.log("ideate.aucune_serie_active", level="warn")
            return {"created": 0}
        # prompt système : version active de la clé « idea » (onglet Agents du dashboard, worker/prompts.py)
        tpl = active_prompt(ctx.db, "idea", DEFAULT_PROMPT)
        created: dict[str, int] = {}
        for i, (s, n) in enumerate(plan):
            ctx.progress(5 + int(90 * i / len(plan)), f"Série {s.slug} · {n} idées")
            created[s.slug] = self._ideate(ctx, s, n, tpl)
        return {"created": sum(created.values()), "series": created}

    def _ideate(self, ctx: Context, s: Series, n: int, tpl: tuple[str, UUID | None]) -> int:
        db = ctx.db
        top = db.fetch_all(
            """select v.title, v.category, v.average_view_pct, v.views from v_video_overview v
               join productions p on p.id = v.production_id
               where v.status = 'published' and (p.series_id = %s or p.series_id is null)
               order by v.average_view_pct desc nulls last, v.views desc limit 20""",
            (s.id,),
        )
        recent = db.fetch_all(
            "select category, count(*) as n from concepts where series_id = %s and created_at > now() - interval '30 days' group by 1",
            (s.id,),
        )
        existing = [
            r["title"]
            for r in db.fetch_all(
                """select title from concepts where series_id = %s and status in ('proposed', 'approved', 'used')
                   order by created_at desc limit 100""",
                (s.id,),
            )
        ]
        docs: list[SourceDoc] = []
        material = ""
        if s.source == "wikipedia":
            docs = self._material(ctx, s)
            if not docs:
                ctx.log("ideate.sans_matiere", level="warn", series=s.slug)
                return 0
            material = material_text(docs, chars=3500)  # tout l'extrait mis en cache : l'enjeu est rarement au début
        system, tpl_id = tpl
        # formats visuels : le guide du format (pas de voix, un titre d'accroche, docs/15) ; sinon les règles du storytelling
        guide = (
            prompt_text(db, f"guide_{s.recipe}", IDEA_GUIDES[s.recipe])
            if s.recipe in IDEA_GUIDES
            else prompt_text(db, "rules_storytelling", RULES)
        )
        user = "\n\n".join(
            part
            for part in (
                f"SÉRIE : {s.name} ({s.slug})\nBrief : {s.brief}\nCatégories : {s.categories or CATEGORIES}\n"
                f"Durée des vidéos : {s.target_duration_s} s",
                guide,
                f"MATIÈRE DU JOUR (sources numérotées, seule base des faits) :\n{material}" if material else "",
                f"Répartition des 30 derniers jours : {recent}\nTop 20 publiées : {top}\nDéjà proposées (éviter) : {existing}",
                f"Stratégie validée :\n{guidance_text(active_strategies(db))}",
                # leçons de l'agent analyste validées dans le Dashboard (docs/25)
                lessons_text(db, "idea", channel_id=ctx.job.payload.get("channel_id"), recipe=s.recipe),
                f"Produis {n} idées"
                + (
                    ", chacune avec 8 à 12 faits sourcés [n] qui couvrent le contexte, l'enjeu, "
                    "l'obstacle ou la controverse, les rebondissements et la fin."
                    if docs
                    else "."
                ),
            )
            if part
        )
        ctx.log("ideate.llm", series=s.slug, sources=len(docs))
        batch = get_llm(ctx.settings, ctx.db, writer=True).complete_json(system, user, IdeaBatch)
        created = 0
        for idea in batch.ideas:
            refs, facts = sources_for(docs, idea.facts) if docs else ([], [])
            if docs and len(facts) < 2:
                ctx.log("ideate.idee_ecartee", level="warn", title=idea.title, reason="moins de 2 faits sourcés")
                continue
            issues = lint_hook(idea.hook)
            if issues:  # on garde l'idée : l'agent script réécrit l'accroche sous contrôle du linter
                ctx.log("ideate.accroche", title=idea.title, issues=issues)
            db.execute(
                """insert into concepts (title, hook, category, premise, visual_beats, source, score, prompt_template_id,
                                         series_id, angle, sources, facts, channel_id)
                   values (%s, %s, %s, %s, %s, 'agent', %s, %s, %s, %s, %s, %s, %s)""",
                (
                    idea.title,
                    idea.hook,
                    idea.category,
                    idea.premise,
                    Jsonb(idea.visual_beats),
                    idea.score,
                    tpl_id,
                    s.id,
                    idea.angle,
                    Jsonb([r.model_dump() for r in refs]),
                    Jsonb([f.model_dump() for f in facts]),
                    ctx.job.payload.get("channel_id"),
                ),
            )
            created += 1
        return created

    @staticmethod
    def _material(ctx: Context, s: Series) -> list[SourceDoc]:
        used = {
            ref.get("url")
            for r in ctx.db.fetch_all(
                "select sources from concepts where series_id = %s and created_at > now() - interval '120 days'", (s.id,)
            )
            for ref in (r["sources"] or [])
        }
        client = WikipediaClient(lang=s.lang, user_agent=ctx.settings.effective_wikipedia_user_agent)
        max_docs = int(s.source_config.get("max_docs", 6))
        docs = cached_material(
            client,
            s.source_config,
            date.today(),
            ctx.settings.data_dir / "sources" / "wikipedia",
            exclude_urls={u for u in used if u},
            max_docs=max_docs,
        )
        if docs or not ctx.job.payload.get("autopilot"):
            return docs
        # Pilote automatique (docs/46) : la matière du jour est déjà exploitée (30/09 : idées du matin) ; on en cherche
        # d'autre, sans cache : toutes les recherches de la série et des pages au hasard, pas les flux du jour
        cfg = s.source_config
        fresh = {
            **cfg,
            "feeds": [],
            "queries_per_day": len(cfg.get("queries") or []),
            "random": max(8, int(cfg.get("random", 0))),
        }
        ctx.log("ideate.matiere_fraiche", series=s.slug)
        return daily_material(client, fresh, date.today(), {u for u in used if u}, max_docs)


DEFAULT_PROMPT = """Tu es le stratège éditorial d'un réseau de chaînes YouTube Shorts. Chaque série a sa ligne
éditoriale (brief), ses catégories, sa durée de vidéo et parfois une matière du jour (extraits de sources numérotées
[n]). Tu proposes des concepts de Shorts racontés comme des histoires qui retiennent : une idée est une histoire, pas un
sujet. Pour chaque concept : une accroche (hook) d'une phrase de 14 mots au plus qui nomme le sujet concret et pose un
contraste (ce qu'on croit contre ce qui est, un paradoxe, un prix absurde, une erreur énorme ; jamais « saviez-vous ») ;
une prémisse (premise) en 2 phrases : le héros (une personne, un groupe, un animal) et ce qu'il veut, ce qui l'en
empêche, ce qu'il risque, puis le renversement ou la chute ; l'angle (angle) = le moteur du récit (enquête, ironie
dramatique où le spectateur voit ce que le héros refuse de voir, course contre la montre, trésor sous les yeux, l'erreur
à un million, David contre Goliath, l'obstination d'une vie, l'arroseur arrosé…) ; 3 à 8 temps visuels (visual_beats)
dans l'ordre du récit ; une catégorie de la série (category). Les formats visuels (chantier, visite) et les drames
suivent en plus leur guide, fourni avec la série. Nombres et années en chiffres, jamais en toutes lettres (« 852
morts », « en 1994 »).
Quand une matière est fournie, chaque concept s'appuie uniquement sur elle : liste 8 à 12 faits (facts) avec le numéro
[n] de la source de chacun, sans rien inventer ni compléter de mémoire. Les faits couvrent l'histoire entière, pas
seulement les chiffres : le contexte (qui, où, quand, la vie d'avant) ; ce que le héros veut et pourquoi ça compte ;
l'obstacle, la controverse ou le drame, avec sa raison ; les tentatives et les rebondissements ; les personnes (qui l'a
voulu, qui s'y est opposé, ce que ça a coûté) ; un chiffre ou une comparaison qui donne l'échelle ; la fin et ce qu'il
en reste aujourd'hui. Préfère le sujet dont la matière contient un vrai conflit, une ironie ou un renversement : une
page qui n'aligne que des dates et des mesures ne fait pas une histoire. Un sujet connu se prend par l'angle que
personne ne prend. Écarte l'actualité brûlante, les décès récents, les fictions et les sujets choquants.
Évite les idées déjà proposées, rééquilibre les catégories sous-représentées, applique les poids de la stratégie
validée. Concepts universels (FR et EN), réalisables en images générées par IA, sans personne réelle reconnaissable.
score = potentiel 0-100 (force de l'histoire × rétention attendue × faisabilité visuelle).
Réponds en JSON : {"ideas":[{title, hook, category, angle, premise, visual_beats[], facts[{claim, source}], score}]}."""
