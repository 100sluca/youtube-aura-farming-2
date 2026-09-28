"""Stratégie : statistiques de performance calculées en code, et accès à la stratégie validée.

Principes repris de youtube-automation-agent (channel-learning-engine), corrigés pour les Shorts :
- chaque vidéo est comparée à la médiane de la chaîne, à âge égal (vues à J+7) ;
- une ventilation n'est crédible qu'avec assez de vidéos : confiance faible < 3, moyenne < 8, bonne au-delà ;
- les chiffres sont calculés ici, jamais par le LLM, qui ne fait que les interpréter ;
- seule une stratégie validée à la main (status = 'active') influence les agents idée, script et SEO.
Pas de taux de clic : dans le flux Shorts, il n'y a pas de clic sur miniature.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .models import StrategyProposal
from .subtitles import strip_emojis


@dataclass(frozen=True)
class VideoPerf:
    title: str
    category: str | None
    format: str | None
    duration_s: float | None
    published_local: datetime | None
    views_d7: int
    average_view_pct: float | None
    subscribers_gained: int
    likes: int
    comments: int
    shares: int
    hook: str | None = None

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> VideoPerf:
        return cls(
            title=r.get("title") or "",
            category=r.get("category"),
            format=r.get("format"),
            duration_s=float(r["duration_s"]) if r.get("duration_s") is not None else None,
            published_local=r.get("published_local"),
            views_d7=int(r.get("views_d7") or 0),
            average_view_pct=float(r["average_view_pct"]) if r.get("average_view_pct") is not None else None,
            subscribers_gained=int(r.get("subscribers_gained") or 0),
            likes=int(r.get("likes") or 0),
            comments=int(r.get("comments") or 0),
            shares=int(r.get("shares") or 0),
            hook=r.get("hook"),
        )


@dataclass
class Group:
    value: str
    n: int
    median_views_d7: float
    mean_view_pct: float | None
    subs_per_1k_views: float | None
    engagement_rate_pct: float | None
    lift_pct: float | None  # écart de la médiane du groupe à la médiane de la chaîne
    confidence: str


def confidence(n: int) -> str:
    return "faible" if n < 3 else "moyenne" if n < 8 else "bonne"


def duration_bucket(d: float | None) -> str | None:
    if d is None:
        return None
    return "moins de 25 s" if d < 25 else "25 à 35 s" if d <= 35 else "plus de 35 s"


def time_slot(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    h = dt.hour
    if 6 <= h < 11:
        return "matin (6-11 h)"
    if 11 <= h < 14:
        return "midi (11-14 h)"
    if 14 <= h < 18:
        return "après-midi (14-18 h)"
    if 18 <= h < 22:
        return "soir (18-22 h)"
    return "nuit (22-6 h)"


def title_features(title: str) -> list[str]:
    feats = []
    if "?" in title:
        feats.append("question")
    if any(ch.isdigit() for ch in title):
        feats.append("chiffre")
    if strip_emojis(title) != title:
        feats.append("émoji")
    n = len(title)
    feats.append("titre court (≤ 40)" if n <= 40 else "titre moyen (41-60)" if n <= 60 else "titre long (> 60)")
    return feats


def _group(rows: Sequence[VideoPerf], key: Callable[[VideoPerf], Iterable[str] | str | None], median_all: float) -> list[Group]:
    buckets: dict[str, list[VideoPerf]] = defaultdict(list)
    for r in rows:
        k = key(r)
        for value in [k] if isinstance(k, str) or k is None else k:
            if value:
                buckets[value].append(r)
    out = []
    for value, items in buckets.items():
        views = [i.views_d7 for i in items]
        med = statistics.median(views)
        pcts = [i.average_view_pct for i in items if i.average_view_pct is not None]
        total_views = sum(views)
        out.append(
            Group(
                value=value,
                n=len(items),
                median_views_d7=round(med, 1),
                mean_view_pct=round(statistics.fmean(pcts), 1) if pcts else None,
                subs_per_1k_views=round(sum(i.subscribers_gained for i in items) * 1000 / total_views, 2) if total_views else None,
                engagement_rate_pct=(
                    round(sum(i.likes + i.comments + i.shares for i in items) * 100 / total_views, 2) if total_views else None
                ),
                lift_pct=round((med / median_all - 1) * 100, 1) if median_all else None,
                confidence=confidence(len(items)),
            )
        )
    return sorted(out, key=lambda g: (-g.median_views_d7, -g.n))


def compute_stats(rows: Sequence[VideoPerf]) -> dict[str, Any]:
    """Ventilations par catégorie, format, durée, créneau, heure et caractéristiques du titre."""
    if not rows:
        return {"n": 0}
    median_all = statistics.median(r.views_d7 for r in rows)
    ranked = sorted(rows, key=lambda r: r.views_d7, reverse=True)

    def brief(r: VideoPerf) -> dict[str, Any]:
        return {
            "titre": r.title,
            "catégorie": r.category,
            "accroche": r.hook,
            "vues_j7": r.views_d7,
            "rétention_pct": r.average_view_pct,
            "durée_s": r.duration_s,
            "publiée": r.published_local.strftime("%a %H:%M") if r.published_local else None,
        }

    def dump(groups: list[Group]) -> list[dict[str, Any]]:
        return [asdict(g) for g in groups]

    return {
        "n": len(rows),
        "median_views_d7": median_all,
        "mean_view_pct": round(statistics.fmean([r.average_view_pct for r in rows if r.average_view_pct is not None]), 1)
        if any(r.average_view_pct is not None for r in rows)
        else None,
        "par_categorie": dump(_group(rows, lambda r: r.category, median_all)),
        "par_format": dump(_group(rows, lambda r: r.format, median_all)),
        "par_duree": dump(_group(rows, lambda r: duration_bucket(r.duration_s), median_all)),
        "par_creneau": dump(_group(rows, lambda r: time_slot(r.published_local), median_all)),
        "par_heure": dump(_group(rows, lambda r: r.published_local.strftime("%H:00") if r.published_local else None, median_all)),
        "par_titre": dump(_group(rows, lambda r: title_features(r.title), median_all)),
        "meilleures": [brief(r) for r in ranked[:5]],
        "moins_bonnes": [brief(r) for r in ranked[-5:][::-1]] if len(ranked) > 5 else [],
    }


def validate_proposal(p: StrategyProposal, stats: dict[str, Any], current_slots: Sequence[str]) -> StrategyProposal:
    """Garde-fous appliqués après le LLM : créneaux au bon format et justifiés, poids bornés selon la confiance."""
    data = p.model_dump()
    slots = p.publish_slots
    if slots:
        clean = sorted({s.strip()[:5] for s in slots if _is_hhmm(s.strip()[:5])})
        slot_conf = {g["value"]: g["confidence"] for g in stats.get("par_heure", [])}
        justified = any(slot_conf.get(s[:2] + ":00") in ("moyenne", "bonne") for s in clean)
        data["publish_slots"] = clean if clean and len(clean) == len(current_slots) and justified else None
    by_cat = {g["value"]: g["confidence"] for g in stats.get("par_categorie", [])}
    for w in data["category_weights"]:
        cap = 3.0 if by_cat.get(w["category"]) == "bonne" else 2.0
        w["weight"] = max(0.0, min(cap, float(w["weight"])))
    return StrategyProposal.model_validate(data)


def _is_hhmm(s: str) -> bool:
    try:
        datetime.strptime(s, "%H:%M")
        return True
    except ValueError:
        return False


def active_strategies(db: Any) -> dict[str, StrategyProposal]:
    """Stratégies validées, par chaîne (slug). Seules celles-ci guident les agents."""
    rows = db.fetch_all(
        """select c.slug, s.proposal from strategies s join channels c on c.id = s.channel_id
           where s.status = 'active' and s.proposal is not null"""
    )
    return {r["slug"]: StrategyProposal.model_validate(r["proposal"]) for r in rows}


def guidance_text(strategies: dict[str, StrategyProposal], *, for_seo: bool = False) -> str:
    """Résumé lisible des stratégies actives, à insérer dans un prompt d'agent."""
    if not strategies:
        return "Aucune stratégie validée pour l'instant : pas de consigne supplémentaire."
    lines = []
    for slug, s in strategies.items():
        lines.append(f"Chaîne {slug} — {s.summary}")
        if for_seo:
            lines += [f"  · modèle de titre qui marche : {t}" for t in s.title_patterns]
        else:
            lines += [f"  · poids catégorie {w.category} = {w.weight:g} ({w.reason})" for w in s.category_weights]
            lines += [f"  · accroche : {h}" for h in s.hook_guidelines]
            if s.target_duration_s:
                lines.append(f"  · durée cible : {s.target_duration_s} s")
            lines += [f"  · expérience à mener : {e}" for e in s.experiments]
        lines += [f"  · à éviter : {a}" for a in s.avoid]
    return "\n".join(lines)
