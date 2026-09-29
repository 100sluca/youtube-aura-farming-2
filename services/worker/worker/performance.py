"""Analyse des performances des vidéos publiées (agent analyste, docs/25-dashboard-statistiques.md).

Le code rassemble, pour chaque vidéo publiée, ses chiffres et sa fiche de fabrication (thème, format, titre, titre
d'accroche, textes à l'écran, narration, rythme des plans, musique, modèle vidéo, hashtags, heure de publication,
commentaires), la note par rapport aux autres et calcule des ventilations (format, thème, durée, créneau, forme du
titre…). Le LLM ne fait qu'interpréter : pourquoi telle vidéo marche et telle autre non, ce qui distingue les deux
groupes, et quelles règles en tirer. Les leçons proposées ne servent qu'une fois validées dans le Dashboard
(worker/lessons.py).

Note d'une vidéo : ses vues à 7 jours (ses vues du moment si elle est plus jeune ou si on ne les connaît pas), divisées
par la médiane des vidéos jugeables de la chaîne. Une vidéo de moins de 24 h est listée mais pas jugée.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from .models import Recipe
from .strategy import confidence, duration_bucket, time_slot, title_features

PARIS = ZoneInfo("Europe/Paris")
DAYS = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")
MIN_AGE_H = 24.0  # plus jeune : listée, pas encore jugée
TOP_SCORE = 1.25  # une vidéo du premier tiers n'est « top » qu'à 1,25 × la médiane au moins
FLOP_SCORE = 0.8  # et une du dernier tiers n'est « flop » qu'à 0,8 × la médiane au plus
MAX_PATTERNS, MAX_LESSONS, MAX_EXPERIMENTS = 5, 6, 3
RECIPE_LABELS = {"timelapse": "chantier en accéléré", "tour": "visite de maison de luxe", "story": "récit narré"}
VIDEO_MODELS = {"gemini_web": "Gemini en ligne", "comfy_wan22_i2v_4step": "Wan 2.2 14B (4 passes)"}

Confidence = Literal["faible", "moyenne", "bonne"]
LessonTarget = Literal["idea", "script", "seo", "production"]
Verdict = Literal["top", "moyen", "flop", "trop récente"]


# ---- Sortie de l'agent -----------------------------------------------------------------------------------------------


class VideoDiagnosis(BaseModel):
    ref: str = Field(description="référence de la vidéo : V1, V2…")
    why: str = Field(description="pourquoi elle a ce verdict, en une ou deux phrases")
    worked: list[str] = Field(default_factory=list, description="ce qui a marché")
    missed: list[str] = Field(default_factory=list, description="ce qui a manqué")


# Types souples à la lecture (un LLM écrit parfois « montage » ou « tous ») : clean_report ramène chaque valeur à la liste
# permise ou écarte l'élément, plutôt que de faire échouer toute l'analyse sur un mot.
class Pattern(BaseModel):
    finding: str
    evidence: str = Field("", description="la preuve chiffrée, tirée des données fournies")
    confidence: str = Field("faible", description="faible | moyenne | bonne")


class LessonProposal(BaseModel):
    target: str = Field(description="idea | script | seo | production")
    recipe: str | None = Field(None, description="timelapse | tour | story ; null = tous les formats")
    rule: str = Field(description="la règle, à l'impératif, applicable telle quelle")
    why: str = Field("", description="la preuve chiffrée")
    confidence: str = Field("faible", description="faible | moyenne | bonne")


class Experiment(BaseModel):
    hypothesis: str
    test: str


class PerformanceReport(BaseModel):
    summary: str
    videos: list[VideoDiagnosis] = Field(default_factory=list)
    patterns: list[Pattern] = Field(default_factory=list)
    lessons: list[LessonProposal] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)


# ---- Fiche d'une vidéo -----------------------------------------------------------------------------------------------


@dataclass
class VideoFacts:
    id: str
    title: str
    origin: str  # app | imported (mise en ligne à la main, importée)
    published_at: datetime
    age_h: float
    duration_s: float | None = None
    series: str | None = None
    recipe: str | None = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int | None = None
    subscribers_gained: int | None = None
    engaged_views: int | None = None
    average_view_pct: float | None = None
    average_view_duration_s: float | None = None
    hook_retention_pct: float | None = None
    end_retention_pct: float | None = None
    views_24h: int | None = None
    views_7d: int | None = None
    # la même vidéo sur TikTok (docs/39, table tiktok_posts), si elle y est sortie
    tiktok_views: int | None = None
    tiktok_likes: int | None = None
    tiktok_comments: int | None = None
    tiktok_shares: int | None = None
    tiktok_completion_pct: float | None = None
    tiktok_for_you_pct: float | None = None
    hook_title: str | None = None
    on_screen: list[str] = field(default_factory=list)
    narration: list[str] = field(default_factory=list)
    shots: int | None = None
    avg_shot_s: float | None = None
    first_shot: str | None = None
    music: str | None = None  # piste posée au montage (videos.music_track, migration 0018), sinon l'ambiance du script
    video_model: str | None = None
    image_model: str | None = None
    tags: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    description_head: str | None = None
    top_comments: list[str] = field(default_factory=list)
    # calculés par rank()
    ref: str = ""
    comparable_views: int = 0
    score: float | None = None
    verdict: Verdict = "trop récente"

    @property
    def published_local(self) -> datetime:
        return self.published_at.astimezone(PARIS)

    @property
    def like_rate_pct(self) -> float | None:
        return round(self.likes * 100 / self.views, 2) if self.views else None


def _text(value: Any, lang: str) -> str:
    """Texte d'un champ {langue: texte} du script, dans la langue de la vidéo (sinon la première trouvée)."""
    if isinstance(value, dict):
        return str(value.get(lang) or next((v for v in value.values() if v), "") or "").strip()
    return str(value or "").strip()


