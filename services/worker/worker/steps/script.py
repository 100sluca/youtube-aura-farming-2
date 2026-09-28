"""Agent script : concept → ScriptV1 (scénario en scènes), vérifié par le linter de storytelling, puis mise en
file de la suite.

Le prompt reçoit le brief de la série, les règles du storytelling (worker/storytelling.py), le concept, ses faits
sourcés et, pour une série documentaire, le DOSSIER : ses pages Wikipédia relues en entier, version anglaise comprise
(sources/wikipedia.source_dossier ; l'agent idée n'en garde que quelques faits). Le script obtenu passe par
lint_script() (règles mesurables) puis par la relecture éditoriale (prompt script_review : enjeu compris avant 10 s,
promesses tenues, conflit et humain, faits du dossier) ; s'il y a des problèmes, le scénariste le réécrit une fois
avec la liste, puis une dernière reprise corrige les écarts mesurables qui resteraient. Les problèmes restants sont
conservés dans productions.lint. Les agents qui écrivent passent par le modèle d'écriture (get_llm(writer=True)).
Une série à recette visuelle (chantier en accéléré, visite de luxe : series.recipe, worker/recipes.py) a son
propre prompt, sa normalisation en code et son linter ; pas de voix, un titre d'accroche et des bruitages.

Suite (worker/dag.py) : la vidéo de la chaîne de la production (productions.channel_id, choisie dans Création ;
une production d'avant 0008 sans chaîne en a une par chaîne active) et son job seo ; puis soit le storyboard
(route image → vidéo, validée à la main), soit directement le rendu (clips, voix, montage, contrôle).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from ..dag import enqueue_render_dag
from ..drama import character_voices, voices_brief
from ..lessons import lessons_text
from ..models import ScriptReview, ScriptV1
from ..music import load_library, mood_brief
from ..prompts import active_prompt, prompt_text
from ..providers.llm import LLM, get_llm
from ..providers.tts import tts_catalog
from ..providers.video import WorkflowError, get_video_provider
from ..recipes import HOOK_RULES, SCRIPT_PROMPTS, has_prompt, lint_recipe_script, montage_format, normalize_script, script_context
from ..series import Series, series_of_concept
from ..settings_store import load_generation_config
from ..sources.wikipedia import source_dossier
from ..storytelling import RULES, feedback, lint_script, normalize_story
from ..strategy import active_strategies, guidance_text
from .base import Context, Step

REVIEW_PROBLEMS_MAX = 8

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
        """Prompt système et consignes : versions actives en base (onglet Agents du dashboard, worker/prompts.py)."""
        series = series_of_concept(ctx.db, prod["concept_id"]) if prod.get("concept_id") else None
        if series and has_prompt(series.recipe):  # formats visuels et drame : leur propre scénariste
            return self._write_recipe(ctx, prod, langs, series)
        system, tpl_id = active_prompt(ctx.db, "script", DEFAULT_PROMPT)
        examples = ctx.db.fetch_all(
            """select p.script from v_video_overview v join productions p on p.id = v.production_id
               where v.status = 'published' and p.script is not null
               order by (p.series_id = %s) desc, v.average_view_pct desc nulls last limit 3""",
            (series.id if series else None,),
        )
        facts = prod.get("facts") or []
        sources = prod.get("sources") or []
        facts_txt = "\n".join(f"- [{int(f.get('source', 0)) + 1}] {f.get('claim', '')}" for f in facts)
        sources_txt = "\n".join(f"[{i + 1}] {s.get('title')} — {s.get('url')}" for i, s in enumerate(sources))
        ctx.progress(10, "Dossier des sources")
        dossier = self._dossier(ctx, sources) if sources else ""
        target = int(prod["target_duration_s"] or 30)
        user = "\n\n".join(
            part
            for part in (
                (f"SÉRIE : {series.name}\nBrief : {series.brief}") if series else "",
                self._music_brief(ctx, "story", series),
                prompt_text(ctx.db, "rules_storytelling", RULES),
                f"CONCEPT : {prod['title']}\nAccroche : {prod['hook']}\nAngle : {prod.get('angle') or '—'}\n"
                f"Prémisse : {prod['premise']}\nCatégorie : {prod['category']}\nTemps visuels : {prod['visual_beats']}",
                f"FAITS SOURCÉS retenus par l'agent idée (points de départ) :\n{facts_txt}\nSources :\n{sources_txt}" if facts_txt else "",
                f"DOSSIER : les pages sources relues en entier. Avec les faits ci-dessus, c'est la seule base des affirmations ; "
                f"puises-y l'enjeu, le conflit et les personnes.\n{dossier}" if dossier else "",
                f"Format : {prod['format']} · Durée cible : {target} s (environ {max(4, round(target / 5))} scènes) · "
                f"Style visuel : {prod['style_preset']} · Langues de narration : {langs} (uniquement celles-ci)",
                prompt_text(ctx.db, "hint_continuity", CONTINUITY_HINT),
                # Titre d'accroche : le modèle de montage (onglet Montage) peut l'afficher aussi sur les récits narrés
                prompt_text(ctx.db, "rules_hook_title", HOOK_RULES),
                f"Stratégie validée :\n{guidance_text(active_strategies(ctx.db))}",
                lessons_text(ctx.db, "script", channel_id=prod.get("channel_id"), recipe="story"),  # leçons validées (docs/25)
                f"Exemples de scripts performants : {[e['script'] for e in examples]}" if examples else "",
            )
            if part
        )
        lint_langs = langs if prod["format"] == "A_voiceover" else []
        llm = get_llm(ctx.settings, ctx.db, writer=True)
        ctx.progress(20, "Appel LLM")
        script = normalize_story(llm.complete_json(system, user, ScriptV1))
        issues = lint_script(script, lint_langs, target)
        ctx.progress(35, "Relecture éditoriale")
        problems = self._review(ctx, llm, script, prod, facts_txt, dossier, langs)
        if issues or problems:
            ctx.log("script.reprise", issues=issues, relecture=problems)
            ctx.progress(50, "Réécriture (relecture et règles)")
            retry = normalize_story(llm.complete_json(
                system, f"{user}\n\n{rewrite_request(issues, problems)}\n\nScript précédent :\n{script.model_dump_json()}", ScriptV1))
            retry_issues = lint_script(retry, lint_langs, target)
            # la relecture porte sur le fond : sa réécriture l'emporte ; sinon, seulement si elle corrige quelque chose
            if problems or len(retry_issues) <= len(issues):
                script, issues = retry, retry_issues
            if issues:  # dernière reprise, pour les seuls écarts mesurables (longueurs, rôles, durée)
                ctx.progress(70, "Reprise du script (règles mesurables)")
                fix = normalize_story(llm.complete_json(
                    system, f"{user}\n\n{feedback(issues)}\n\nScript précédent :\n{script.model_dump_json()}", ScriptV1))
                fix_issues = lint_script(fix, lint_langs, target)
                if len(fix_issues) < len(issues):
                    script, issues = fix, fix_issues
        if issues:
            ctx.log("script.problemes_restants", level="warn", issues=issues)
        # quel modèle a vraiment répondu à chaque appel (chaîne d'écriture, Réglages → IA)
        ctx.log("script.modeles", modeles=list(getattr(llm, "used", [])))
        return script, issues, tpl_id

    @staticmethod
    def _dossier(ctx: Context, sources: list[dict[str, Any]]) -> str:
        """Pages sources entières (sources/wikipedia.source_dossier) ; sans elles, le script s'écrit sur les faits de l'idée."""
        try:
            return source_dossier(sources, ctx.settings.data_dir / "sources" / "wikipedia", ctx.settings.effective_wikipedia_user_agent)
        except Exception as exc:  # noqa: BLE001
            ctx.log("script.dossier_indisponible", level="warn", erreur=str(exc)[:300])
            return ""

    @staticmethod
    def _review(ctx: Context, llm: LLM, script: ScriptV1, prod: dict[str, Any], facts_txt: str, dossier: str,
                langs: list[str]) -> list[str]:
        """Relecture éditoriale (prompt script_review, onglet Agents) : ce que le correcteur ne mesure pas. Renvoie les
        problèmes à corriger, [] si le relecteur laisse partir le script ; un échec de la relecture ne bloque rien."""
        lang = langs[0] if langs else "fr"
        story = "\n".join(
            f"{s.index + 1}. [{s.role or '—'}, {s.duration_s:g} s]" + (f" CARTE de « {s.map.place} »" if s.map and s.is_map else "")
            + f" {s.narration.get(lang, '') or '(sans voix) ' + s.visual_prompt[:120]}"  # type: ignore[call-overload]
            for s in script.scenes
        )
        user = "\n\n".join(
            part
            for part in (
                f"CONCEPT : {prod['title']}\nAccroche : {prod['hook']}\nPrémisse : {prod['premise']}",
                f"SCRIPT À RELIRE (langue {lang}, {script.duration_s:g} s) :\n"
                f"Titre d'accroche : {script.hook_title.get(lang) or '—'}\n{story}\nBoucle : {script.loop_note or '—'}",  # type: ignore[call-overload]
                f"FAITS DE L'IDÉE :\n{facts_txt}" if facts_txt else "",
                f"DOSSIER :\n{dossier}" if dossier else "",
            )
            if part
        )
        try:
            review = llm.complete_json(prompt_text(ctx.db, "script_review", REVIEW_PROMPT), user, ScriptReview)
        except Exception as exc:  # noqa: BLE001
            ctx.log("script.relecture_indisponible", level="warn", erreur=str(exc)[:300])
            return []
        problems = [p.strip() for p in review.problems if p.strip()][:REVIEW_PROBLEMS_MAX]
        ctx.log("script.relecture", ok=review.ok, problemes=problems)
        return [] if review.ok else problems

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
        voices = voices_brief(character_voices(tts_catalog(ctx.settings), langs[0] if langs else "fr")) if recipe == "drama" else ""
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
                llm.complete_json(system, f"{user}\n\n{feedback(issues)}\n\nScript précédent :\n{script.model_dump_json()}", ScriptV1),
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
                (pid, ch["id"], lang, fmt, meta.title if meta else None, meta.description if meta else None,
                 meta.tags if meta else [], narration),
            )
            out.append(row["id"])
            ctx.log("dag.video", video_id=str(row["id"]), lang=lang)
        return out


def rewrite_request(issues: list[str], problems: list[str]) -> str:
    """Message de réécriture : les corrections de fond de la relecture, puis les écarts mesurables du correcteur."""
    parts = []
    if problems:
        parts.append("La relecture éditoriale demande ces corrections (le fond du récit) :\n- " + "\n- ".join(problems))
    if issues:
        parts.append(feedback(issues))
    return "\n\n".join(parts) + "\n\nRéécris le script en entier en appliquant tout cela, en gardant ce qui marche."


DEFAULT_PROMPT = """Tu écris le script d'UN YouTube Short (9:16) raconté en voix off, pour une série dont tu reçois le
brief, le concept (accroche, prémisse, temps visuels, faits sourcés), le DOSSIER des sources (séries documentaires)
et les règles du storytelling. Tu racontes une histoire, pas une fiche : ce que c'est, pourquoi ça compte, ce qui
s'y est joué, ce que ça a coûté.
Découpage : une scène de 4 à 6 s par tranche de 5 s de la durée cible (8 scènes pour 40 s), chacune avec son rôle
(role : hook, setup, reveal, escalation, payoff, loop). Chaque scène :
- visual_prompt, en anglais : la PREMIÈRE image de la scène, décrite comme une photo (sujet, lieu, époque,
  matières, lumière, cadrage, objectif), sans texte, sans visage reconnaissable ;
