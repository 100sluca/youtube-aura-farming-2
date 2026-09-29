"""Agent script : concept → ScriptV1 (scénario en scènes), vérifié par les correcteurs, puis mise en file de la suite.

Récits narrés (recette story : histoires vraies, animaux, maisons de rêve), refondus le 29/09 (docs/37, « Le trésor de
Begrâm » : des faits juxtaposés, sans héros ni fil) : l'histoire s'écrit d'abord EN ENTIER, puis se découpe.
1. Le conteur (prompt script, onglet Agents) écrit le récit (StoryDraft, worker/storycraft.py) avec le brief de la série,
   les règles du récit (rules_storytelling), l'idée, ses faits sourcés et, pour une série documentaire, le DOSSIER : ses
   pages Wikipédia relues en entier, version anglaise comprise (sources/wikipedia.source_dossier) ; la durée visée est
   donnée en mots dits.
2. Le correcteur du récit (storycraft.lint_story) et le relecteur (prompt script_review, la checklist du récit) le font
   réécrire une fois, puis une dernière reprise corrige les écarts mesurables qui resteraient.
3. Le code découpe le récit en scènes sans en changer un mot (storycraft.split_scenes), le réalisateur (prompt
   script_shots) décide les plans (image, mouvement, carte, musique), storycraft.build_script assemble le ScriptV1,
   que vérifie encore storytelling.lint_script. Les problèmes restants sont conservés dans productions.lint.
Les agents qui écrivent passent par la chaîne d'écriture (get_llm(writer=True)).
Une série à recette (chantier en accéléré, visite de luxe, drame : series.recipe, worker/recipes.py) a son propre
prompt, sa normalisation en code et son correcteur ; le scénariste des drames reçoit aussi les règles du récit.

Suite (worker/dag.py) : la vidéo de la chaîne de la production (productions.channel_id, choisie dans Création ;
une production d'avant 0008 sans chaîne en a une par chaîne active) et son job seo ; puis soit le storyboard
(route image → vidéo, validée à la main), soit directement le rendu (clips, voix, montage, contrôle).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from ..dag import enqueue_render_dag
from ..drama import character_voices, voices_brief
from ..lessons import lessons_text
from ..models import ScriptReview, ScriptV1, ShotList, StoryDraft
from ..music import load_library, mood_brief
from ..postpone import Postpone
from ..prompts import active_prompt, prompt_text
from ..providers.llm import LLM, FallbackLLM, get_llm
from ..providers.tts import tts_catalog
from ..providers.video import WorkflowError, get_video_provider
from ..recipes import HOOK_RULES, SCRIPT_PROMPTS, has_prompt, lint_recipe_script, montage_format, normalize_script, script_context
from ..series import Series, series_of_concept
from ..settings_store import load_generation_config
from ..sources.wikipedia import source_dossier
from ..storycraft import (
    REVIEW_PROMPT,
    SHOTS_PROMPT,
    STORY_PROMPT,
    Chunk,
    build_script,
    lint_story,
    missing_shots,
    normalize_draft,
    polish_request,
    rewrite_request,
    scenes_listing,
    split_scenes,
    story_listing,
    story_words,
    told_story,
    word_budget,
)
from ..storytelling import IMAGE_RULES, RULES, feedback, lint_script, normalize_story
from ..strategy import active_strategies, guidance_text
from .base import Context, Step

REVIEW_PROBLEMS_MAX = 8
# Le conteur et son relecteur n'écrivent qu'avec les modèles forts de la chaîne d'écriture (Réglages → IA). Essai Begrâm
# du 29/09 : quotas des Flash épuisés, Gemini 3.5 Flash-Lite a écrit un récit trop court, monotone, avec une mort
# inventée. S'ils sont tous épuisés, la tâche attend une heure sans échouer, puis se contente du secours après 12 h.
WEAK_WRITERS = re.compile(r"lite|nano", re.I)
STRONG_WAIT_S = 3600.0
STRONG_WAIT_MAX = timedelta(hours=12)
DRAMA_RULES_NOTE = (
    "(Pour un drame joué en dialogues, ces règles s'appliquent aux répliques et aux plans ; la structure du "
    "format, dans tes consignes, prime en cas de doute.)"
)

CONTINUITY_HINT = """Continuité entre clips : pour chaque scène, continues_previous = true si elle prolonge le plan
précédent (même lieu, même sujet, l'action continue : le clip partira de la dernière image du précédent) ;
false pour une coupe (nouveau lieu, nouvelle valeur de plan, nouvelle échelle). Alterne les deux : une coupe
est aussi un changement visuel. La scène 1 et la scène loop sont toujours des coupes."""


class ScriptStep(Step):
    type = "script"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        pid = ctx.job.production_id
        assert pid, "script: production_id requis"
        prod = ctx.db.fetch_one(
            """select p.*, c.title, c.hook, c.premise, c.visual_beats, c.category, c.angle, c.facts, c.sources
               from productions p left join concepts c on c.id = p.concept_id where p.id = %s""",
            (pid,),
        )
        assert prod, "production introuvable"
        ctx.db.set_status("productions", pid, "scripting")
        channels = self._channels(ctx, prod)
        langs = sorted({c["lang"] for c in channels})

        issues: list[str] = list(prod.get("lint") or [])
        if prod["script"]:  # idempotence : script déjà produit → on ne fait que (re)créer la suite
            script = ScriptV1.model_validate(prod["script"])
        else:
            script, issues, tpl_id = self._write(ctx, prod, langs)
            ctx.db.execute(
                "update productions set script = %s, prompt_template_id = %s, lint = %s where id = %s",
                (Jsonb(script.model_dump()), tpl_id, Jsonb(issues), pid),
            )

        ctx.progress(60, "Création des jobs")
        # Modèles de la production figés ici (Réglages → Modèles de génération) : changer les réglages ensuite
        # ne touche pas une production en cours ; pour comparer, refaire la production (remake_production).
        gen = load_generation_config(ctx.settings, ctx.db)
        video_provider = prod["video_provider"] or gen.video_provider
        ctx.db.execute(
            "update productions set video_provider = %s, image_workflow = coalesce(image_workflow, %s) where id = %s",
            (video_provider, gen.image_workflow, pid),
        )
        videos = self._create_videos(ctx, pid, prod["format"], script, channels)
        if ctx.settings.seo_enabled:
            for vid in videos:
                ctx.enqueue("seo", video_id=vid, production_id=pid, priority=110)
        if ctx.settings.storyboard_enabled and self._image_to_video(ctx, video_provider):
            ctx.enqueue("storyboard", production_id=pid, priority=90)
            ctx.db.set_status("productions", pid, "generating")
            nxt = "storyboard"
        else:
            enqueue_render_dag(ctx.db, pid, ctx.settings.clip_continuity, ctx.settings.continuity_max_chain)
            nxt = "rendu"
        return {"scenes": len(script.scenes), "duration_s": script.duration_s, "videos": len(videos), "next": nxt, "lint": issues}

    def _write(self, ctx: Context, prod: dict[str, Any], langs: list[str]) -> tuple[ScriptV1, list[str], UUID | None]:
        """Prompts système et consignes : versions actives en base (onglet Agents du dashboard, worker/prompts.py)."""
        series = series_of_concept(ctx.db, prod["concept_id"]) if prod.get("concept_id") else None
        if series and has_prompt(series.recipe):  # formats visuels et drame : leur propre scénariste
            return self._write_recipe(ctx, prod, langs, series)
        return self._write_story(ctx, prod, langs, series)

    def _write_story(
        self, ctx: Context, prod: dict[str, Any], langs: list[str], series: Series | None
    ) -> tuple[ScriptV1, list[str], UUID | None]:
        """Récit narré (docs/37) : le conteur écrit l'histoire en entier, le correcteur et le relecteur la font réécrire
        une fois, le code la découpe en scènes sans en changer un mot, le réalisateur décide les plans."""
        lang = langs[0] if langs else "fr"
        target = int(prod["target_duration_s"] or 30)
        facts = prod.get("facts") or []
        sources = prod.get("sources") or []
        facts_txt = "\n".join(f"- [{int(f.get('source', 0)) + 1}] {f.get('claim', '')}" for f in facts)
        sources_txt = "\n".join(f"[{i + 1}] {s.get('title')} — {s.get('url')}" for i, s in enumerate(sources))
        ctx.progress(10, "Dossier des sources")
        dossier = self._dossier(ctx, sources) if sources else ""
        lo, aim, hi = word_budget(target)
        examples = ctx.db.fetch_all(
            """select p.script from v_video_overview v join productions p on p.id = v.production_id
               where v.status = 'published' and p.script is not null
               order by (p.series_id = %s) desc, v.average_view_pct desc nulls last limit 3""",
            (series.id if series else None,),
        )
        told = [t for t in (told_story(e["script"], lang) for e in examples) if t]
        user = "\n\n".join(
            part
            for part in (
                (f"SÉRIE : {series.name}\nBrief : {series.brief}") if series else "",
                prompt_text(ctx.db, "rules_storytelling", RULES),
                f"IDÉE : {prod['title']}\nAccroche proposée : {prod['hook']}\nAngle : {prod.get('angle') or '—'}\n"
                f"Prémisse : {prod['premise']}\nCatégorie : {prod['category']}\nTemps visuels : {prod['visual_beats']}",
                f"FAITS SOURCÉS retenus par l'agent idées (points de départ) :\n{facts_txt}\nSources :\n{sources_txt}"
                if facts_txt
                else "",
                f"DOSSIER : les pages sources relues en entier. Avec les faits ci-dessus, c'est la seule base des affirmations ; "
                f"puises-y le héros, l'enjeu, le contexte, le conflit et le renversement.\n{dossier}"
                if dossier
                else "",
                f"DURÉE VISÉE : {target} s, soit environ {aim} mots dits (entre {lo} et {hi}) : environ {round(aim / 11)} "
                f"phrases en {max(5, round(target / 9))} à {max(7, round(target / 6))} temps · Langue du récit : {lang}",
                prompt_text(ctx.db, "rules_hook_title", HOOK_RULES),
                f"Stratégie validée :\n{guidance_text(active_strategies(ctx.db))}",
                lessons_text(ctx.db, "script", channel_id=prod.get("channel_id"), recipe="story"),  # leçons validées (docs/25)
                "Histoires de la chaîne qui ont bien marché (pour le ton, jamais pour les faits) :\n" + "\n---\n".join(told)
                if told
                else "",
            )
            if part
        )
        system, tpl_id = active_prompt(ctx.db, "script", STORY_PROMPT)
        llm = get_llm(ctx.settings, ctx.db, writer=True)
        teller = strong_writers(llm)
        ask = self._asker(ctx, teller, llm)
        ctx.progress(15, "Le conteur écrit l'histoire")
        draft = normalize_draft(ask(system, user, StoryDraft), lang)
        issues = lint_story(draft, lang, target)
        ctx.progress(25, "Relecture de l'histoire")
        problems = self._review_story(ctx, ask, draft, prod, facts_txt, dossier, lang, target)
        # Le fond : deux réécritures au plus, demandées par le relecteur (avec les écarts mesurés). La première est relue à
        # son tour : une réécriture peut inventer (essai Begrâm du 29/09 : « meurent au combat » apparu à la réécriture,
        # jamais relu) ; la seconde ne l'est plus.
        for attempt in (1, 2):
            if not problems:
                break
            ctx.log("script.reprise", tour=attempt, issues=issues, relecture=problems)
            ctx.progress(25 + 10 * attempt, f"Réécriture de l'histoire ({attempt})")
            draft = normalize_draft(
                ask(
                    system,
                    f"{user}\n\n{rewrite_request(issues, problems)}\n\nHistoire précédente :\n{draft.model_dump_json()}",
                    StoryDraft,
                ),
                lang,
            )
            issues = lint_story(draft, lang, target)
            problems = []
            if attempt == 1:
                ctx.progress(40, "Relecture de la réécriture")
                problems = self._review_story(ctx, ask, draft, prod, facts_txt, dossier, lang, target)
        # La forme : une dernière passe pour les seuls écarts mesurables (rythme, longueurs, budget), sans toucher au fond
        # relu ; gardée seulement si elle en corrige.
        if issues:
            ctx.log("script.forme", issues=issues)
            ctx.progress(45, "Reprise de la forme (rythme, longueurs)")
            fix = normalize_draft(
                ask(
                    system, f"{user}\n\n{polish_request(issues)}\n\nHistoire précédente :\n{draft.model_dump_json()}", StoryDraft
                ),
                lang,
            )
            fix_issues = lint_story(fix, lang, target)
            if len(fix_issues) < len(issues):
                draft, issues = fix, fix_issues
        ctx.log(
            "script.histoire",
            mots=story_words(draft, lang),
            temps=len(draft.beats),
            moteur=draft.engine,
            idee=draft.central_idea,
            problemes=issues,
        )
        ctx.progress(50, "Découpage en plans")
        chunks = split_scenes(draft, lang)
        shots = self._shots(ctx, llm, prod, series, draft, chunks, langs, facts_txt, dossier)
        script = normalize_story(build_script(draft, chunks, shots, lang, langs, title=prod.get("title") or ""))
        lint_langs = langs if prod["format"] == "A_voiceover" else []
        remaining = lint_script(script, lint_langs, target) + [
            f"récit : {i}" for i in lint_story(draft, lang, target, shared=False)
        ]
        if remaining:
            ctx.log("script.problemes_restants", level="warn", issues=remaining)
        # quel modèle a vraiment répondu à chaque appel (chaîne d'écriture, Réglages → IA)
        used = [*getattr(teller, "used", []), *(getattr(llm, "used", []) if teller is not llm else [])]
        ctx.log("script.modeles", modeles=list(used))
        return script, remaining, tpl_id

    @staticmethod
    def _asker(ctx: Context, teller: LLM, fallback: LLM) -> Callable[[str, str, type[Any]], Any]:
        """Un appel du conteur ou de son relecteur : les modèles forts de la chaîne d'écriture (strong_writers) ; s'ils
        sont tous épuisés, la tâche attend une heure (Postpone, sans échouer), puis se contente du secours après 12 h."""

        def ask(system: str, user: str, schema: type[Any]) -> Any:
            try:
                return teller.complete_json(system, user, schema)
            except Exception as exc:
                if teller is fallback:
                    raise
                waited = datetime.now(UTC) - ctx.job.created_at
                if waited < STRONG_WAIT_MAX:
                    raise Postpone(
                        "modèles d'écriture forts épuisés",
                        STRONG_WAIT_S,
                        label="Le conteur attend un modèle d'écriture fort (quota)",
                        error=str(exc)[:500],
                    ) from exc
                ctx.log("script.modele_de_secours", level="warn", attente_h=round(waited.total_seconds() / 3600, 1))
                return fallback.complete_json(system, user, schema)

        return ask

    @staticmethod
    def _dossier(ctx: Context, sources: list[dict[str, Any]]) -> str:
        """Pages sources entières (sources/wikipedia.source_dossier) ; sans elles, le script s'écrit sur les faits de l'idée."""
        try:
            return source_dossier(
                sources, ctx.settings.data_dir / "sources" / "wikipedia", ctx.settings.effective_wikipedia_user_agent
            )
        except Exception as exc:  # noqa: BLE001
            ctx.log("script.dossier_indisponible", level="warn", erreur=str(exc)[:300])
            return ""

    @staticmethod
    def _review_story(
        ctx: Context,
        ask: Callable[[str, str, type[Any]], Any],
        draft: StoryDraft,
        prod: dict[str, Any],
        facts_txt: str,
        dossier: str,
        lang: str,
        target: int,
    ) -> list[str]:
        """Relecture du récit (prompt script_review, onglet Agents) : ce que le correcteur ne mesure pas, avec la
        checklist du récit. Renvoie les problèmes à corriger, [] si le relecteur laisse partir l'histoire ; un échec de
        la relecture ne bloque rien (l'attente d'un modèle fort, elle, remet la tâche à plus tard)."""
        user = "\n\n".join(
            part
            for part in (
                f"IDÉE : {prod['title']}\nAccroche proposée : {prod['hook']}\nPrémisse : {prod['premise']}",
                f"HISTOIRE À RELIRE (langue {lang}, durée visée {target} s) :\n{story_listing(draft, lang)}",
                prompt_text(ctx.db, "rules_storytelling", RULES),
                f"FAITS DE L'IDÉE :\n{facts_txt}" if facts_txt else "",
                f"DOSSIER :\n{dossier}" if dossier else "",
            )
            if part
        )
        try:
            review = ask(prompt_text(ctx.db, "script_review", REVIEW_PROMPT), user, ScriptReview)
        except Postpone:
            raise
        except Exception as exc:  # noqa: BLE001
            ctx.log("script.relecture_indisponible", level="warn", erreur=str(exc)[:300])
            return []
        problems = [p.strip() for p in review.problems if p.strip()][:REVIEW_PROBLEMS_MAX]
        ctx.log("script.relecture", ok=review.ok, problemes=problems)
        return [] if review.ok else problems

    def _shots(
        self,
        ctx: Context,
        llm: LLM,
        prod: dict[str, Any],
        series: Series | None,
        draft: StoryDraft,
        chunks: list[Chunk],
        langs: list[str],
        facts_txt: str,
        dossier: str,
    ) -> ShotList:
        """Le réalisateur (prompt script_shots) : un plan par scène du découpage ; une reprise s'il en oublie."""
        lang = langs[0] if langs else "fr"
        others = [x for x in langs if x != lang]
        total = sum(c.duration_s for c in chunks)
        user = "\n\n".join(
            part
            for part in (
                (f"SÉRIE : {series.name}\nBrief : {series.brief}") if series else "",
                self._music_brief(ctx, "story", series),
                prompt_text(ctx.db, "rules_images", IMAGE_RULES),
                prompt_text(ctx.db, "hint_continuity", CONTINUITY_HINT),
                f"IDÉE : {prod['title']}\nPrémisse : {prod['premise']}\nTemps visuels proposés : {prod['visual_beats']}",
                f"L'HISTOIRE :\n{story_listing(draft, lang)}",
                f"SCÈNES À FILMER ({len(chunks)} scènes, {total:.0f} s ; index de 0 à {len(chunks) - 1}) :\n{scenes_listing(chunks)}",
                f"Style visuel : {prod['style_preset']} · Langue du récit : {lang} · "
                + (f"Traduis la narration de chaque scène en : {others}" if others else "Aucune autre langue : narration = {}"),
                f"FAITS SOURCÉS (pour l'exactitude des images : époque, lieux, objets) :\n{facts_txt}" if facts_txt else "",
                f"DOSSIER :\n{dossier}" if dossier else "",
            )
            if part
        )
        system = prompt_text(ctx.db, "script_shots", SHOTS_PROMPT)
        shots = llm.complete_json(system, user, ShotList)
        missing = missing_shots(chunks, shots)
        if missing:
            ctx.log("script.plans_manquants", scenes=missing)
            ctx.progress(55, "Découpage : plans manquants")
            retry = llm.complete_json(
                system,
                f"{user}\n\nTon découpage oublie les scènes {missing} : rends TOUTES les scènes, index de 0 à {len(chunks) - 1}."
                f"\n\nDécoupage précédent :\n{shots.model_dump_json()}",
                ShotList,
            )
            if len(missing_shots(chunks, retry)) < len(missing):
                shots = retry
        return shots

    def _write_recipe(
        self, ctx: Context, prod: dict[str, Any], langs: list[str], series: Series
    ) -> tuple[ScriptV1, list[str], UUID | None]:
        """Script d'un format visuel (chantier en accéléré, visite de luxe) : prompt et règles de la recette
        (worker/recipes.py, clés script_<recette> et rules_hook_title de worker/prompts.py), mécanique imposée en code
        (normalize_script), puis vérification et une reprise."""
        recipe = series.recipe
        target = int(prod["target_duration_s"] or 30)
        examples = ctx.db.fetch_all(
            """select p.script from v_video_overview v join productions p on p.id = v.production_id
               where v.status = 'published' and p.script is not null and p.series_id = %s
               order by v.average_view_pct desc nulls last limit 2""",
            (series.id,),
        )
        # Drame : les voix de synthèse que peuvent prendre ses personnages (série en voix constantes, docs/35)
        voices = (
            voices_brief(character_voices(tts_catalog(ctx.settings), langs[0] if langs else "fr")) if recipe == "drama" else ""
        )
        user = "\n\n".join(
            part
            for part in (
                f"SÉRIE : {series.name}\nBrief : {series.brief}",
                self._music_brief(ctx, montage_format(recipe), series),  # un drame a les musiques des récits
                f"CONCEPT : {prod['title']}\nAccroche : {prod['hook']}\nAngle : {prod.get('angle') or '—'}\n"
                f"Prémisse : {prod['premise']}\nCatégorie : {prod['category']}\nTemps visuels : {prod['visual_beats']}",
                f"Durée cible : {target} s · Style visuel : {prod['style_preset']} · Langues (hook_title, on_screen_text, "
                f"metadata{', répliques' if recipe == 'drama' else ''}) : {langs}",
                voices,
                # Règles du récit (docs/37) : valables aussi en dialogues ; la structure du drame, dans son prompt, prime
                (f"{prompt_text(ctx.db, 'rules_storytelling', RULES)}\n{DRAMA_RULES_NOTE}" if recipe == "drama" else ""),
                script_context(recipe, prompt_text(ctx.db, "rules_hook_title", HOOK_RULES)),
                f"Stratégie validée :\n{guidance_text(active_strategies(ctx.db))}",
                lessons_text(ctx.db, "script", channel_id=prod.get("channel_id"), recipe=recipe),  # leçons validées (docs/25)
                f"Exemples de scripts performants de la série : {[e['script'] for e in examples]}" if examples else "",
            )
            if part
        )
        system, tpl_id = active_prompt(ctx.db, f"script_{recipe}", SCRIPT_PROMPTS[recipe])
        llm = get_llm(ctx.settings, ctx.db, writer=True)
        ctx.progress(20, f"Appel LLM · recette {recipe}")
        script = normalize_script(llm.complete_json(system, user, ScriptV1), recipe)
        issues = lint_recipe_script(script, recipe, langs, target)
        if issues:
            ctx.log("script.reprise", recipe=recipe, issues=issues)
            ctx.progress(40, "Reprise du script (règles du format)")
            retry = normalize_script(
                llm.complete_json(
                    system, f"{user}\n\n{feedback(issues)}\n\nScript précédent :\n{script.model_dump_json()}", ScriptV1
                ),
                recipe,
            )
            retry_issues = lint_recipe_script(retry, recipe, langs, target)
            if len(retry_issues) <= len(issues):
                script, issues = retry, retry_issues
        if issues:
            ctx.log("script.problemes_restants", level="warn", recipe=recipe, issues=issues)
        return script, issues, tpl_id

    @staticmethod
    def _music_brief(ctx: Context, recipe: str, series: Series | None) -> str:
        """Ambiances des musiques de Luca qui ont une piste pour ce format (worker/music.py, docs/26-musique.md), à
        choisir dans music_mood ; sans bibliothèque, les ambiances conseillées par la série."""
        moods = series.music_moods if series else []
        tracks = load_library(ctx.db, ctx.settings.effective_music_library_dir)
        return mood_brief(tracks, recipe, moods) or (f"Ambiances musicales conseillées : {moods}" if moods else "")

    @staticmethod
    def _image_to_video(ctx: Context, override: str | None) -> bool:
        try:
            return get_video_provider(ctx.settings, override).image_to_video
        except (WorkflowError, OSError):
            return False

    @staticmethod
    def _channels(ctx: Context, prod: dict[str, Any]) -> list[dict[str, Any]]:
        """La chaîne visée par la production (Création, migration 0008). Une production d'avant 0008, sans chaîne,
        garde l'ancienne règle : une vidéo par chaîne active."""
        if prod.get("channel_id"):
            rows = ctx.db.fetch_all("select id, lang from channels where id = %s", (prod["channel_id"],))
            if rows:
                return rows
        return ctx.db.fetch_all("select id, lang from channels where is_active order by lang")

    @staticmethod
    def _create_videos(ctx: Context, pid: UUID, fmt: str, script: ScriptV1, channels: list[dict[str, Any]]) -> list[UUID]:
        out = []
        for ch in channels:
            lang = ch["lang"]
            meta = script.metadata.get(lang)
            narration = " ".join(s.narration.get(lang, "") for s in script.scenes).strip() or None
            row = ctx.db.fetch_one(
                """insert into videos (production_id, channel_id, lang, format, title, description, tags, narration_text)
                   values (%s, %s, %s, %s, %s, %s, %s, %s)
                   on conflict (production_id, channel_id) do update set narration_text = excluded.narration_text
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
            out.append(row["id"])
            ctx.log("dag.video", video_id=str(row["id"]), lang=lang)
        return out


def strong_writers(llm: LLM) -> LLM:
    """La chaîne d'écriture sans ses modèles de secours (Flash-Lite…), pour le conteur et son relecteur ; la même chaîne
    si elle n'a que ceux-là ou si elle n'en a aucun."""
    chain = getattr(llm, "chain", None)
    if not chain:
        return llm
    strong = [p for p in chain if not WEAK_WRITERS.search(str(getattr(p, "model", "")))]
    return FallbackLLM(strong) if strong and len(strong) < len(chain) else llm