def script_features(script: dict[str, Any] | None, lang: str) -> dict[str, Any]:
    """Ce que le script dit de la vidéo : titre d'accroche, textes à l'écran, narration, plans, premier plan, musique."""
    if not script:
        return {}
    scenes = [s for s in script.get("scenes") or [] if isinstance(s, dict)]
    durations = [float(s.get("duration_s") or 0) for s in scenes]
    return {
        "hook_title": _text(script.get("hook_title"), lang) or None,
        "on_screen": [t for s in scenes if (t := _text(s.get("on_screen_text"), lang))],
        "narration": [t for s in scenes if (t := _text(s.get("narration"), lang))],
        "shots": len(scenes) or None,
        "avg_shot_s": round(sum(durations) / len(scenes), 1) if scenes else None,
        "first_shot": (str(scenes[0].get("visual_prompt") or "")[:220] or None) if scenes else None,
        "music": script.get("music_mood") or None,
    }


HASHTAG = re.compile(r"#[\wÀ-ɏ]+", re.UNICODE)


def hashtags_of(description: str | None) -> list[str]:
    seen: list[str] = []
    for h in HASHTAG.findall(description or ""):
        if h.lower() not in (s.lower() for s in seen):
            seen.append(h)
    return seen


def description_head(description: str | None) -> str | None:
    """Début de la description, sans les hashtags ni la mention IA ajoutée à la fin."""
    lines = [ln.strip() for ln in (description or "").splitlines() if ln.strip() and not ln.strip().startswith("#")]
    lines = [ln for ln in lines if not ln.lower().startswith("lieu imaginaire")]
    head = " ".join(lines)
    return head[:220] or None


def _music(r: dict[str, Any], mood: str | None) -> str | None:
    """La piste posée au montage (titre, sinon identifiant) et l'ambiance demandée par le script."""
    track = r.get("music_title") or r.get("music_track")
    if track and mood:
        return f"{track} (ambiance {mood})"
    return track or (f"ambiance {mood}" if mood else None)


def _num(v: Any) -> float | None:
    return None if v is None else float(v)


def _int(v: Any) -> int | None:
    return None if v is None else int(v)


