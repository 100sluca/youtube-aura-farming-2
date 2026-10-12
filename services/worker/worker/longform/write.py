"""L'écriture d'une vidéo longue (docs/63 §3) : sujets proposés avec leur emballage, dossier Wikipédia, plan en
chapitres, texte chapitre par chapitre, relecture et corrections, plans du réalisateur, publication (titres,
description, miniatures).

Chaque étape est enregistrée dès qu'elle est faite (long_videos.script["work"]) : si les modèles d'écriture forts sont
épuisés en route, la tâche attend (Postpone) et reprend où elle s'était arrêtée, sans refaire les appels déjà payés en
quota. Les agents passent par la chaîne d'écriture sans ses modèles de secours (strong_writers, comme le conteur des
Shorts) ; après 12 h d'attente, le secours écrit quand même.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from psycopg.types.json import Jsonb

from ..lessons import lessons_text
from ..numbers import to_digits
from ..postpone import Postpone
from ..prompts import prompt_text
from ..providers.llm import get_llm
from ..sources.wikipedia import WikipediaClient, cached_page, subject_page
from ..storytelling import BANNED_OPENERS, CALLS_TO_ACTION, EMPTY_SUPERLATIVES, RULES, sentences, words
from .models import (
    ChapterBatch,
    ChapterText,
    FactCheck,
    LongIdea,
    LongIdeaBatch,
    LongReview,
    Outline,
    Packaging,
    Proof,
    ReviewProblem,
    ShotBatch,
    ShotSpec,
    ThumbConcepts,
    ThumbStyle,
)
from .prompts import (
    DIRECTOR_PROMPT,
    FACTCHECK_PROMPT,
    GUIDE_THUMB_NICHE,
    GUIDES,
    IDEA_PROMPT,
    OUTLINE_PROMPT,
    PACKAGING_PROMPT,
    REVIEW_PROMPT,
    RULES_LONG,
    THUMB_RULES,
    THUMB_STYLE_PROMPT,
    THUMBS_PROMPT,
    WORDS_PER_MIN,
    WRITER_PROMPT,
)
from .sources import external_sources

log = structlog.get_logger(__name__)

BUDGET_RANGE = (0.9, 1.12)  # part du nombre de mots visé admise pour toute la vidéo
CHAPTER_RANGE = (0.75, 1.3)  # et pour un chapitre
PARA_WORDS = (20, 140)
SENTENCE_MAX = 26
HOOK_MAX = 24  # 1re phrase de la vidéo
CHAPTERS_PER_CALL = 3
REVIEW_ROUNDS = 2
DIRECTOR_WORDS_PER_CALL = 900
STRONG_WAIT_S = 3600.0
STRONG_WAIT_MAX = timedelta(hours=12)
DOSSIER_CHARS = (32000, 14000, 20000, 10000)  # page principale, pages suivantes, version anglaise, pages anglaises
AND_THEN = re.compile(r"(^\W*(ensuite|puis|après ça|après cela|et après)\b)|\bet (ensuite|puis)\b", re.I)


Ask = Callable[[str, str, type[Any]], Any]


def word_budget(minutes: float) -> int:
    return round(minutes * WORDS_PER_MIN)


def para_key(chapter: int, para: int) -> str:
    return f"c{chapter}p{para}"


def rules_text(db: Any, fmt: str) -> str:
    guide = prompt_text(db, f"guide_long_{fmt}", GUIDES.get(fmt, "")) if fmt in GUIDES else ""
    return "\n\n".join(
        x for x in (guide, prompt_text(db, "rules_storytelling", RULES), prompt_text(db, "rules_long", RULES_LONG)) if x
    )


def asker(ctx: Any) -> Ask:
    """Un appel d'agent d'écriture : modèles forts d'abord ; tous épuisés, la tâche attend une heure (12 h au plus)."""
    from ..steps.script import strong_writers

    full = get_llm(ctx.settings, ctx.db, writer=True)
    strong = strong_writers(full)

    def ask(system: str, user: str, schema: type[Any]) -> Any:
        try:
            return strong.complete_json(system, user, schema)
        except Exception as exc:
            if strong is full:
                raise
            if datetime.now(UTC) - ctx.job.created_at < STRONG_WAIT_MAX:
                raise Postpone(
                    "modèles d'écriture forts épuisés",
                    STRONG_WAIT_S,
                    label="Vidéo longue : attend un modèle d'écriture fort (quota)",
                    error=str(exc)[:500],
                ) from exc
            return full.complete_json(system, user, schema)

    return ask


# ---------------------------------------------------------------------------------------------------------------------
# Sujets
# ---------------------------------------------------------------------------------------------------------------------


def done_subjects(db: Any, channel_id: Any) -> list[str]:
    rows = db.fetch_all(
        """select coalesce(idea->>'title', subject) as t from long_videos
           where channel_id = %s and stage <> 'archived' order by created_at desc limit 60""",
        (channel_id,),
    )
    return [r["t"] for r in rows if r["t"]]


PROVEN_CATEGORIES = ("histoire", "mystere_crime", "science_education", "espace_sommeil", "geopolitique_guerre", "survie_nature")