- motion_prompt, en anglais : le seul mouvement de la scène à partir de cette image (caméra ou action) ;
- narration dans chaque langue demandée (format A) : 10 à 15 mots par scène de 5 s, une information nouvelle,
  des phrases courtes, les nombres et les années en chiffres (« 852 morts », « en 1994 ») ; ou sfx (format B) ;
- on_screen_text, optionnel : 5 mots au plus, un nombre en chiffres ou un mot-clé.
Séries documentaires : le DOSSIER contient bien plus que les faits de l'idée ; puises-y ce qui fait l'histoire (à
quoi ça sert, l'obstacle ou la controverse et sa raison, les personnes, les tentatives ratées, les chiffres de
comparaison, ce qu'il en reste). Chaque affirmation vient des faits ou du dossier : rien d'inventé ni de complété de
mémoire. Un mot qui intrigue (« controversé », « secret ») est expliqué dans la même scène ou la suivante.
SCÈNE CARTE (champ map) : quand le sujet est un lieu réel (ville, île, canal, fleuve, monument, montagne, route
d'une expédition), une scène, de préférence la 2e, est une carte rendue par le code : la caméra descend de l'espace
jusqu'au lieu, dont le tracé se dessine. map.place = le lieu, tel que le titre de sa page Wikipédia (ex. « Canal
Rhin-Main-Danube ») ; map.ends = 0 à 2 repères aux deux bouts du tracé (ex. ["Bamberg", "Kelheim"]) ; map.context
= 0 à 3 grands repères montrés avant le zoom pour situer (ex. ["Mer du Nord", "Mer Noire"]). Les repères
s'affichent tels quels : écris-les dans la langue de la vidéo. Sa narration dit où c'est et ce que ça relie ou
change ; son visual_prompt décrit quand même le lieu vu du ciel (secours) ; 5 à 7 s. Une seule scène carte par
Short, aucune pour un sujet sans lieu précis.
loop_note : comment le dernier plan renvoie au premier. music_mood : l'ambiance de la musique de fond, prise dans la
liste MUSIQUE DE FOND (identifiant tel quel). metadata : brouillon par langue (titre ≤ 60 caractères,
description, 10 tags), affiné ensuite par l'agent SEO. Applique la stratégie validée. Réponds uniquement en JSON
conforme à ScriptV1."""

REVIEW_PROMPT = """Tu es le rédacteur en chef d'une chaîne YouTube Shorts d'histoires racontées. Tu relis le script d'un
Short avant le tournage, à la place d'un spectateur qui ne connaît rien au sujet et qui décroche dès qu'il ne
comprend pas pourquoi il devrait rester. Tu ne réécris pas le script : tu dis précisément ce qui ne va pas et quoi
faire, en t'appuyant sur le dossier quand il y en a un.
Vérifie, dans cet ordre :
1. Enjeu : avant la 10e seconde, sait-on ce que c'est, où c'est, et pourquoi ça compte (à quoi ça sert, ce qui
   était en jeu) ?
2. Promesses tenues : chaque mot qui intrigue (controversé, secret, fou, maudit, personne ne savait…) est-il
   expliqué par un fait concret dans la même scène ou la suivante ?
3. Conflit et humain : y a-t-il un obstacle, un adversaire ou un prix payé, et au moins une personne, une date ou
   une citation qui rend l'histoire humaine ? Le dossier en contient-il qui manquent au script ?
4. Progression : chaque scène apporte-t-elle une information nouvelle ? Relève les phrases creuses et les redites.
5. Exactitude : chaque chiffre, nom, date ou citation est-il dans les faits ou le dossier ? Le titre d'accroche
   dit-il vrai, sans contresens ?
6. Fin : la dernière phrase répond-elle à l'accroche et donne-t-elle envie de revoir le début ?
ok = true seulement si le script peut partir tel quel. problems : 6 au plus, chacun avec la scène visée et la
correction attendue (« scène 2 : dire pourquoi le projet était contesté, avec le fait du dossier qui l'explique »).
Réponds uniquement en JSON : {"ok": true ou false, "problems": ["…"]}."""