def facts_from_row(r: dict[str, Any], now: datetime, comments: Sequence[str] = ()) -> VideoFacts:
    """Fiche d'une vidéo depuis une ligne de v_video_overview (+ script et commentaires)."""
    lang = r.get("lang") or "fr"
    feats = script_features(r.get("script"), lang)
    provider = r.get("video_provider")
    return VideoFacts(
        id=str(r["id"]),
        title=r.get("title") or "Sans titre",
        origin=r.get("origin") or "app",
        published_at=r["published_at"],
        age_h=round((now - r["published_at"]).total_seconds() / 3600, 1),
        duration_s=_num(r.get("duration_s")),
        series=r.get("series_name"),
        recipe=r.get("recipe"),
        views=int(r.get("views") or 0),
        likes=int(r.get("likes") or 0),
        comments=int(r.get("comments") or 0),
        shares=_int(r.get("shares")),
        subscribers_gained=_int(r.get("subscribers_gained")),
        engaged_views=_int(r.get("engaged_views")),
        average_view_pct=_num(r.get("average_view_pct")),
        average_view_duration_s=_num(r.get("average_view_duration_s")),
        hook_retention_pct=_num(r.get("hook_retention_pct")),
        end_retention_pct=_num(r.get("end_retention_pct")),
        views_24h=_int(r.get("views_24h")),
        views_7d=_int(r.get("views_7d")),
        tiktok_views=_int(r.get("tt_views")),
        tiktok_likes=_int(r.get("tt_likes")),
        tiktok_comments=_int(r.get("tt_comments")),
        tiktok_shares=_int(r.get("tt_shares")),
        tiktok_completion_pct=_num(r.get("tt_completion_pct")),
        tiktok_for_you_pct=_num(r.get("tt_for_you_pct")),
        hook_title=feats.get("hook_title"),
        on_screen=feats.get("on_screen", []),
        narration=feats.get("narration", []),
        shots=feats.get("shots"),
        avg_shot_s=feats.get("avg_shot_s"),
        first_shot=feats.get("first_shot"),
        music=_music(r, feats.get("music")),
        video_model=VIDEO_MODELS.get(provider, provider) if provider else None,
        image_model=r.get("image_workflow"),
        tags=list(r.get("tags") or []),
        hashtags=hashtags_of(r.get("description")),
        description_head=description_head(r.get("description")),
        top_comments=list(comments)[:3],
    )


def load_facts(db: Any, channel_id: Any, window_days: int, now: datetime | None = None) -> list[VideoFacts]:
    """Les vidéos publiées de la chaîne sur la fenêtre, avec leur fiche."""
    now = now or datetime.now(UTC)
    rows = db.fetch_all(
        """select o.*, p.script, tt.views as tt_views, tt.likes as tt_likes, tt.comments as tt_comments,
                  tt.shares as tt_shares, tt.completion_pct as tt_completion_pct,
                  round((tt.impression_sources->>'forYou')::numeric * 100, 1) as tt_for_you_pct
           from v_video_overview o left join productions p on p.id = o.production_id
           -- la même vidéo sur TikTok (docs/39), vues relevées par Zernio (pas une vidéo tout juste lue en direct)
           left join lateral (select * from tiktok_posts t where t.video_id = o.id and coalesce(t.sync_status, '') <> 'live'
                              order by t.views desc limit 1) tt on true
           where o.channel_id = %s and o.status = 'published' and o.published_at is not null
             and o.published_at > now() - make_interval(days => %s)
           order by o.published_at""",
        (channel_id, window_days),
    )
    ids = [r["id"] for r in rows]
    comments: dict[str, list[str]] = defaultdict(list)
    if ids:
        for c in db.fetch_all(
            "select video_id, text from video_comments where video_id = any(%s) order by like_count desc, published_at desc",
            (ids,),
        ):
            comments[str(c["video_id"])].append(" ".join(str(c["text"] or "").split())[:160])
    return [facts_from_row(r, now, comments.get(str(r["id"]), [])) for r in rows]


# ---- Notes et ventilations -------------------------------------------------------------------------------------------