def proven_videos(db: Any, limit: int = 40) -> list[dict[str, Any]]:
    """Les vidéos longues qui ont déjà marché dans nos thèmes : celles des chaînes de la Découverte (docs/63 §9),
    puis celles de la veille ; {title, views, channel, url, lang}."""
    out: list[dict[str, Any]] = []
    try:
        for r in db.fetch_all(
            """select title as channel, lang, top_videos from research_channels
               where status <> 'dismissed' and coalesce(classification->>'category', '') = any(%s)
               order by monthly_revenue desc nulls last limit 80""",
            (list(PROVEN_CATEGORIES),),
        ):
            for v in r["top_videos"] or []:
                if int(v.get("views") or 0) >= 50_000 and int(v.get("duration_s") or 0) >= 480:
                    out.append(
                        {
                            "title": v.get("title", ""),
                            "views": int(v["views"]),
                            "channel": r["channel"],
                            "url": f"https://www.youtube.com/watch?v={v.get('id')}",
                            "lang": r["lang"],
                        }
                    )
        for r in db.fetch_all(
            """select title, channel_title, views, url, lang from research_videos
               where duration_s >= 480 and status <> 'dismissed' and views >= 50000
                 and published_at > now() - interval '180 days' order by views desc limit 25"""
        ):
            out.append(
                {"title": r["title"], "views": int(r["views"]), "channel": r["channel_title"], "url": r["url"], "lang": r["lang"]}
            )
    except Exception:  # noqa: BLE001 — migrations 0050 / 0055 absentes
        return []
    seen: set[str] = set()
    uniq = []
    for v in sorted(out, key=lambda v: -v["views"]):
        key = v["title"].strip().lower()
        if key and key not in seen:
            seen.add(key)
            uniq.append(v)
    return uniq[:limit]


def demand_hints(db: Any) -> str:
    """Vidéos longues qui ont déjà marché (Découverte et veille de la page Recherche) ; vide sinon."""
    rows = proven_videos(db)
    if not rows:
        return ""
    lines = [
        f"- « {r['title']} » ({r['channel']}, {format(r['views'], ',').replace(',', ' ')} vues, {r['lang'] or '?'})" for r in rows
    ]
    return "VIDÉOS QUI ONT DÉJÀ MARCHÉ (page Recherche, vues réelles) :\n" + "\n".join(lines)


def keep_real_proofs(idea: LongIdea, proven: list[dict[str, Any]]) -> LongIdea:
    """Les preuves que l'agent cite, gardées seulement si elles sont dans la liste fournie (jamais inventées)."""
    by_title = {v["title"].strip().lower(): v for v in proven}
    kept = []
    for p in idea.proof:
        v = by_title.get(p.title.strip().strip("«»\"' ").lower())
        if v:
            kept.append(Proof(title=v["title"], views=v["views"], channel=v["channel"], url=v["url"]))
    return idea.model_copy(update={"proof": kept})


def wiki_exists(ctx: Any, title: str, lang: str = "fr") -> str | None:
    """Le titre exact d'une page Wikipédia qui existe (recherche si le titre donné n'existe pas tel quel)."""
    client = WikipediaClient(lang=lang, user_agent=ctx.settings.effective_wikipedia_user_agent)
    try:
        if client.page(title, 200):
            return title
        return subject_page(client, title)
    except Exception:  # noqa: BLE001
        return None


def propose_ideas(ctx: Any, channel_id: UUID, count: int, formats: Sequence[str], note: str = "") -> int:
    """Sujets proposés avec leur emballage, gardés seulement si leur page Wikipédia existe : lignes long_videos « idea »."""
    ask = asker(ctx)
    proven = proven_videos(ctx.db)
    share = ", ".join(f"{f}" for f in formats) or "mystere, epoque"
    done = done_subjects(ctx.db, channel_id)
    user = "\n\n".join(
        x
        for x in (
            f"FORMATS DE LA CHAÎNE (à alterner, dans cette proportion : {share}) :\n"
            + "\n\n".join(prompt_text(ctx.db, f"guide_long_{f}", GUIDES[f]) for f in formats if f in GUIDES),
            prompt_text(ctx.db, "rules_storytelling", RULES),
            prompt_text(ctx.db, "rules_long", RULES_LONG),
            prompt_text(ctx.db, "rules_thumbnail", THUMB_RULES),
            (
                "VIDÉOS QUI ONT DÉJÀ MARCHÉ (page Recherche, vues réelles) :\n"
                + "\n".join(
                    f"- « {v['title']} » ({v['channel']}, {format(v['views'], ',').replace(',', ' ')} vues)" for v in proven
                )
            )
            if proven
            else "",
            lessons_text(ctx.db, "idea", channel_id=channel_id),
            ("SUJETS DÉJÀ TRAITÉS OU PROPOSÉS (ne pas refaire) :\n" + "\n".join(f"- {t}" for t in done)) if done else "",
            f"DEMANDE DE LUCA : {note}" if note else "",
            f"Propose {count} idées.",
        )
        if x
    )
    ctx.progress(10, f"Vidéos longues : {count} sujets à trouver")
    batch: LongIdeaBatch = ask(prompt_text(ctx.db, "long_idea", IDEA_PROMPT), user, LongIdeaBatch)
    kept = 0
    # la preuve d'abord : un sujet qui a déjà marché ailleurs passe devant, puis la note
    for i, idea in enumerate(sorted(batch.ideas, key=lambda x: (not x.proof, -x.score))):
        ctx.progress(30 + int(60 * i / max(1, len(batch.ideas))), f"Vérification des sources : {idea.subject[:60]}")
        pages = [p for p in (wiki_exists(ctx, t) for t in idea.wikipedia[:4]) if p]
        if not pages:
            ctx.log("long.idee_sans_source", level="warn", sujet=idea.subject, pages=idea.wikipedia)
            continue
        idea.wikipedia = list(dict.fromkeys(pages))
        idea.title = to_digits(idea.title.strip())[:100]
        idea = keep_real_proofs(idea, proven)
        ctx.db.execute(
            """insert into long_videos (channel_id, stage, format, origin, subject, idea)
               values (%s, 'idea', %s, 'agent', %s, %s)""",
            (channel_id, idea.format, idea.subject, Jsonb(idea.model_dump())),
        )
        kept += 1
    return kept


