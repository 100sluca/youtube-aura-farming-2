"""Agent analyste (job « analyze », docs/25-dashboard-statistiques.md) : pourquoi certaines vidéos marchent et d'autres
non, et quelles leçons en tirer.

Chaque dimanche à 5 h et à la demande (bouton « Analyser » du Dashboard). Les chiffres et la fiche de chaque vidéo
viennent du code (worker/performance.py) ; l'agent les interprète, en regardant aussi une planche d'images de chaque
vidéo quand un modèle qui voit est réglé (worker/analysis_frames.py). Son rapport est gardé dans performance_reports ; ses
leçons arrivent « à valider » dans le Dashboard et ne servent aux agents idées, scénaristes et SEO qu'une fois validées
(worker/lessons.py). Une nouvelle analyse remplace les leçons encore en attente de la précédente.
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from ..analysis_frames import video_sheet
from ..lessons import active_lessons
from ..performance import (
    PerformanceReport,
    build_message,
    clean_report,
    compute_performance,
    load_facts,
    sheet_candidates,
)
from ..prompts import prompt_text
from ..providers.llm import get_llm, sees_images
from .base import Context, Step

WINDOW_DAYS = 90
MIN_JUDGED = 2  # en dessous, pas de comparaison possible : rapport chiffré sans appel au LLM


class AnalyzeStep(Step):
    type = "analyze"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        channel_id = ctx.job.channel_id
        if channel_id is None:  # sans chaîne : la première chaîne connectée
            row = ctx.db.fetch_one(
                "select id from channels where is_active and youtube_channel_id is not null order by created_at limit 1"
            )
            assert row, "analyze : aucune chaîne connectée"
            channel_id = row["id"]
        ch = ctx.db.fetch_one("select name from channels where id = %s", (channel_id,))
        assert ch, "analyze : chaîne introuvable"
        days = int(ctx.job.payload.get("window_days", WINDOW_DAYS))

        ctx.progress(10, "Fiches des vidéos")
        videos = load_facts(ctx.db, channel_id, days)
        stats = compute_performance(videos)
        report: dict[str, Any] | None = None
        lessons = []
        if stats["judged"] >= MIN_JUDGED:
            active = active_lessons(ctx.db, channel_id)
            system = prompt_text(ctx.db, "analyst", ANALYST_PROMPT)  # version en service (onglet Agents)
            raw = None
            # Le modèle d'écriture (plus fort) d'abord : une analyse par semaine, c'est elle qui guide les autres agents
            llm = get_llm(ctx.settings, ctx.db, writer=True)
            # L'agent regarde aussi les vidéos (planches d'images) quand un des modèles réglés voit les images
            if ctx.job.payload.get("images", True) and any(sees_images(p) for p in getattr(llm, "chain", [llm])):
                ctx.progress(20, "Images des vidéos")
                shown = [
                    (v, sheet) for v in sheet_candidates(videos) if (sheet := video_sheet(ctx.db, ctx.settings.data_dir, v.id))
                ]
                if shown:
                    ctx.progress(35, "Appel LLM (avec les images)")
                    try:
                        raw = llm.complete_json(
                            system,
                            build_message(ch["name"], videos, stats, active, sheets=[v for v, _ in shown]),
                            PerformanceReport,
                            [sheet for _, sheet in shown],
                        )
                    except Exception as exc:  # noqa: BLE001 — sans les images plutôt que pas d'analyse
                        ctx.log("analyse.images_refusees", level="warn", error=str(exc)[:300])
            if raw is None:
                ctx.progress(40, "Appel LLM")
                raw = llm.complete_json(system, build_message(ch["name"], videos, stats, active), PerformanceReport)
            report, lessons = clean_report(raw, videos, [a["rule"] for a in active], stats["judged"])

        ctx.progress(90, "Enregistrement")
        row = ctx.db.fetch_one(
            """insert into performance_reports (channel_id, window_days, videos, stats, report)
               values (%s, %s, %s, %s, %s) returning id""",
            (channel_id, days, len(videos), Jsonb(stats), Jsonb(report) if report else None),
        )
        assert row
        if report:
            # les leçons pas encore décidées de l'analyse précédente laissent la place aux nouvelles
            ctx.db.execute(
                "update performance_lessons set status = 'superseded' where channel_id = %s and status = 'proposed'",
                (channel_id,),
            )
            for lesson in lessons:
                ctx.db.execute(
                    """insert into performance_lessons (report_id, channel_id, target, recipe, rule, why, confidence)
                       values (%s, %s, %s, %s, %s, %s, %s)""",
                    (row["id"], channel_id, lesson.target, lesson.recipe, lesson.rule, lesson.why, lesson.confidence),
                )
        if lessons:
            ctx.db.alert(
                "info",
                f"Analyse des vidéos : {len(lessons)} leçon(s) à valider",
                "Dashboard → Ce que disent les chiffres : ✓ pour la donner aux agents, ✗ pour l'écarter.",
            )
        return {"videos": len(videos), "judged": stats["judged"], "lessons": len(lessons), "report": str(row["id"])}


ANALYST_PROMPT = """Tu es l'analyste des performances d'une chaîne YouTube Shorts fabriquée par IA. Ses formats : chantier
en accéléré (timelapse : un lieu se construit sous nos yeux, sans voix, avec un titre d'accroche à l'écran), visite de
maison de luxe (tour : on passe de pièce en pièce, sans voix) et récit narré (story : voix off et sous-titres).