def rank(videos: list[VideoFacts]) -> dict[str, Any]:
    """Note chaque vidéo (vues comparables ÷ médiane des vidéos jugeables) et lui donne son verdict. Les références V1,
    V2… suivent le classement (V1 = la meilleure), les vidéos trop récentes à la fin."""
    for v in videos:
        v.comparable_views = v.views_7d if v.views_7d is not None and v.age_h >= 7 * 24 else v.views
    judged = sorted((v for v in videos if v.age_h >= MIN_AGE_H), key=lambda v: v.comparable_views, reverse=True)
    young = sorted((v for v in videos if v.age_h < MIN_AGE_H), key=lambda v: v.comparable_views, reverse=True)
    median = statistics.median(v.comparable_views for v in judged) if judged else None
    base = max(float(median or 0), 1.0)
    third = max(1, round(len(judged) / 3))  # 4 vidéos : 1 top possible, 2 au milieu, 1 flop possible
    for i, v in enumerate(judged):
        v.score = round(v.comparable_views / base, 2)
        if len(judged) >= 2 and i < third and v.score >= TOP_SCORE:
            v.verdict = "top"
        elif len(judged) >= 2 and i >= len(judged) - third and v.score <= FLOP_SCORE:
            v.verdict = "flop"
        else:
            v.verdict = "moyen"
    for v in young:
        v.score = round(v.comparable_views / base, 2) if judged else None
        v.verdict = "trop récente"
    for i, v in enumerate([*judged, *young]):
        v.ref = f"V{i + 1}"
    return {"judged": len(judged), "median_views": median}


def _group(videos: Sequence[VideoFacts], key: Callable[[VideoFacts], Iterable[str] | str | None]) -> list[dict[str, Any]]:
    buckets: dict[str, list[VideoFacts]] = defaultdict(list)
    for v in videos:
        k = key(v)
        for value in [k] if isinstance(k, str) or k is None else k:
            if value:
                buckets[value].append(v)
    out = []
    for value, items in buckets.items():
        views = sum(i.views for i in items)
        pcts = [i.average_view_pct for i in items if i.average_view_pct is not None]
        hooks = [i.hook_retention_pct for i in items if i.hook_retention_pct is not None]
        out.append(
            {
                "value": value,
                "n": len(items),
                "median_score": round(statistics.median(i.score or 0 for i in items), 2),
                "median_views": statistics.median(i.comparable_views for i in items),
                "mean_view_pct": round(statistics.fmean(pcts), 1) if pcts else None,
                "mean_hook_pct": round(statistics.fmean(hooks), 1) if hooks else None,
                "like_rate_pct": round(sum(i.likes for i in items) * 100 / views, 2) if views else None,
                "confidence": confidence(len(items)),
            }
        )
    return sorted(out, key=lambda g: (-g["median_score"], -g["n"]))


def breakdowns(videos: Sequence[VideoFacts]) -> dict[str, list[dict[str, Any]]]:
    """Ventilations des vidéos jugées (notées) : format, thème, durée, créneau, forme du titre, accroche, voix…"""
    judged = [v for v in videos if v.verdict != "trop récente"]
    return {
        "format": _group(judged, lambda v: RECIPE_LABELS.get(v.recipe or "", "inconnu (mise en ligne à la main)")),
        "thème": _group(judged, lambda v: v.series),
        "durée": _group(judged, lambda v: duration_bucket(v.duration_s)),
        "créneau": _group(judged, lambda v: time_slot(v.published_local)),
        "titre": _group(judged, lambda v: title_features(v.title)),
        "titre d'accroche à l'écran": _group(
            judged, lambda v: None if v.origin == "imported" else ("oui" if v.hook_title else "non")
        ),
        "voix off": _group(judged, lambda v: None if v.origin == "imported" else ("oui" if v.narration else "non")),
        "modèle vidéo": _group(judged, lambda v: v.video_model),
        "musique": _group(judged, lambda v: None if v.origin == "imported" else (v.music or "sans musique")),
        "origine": _group(judged, lambda v: "appli" if v.origin == "app" else "mise en ligne à la main"),
    }