def frame_subject(ctx: Any, lv: dict[str, Any]) -> LongIdea:
    """Un sujet tapé par Luca (« Mon sujet ») devient une idée complète : titre, miniature, promesse, pages Wikipédia."""
    ask = asker(ctx)
    fmt = lv["format"] if lv["format"] in GUIDES else "mystere"
    user = "\n\n".join(
        x
        for x in (
            f"FORMAT IMPOSÉ : {fmt}\n" + prompt_text(ctx.db, f"guide_long_{fmt}", GUIDES[fmt]),
            prompt_text(ctx.db, "rules_long", RULES_LONG),
            prompt_text(ctx.db, "rules_thumbnail", THUMB_RULES),
            f"SUJET IMPOSÉ PAR LUCA : {lv['subject']}",
            f"SES REMARQUES : {lv['notes']}" if lv.get("notes") else "",
            "Propose exactement 1 idée sur CE sujet (le meilleur angle, le meilleur emballage), au format demandé ; ignore la note "
            "minimale de 70.",
        )
        if x
    )
    batch: LongIdeaBatch = ask(prompt_text(ctx.db, "long_idea", IDEA_PROMPT), user, LongIdeaBatch)
    if not batch.ideas:
        raise RuntimeError("aucune idée rendue pour ce sujet")
    idea = batch.ideas[0]
    idea.format = fmt  # type: ignore[assignment]
    pages = [p for p in (wiki_exists(ctx, t) for t in idea.wikipedia[:4]) if p]
    if not pages:
        found = wiki_exists(ctx, lv["subject"])
        pages = [found] if found else []
    idea.wikipedia = list(dict.fromkeys(pages))
    idea.title = to_digits(idea.title.strip())[:100]
    return idea


# ---------------------------------------------------------------------------------------------------------------------
# Dossier
# ---------------------------------------------------------------------------------------------------------------------


def build_dossier(ctx: Any, idea: LongIdea, workdir: Path) -> tuple[str, list[dict[str, Any]]]:
    """Les pages Wikipédia de l'idée, entières (la page principale jusqu'à 32 000 signes), plus leur version anglaise
    et les pages anglaises proposées, numérotées [n] ; le texte est rangé dans workdir/dossier.txt."""
    ua = ctx.settings.effective_wikipedia_user_agent
    cache = ctx.settings.data_dir / "sources" / "wikipedia"
    fr = WikipediaClient(lang="fr", user_agent=ua)
    en = WikipediaClient(lang="en", user_agent=ua)
    blocks: list[str] = []
    sources: list[dict[str, Any]] = []
    titles = list(idea.wikipedia) or [p for p in [subject_page(fr, idea.subject)] if p]
    en_titles = list(idea.wikipedia_en)
    for i, title in enumerate(titles[:4]):
        doc = cached_page(fr, title, DOSSIER_CHARS[0] if i == 0 else DOSSIER_CHARS[1], cache)
        if not doc:
            continue
        n = len(sources) + 1
        sources.append({"n": n, "title": doc.title, "url": doc.url, "lang": "fr"})
        blocks.append(f"[{n}] {doc.title} — {doc.url}\n{doc.extract}")
        if i == 0:
            other = fr.langlink(title, "en")
            if other and other not in en_titles:
                en_titles.insert(0, other)
    for j, title in enumerate(en_titles[:3]):
        doc = cached_page(en, title, DOSSIER_CHARS[2] if j == 0 else DOSSIER_CHARS[3], cache)
        if not doc:
            continue
        n = len(sources) + 1
        sources.append({"n": n, "title": doc.title, "url": doc.url, "lang": "en"})
        blocks.append(f"[{n}] (en anglais) {doc.title} — {doc.url}\n{doc.extract}")
    # les sources sérieuses que ces articles citent eux-mêmes (CNRS, INRAP, musées, revues… : longform/sources.py)
    wiki = [(s["title"], s["lang"]) for s in sources]
    try:
        extra = external_sources(wiki, f"{idea.subject} {idea.title}", ctx.settings.data_dir / "sources" / "web", ua)
    except Exception as exc:  # noqa: BLE001 — les sources extérieures complètent, elles ne bloquent pas
        log.warning("long.sources_exterieures", error=str(exc)[:300])
        extra = []
    for page in extra:
        n = len(sources) + 1
        sources.append(
            {"n": n, "title": page["title"] or page["label"], "url": page["url"], "lang": "web", "label": page["label"]}
        )
        blocks.append(f"[{n}] ({page['label']}) {page['title']} — {page['url']}\n{page['text']}")
    text = "\n\n".join(blocks)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "dossier.txt").write_text(text, encoding="utf-8")
    return text, sources


