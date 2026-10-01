"""Calculs sur les relevés YouTube (docs/25-dashboard-statistiques.md) : fonctions pures, testées sans base.

- `views_at` : vues d'une vidéo à un instant donné (24 h, 7 jours après sa mise en ligne), d'après les relevés horaires
  des compteurs publics ;
- `retention_summary` : ce qu'on retient de la courbe de rétention d'un Short, la part de l'audience encore là à 3 s
  (l'accroche a-t-elle retenu ?) et à la dernière seconde ;
- `retention_by_scene` : la courbe posée sur les phrases dites (timeline de la voix) : combien partent pendant chaque
  phrase, pour que l'analyste dise POURQUOI on décroche à tel moment (docs/49).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

HOOK_S = 3.0  # l'accroche d'un Short : part de l'audience encore là à 3 s
HOOK_RATIO_FALLBACK = 0.15  # durée inconnue : 3 s d'un Short de 20 s


def views_at(
    snapshots: Sequence[tuple[datetime, int]],
    published_at: datetime,
    at: datetime,
    max_gap: timedelta,
) -> int | None:
    """Vues à l'instant `at` d'après les relevés (instant, vues) : interpolation linéaire entre les deux relevés qui
    l'encadrent, s'ils sont à moins de `max_gap` l'un de l'autre. La mise en ligne compte comme un relevé à 0 vue.
    None quand les relevés ne permettent pas de le dire (worker arrêté à ce moment-là, instant pas encore atteint)."""
    points = sorted([(published_at, 0), *((t, int(v)) for t, v in snapshots if t >= published_at)], key=lambda p: p[0])
    before: tuple[datetime, int] | None = None
    after: tuple[datetime, int] | None = None
    for t, v in points:
        if t <= at:
            before = (t, v)
        else:
            after = (t, v)
            break
    if before is None:
        return None
    if before[0] == at:
        return before[1]
    if after is None or after[0] - before[0] > max_gap:
        return None
    frac = (at - before[0]) / (after[0] - before[0])
    return round(before[1] + (after[1] - before[1]) * frac)


def retention_at(curve: Sequence[Mapping[str, Any]], ratio: float) -> float | None:
    """Audience (en %, peut dépasser 100 avec les revisionnages) à l'avancement `ratio` (0 → 1) de la vidéo."""
    pts = sorted((float(p["t"]), float(p["w"])) for p in curve if p.get("t") is not None and p.get("w") is not None)
    if not pts:
        return None
    if ratio <= pts[0][0]:
        return round(pts[0][1] * 100, 2)
    for (t0, w0), (t1, w1) in zip(pts, pts[1:], strict=False):
        if t0 <= ratio <= t1:
            w = w0 if t1 == t0 else w0 + (w1 - w0) * (ratio - t0) / (t1 - t0)
            return round(w * 100, 2)
    return round(pts[-1][1] * 100, 2)


def retention_summary(curve: Sequence[Mapping[str, Any]], duration_s: float | None) -> tuple[float | None, float | None]:
    """(audience encore là à 3 s, audience à la dernière seconde), en %."""
    if not curve:
        return None, None
    hook_ratio = min(1.0, HOOK_S / duration_s) if duration_s and duration_s > 0 else HOOK_RATIO_FALLBACK
    return retention_at(curve, hook_ratio), retention_at(curve, 1.0)


def retention_by_scene(
    curve: Sequence[Mapping[str, Any]], duration_s: float | None, scenes: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Audience à l'entrée et à la sortie de chaque scène de la timeline de la voix (`scenes` : start, duration, words),
    en % : [{"start", "end", "text", "before", "after", "lost"}]. Vide sans courbe, sans durée ou sans timeline."""
    if not curve or not duration_s or duration_s <= 0 or not scenes:
        return []
    out = []
    for sc in scenes:
        start = float(sc.get("start") or 0)
        end = min(duration_s, start + float(sc.get("duration") or 0))
        if end <= start or start >= duration_s:
            continue
        before, after = retention_at(curve, start / duration_s), retention_at(curve, end / duration_s)
        if before is None or after is None:
            continue
        text = " ".join(str(w.get("text") or "") for w in sc.get("words") or []).strip()
        out.append(
            {
                "start": round(start, 1),
                "end": round(end, 1),
                "text": text,
                "before": before,
                "after": after,
                "lost": round(before - after, 1),
            }
        )
    return out


def retention_drops(by_scene: Sequence[Mapping[str, Any]], n: int = 3) -> list[Mapping[str, Any]]:
    """Les `n` scènes où l'audience baisse le plus vite (points perdus par seconde), hors scènes sans perte, dans
    l'ordre de la vidéo."""
    lossy = [s for s in by_scene if s["lost"] > 0]
    worst = sorted(lossy, key=lambda s: s["lost"] / max(0.5, s["end"] - s["start"]), reverse=True)[:n]
    return sorted(worst, key=lambda s: s["start"])