def compute_performance(videos: list[VideoFacts]) -> dict[str, Any]:
    """Chiffres calculés en code, gardés avec le rapport (performance_reports.stats) et envoyés à l'agent."""
    ranking = rank(videos)
    return {
        "n": len(videos),
        "judged": ranking["judged"],
        "median_views": ranking["median_views"],
        "videos": [
            {
                "ref": v.ref,
                "id": v.id,
                "title": v.title,
                "verdict": v.verdict,
                "score": v.score,
                "views": v.views,
                "comparable_views": v.comparable_views,
                "age_h": v.age_h,
            }
            for v in sorted(videos, key=lambda v: int(v.ref[1:]) if v.ref[1:].isdigit() else 0)
        ],
        "groups": breakdowns(videos),
    }


# ---- Message de l'agent ----------------------------------------------------------------------------------------------


def _fmt(n: float | int | None, suffix: str = "", digits: int = 0) -> str:
    if n is None:
        return "—"
    return f"{n:,.{digits}f}".replace(",", " ").replace(".", ",") + suffix


def video_block(v: VideoFacts) -> str:
    """Fiche d'une vidéo pour l'agent : chiffres puis fabrication."""
    verdict = v.verdict.upper() if v.verdict != "trop récente" else "TROP RÉCENTE (pas jugée)"
    score = f"×{_fmt(v.score, digits=2)} la médiane" if v.score is not None else "pas de note"
    origin = "produite par l'appli" if v.origin == "app" else "mise en ligne à la main (importée, fiche incomplète)"
    lines = [
        f"{v.ref} · {verdict} · {score} · « {v.title} » · {origin}",
        f"  Publiée {DAYS[v.published_local.weekday()]} {v.published_local.strftime('%d/%m %H:%M')} (heure de Paris), "
        f"il y a {_fmt(v.age_h)} h · "
        f"durée {_fmt(v.duration_s, ' s', 1)} · format : {RECIPE_LABELS.get(v.recipe or '', 'inconnu')}"
        + (f" · thème : {v.series}" if v.series else ""),
        f"  Vues {_fmt(v.views)} (à 24 h : {_fmt(v.views_24h)} ; à 7 j : {_fmt(v.views_7d)}) · vues engagées "
        f"{_fmt(v.engaged_views)} · rétention moyenne {_fmt(v.average_view_pct, ' %', 1)} · encore là à 3 s "
        f"{_fmt(v.hook_retention_pct, ' %', 1)} · à la fin {_fmt(v.end_retention_pct, ' %', 1)} · durée moyenne regardée "
        f"{_fmt(v.average_view_duration_s, ' s', 1)}",
        f"  J'aime {_fmt(v.likes)} ({_fmt(v.like_rate_pct, ' %', 2)} des vues) · commentaires {_fmt(v.comments)} · "
        f"partages {_fmt(v.shares)} · abonnés gagnés {_fmt(v.subscribers_gained)}",
    ]
    if v.tiktok_views is not None:
        lines.append(
            f"  TikTok (même vidéo) : vues {_fmt(v.tiktok_views)} · j'aime {_fmt(v.tiktok_likes)} · commentaires "
            f"{_fmt(v.tiktok_comments)} · partages {_fmt(v.tiktok_shares)} · vue jusqu'au bout "
            f"{_fmt(v.tiktok_completion_pct, ' %', 1)} · vues venues de « Pour toi » {_fmt(v.tiktok_for_you_pct, ' %')}"
        )
    if v.hook_title:
        lines.append(f"  Titre d'accroche affiché : « {v.hook_title} »")
    if v.shots:
        lines.append(
            f"  {v.shots} plans (en moyenne {_fmt(v.avg_shot_s, ' s', 1)} chacun) · "
            f"voix off : {'oui' if v.narration else 'non'} · musique : {v.music or 'aucune'}"
        )
    if v.first_shot:
        lines.append(f"  Premier plan : {v.first_shot}")
    if v.on_screen:
        lines.append("  Textes à l'écran : " + " | ".join(v.on_screen[:8]))
    if v.narration:
        lines.append("  Narration : " + " / ".join(v.narration[:8]))
    if v.video_model or v.image_model:
        lines.append(f"  Modèles : vidéo {v.video_model or '—'} · images {v.image_model or '—'}")
    if v.description_head:
        lines.append(f"  Description : {v.description_head}")
    if v.hashtags or v.tags:
        lines.append(f"  Hashtags : {' '.join(v.hashtags) or '—'} · tags : {', '.join(v.tags[:12]) or '—'}")
    if v.top_comments:
        lines.append("  Commentaires : " + " / ".join(f"« {c} »" for c in v.top_comments))
    return "\n".join(lines)