# ---------------------------------------------------------------------------------------------------------------------
# Script
# ---------------------------------------------------------------------------------------------------------------------


def fact_summary(check: FactCheck, corrected: Sequence[str] = ()) -> dict[str, Any]:
    """Le bilan de la vérification des faits, tel que la fiche le montre : combien de faits, combien confirmés par les
    sources, les hypothèses dites comme telles, ce qui a été corrigé, ce qui reste à voir."""
    counts = {
        s: sum(1 for c in check.claims if c.status == s) for s in ("confirmed", "hypothesis", "unsupported", "contradicted")
    }
    return {
        "total": len(check.claims),
        **counts,
        "summary": check.summary,
        "corrected": list(corrected),
        "claims": [c.model_dump() for c in check.claims],
    }


def chapters_listing(chapters: Sequence[dict[str, Any]], numbered: bool = True) -> str:
    out = []
    for c in chapters:
        out.append(f"CHAPITRE {c['index']} — {c.get('title', '')}")
        for j, p in enumerate(c["paragraphs"]):
            prefix = f"  [{c['index']}.{j}] " if numbered else "  "
            out.append(f"{prefix}{p['text']}\n      (on voit : {p.get('show', '')})")
    return "\n".join(out)


def script_words(chapters: Sequence[dict[str, Any]]) -> int:
    return sum(len(words(p["text"])) for c in chapters for p in c["paragraphs"])


def lint_long(chapters: Sequence[dict[str, Any]], outline: Outline, target_minutes: float) -> list[ReviewProblem]:
    """Ce qui se mesure : longueur totale et par chapitre, paragraphes, phrases trop longues, ouverture, formules
    interdites (salutation, appel à s'abonner, superlatifs vides, « et ensuite »)."""
    problems: list[ReviewProblem] = []
    budget = word_budget(target_minutes)
    total = script_words(chapters)
    if not BUDGET_RANGE[0] * budget <= total <= BUDGET_RANGE[1] * budget:
        problems.append(
            ReviewProblem(
                chapter=0,
                problem=f"{total} mots pour {budget} visés ({target_minutes:g} min à {WORDS_PER_MIN} mots/min)",
                fix="rallonger ou raccourcir les chapitres trop courts ou trop longs (voir les nombres de mots visés)",
            )
        )
    for c in chapters:
        idx = c["index"]
        plan = outline.chapters[idx] if idx < len(outline.chapters) else None
        n = sum(len(words(p["text"])) for p in c["paragraphs"])
        if plan:
            aim = word_budget(plan.minutes)
            if not CHAPTER_RANGE[0] * aim <= n <= CHAPTER_RANGE[1] * aim:
                problems.append(ReviewProblem(chapter=idx, problem=f"{n} mots pour {aim} visés", fix=f"viser {aim} mots"))
        for j, p in enumerate(c["paragraphs"]):
            text = p["text"]
            pw = len(words(text))
            if not PARA_WORDS[0] <= pw <= PARA_WORDS[1]:
                problems.append(
                    ReviewProblem(
                        chapter=idx, paragraph=j, problem=f"paragraphe de {pw} mots", fix="40 à 110 mots par paragraphe"
                    )
                )
            for s in sentences(text):
                if len(words(s)) > SENTENCE_MAX:
                    problems.append(
                        ReviewProblem(
                            chapter=idx,
                            paragraph=j,
                            problem=f"phrase de {len(words(s))} mots : « {s[:80]}… »",
                            fix="la couper en deux",
                        )
                    )
                if AND_THEN.search(s):
                    problems.append(
                        ReviewProblem(
                            chapter=idx,
                            paragraph=j,
                            problem=f"« et ensuite » : « {s[:80]} »",
                            fix="relier par une cause (donc) ou un obstacle (mais)",
                        )
                    )
            for rx, what in ((CALLS_TO_ACTION["fr"], "appel au public"), (EMPTY_SUPERLATIVES["fr"], "superlatif vide")):
                m = re.search(rx, text, re.I)
                if m:
                    problems.append(
                        ReviewProblem(chapter=idx, paragraph=j, problem=f"{what} : « {m.group(0)} »", fix="le retirer")
                    )
    first = chapters[0]["paragraphs"][0]["text"] if chapters and chapters[0]["paragraphs"] else ""
    first_sentence = (sentences(first) or [""])[0]
    if re.search(BANNED_OPENERS["fr"], first_sentence, re.I):
        problems.append(
            ReviewProblem(
                chapter=0, paragraph=0, problem="la vidéo s'ouvre sur une formule d'introduction", fix="ouvrir sur la scène"
            )
        )
    if len(words(first_sentence)) > HOOK_MAX:
        problems.append(
            ReviewProblem(
                chapter=0, paragraph=0, problem=f"1re phrase de {len(words(first_sentence))} mots", fix=f"{HOOK_MAX} mots au plus"
            )
        )
    return problems