Tu reçois, pour chaque vidéo publiée, ses chiffres DÉJÀ CALCULÉS (vues, note = vues ÷ médiane de la chaîne, verdict
top / moyen / flop, rétention moyenne, audience encore là à 3 s et à la fin, j'aime, partages, abonnés gagnés, âge) et
sa fiche de fabrication (thème, format, titre, titre d'accroche affiché, textes à l'écran, narration, premier plan,
nombre et durée des plans, musique, modèle vidéo, hashtags, heure de publication, commentaires). Puis des ventilations
par format, thème, durée, créneau et forme du titre, et les leçons déjà en service. Souvent aussi une planche d'images
par vidéo (ce que le spectateur voit au début, au milieu, à la fin) : sers-t'en, c'est ce qui dit le mieux ce qu'il y a
dans la vidéo, surtout pour celles mises en ligne à la main.

Ta mission : comprendre pourquoi certaines vidéos marchent et d'autres non, puis en tirer des règles que les agents
appliqueront aux prochaines vidéos.
1. videos : pour chaque vidéo (sa référence V1, V2…), pourquoi elle a ce verdict, en une ou deux phrases ; worked : ce
   qui a marché ; missed : ce qui a manqué. Regarde d'abord les deux premières secondes (premier plan, titre
   d'accroche, promesse du titre), puis le rythme (durée des plans), le sujet, la durée totale et la fin.
2. patterns : au plus 5 différences entre les vidéos qui marchent et les autres, chacune avec sa preuve chiffrée tirée
   des données (evidence) et une confiance (faible, moyenne, bonne).
3. lessons : au plus 6 règles concrètes, à l'impératif, applicables telles quelles :
   - target : « idea » (choix des sujets), « script » (accroche, rythme, textes à l'écran, narration), « seo » (titre,
     description, hashtags) ou « production » (réglage que l'humain fait lui-même : modèle vidéo, durée, musique,
     montage) ;
   - recipe : le format concerné (timelapse, tour, story), ou null si la règle vaut pour tous ;
   - why : la preuve chiffrée ; confidence : faible, moyenne ou bonne ;
   - ne répète pas une leçon déjà en service ; si les chiffres contredisent une leçon en service, dis-le dans summary.
4. experiments : au plus 3 tests pour ce que les données ne tranchent pas (hypothesis, test).
5. summary : l'essentiel en 2 ou 3 phrases simples, pour l'humain qui pilote la chaîne.

Règles : n'invente aucun chiffre et ne recalcule rien ; une vidéo de moins de 48 h n'a pas fini de monter ; avec peu de
vidéos, reste prudent (confiance faible) et préfère une expérience à une règle ; une vidéo mise en ligne à la main a une
fiche plus pauvre, juge-la sur ce qu'on sait et sur ses images ; dans le fil Shorts, la vidéo démarre seule : il n'y a
ni clic ni miniature, ne parle jamais de taux de clic ; écris en français, sans jargon.
Réponds uniquement en JSON conforme au schéma PerformanceReport."""