def groups_block(groups: dict[str, list[dict[str, Any]]]) -> str:
    out = []
    for name, items in groups.items():
        if not items:
            continue
        parts = [
            f"{g['value']} : {g['n']} vidéo(s), note médiane ×{_fmt(g['median_score'], digits=2)}, rétention "
            f"{_fmt(g['mean_view_pct'], ' %', 1)}, à 3 s {_fmt(g['mean_hook_pct'], ' %', 1)}, j'aime "
            f"{_fmt(g['like_rate_pct'], ' %', 2)} (confiance {g['confidence']})"
            for g in items
        ]
        out.append(f"- {name} : " + " ; ".join(parts))
    return "\n".join(out)


def build_message(
    channel: str,
    videos: Sequence[VideoFacts],
    stats: dict[str, Any],
    active: Sequence[dict[str, Any]],
    sheets: Sequence[VideoFacts] = (),
) -> str:
    """Message de l'agent. `sheets` : les vidéos dont une planche d'images est jointe, dans l'ordre des images."""
    ordered = sorted(videos, key=lambda v: int(v.ref[1:]) if v.ref[1:].isdigit() else 0)
    rules = "\n".join(f"- [{a['target']}{'/' + a['recipe'] if a.get('recipe') else ''}] {a['rule']}" for a in active)
    images = (
        "IMAGES JOINTES : une planche par vidéo, dans cet ordre : "
        + ", ".join(v.ref for v in sheets)
        + ". Vidéo produite par l'appli : de gauche à droite 0,5 s et 2,5 s (l'accroche), le milieu, 90 %. Vidéo mise en ligne"
        " à la main : 25 %, 50 %, 75 % de la vidéo. Regarde ce que le spectateur voit d'abord, si l'image change et si le"
        " sujet se comprend sans le son."
        if sheets
        else ""
    )
    return "\n\n".join(
        part
        for part in (
            f"Chaîne : {channel}. {stats['n']} vidéo(s) publiée(s), {stats['judged']} jugée(s) (au moins 24 h) ; "
            f"médiane des vues comparables : {_fmt(stats['median_views'])}. Note = vues à 7 jours (sinon vues du moment) "
            "÷ cette médiane. Top : premier tiers et ×1,25 au moins ; flop : dernier tiers et ×0,8 au plus.",
            "VIDÉOS (V1 = la meilleure) :\n" + "\n\n".join(video_block(v) for v in ordered),
            "VENTILATIONS (vidéos jugées) :\n" + (groups_block(stats["groups"]) or "—"),
            "LEÇONS DÉJÀ EN SERVICE :\n" + (rules or "aucune"),
            images,
        )
        if part
    )


