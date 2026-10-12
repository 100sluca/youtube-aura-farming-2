"""Réécrire le récit d'une vidéo sur ses plans déjà faits (docs/49 §6).

Demandé par Luca le 01/10 devant « Begrâm » : les images et le thème sont bons, l'écriture ne l'est pas (« ce mur cache
le trésor de la route de la soie » : quel trésor, pourquoi il compte ? des faits importants posés sans qu'on sente
l'enjeu). Plutôt que de tout refaire (storyboard, clips : des heures de GPU), le conteur réécrit ce que dit la voix,
scène par scène, sur les plans tels qu'ils sont : chaque phrase colle à l'image de sa scène et tient dans la durée de
son clip. Les remarques de Luca (« une mission jamais achevée ») guident l'angle, le dossier reste la seule source.

Puis correcteur et relecteur comme au script (une réécriture au plus), et la variante part comme une variante
d'accroche (worker/hookvariant.clone) : copie de la production, clips liés, voix → montage → contrôle, SEO refait ;
elle arrive à valider. Le script et la vidéo d'origine ne changent pas.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel, Field, ValidationError

from .hooktitle import clean_hook
from .hookvariant import Variant, check_texts, clone, make_variant, source_of
from .models import LangText, ScriptReview, ScriptV1, StoryDraft, StoryPart
from .numbers import to_digits
from .prompts import prompt_text
from .recipes import HOOK_RULES
from .sources.wikipedia import source_dossier
from .storycraft import (
    BUDGET_WPS,
    REVIEW_PROMPT,
    lint_story,
    normalize_draft,
    rewrite_request,
    scene_seconds,
    story_listing,
    word_budget,
)
from .storytelling import EMPTY_SUPERLATIVES, RULES, said_words

log = structlog.get_logger(__name__)

WORDS_MARGIN = 1.15  # mots dits d'une scène : la durée de son clip × débit du récit, avec un peu de marge


class SceneText(BaseModel):
    index: int
    part: StoryPart
    text: str = Field(description="ce que dit la voix pendant cette scène, mot pour mot")
    on_screen: str = Field("", description="texte gravé à l'écran sur cette scène (3 mots au plus), vide le plus souvent")


class StoryRewrite(BaseModel):
    central_idea: str = ""
    engine: str = ""
    protagonist: str = ""
    stakes: str = ""
    ending: str = ""
    scenes: list[SceneText]
    hook_title: LangText = Field(default_factory=dict)
    title: str = Field("", description="titre YouTube, 70 caractères au plus")


@dataclass
class Shot:
    index: int
    seconds: float  # durée du clip
    shows: str  # ce qu'on voit (français si le conteur l'avait écrit, sinon le prompt d'image)
    said: str  # ce que la voix disait
    words_max: int


REWRITE_PROMPT = """Tu es le conteur d'une chaîne YouTube Shorts d'histoires racontées en voix off (9:16). Les IMAGES
d'un Short sont déjà faites et bonnes ; c'est l'ÉCRITURE qui n'a pas marché : on ne sentait ni l'enjeu ni pourquoi le
sujet compte. Tu réécris ce que dit la voix, scène par scène, sur les plans tels qu'ils sont.

Tu reçois : les remarques de l'humain qui pilote la chaîne (elles priment sur tout, sauf sur les faits), les règles du
récit, le dossier (la seule source des faits), l'ancien texte, et la liste des scènes, chacune avec ce qu'on y voit, la
durée de son clip et le nombre de mots dits qu'elle peut porter.