def normalize_chapters(chapters: Sequence[ChapterText], outline: Outline) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in sorted(chapters, key=lambda c: c.index):
        title = (c.title or (outline.chapters[c.index].title if c.index < len(outline.chapters) else "")).strip()
        paras = []
        for p in c.paragraphs:
            text = to_digits(re.sub(r"\s+", " ", p.text).strip())
            if text:
                paras.append({"text": text, "show": re.sub(r"\s+", " ", p.show).strip()})
        out.append({"index": c.index, "title": title, "paragraphs": paras})
    return out


def keyed(chapters: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chapitres avec la clé de chaque paragraphe (« c2p3 ») et son nombre de mots."""
    out = []
    for c in chapters:
        paras = [{**p, "key": para_key(c["index"], j), "words": len(words(p["text"]))} for j, p in enumerate(c["paragraphs"])]
        out.append({**c, "paragraphs": paras})
    return out


class Writer:
    """L'écriture d'une vidéo longue, étape par étape, reprise là où elle s'est arrêtée (work)."""

    def __init__(self, ctx: Any, lv: dict[str, Any], save: Callable[[dict[str, Any]], None]) -> None:
        self.ctx, self.lv, self.save = ctx, lv, save
        self.idea = LongIdea.model_validate(
            lv["idea"]
            or {"subject": lv["subject"], "title": lv["subject"], "hook": "", "promise": "", "thumbnail": {"prompt": ""}}
        )
        self.fmt = lv["format"]
        self.minutes = float(lv["target_minutes"])
        self.work: dict[str, Any] = dict((lv.get("script") or {}).get("work") or {})
        self.ask = asker(ctx)
        self.rules = rules_text(ctx.db, self.fmt)

    def checkpoint(self) -> None:
        self.save({"work": self.work})

    def idea_text(self) -> str:
        i = self.idea
        return (
            f"IDÉE : {i.subject}\nTITRE : {i.title}\nAUTRES TITRES : {' | '.join(i.alt_titles)}\nACCROCHE : {i.hook}\n"
            f"PROMESSE : {i.promise}\nANGLE : {i.angle}\nMINIATURE : {i.thumbnail.idea} (texte : {i.thumbnail.text or 'aucun'})"
            + (f"\nREMARQUES DE LUCA : {self.lv['notes']}" if self.lv.get("notes") else "")
        )

    def run(self, dossier: str, progress: Callable[[int, str], None]) -> dict[str, Any]:
        lessons = lessons_text(self.ctx.db, "script", channel_id=self.lv["channel_id"])
        budget = word_budget(self.minutes)
        if "outline" not in self.work:
            progress(15, "Plan en chapitres")
            user = "\n\n".join(
                x
                for x in (
                    self.rules,
                    self.idea_text(),
                    f"DURÉE VISÉE : {self.minutes:g} min, soit environ {budget} mots lus ({WORDS_PER_MIN} mots par minute).",
                    lessons,
                    "DOSSIER :\n" + dossier,
                )
                if x
            )
            outline = self.ask(prompt_text(self.ctx.db, "long_outline", OUTLINE_PROMPT), user, Outline)
            self.work["outline"] = outline.model_dump()
            self.checkpoint()
        outline = Outline.model_validate(self.work["outline"])
        chapters: dict[int, dict[str, Any]] = {int(k): v for k, v in (self.work.get("chapters") or {}).items()}
        todo = [i for i in range(len(outline.chapters)) if i not in chapters]
        for start in range(0, len(todo), CHAPTERS_PER_CALL):
            group = todo[start : start + CHAPTERS_PER_CALL]
            progress(
                25 + int(40 * len(chapters) / len(outline.chapters)),
                f"Écriture des chapitres {', '.join(str(g + 1) for g in group)}",
            )
            for c in self._write(outline, dossier, sorted(chapters.values(), key=lambda c: c["index"]), group, []):
                chapters[c["index"]] = c
            self.work["chapters"] = {str(k): v for k, v in chapters.items()}
            self.checkpoint()
        ordered = [chapters[i] for i in sorted(chapters)]
        rounds = int(self.work.get("rounds", 0))
        review: LongReview | None = LongReview.model_validate(self.work["review"]) if self.work.get("review") else None
        corrected = bool(self.work.get("corrected"))  # des corrections ont suivi la dernière relecture
        while rounds < REVIEW_ROUNDS:
            progress(68 + 8 * rounds, f"Relecture ({rounds + 1})")
            measured = lint_long(ordered, outline, self.minutes)
            review = self._review(ordered, dossier, budget)
            corrected = False
            self.work["corrected"] = False
            problems = [*review.problems, *measured]
            self.work["review"] = review.model_dump()
            rounds += 1
            self.work["rounds"] = rounds
            self.checkpoint()
            if review.ok and not measured:
                break
            targets = sorted({p.chapter for p in problems if 0 <= p.chapter < len(ordered)}) or [0]
            progress(70 + 8 * rounds, f"Corrections des chapitres {', '.join(str(t + 1) for t in targets)}")
            for start in range(0, len(targets), CHAPTERS_PER_CALL):
                group = targets[start : start + CHAPTERS_PER_CALL]
                fixes = [p for p in problems if p.chapter in group]
                for c in self._write(outline, dossier, ordered, group, fixes):
                    chapters[c["index"]] = c
                ordered = [chapters[i] for i in sorted(chapters)]
                self.work["chapters"] = {str(k): v for k, v in chapters.items()}
                self.checkpoint()
            corrected = True
            self.work["corrected"] = True
            self.checkpoint()
        if corrected:  # relecture finale, sans réécriture : ce qui reste vraiment à voir pour Luca
            progress(88, "Relecture finale")
            self.work["review"] = self._review(ordered, dossier, budget).model_dump()
            self.work["corrected"] = False
            self.checkpoint()
        if "factcheck" not in self.work:  # chaque fait confronté aux sources (exigence de Luca : pas de désinformation)
            progress(90, "Vérification des faits")
            check = self._factcheck(ordered, dossier)
            bad = [c for c in check.claims if c.status in ("unsupported", "contradicted")]
            if bad:
                progress(92, f"Corrections : {len(bad)} fait(s) non confirmé(s) par les sources")
                fixes = [
                    ReviewProblem(
                        chapter=c.chapter,
                        paragraph=c.paragraph,
                        problem=f"fait non confirmé par les sources : « {c.claim} »",
                        fix=c.fix or "le retirer, ou le dire comme une hypothèse, d'après le dossier",
                    )
                    for c in bad
                ]
                targets = sorted({p.chapter for p in fixes if 0 <= p.chapter < len(ordered)})
                for start in range(0, len(targets), CHAPTERS_PER_CALL):
                    group = targets[start : start + CHAPTERS_PER_CALL]
                    for c in self._write(outline, dossier, ordered, group, [p for p in fixes if p.chapter in group]):
                        chapters[c["index"]] = c
                    ordered = [chapters[i] for i in sorted(chapters)]
                    self.work["chapters"] = {str(k): v for k, v in chapters.items()}
                    self.checkpoint()
                progress(95, "Vérification des faits après correction")
                check = self._factcheck(ordered, dossier)
            self.work["factcheck"] = fact_summary(check, corrected=[c.claim for c in bad])
            self.checkpoint()
        final = keyed(ordered)
        remaining = lint_long(ordered, outline, self.minutes)
        return {
            "version": 1,
            "central_idea": outline.central_idea,
            "engine": outline.engine,
            "protagonist": outline.protagonist,
            "stakes": outline.stakes,
            "promise": outline.promise,
            "ending": to_digits(outline.ending),
            "chapters": [
                {**c, "question": outline.chapters[c["index"]].question if c["index"] < len(outline.chapters) else ""}
                for c in final
            ],
            "words": script_words(ordered),
            "minutes_at_150": round(script_words(ordered) / WORDS_PER_MIN, 1),
            "lint": [p.model_dump() for p in remaining],
            "factcheck": self.work.get("factcheck"),
            "work": self.work,
        }

    def _factcheck(self, ordered: Sequence[dict[str, Any]], dossier: str) -> FactCheck:
        return self.ask(
            prompt_text(self.ctx.db, "long_factcheck", FACTCHECK_PROMPT),
            "SCRIPT :\n" + chapters_listing(ordered) + "\n\nDOSSIER :\n" + dossier,
            FactCheck,
        )

    def _review(self, ordered: Sequence[dict[str, Any]], dossier: str, budget: int) -> LongReview:
        return self.ask(
            prompt_text(self.ctx.db, "long_review", REVIEW_PROMPT),
            "\n\n".join(
                (
                    self.rules,
                    self.idea_text(),
                    f"DURÉE VISÉE : {self.minutes:g} min ({budget} mots) ; le script en fait {script_words(ordered)}.",
                    "SCRIPT :\n" + chapters_listing(ordered),
                    "DOSSIER :\n" + dossier,
                )
            ),
            LongReview,
        )

    def _write(
        self,
        outline: Outline,
        dossier: str,
        written: Sequence[dict[str, Any]],
        group: Sequence[int],
        fixes: Sequence[ReviewProblem],
    ) -> list[dict[str, Any]]:
        plan_lines = []
        for i, ch in enumerate(outline.chapters):
            plan_lines.append(
                f"{i}. {ch.title} ({ch.minutes:g} min, {word_budget(ch.minutes)} mots) — {ch.goal}\n   faits : "
                + " ; ".join(ch.beats)
                + f"\n   finit sur : {ch.question}"
            )
        before = [c for c in written if c["index"] < min(group)]
        current = [c for c in written if c["index"] in group]
        asked = "\n".join(
            f"- chapitre {i} « {outline.chapters[i].title} » : {word_budget(outline.chapters[i].minutes)} mots" for i in group
        )
        parts = [
            self.rules,
            self.idea_text(),
            f"PLAN : idée centrale « {outline.central_idea} » ; promesse « {outline.promise} » ; dernière phrase de la vidéo "
            f"« {outline.ending} » ; ouverture : {outline.hook}\n" + "\n".join(plan_lines),
            (
                "CHAPITRES DÉJÀ ÉCRITS (pour la continuité, ne pas les réécrire) :\n"
                + chapters_listing(before[-2:], numbered=False)
            )
            if before
            else "",
            f"CHAPITRES À ÉCRIRE :\n{asked}",
        ]
        if fixes:
            parts.append("VERSION ACTUELLE DE CES CHAPITRES :\n" + chapters_listing(current))
            parts.append(
                "CORRECTIONS (à appliquer toutes, en gardant ce qui marche) :\n"
                + "\n".join(
                    f"- chapitre {p.chapter}"
                    + (f", paragraphe {p.paragraph}" if p.paragraph is not None else "")
                    + f" : {p.problem} → {p.fix}"
                    for p in fixes
                )
            )
        parts.append("DOSSIER :\n" + dossier)
        batch: ChapterBatch = self.ask(
            prompt_text(self.ctx.db, "long_writer", WRITER_PROMPT), "\n\n".join(p for p in parts if p), ChapterBatch
        )
        got = {c.index: c for c in batch.chapters if c.index in group}
        if len(got) < len(group) and len(batch.chapters) == len(group):  # numérotation décalée : dans l'ordre demandé
            got = {i: c.model_copy(update={"index": i}) for i, c in zip(group, batch.chapters, strict=False)}
        missing = [i for i in group if i not in got]
        if missing:
            raise RuntimeError(f"le conteur n'a pas rendu les chapitres {missing}")
        return normalize_chapters(list(got.values()), outline)


# ---------------------------------------------------------------------------------------------------------------------
# Emballage et plans
# ---------------------------------------------------------------------------------------------------------------------


def packaging(ctx: Any, lv: dict[str, Any], script: dict[str, Any], moods: str) -> Packaging:
    idea = lv["idea"] or {}
    user = "\n\n".join(
        x
        for x in (
            prompt_text(ctx.db, "rules_thumbnail", THUMB_RULES),
            niche_thumb_style(ctx.db),
            f"IDÉE : {lv['subject']}\nTITRE DE DÉPART : {idea.get('title', '')}\nAUTRES : {' | '.join(idea.get('alt_titles') or [])}\n"
            f"MINIATURE DE DÉPART : {(idea.get('thumbnail') or {}).get('idea', '')} (texte : {(idea.get('thumbnail') or {}).get('text', '')})",
            f"AMBIANCES DE MUSIQUE DISPONIBLES : {moods}" if moods else "",
            lessons_text(ctx.db, "seo", channel_id=lv["channel_id"]),
            "SCRIPT :\n" + chapters_listing(script["chapters"], numbered=False),
        )
        if x
    )
    pack: Packaging = asker(ctx)(prompt_text(ctx.db, "long_packaging", PACKAGING_PROMPT), user, Packaging)
    pack.titles = [t.model_copy(update={"title": to_digits(t.title.strip())[:100]}) for t in pack.titles if t.title.strip()]
    pack.chosen = min(pack.chosen, len(pack.titles) - 1)
    pack.hashtags = [h if h.startswith("#") else f"#{h}" for h in (re.sub(r"\s+", "", x) for x in pack.hashtags) if h][:3]
    return pack


def niche_thumb_style(db: Any) -> str:
    """Le style des miniatures de la niche : celui que la vision a relevé sur les miniatures qui marchent (« Étudier
    les miniatures de la niche »), sinon la consigne guide_thumb_niche."""
    row = db.fetch_one("select value->'thumb_style' as s from app_settings where key = 'long'")
    learned = (row or {}).get("s") or {}
    if learned.get("style"):
        rules = "\n".join(f"- {r}" for r in learned.get("rules") or [])
        return f"STYLE DES MINIATURES QUI MARCHENT DANS LA NICHE (relevé sur {learned.get('n', '?')} miniatures) :\n{learned['style']}\n{rules}"
    return prompt_text(db, "guide_thumb_niche", GUIDE_THUMB_NICHE)


def more_thumb_concepts(ctx: Any, lv: dict[str, Any], candidates: Sequence[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """`n` nouveaux concepts de miniature, différents de ceux qui existent (gardés par Luca ou non), dans le style de la
    niche, et censés faire mieux que la meilleure note."""
    pack = lv.get("packaging") or {}
    titles = pack.get("titles") or [{"title": lv["subject"]}]
    title = pack.get("final_title") or titles[min(int(pack.get("chosen") or 0), len(titles) - 1)]["title"]
    script = lv.get("script") or {}
    existing = "\n".join(
        f"- {'[GARDÉE PAR LUCA] ' if c.get('kept') else ''}{c.get('idea', '')} (texte : {c.get('text') or 'aucun'}) — "
        f"note {c.get('score', '?')}/10 : {c.get('note', '')}"
        for c in candidates
    )
    user = "\n\n".join(
        x
        for x in (
            prompt_text(ctx.db, "rules_thumbnail", THUMB_RULES),
            niche_thumb_style(ctx.db),
            f"TITRE : {title}\nSUJET : {lv['subject']}\nIDÉE CENTRALE : {script.get('central_idea', '')}\nPROMESSE : {script.get('promise', '')}",
            "CHAPITRES : " + " · ".join(c.get("title", "") for c in script.get("chapters") or []),
            f"MINIATURES DÉJÀ FAITES :\n{existing}" if existing else "",
            f"Propose {n} nouveaux concepts.",
        )
        if x
    )
    res: ThumbConcepts = asker(ctx)(prompt_text(ctx.db, "long_thumbs", THUMBS_PROMPT), user, ThumbConcepts)
    return [c.model_dump() for c in res.thumbnails[:n]]


def study_thumbnails(ctx: Any, limit: int = 12) -> dict[str, Any]:
    """Le style des miniatures qui marchent dans la niche : les miniatures des vidéos les plus vues de la Découverte
    (histoire, mystères…), regardées par la vision ; rangé dans app_settings.long.thumb_style."""
    import httpx

    from ..providers.llm import get_vision_llm

    videos = [v for v in proven_videos(ctx.db, limit=60) if "watch?v=" in v["url"]][:limit]
    if len(videos) < 4:
        raise RuntimeError("pas assez de vidéos qui marchent dans la niche : lancer d'abord une Découverte (page Recherche)")
    folder = ctx.settings.data_dir / "research" / "miniatures_niche"
    folder.mkdir(parents=True, exist_ok=True)
    files, lines = [], []
    for v in videos:
        vid = v["url"].split("watch?v=")[1][:11]
        path = folder / f"{vid}.jpg"
        if not path.exists():
            try:
                r = httpx.get(f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", timeout=20)
                r.raise_for_status()
                path.write_bytes(r.content)
            except httpx.HTTPError:
                continue
        lines.append(f"Image {len(files)} : « {v['title']} » ({format(v['views'], ',').replace(',', ' ')} vues, {v['channel']})")
        files.append(path)
    vision = get_vision_llm(ctx.settings, ctx.db)
    if not vision:
        raise RuntimeError("aucun modèle qui voit les images dans Réglages → IA")
    res: ThumbStyle = vision.complete_json(
        prompt_text(ctx.db, "long_thumb_style", THUMB_STYLE_PROMPT), "\n".join(lines), ThumbStyle, images=files
    )
    value = {"style": res.style, "rules": res.rules, "n": len(files), "at": datetime.now(UTC).isoformat()}
    ctx.db.execute(
        """insert into app_settings (key, value) values ('long', jsonb_build_object('thumb_style', %s::jsonb))
           on conflict (key) do update set value = app_settings.value || jsonb_build_object('thumb_style', %s::jsonb)""",
        (Jsonb(value), Jsonb(value)),
    )
    return value


def numbered_text(text: str) -> tuple[str, int]:
    """Le texte d'un paragraphe avec ses mots numérotés toutes les 5 (« [0] Tu as 14 ans, [5] nous… ») ; nombre de mots."""
    toks = text.split()
    out = []
    for i, t in enumerate(toks):
        out.append(f"[{i}] {t}" if i % 5 == 0 else t)
    return " ".join(out), len(toks)


def director_groups(paragraphs: Sequence[dict[str, Any]], max_words: int = DIRECTOR_WORDS_PER_CALL) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    n = 0
    for p in paragraphs:
        if cur and n + p["words"] > max_words:
            groups.append(cur)
            cur, n = [], 0
        cur.append(p)
        n += p["words"]
    if cur:
        groups.append(cur)
    return groups


def sanitize_shots(shots: Sequence[ShotSpec], paragraphs: Sequence[dict[str, Any]]) -> list[ShotSpec]:
    """Les plans gardés dans l'ordre des paragraphes : un plan au mot 0 de chaque paragraphe (le premier plan du
    paragraphe recule au mot 0 s'il le faut), mots dans le paragraphe, deux plans jamais au même mot."""
    by_para: dict[str, list[ShotSpec]] = {}
    for s in shots:
        by_para.setdefault(s.para, []).append(s)
    out: list[ShotSpec] = []
    for p in paragraphs:
        n_words = len(p["text"].split())
        mine = sorted(by_para.get(p["key"], []), key=lambda s: s.at_word)
        if not mine:
            mine = [ShotSpec(para=p["key"], at_word=0, kind="image", visual_prompt=p.get("show") or p["text"][:200], motion="in")]
        mine[0] = mine[0].model_copy(update={"at_word": 0})
        seen: set[int] = set()
        for s in mine:
            w = min(max(0, s.at_word), max(0, n_words - 3))
            if w in seen:
                continue
            seen.add(w)
            out.append(s.model_copy(update={"at_word": w}))
    return out


def plan_shots(
    ctx: Any, lv: dict[str, Any], script: dict[str, Any], image_rules: str, progress: Callable[[int, str], None]
) -> tuple[list[ShotSpec], str | None]:
    ask = asker(ctx)
    paragraphs = [p for c in script["chapters"] for p in c["paragraphs"]]
    groups = director_groups(paragraphs)
    bible: str | None = script.get("design_bible")
    shots: list[ShotSpec] = []
    for gi, group in enumerate(groups):
        progress(10 + int(80 * gi / max(1, len(groups))), f"Plans du réalisateur ({gi + 1}/{len(groups)})")
        listing = []
        for p in group:
            text, n = numbered_text(p["text"])
            listing.append(f"{p['key']} ({n} mots) : {text}\n   on voit : {p.get('show', '')}")
        user = "\n\n".join(
            x
            for x in (
                image_rules,
                f"BIBLE VISUELLE : {bible}" if bible else "BIBLE VISUELLE : à écrire (design_bible).",
                f"SUJET : {lv['subject']} ; TITRE : {(lv['idea'] or {}).get('title', '')}",
                "Ces paragraphes ouvrent la vidéo (la 1re minute)." if gi == 0 else "",
                "PARAGRAPHES :\n" + "\n".join(listing),
            )
            if x
        )
        batch: ShotBatch = ask(prompt_text(ctx.db, "long_director", DIRECTOR_PROMPT), user, ShotBatch)
        if not bible and batch.design_bible:
            bible = batch.design_bible.strip()
        shots.extend(sanitize_shots(batch.shots, group))
    return shots, bible