def sheet_candidates(videos: Sequence[VideoFacts], limit: int = 8) -> list[VideoFacts]:
    """Les vidéos à montrer en images : toutes les jugées s'il y en a peu, sinon les meilleures et les moins bonnes."""
    judged = sorted(
        (v for v in videos if v.verdict != "trop récente"), key=lambda v: int(v.ref[1:]) if v.ref[1:].isdigit() else 0
    )
    if len(judged) <= limit:
        return judged
    return [*judged[: limit // 2], *judged[-(limit - limit // 2) :]]


# ---- Vérification de la sortie ---------------------------------------------------------------------------------------

CONFIDENCE_ORDER = ("faible", "moyenne", "bonne")


def confidence_cap(judged: int) -> Confidence:
    """Confiance maximale qu'autorise l'échantillon : faible sous 4 vidéos jugées, moyenne sous 10."""
    return "faible" if judged < 4 else "moyenne" if judged < 10 else "bonne"


def _capped(value: str, cap: str) -> Confidence:
    level = min(CONFIDENCE_ORDER.index(value) if value in CONFIDENCE_ORDER else 0, CONFIDENCE_ORDER.index(cap))
    return CONFIDENCE_ORDER[level]  # type: ignore[return-value]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9àâäéèêëîïôöùûüç]+", " ", text.lower()).strip()


TARGETS: dict[str, LessonTarget] = {
    "idea": "idea",
    "ideas": "idea",
    "idee": "idea",
    "idée": "idea",
    "idées": "idea",
    "sujet": "idea",
    "sujets": "idea",
    "script": "script",
    "scenario": "script",
    "scénario": "script",
    "scenariste": "script",
    "scénariste": "script",
    "seo": "seo",
    "titre": "seo",
    "titres": "seo",
    "description": "seo",
    "hashtags": "seo",
    "production": "production",
    "montage": "production",
    "réglage": "production",
    "reglage": "production",
    "réglages": "production",
    "fabrication": "production",
}
RECIPES: dict[str, Recipe] = {
    "timelapse": "timelapse",
    "chantier": "timelapse",
    "tour": "tour",
    "visite": "tour",
    "story": "story",
    "récit": "story",
}


def normalize_target(value: str) -> LessonTarget | None:
    return TARGETS.get(_norm(value).split(" ")[0]) if value else None


def normalize_recipe(value: str | None) -> Recipe | None:
    return RECIPES.get(_norm(value).split(" ")[0]) if value else None


def clean_report(
    raw: PerformanceReport, videos: Sequence[VideoFacts], active_rules: Sequence[str], judged: int
) -> tuple[dict[str, Any], list[LessonProposal]]:
    """Garde-fous après le LLM : vidéos inconnues retirées, verdicts et notes repris du code, listes bornées, confiance
    plafonnée selon le nombre de vidéos jugées, leçons en double (entre elles ou avec celles en service) retirées."""
    cap = confidence_cap(judged)
    by_ref = {v.ref: v for v in videos}
    diagnoses: list[dict[str, Any]] = []
    for d in raw.videos:
        v = by_ref.get(d.ref.strip().upper())
        if v is None or any(x["video_id"] == v.id for x in diagnoses):
            continue
        diagnoses.append(
            {
                "video_id": v.id,
                "ref": v.ref,
                "title": v.title,
                "verdict": v.verdict,
                "score": v.score,
                "why": d.why.strip(),
                "worked": [w.strip() for w in d.worked if w.strip()][:4],
                "missed": [m.strip() for m in d.missed if m.strip()][:4],
            }
        )
    diagnoses.sort(key=lambda x: int(x["ref"][1:]) if x["ref"][1:].isdigit() else 0)
    seen = {_norm(r) for r in active_rules}
    lessons: list[LessonProposal] = []
    for lesson in raw.lessons:
        rule = " ".join(lesson.rule.split())
        target = normalize_target(lesson.target)
        if target is None or len(rule) < 8 or _norm(rule) in seen:
            continue
        seen.add(_norm(rule))
        lessons.append(
            LessonProposal(
                target=target,
                recipe=normalize_recipe(lesson.recipe),
                rule=rule[:600],
                why=" ".join(lesson.why.split())[:600],
                confidence=_capped(_norm(lesson.confidence), cap),
            )
        )
        if len(lessons) >= MAX_LESSONS:
            break
    report = {
        "summary": raw.summary.strip(),
        "videos": diagnoses,
        "patterns": [
            {"finding": p.finding.strip(), "evidence": p.evidence.strip(), "confidence": _capped(_norm(p.confidence), cap)}
            for p in raw.patterns[:MAX_PATTERNS]
            if p.finding.strip()
        ],
        "experiments": [asdict_experiment(e) for e in raw.experiments[:MAX_EXPERIMENTS] if e.hypothesis.strip()],
        "confidence_cap": cap,
    }
    return report, lessons


def asdict_experiment(e: Experiment) -> dict[str, str]:
    return {"hypothesis": e.hypothesis.strip(), "test": e.test.strip()}


__all__ = [
    "LessonProposal",
    "PerformanceReport",
    "VideoFacts",
    "build_message",
    "clean_report",
    "compute_performance",
    "facts_from_row",
    "load_facts",
    "rank",
    "script_features",
]