MÉTHODE :
1. Cherche dans le dossier ce qui fait ressentir quelque chose à un ado de 13 ans qui ne connaît rien au sujet : une
   perte, un gâchis, un sacrifice, une mission inachevée, ou une chose unique qui semble sortie d'un film. Dis-le dans
   central_idea, stakes et ending (la dernière phrase, écrite d'abord, 12 mots au plus).
2. Écris une phrase (deux courtes au plus) par scène, dans l'ordre des scènes, TOUTES les scènes, sans en sauter :
   - elle colle à l'image de sa scène : elle dit ce qu'on voit, ou ce que l'image illustre ; jamais une chose que
     l'image contredit ;
   - elle tient dans le nombre de mots de la scène (un nombre compte pour les mots qui le disent) et en approche
     le plus souvent : la voix doit remplir le plan, sinon le récit est trop court pour être compris ; une phrase de
     5 mots ou moins de temps en temps seulement, là où l'histoire bascule ;
   - part = le temps du récit : la 1re scène est l'accroche (hook), la 2e la promesse (promise), puis context,
     conflict (un ou plusieurs), twist (facultatif), payoff, et la dernière scène est la chute (ending, mot pour mot
     ta dernière phrase) ; les scènes d'un même temps se suivent.
3. L'accroche : le sujet concret et ce qu'il a d'extraordinaire ou ce qui a été perdu, en mots de tous les jours (« la
   route de la soie » ne dit rien à un ado : dis ce que c'est ou ce que ça veut dire, en quelques mots). La promesse
   annonce la fin sans la donner. Le contexte dit qui, où, quand, et POURQUOI ÇA COMPTE (ce que vaut la chose, ce
   qu'elle a d'unique). Puis la danse des « mais » et des « donc » jusqu'à la réponse et la chute.
4. Faits : chaque fait, nom, nombre, date ou circonstance vient du dossier. Quand le dossier reste vague
   (« disparaissent tragiquement »), tu restes vague : rien n'est inventé pour dramatiser.
5. on_screen : seulement si un mot ou un chiffre clé gagne à être lu (3 mots au plus), sinon vide.
6. hook_title : le titre d'accroche gravé à l'écran (règles fournies) ; title : le titre YouTube.

Phrases de 3 à 16 mots, présent de narration, voix active, nombres en chiffres, ton d'une histoire qu'on raconte à un
ami. Réponds uniquement en JSON conforme à StoryRewrite : {"central_idea": "…", "engine": "…", "protagonist": "…",
"stakes": "…", "ending": "…", "scenes": [{"index": 0, "part": "hook", "text": "…", "on_screen": ""}, …],
"hook_title": {"fr": "…"}, "title": "…"}."""


def shots_of(script: ScriptV1, clips: dict[int, float], lang: str) -> list[Shot]:
    """Les plans à garder : ce qu'on voit (le « show » du conteur quand la scène porte un seul temps, sinon le prompt
    d'image), la durée du clip et les mots que la scène peut porter."""
    shows: dict[int, str] = {}
    if script.story:
        said = [s.narration.get(lang, "") for s in script.scenes]  # type: ignore[call-overload]
        for beat in script.story.beats:
            for i, text in enumerate(said):
                if text and text in beat.text and i not in shows:
                    shows[i] = beat.show
    out = []
    for s in script.scenes:
        seconds = float(clips.get(s.index) or s.duration_s)
        out.append(
            Shot(
                index=s.index,
                seconds=seconds,
                shows=shows.get(s.index) or s.visual_prompt,
                said=s.narration.get(lang, ""),  # type: ignore[call-overload]
                words_max=max(4, int(seconds * BUDGET_WPS * WORDS_MARGIN)),
            )
        )
    return out


def to_draft(rw: StoryRewrite, shots: list[Shot], lang: str) -> StoryDraft:
    """Le récit réécrit vu comme un récit du conteur (temps = scènes consécutives du même part), pour le correcteur et
    le relecteur."""
    by_index = {s.index: s for s in rw.scenes}
    beats: list[dict[str, Any]] = []
    for shot in shots:
        sc = by_index.get(shot.index)
        if sc is None or not sc.text.strip():
            continue
        if beats and beats[-1]["part"] == sc.part:
            beats[-1]["text"] += " " + sc.text.strip()
        else:
            beats.append({"part": sc.part, "text": sc.text.strip(), "show": shot.shows})
    draft = StoryDraft.model_validate(
        {
            "central_idea": rw.central_idea,
            "engine": rw.engine,
            "protagonist": rw.protagonist,
            "stakes": rw.stakes,
            "ending": rw.ending,
            "beats": beats,
            "hook_title": rw.hook_title,
        }
    )
    return normalize_draft(draft, lang)


def lint_rewrite(rw: StoryRewrite, shots: list[Shot], lang: str, target_s: float) -> list[str]:
    """Écarts mesurables : une scène sans texte, trop de mots pour son clip, l'accroche ou la chute pas à leur place,
    puis ceux du correcteur du récit (structure, rythme, « et ensuite », chute, nombres, budget)."""
    issues = []
    by_index = {s.index: s for s in rw.scenes}
    missing = [s.index for s in shots if not (by_index.get(s.index) and by_index[s.index].text.strip())]
    if missing:
        issues.append(f"scènes sans texte : {', '.join(map(str, missing))} ; chaque scène a sa phrase")
    long = [
        f"scène {s.index} ({n} mots, {s.words_max} au plus)"
        for s in shots
        if (sc := by_index.get(s.index)) and (n := len(said_words(sc.text, lang))) > s.words_max
    ]
    if long:
        issues.append("trop long pour le clip : " + ", ".join(long[:6]))
    if shots and (first := by_index.get(shots[0].index)) and first.part != "hook":
        issues.append("la 1re scène est l'accroche (part « hook »)")
    if shots and (last := by_index.get(shots[-1].index)) and last.part != "ending":
        issues.append("la dernière scène est la chute (part « ending »)")
    if missing:
        return issues
    text = " ".join(s.text for s in rw.scenes)
    if m := re.search(EMPTY_SUPERLATIVES.get(lang, EMPTY_SUPERLATIVES["fr"]), text, re.I):
        issues.append(f"superlatif vide « {m.group(0)} » : montre le fait qui le prouve")
    try:
        draft = to_draft(rw, shots, lang)
    except ValidationError:
        return [*issues, "trop peu de temps du récit : accroche, promesse, contexte, conflit, réponse et chute"]
    return issues + lint_story(draft, lang, target_s, shared=False)


def rewritten_script(script: ScriptV1, rw: StoryRewrite, shots: list[Shot], lang: str) -> ScriptV1:
    """Le script de la variante : mêmes plans, la voix et les textes à l'écran réécrits, la durée de chaque scène suit
    son nouveau texte (lint_rewrite borne ses mots à la durée de son clip)."""
    by_index = {s.index: s for s in rw.scenes}
    scenes = []
    for s in script.scenes:
        sc = by_index[s.index]
        text = to_digits(sc.text.strip(), lang)
        shown = to_digits(sc.on_screen.strip(), lang)
        others = {k: v for k, v in s.on_screen_text.items() if k != lang}
        seconds = scene_seconds(len(said_words(text, lang)))
        scenes.append(
            s.model_copy(
                update={
                    "narration": {**s.narration, lang: text},
                    "on_screen_text": {**others, lang: shown} if shown else others,
                    "duration_s": seconds,
                }
            )
        )
    draft = to_draft(rw, shots, lang)
    hook_title = {**script.hook_title, lang: clean_hook((rw.hook_title or {}).get(lang) or "")}  # type: ignore[call-overload]
    metadata = dict(script.metadata)
    if lang in metadata and rw.title.strip():
        metadata[lang] = metadata[lang].model_copy(update={"title": rw.title.strip()[:100]})  # type: ignore[index]
    return script.model_copy(update={"scenes": scenes, "hook_title": hook_title, "metadata": metadata, "story": draft})


def shots_listing(shots: list[Shot]) -> str:
    return "\n".join(
        f"Scène {s.index} · clip de {s.seconds:.1f} s · {s.words_max} mots dits au plus\n"
        f"  on voit : {s.shows}\n  l'ancien texte disait : {s.said or '—'}"
        for s in shots
    )


def incomplete(issues: Sequence[str]) -> bool:
    return any(i.startswith("scènes sans texte") for i in issues)


@dataclass
class Source:
    """La vidéo d'origine, sa production, son script et ses plans tels qu'ils sont montés."""

    video: dict[str, Any]
    production: dict[str, Any]
    script: ScriptV1
    shots: list[Shot]
    lang: str
    target: float  # durée visée (s)


def load_source(db: Any, video_id: str | UUID) -> Source:
    v, p = source_of(db, video_id)
    lang = v["lang"]
    script = ScriptV1.model_validate(p["script"])
    clips = {
        int(c["scene_index"]): float(c["duration_s"] or 0)
        for c in db.fetch_all(
            """select distinct on (scene_index) scene_index, duration_s from assets
               where production_id = %s and kind = 'clip' order by scene_index, created_at desc""",
            (p["id"],),
        )
    }
    target = float(p["target_duration_s"] or script.duration_s)
    return Source(v, p, script, shots_of(script, clips, lang), lang, target)


def load_dossier(db: Any, settings: Any, data_dir: Path, src: Source, pages: Sequence[str]) -> tuple[dict[str, Any], str]:
    """(idée, dossier) : les sources de l'idée, plus les pages Wikipédia demandées."""
    concept = (
        db.fetch_one("select title, hook, premise, sources from concepts where id = %s", (src.production["concept_id"],)) or {}
    )
    sources = [*(concept.get("sources") or []), *({"kind": "wikipedia", "lang": src.lang, "title": t} for t in pages)]
    dossier = source_dossier(
        sources,
        data_dir / "sources" / "wikipedia",
        settings.effective_wikipedia_user_agent,
        max_pages=3 + len(pages),
        subject=concept.get("title"),
    )
    return concept, dossier


def rewrite_story(
    db: Any,
    settings: Any,
    data_dir: Path,
    video_id: str | UUID,
    note: str = "",
    *,
    pages: Sequence[str] = (),
    dry: bool = False,
    progress: Callable[[int, str], None] | None = None,
) -> tuple[Variant | None, StoryRewrite, list[str]]:
    """Réécrit le récit de la vidéo sur ses plans ; `pages` : pages Wikipédia ajoutées au dossier (Begrâm : « Joseph
    Hackin », qui raconte la France libre et le cargo torpillé) ; `dry` : sans rien créer (pour relire le texte) ;
    `progress` : avancement (job rewrite du Dashboard, qui s'arrête là si on le lui demande)."""
    step = progress or (lambda _pct, _label: None)
    from .providers.llm import get_llm
    from .steps.script import strong_writers

    src = load_source(db, video_id)
    v, p, script, shots, lang, target = src.video, src.production, src.script, src.shots, src.lang, src.target
    concept, dossier = load_dossier(db, settings, data_dir, src, pages)
    lo, aim, hi = word_budget(target)
    user = "\n\n".join(
        part
        for part in (
            f"REMARQUES DE L'HUMAIN SUR LA VERSION ACTUELLE (à suivre) :\n{note}" if note.strip() else "",
            prompt_text(db, "rules_storytelling", RULES),
            f"SUJET : {concept.get('title') or v['title']}\nPrémisse : {concept.get('premise') or '—'}",
            f"DOSSIER (seule source des faits) :\n{dossier}" if dossier else "",
            f"ANCIEN TEXTE (ce qui n'a pas marché) :\n{v.get('narration_text') or ''}",
            f"SCÈNES ({len(shots)}, dans l'ordre ; durée visée {target:.0f} s, soit environ {aim} mots dits au total, "
            f"entre {lo} et {hi}, environ {round(aim / max(1, len(shots)))} par scène ; langue {lang}) :\n"
            f"{shots_listing(shots)}",
            prompt_text(db, "rules_hook_title", HOOK_RULES),
        )
        if part
    )
    llm = strong_writers(get_llm(settings, db, writer=True))
    system = prompt_text(db, "script_rewrite", REWRITE_PROMPT)
    step(10, "Le conteur réécrit le récit")
    rw = llm.complete_json(system, user, StoryRewrite)
    issues = lint_rewrite(rw, shots, lang, target)

    def review(draft_rw: StoryRewrite) -> list[str]:
        review_user = "\n\n".join(
            part
            for part in (
                f"HISTOIRE À RELIRE (langue {lang}, durée visée {target:.0f} s ; les images sont fixées, seul le texte "
                f"change) :\n{story_listing(to_draft(draft_rw, shots, lang), lang)}",
                f"REMARQUES DE L'HUMAIN :\n{note}" if note.strip() else "",
                f"DOSSIER :\n{dossier}" if dossier else "",
            )
            if part
        )
        try:
            got = llm.complete_json(prompt_text(db, "script_review", REVIEW_PROMPT), review_user, ScriptReview)
            return [] if got.ok else [x.strip() for x in got.problems if x.strip()][:8]
        except Exception as exc:  # noqa: BLE001 — une relecture manquée ne bloque pas
            log.warning("reecriture.relecture_indisponible", error=str(exc)[:300])
            return []

    # Deux réécritures au plus, chacune relue (Begrâm, 29/09 : une invention apparue à la réécriture) ; on garde la
    # version qui laisse le moins d'écarts, ceux qui restent sont signalés
    step(40, "Le relecteur relit")
    best = (rw, issues, [] if incomplete(issues) else review(rw))
    for attempt in (1, 2):
        cur, cur_issues, problems = best
        if not cur_issues and not problems:
            break
        log.info("reecriture.reprise", tour=attempt, issues=cur_issues, relecture=problems)
        step(40 + 25 * attempt, f"Réécriture {attempt + 1} sur 3, d'après les remarques")
        again = llm.complete_json(
            system,
            f"{user}\n\n{rewrite_request(cur_issues, problems)}\n\nVersion précédente :\n{cur.model_dump_json()}",
            StoryRewrite,
        )
        again_issues = lint_rewrite(again, shots, lang, target)
        if incomplete(again_issues):
            continue
        candidate = (again, again_issues, review(again))
        if len(candidate[1]) + len(candidate[2]) <= len(cur_issues) + len(problems):
            best = candidate
    rw, issues = best[0], best[1] + [f"relecteur : {x}" for x in best[2]]
    if incomplete(issues):
        raise ValueError("réécriture incomplète : " + "; ".join(issues))
    if dry:
        return None, rw, issues
    new = rewritten_script(script, rw, shots, lang)
    title = rw.title.strip() or v["title"]
    return clone(db, data_dir, v, p, new, title, None, issues, seo=True), rw, issues


def make_story(db: Any, data_dir: Path, video_id: str | UUID, rw: StoryRewrite) -> tuple[Variant, list[str]]:
    """La vidéo d'un récit déjà réécrit, relu et parfois corrigé à la main (Retoucher → Récit) : mêmes plans, nouvelle
    voix, montage, contrôle et SEO. Les écarts du correcteur sont rendus sans bloquer, sauf une scène sans texte."""
    src = load_source(db, video_id)
    issues = lint_rewrite(rw, src.shots, src.lang, src.target)
    if incomplete(issues):
        raise ValueError("; ".join(issues))
    try:
        new = rewritten_script(src.script, rw, src.shots, src.lang)
    except ValidationError as exc:
        raise ValueError("récit incomplet : accroche, promesse, contexte, conflit, réponse et chute") from exc
    title = rw.title.strip() or src.video["title"]
    return clone(db, data_dir, src.video, src.production, new, title, None, issues, seo=True), issues


# ---------------------------------------------------------------------------------------------------------------------
# L'accroche seule (Retoucher → Récit) : la 1re phrase dite et la promesse qui suit, le reste du récit ne bouge pas
# ---------------------------------------------------------------------------------------------------------------------


class HookRewrite(BaseModel):
    angle: str = Field("", description="le ressort choisi (gâchis, perte, émerveillement) et pourquoi il marche ici")
    hook: str = Field(description="1re phrase dite")
    promise: str = Field(description="2e phrase dite")
    on_screen: str = Field("", description="texte gravé sur le plan de l'accroche (3 mots au plus), vide le plus souvent")
    hook_title: LangText = Field(default_factory=dict)
    title: str = Field("", description="titre YouTube, 70 caractères au plus")


HOOK_PROMPT = """Tu es le conteur d'une chaîne YouTube Shorts d'histoires racontées en voix off (9:16). Un Short est
fait (images, voix, montage) ; seule son OUVERTURE change : l'ACCROCHE (la 1re phrase dite) et la PROMESSE (la 2e). Le
reste du récit ne bouge pas, mot pour mot : la promesse annonce la fin qu'il donne, sans la dire.

Tu reçois : les remarques de l'humain qui pilote la chaîne (elles priment sur tout, sauf sur les faits), les règles du
récit, le dossier (la seule source des faits), le récit actuel en entier, les deux premiers plans (ce qu'on y voit, le
nombre de mots dits qu'ils peuvent porter), puis les règles du titre d'accroche.

- hook : UNE phrase de 14 mots au plus, le sujet concret dès les premiers mots et un contraste (ce qu'on croit contre
  ce qui est, un paradoxe, un prix absurde, une erreur énorme). Elle vise un ado de 13 ans qui fait défiler et ne
  connaît rien au sujet : il doit ressentir quelque chose dès la 1re seconde, avec des mots de tous les jours. Deux
  ressorts marchent : le GÂCHIS ou la PERTE qu'on sent dans le ventre (« Cette capitale a coûté 4 milliards d'euros,
  mais personne n'y vit. »), ou l'ÉMERVEILLEMENT d'une chose qui semble sortie d'un film et existe pourtant vraiment.
  Une durée seule (« a survécu 2 000 ans ») ou une notion abstraite (« contre le désert ») ne fait rien ressentir.
  Relis-la seule : si elle peut se lire de deux façons, réécris-la. Elle colle à l'image du 1er plan.
- promise : UNE phrase qui annonce la fin du récit sans la donner (« Pourtant, personne n'a le droit d'en toucher une
  seule pièce. ») ; un fait de plus n'est pas une promesse. Elle colle à l'image du 2e plan.
- Accroche et promesse : 22 mots dits au plus à elles deux (6 s), et chacune tient dans les mots de son plan.
- on_screen : seulement si un mot ou un chiffre clé gagne à être lu sur le 1er plan (3 mots au plus), sinon vide.
- hook_title : le titre d'accroche gravé à l'écran (règles fournies) ; title : le titre YouTube, 70 caractères au
  plus, qui tient la même promesse.
- angle : en une phrase, le ressort choisi et pourquoi il marche ici.

Faits : chaque fait, nom, nombre ou date vient du dossier ou du récit actuel ; rien n'est inventé pour dramatiser.
Présent de narration, voix active, nombres en chiffres. Réponds uniquement en JSON conforme à HookRewrite :
{"angle": "…", "hook": "…", "promise": "…", "on_screen": "", "hook_title": {"fr": "…"}, "title": "…"}."""


def opening_of(script: ScriptV1, lang: str) -> dict[str, int]:
    """Scène de l'accroche et scène de la promesse, chacune seule dans son plan (hookvariant.variant_script)."""
    story = script.story
    if story is None or len(story.beats) < 2 or [b.part for b in story.beats[:2]] != ["hook", "promise"]:
        raise ValueError("seul un récit écrit par le conteur (accroche puis promesse) a une accroche à réécrire seule")
    found: dict[str, int] = {}
    for beat in story.beats[:2]:
        for scene in script.scenes[:4]:
            if scene.narration.get(lang, "").strip() == beat.text.strip():  # type: ignore[call-overload]
                found[beat.part] = scene.index
                break
    if len(found) < 2:
        raise ValueError("l'accroche ou la promesse est répartie sur plusieurs plans : réécris tout le récit")
    return found


def tidy_hook(hr: HookRewrite, lang: str) -> HookRewrite:
    """Espaces, nombres en chiffres (docs/33) et titre d'accroche nettoyé, comme pour le récit du conteur."""

    def one(text: str) -> str:
        return to_digits(re.sub(r"[ \t\r\n]+", " ", text).strip(), lang)

    return hr.model_copy(
        update={
            "hook": one(hr.hook),
            "promise": one(hr.promise),
            "on_screen": one(hr.on_screen),
            "hook_title": {k: clean_hook(to_digits(v, k)) for k, v in hr.hook_title.items() if clean_hook(v)},  # type: ignore[misc]
            "title": re.sub(r"\s+", " ", hr.title).strip()[:100],
        }
    )


def hook_issues(hr: HookRewrite, shots: Sequence[Shot], opening: dict[str, int], lang: str) -> list[str]:
    """Ce que le correcteur dit de la nouvelle ouverture (hookvariant.check_texts), plus la place de chaque phrase dans
    son plan."""
    if not hr.hook.strip() or not hr.promise.strip():
        return ["accroche ou promesse vide : il faut les deux phrases"]
    by_index = {s.index: s for s in shots}
    issues = check_texts(hr.hook, hr.promise, (hr.hook_title or {}).get(lang) or "", lang)  # type: ignore[call-overload]
    for part, key, text in (("accroche", "hook", hr.hook), ("promesse", "promise", hr.promise)):
        shot = by_index.get(opening[key])
        if shot and (n := len(said_words(text, lang))) > shot.words_max:
            issues.append(f"{part} de {n} mots dits : son plan en porte {shot.words_max} au plus")
    return issues


def rewrite_hook(
    db: Any,
    settings: Any,
    data_dir: Path,
    video_id: str | UUID,
    note: str = "",
    *,
    pages: Sequence[str] = (),
    progress: Callable[[int, str], None] | None = None,
) -> tuple[HookRewrite, list[str]]:
    """Nouvelle accroche et nouvelle promesse pour la vidéo, d'après les remarques de Luca ; une reprise si le correcteur
    trouve un écart, on garde la version qui en laisse le moins."""
    from .providers.llm import get_llm
    from .steps.script import strong_writers

    step = progress or (lambda _pct, _label: None)
    src = load_source(db, video_id)
    opening = opening_of(src.script, src.lang)
    concept, dossier = load_dossier(db, settings, data_dir, src, pages)
    by_index = {s.index: s for s in src.shots}
    plans = "\n".join(
        f"{label} (scène {i}) · clip de {by_index[i].seconds:.1f} s · {by_index[i].words_max} mots dits au plus\n"
        f"  on voit : {by_index[i].shows}\n  la voix disait : {by_index[i].said or '—'}"
        for label, i in (("Plan de l'accroche", opening["hook"]), ("Plan de la promesse", opening["promise"]))
    )
    story = src.script.story
    current = story_listing(story, src.lang) if story else src.video.get("narration_text") or ""
    user = "\n\n".join(
        part
        for part in (
            f"REMARQUES DE L'HUMAIN SUR L'OUVERTURE ACTUELLE (à suivre) :\n{note}" if note.strip() else "",
            prompt_text(db, "rules_storytelling", RULES),
            f"SUJET : {concept.get('title') or src.video['title']}\nPrémisse : {concept.get('premise') or '—'}",
            f"DOSSIER (seule source des faits) :\n{dossier}" if dossier else "",
            f"RÉCIT ACTUEL (langue {src.lang} ; seules ses deux premières phrases changent) :\n{current}",
            f"TITRE YOUTUBE ACTUEL : {src.video['title']}",
            f"LES DEUX PREMIERS PLANS :\n{plans}",
            prompt_text(db, "rules_hook_title", HOOK_RULES),
        )
        if part
    )
    llm = strong_writers(get_llm(settings, db, writer=True))
    system = prompt_text(db, "hook_rewrite", HOOK_PROMPT)
    step(15, "Le conteur réécrit l'accroche")
    best = tidy_hook(llm.complete_json(system, user, HookRewrite), src.lang)
    issues = hook_issues(best, src.shots, opening, src.lang)
    if issues:
        step(60, "Deuxième version, d'après le correcteur")
        again = tidy_hook(
            llm.complete_json(
                system,
                f"{user}\n\n{rewrite_request(issues, [])}\n\nVersion précédente :\n{best.model_dump_json()}",
                HookRewrite,
            ),
            src.lang,
        )
        again_issues = hook_issues(again, src.shots, opening, src.lang)
        if len(again_issues) <= len(issues):
            best, issues = again, again_issues
    return best, issues


def make_hook(db: Any, data_dir: Path, video_id: str | UUID, hr: HookRewrite) -> Variant:
    """La variante d'accroche (hookvariant.make_variant) avec une ouverture relue, parfois corrigée à la main."""
    src = load_source(db, video_id)
    hr = tidy_hook(hr, src.lang)
    if not hr.hook or not hr.promise:
        raise ValueError("accroche ou promesse vide : il faut les deux phrases")
    hook_title = (hr.hook_title or {}).get(src.lang) or (src.script.hook_title or {}).get(src.lang) or ""  # type: ignore[call-overload]
    return make_variant(
        db,
        data_dir,
        video_id,
        hook=hr.hook,
        promise=hr.promise,
        hook_title=hook_title,
        title=hr.title or src.video["title"],
        on_screen=hr.on_screen,
    )
