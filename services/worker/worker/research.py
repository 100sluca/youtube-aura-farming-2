"""Page Recherche (docs/60-recherche-niches.md) : calculs sur les Shorts des autres, fonctions pures testées sans base.

Ce que font les outils payants (Virlo, Pentos, Exolyt, Nexlev…), refait avec des données gratuites :

- `views_per_day` : vitesse d'une vidéo (vues ÷ jours depuis sa mise en ligne) ;
- `outlier` : combien de fois une vidéo dépasse ce que fait d'habitude sa chaîne (vues ÷ médiane des derniers Shorts de
  la chaîne ; à défaut vues ÷ abonnés) : la mesure des « outliers » de 1of10, Nexlev ou vidIQ. Une vidéo à × 10 sur une
  petite chaîne, c'est le sujet qui a porté, pas l'audience de la chaîne : c'est elle qu'on veut reproduire ;
- `window_stats` : une niche vue par une recherche (les 50 Shorts les plus vus publiés dans les 7 derniers jours, ou
  dans un mois donné) : demande, nombre de tubes, part des tubes faits par de petites ou de nouvelles chaînes (la
  porte est-elle encore ouverte ?), concentration sur quelques chaînes ;
- `niche_phase` : où en est la niche (émergente, en hausse, installée, en baisse, à vide), d'après sa courbe mois par
  mois (chaque mois jugé 3 semaines après sa fin), ou d'après les relevés de chaque semaine tant que la courbe est
  trop courte ;
- `niche_score` et `remake_score` : le classement des niches à essayer et des vidéos à reproduire.

Les chiffres sont calculés ici, jamais par le LLM, qui ne fait que classer (format, recette) et expliquer.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

SHORT_MAX_S = 180.0  # un Short dure 3 min au plus depuis octobre 2024
SUBS_FLOOR = 1_000  # vues ÷ abonnés : une chaîne de 12 abonnés ne fait pas un × 5 000
SMALL_CHANNEL = 10_000  # « petite chaîne » : moins de 10 k abonnés
NEW_CHANNEL_DAYS = 180  # « nouvelle chaîne » : créée il y a moins de 6 mois
# Un tube : 100 k vues en une semaine ; 1 M pour un mois de la courbe (vues tassées).
HIT_VIEWS = {7: 100_000}
HIT_MONTH = 1_000_000  # un tube, pour un mois de la courbe
MATURE_DAYS = 21  # un mois n'est jugé que 3 semaines après sa fin (les vues d'un Short se tassent en 2 à 3 semaines)
CURVE_MONTHS = 12  # longueur de la courbe d'une niche
EMPTY_VIEWS = 100_000  # sous cette médiane, sans aucun tube, la niche est « à vide »
RISE, FALL = 1.3, 0.7  # hausse et baisse : rapport des deux derniers mois (ou semaines) aux précédents
# Un mois mesuré sur moins de 10 Shorts ne dit rien (le 02/10, « faits insolites » d'août : 3 Shorts d'une seule chaîne,
# 9,5 M de vues médianes) : il n'entre pas dans la courbe et se remesure au relevé suivant.
MIN_MONTH_SHORTS = 10
MARKET_MIN_NICHES = 5  # l'élan du marché (toutes les niches) se calcule sur 5 niches au moins
MIN_CHANNEL_SHORTS = 5  # médiane d'une chaîne : sur 5 Shorts jugeables au moins
CHANNEL_MIN_AGE_D = 2.0  # un Short de moins de 2 jours n'entre pas dans la médiane de sa chaîne

Phase = Literal["émergente", "en hausse", "installée", "en baisse", "à vide", "inconnue"]
PHASE_MOMENTUM: dict[str, float] = {
    "émergente": 1.0,
    "en hausse": 0.9,
    "installée": 0.6,
    "inconnue": 0.5,
    "en baisse": 0.2,
    "à vide": 0.0,
}


@dataclass(frozen=True)
class ShortVideo:
    """Ce qu'on sait d'un Short d'une autre chaîne au moment du relevé."""

    external_id: str
    title: str
    channel_id: str
    published_at: datetime
    views: int
    likes: int = 0
    comments: int = 0
    duration_s: float | None = None
    channel_subs: int | None = None
    channel_created_at: datetime | None = None
    channel_median: float | None = None  # médiane des vues des derniers Shorts de la chaîne


def age_days(published_at: datetime, now: datetime) -> float:
    """Âge en jours, une heure au moins (une vidéo de 5 min n'a pas une vitesse infinie)."""
    return max((now - published_at).total_seconds() / 86_400, 1 / 24)


def views_per_day(v: ShortVideo, now: datetime) -> float:
    return v.views / age_days(v.published_at, now)


def engagement_pct(v: ShortVideo) -> float | None:
    """(likes + commentaires) ÷ vues, en %."""
    return round(100 * (v.likes + v.comments) / v.views, 2) if v.views > 0 else None


def outlier(v: ShortVideo) -> tuple[float | None, str | None]:
    """(× combien la vidéo dépasse sa chaîne, base du calcul) : vues ÷ médiane des Shorts de la chaîne quand on la
    connaît, sinon vues ÷ abonnés (1 000 au moins). (None, None) sans aucun des deux."""
    if v.channel_median and v.channel_median > 0:
        return round(v.views / v.channel_median, 2), "chaîne"
    if v.channel_subs is not None:
        return round(v.views / max(v.channel_subs, SUBS_FLOOR), 2), "abonnés"
    return None, None


def channel_median(shorts: Sequence[tuple[datetime, int]], now: datetime) -> float | None:
    """Médiane des vues des Shorts (mise en ligne, vues) d'une chaîne, ceux de moins de 2 jours exclus ; None sous 5."""
    views = [n for t, n in shorts if age_days(t, now) >= CHANNEL_MIN_AGE_D]
    return float(statistics.median(views)) if len(views) >= MIN_CHANNEL_SHORTS else None


def is_short(duration_s: float | None, embed_w: int | None = None, embed_h: int | None = None) -> bool:
    """Un Short : 3 min au plus et, quand l'API donne la taille du lecteur, plus haut que large (ou carré)."""
    if duration_s is None or duration_s <= 0 or duration_s > SHORT_MAX_S:
        return False
    if embed_w and embed_h:
        return embed_h >= embed_w
    return True


def parse_iso_duration(s: str | None) -> float | None:
    """« PT1M5S » → 65.0 (durée des vidéos dans l'API YouTube)."""
    if not s or not s.startswith("P"):
        return None
    total, num = 0.0, ""
    in_time = False
    units = {"D": 86_400, "H": 3_600, "M": 60, "S": 1}
    for ch in s[1:]:
        if ch == "T":
            in_time = True
        elif ch.isdigit() or ch == ".":
            num += ch
        elif ch in units and num:
            if ch == "M" and not in_time:  # mois : jamais pour une vidéo
                return None
            total += float(num) * units[ch]
            num = ""
    return total


# ---- Une niche vue par une recherche ---------------------------------------------------------------------------------


@dataclass
class WindowStats:
    """Les Shorts d'une recherche : 7 derniers jours (chaque jour) ou un mois de mise en ligne (courbe de la niche)."""

    window_days: int  # 7, ou 30 pour un mois de la courbe
    n: int
    channels: int
    median_views: float | None
    median_vpd: float | None  # vues par jour
    top_views: int
    hits: int  # tubes : 100 k vues en 7 jours, 1 M pour un mois
    open_hits: int  # tubes faits par une petite ou une nouvelle chaîne
    concentration: float | None  # part des tubes des 3 chaînes qui en ont le plus
    median_engagement: float | None

    @property
    def open_share(self) -> float | None:
        return round(self.open_hits / self.hits, 2) if self.hits else None

    def to_json(self) -> dict[str, Any]:
        return asdict(self) | {"open_share": self.open_share}

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> WindowStats:
        keys = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in keys})


def _is_open(v: ShortVideo, now: datetime) -> bool:
    small = v.channel_subs is not None and v.channel_subs < SMALL_CHANNEL
    new = v.channel_created_at is not None and (now - v.channel_created_at) < timedelta(days=NEW_CHANNEL_DAYS)
    return small or new


def window_stats(videos: Sequence[ShortVideo], window_days: int, now: datetime) -> WindowStats:
    """Résumé d'une recherche (les Shorts les plus vus de la fenêtre)."""
    hit_at = HIT_VIEWS.get(window_days) or HIT_MONTH
    hits = [v for v in videos if v.views >= hit_at]
    by_channel = Counter(v.channel_id for v in hits)
    top3 = sum(n for _, n in by_channel.most_common(3))
    engagements = [e for v in videos if (e := engagement_pct(v)) is not None]
    return WindowStats(
        window_days=window_days,
        n=len(videos),
        channels=len({v.channel_id for v in videos}),
        median_views=float(statistics.median(v.views for v in videos)) if videos else None,
        median_vpd=round(statistics.median(views_per_day(v, now) for v in videos), 1) if videos else None,
        top_views=max((v.views for v in videos), default=0),
        hits=len(hits),
        open_hits=sum(1 for v in hits if _is_open(v, now)),
        concentration=round(top3 / len(hits), 2) if hits else None,
        median_engagement=round(statistics.median(engagements), 2) if engagements else None,
    )


# ---- Courbe d'une niche, mois par mois ---------------------------------------------------------------------------------
#
# La recherche YouTube « les plus vus de l'année » favorise les vieilles vidéos, qui ont eu le temps d'accumuler des vues.
# La courbe compare donc des mois entre eux : pour chaque mois de mise en ligne, les Shorts les plus vus publiés ce
# mois-là. Un mois n'est jugé que 3 semaines après sa fin, quand les vues de ses Shorts se sont tassées ; ensuite il ne
# change plus : il se mesure une fois, ce qui coûte une recherche par mois et par niche.


def month_key(d: datetime) -> str:
    return d.astimezone(UTC).strftime("%Y-%m")


def month_bounds(key: str) -> tuple[datetime, datetime]:
    """(début, fin exclue) du mois « 2026-09 », en UTC."""
    y, m = (int(x) for x in key.split("-"))
    start = datetime(y, m, 1, tzinfo=UTC)
    end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=UTC)
    return start, end


def last_months(now: datetime, n: int) -> list[str]:
    """Les `n` derniers mois entiers, du plus récent au plus ancien (le mois en cours exclu)."""
    y, m = now.year, now.month
    out = []
    for _ in range(n):
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        out.append(f"{y}-{m:02d}")
    return out


def is_mature(key: str, at: datetime) -> bool:
    """Mois jugeable à l'instant `at` : fini depuis 3 semaines au moins."""
    return month_bounds(key)[1] + timedelta(days=MATURE_DAYS) <= at


def _month_index(key: str) -> int:
    y, m = key.split("-")
    return int(y) * 12 + int(m) - 1


def month_ok(w: WindowStats) -> bool:
    """Un mois mesuré sur assez de Shorts pour entrer dans la courbe."""
    return w.n >= MIN_MONTH_SHORTS


def curve_ratio(months: Mapping[str, WindowStats]) -> float | None:
    """Vues médianes des deux derniers mois jugés ÷ celles des trois d'avant (4 mois au moins), None sinon."""
    keys = sorted(months)
    if len(keys) < 4:
        return None
    recent = statistics.mean(months[k].median_views or 0.0 for k in keys[-2:])
    before = statistics.mean(months[k].median_views or 0.0 for k in keys[-5:-2])
    return recent / before if before > 0 else None


def market_ratio(curves: Sequence[Mapping[str, WindowStats]]) -> float | None:
    """L'élan de tout le marché : la médiane des `curve_ratio` des niches (5 au moins). En juillet 2026, presque toutes
    les niches suivies ont bondi d'un coup (× 1,9 en médiane) : une niche n'est « en hausse » que si elle monte plus
    vite que les autres, sinon toutes le seraient."""
    ratios = [r for c in curves if (r := curve_ratio(c)) is not None]
    return round(statistics.median(ratios), 2) if len(ratios) >= MARKET_MIN_NICHES else None


def niche_phase(
    months: Mapping[str, WindowStats], weekly: Sequence[WindowStats], now: datetime, market: float | None = None
) -> tuple[Phase, str]:
    """(phase, raison en une phrase).

    `months` : la courbe {« 2026-08 » : relevé du mois} (mois jugeables seulement) ; `weekly` : les relevés « 7 derniers
    jours », un par semaine, du plus ancien au plus récent. La courbe décide dès 4 mois ; avant, les semaines.
    Niveau d'un mois : la médiane des vues de ses Shorts les plus vus (robuste aux tubes isolés). `market` : l'élan de
    toutes les niches (`market_ratio`) ; la hausse et la baisse se jugent par rapport à lui.
    """
    keys = sorted(months)
    if len(keys) >= 4:
        cur = _month_index(month_key(now))
        level = {k: months[k].median_views or 0.0 for k in keys}
        with_hits = [k for k in keys if months[k].hits > 0]
        if not with_hits and max(level.values()) < EMPTY_VIEWS:
            return "à vide", f"aucun Short à 1 M de vues en {len(keys)} mois"
        if with_hits and cur - _month_index(with_hits[0]) <= 4 and len(with_hits) < len(keys):
            return "émergente", f"premier tube en {with_hits[0]}, rien d'aussi fort avant"
        recent = statistics.mean(level[k] for k in keys[-2:])
        peak_key = max(keys, key=lambda k: level[k])
        raw = curve_ratio(months) or 9.9
        ratio = raw / market if market else raw
        vs = f" (toutes les niches : × {market:.1f})" if market else ""
        if ratio >= RISE:
            return "en hausse", f"vues des meilleurs Shorts × {raw:.1f} sur les deux derniers mois jugés{vs}"
        peak_age = cur - _month_index(peak_key)
        if ratio <= FALL or (recent <= 0.5 * level[peak_key] and peak_age >= 4):
            return "en baisse", f"× {raw:.1f} en deux mois{vs} ; pic en {peak_key} ({_short(level[peak_key])} vues médianes)"
        return "installée", f"{'suit le marché' if market else 'stable'} : × {raw:.1f} sur les deux derniers mois{vs}"
    if len(weekly) >= 4:

        def lvl(ws: Sequence[WindowStats]) -> float:
            return statistics.mean(w.median_vpd or 0.0 for w in ws)

        before, after = lvl(weekly[-4:-2]), lvl(weekly[-2:])
        if before <= 0 and after <= 0:
            return "à vide", "aucune vue ces 4 dernières semaines"
        ratio = after / before if before > 0 else 9.9
        if ratio >= RISE:
            return "en hausse", f"vues par jour des nouveautés × {ratio:.1f} en deux semaines"
        if ratio <= FALL:
            return "en baisse", f"vues par jour des nouveautés × {ratio:.1f} en deux semaines"
        return "installée", "aussi forte que les deux semaines d'avant"
    return "inconnue", f"courbe trop courte ({len(keys)} mois, {len(weekly)} semaines)"


def _short(n: float) -> str:
    return f"{n / 1e6:.1f} M" if n >= 1e6 else f"{n / 1e3:.0f} k"


def niche_age_months(months: Mapping[str, WindowStats], now: datetime) -> int | None:
    """Mois écoulés depuis le premier mois de la courbe qui a eu un tube (borné par la longueur de la courbe)."""
    with_hits = sorted(k for k, w in months.items() if w.hits > 0)
    if not with_hits:
        return None
    return _month_index(month_key(now)) - _month_index(with_hits[0])


# ---- Classements -----------------------------------------------------------------------------------------------------

# Effort pour nous : 1 = une recette existante le fait seule ; 5 = hors de portée (vraie caméra, visage, jeu vidéo…)
EFFORT_FEASIBILITY = {1: 1.0, 2: 0.8, 3: 0.55, 4: 0.3, 5: 0.0}


def _demand(views: float | None) -> float:
    """10 k vues → 0, 10 M → 1 (échelle logarithmique)."""
    if not views or views <= 0:
        return 0.0
    return max(0.0, min(1.0, (math.log10(views) - 4) / 3))


def niche_score(month: WindowStats | None, phase: str, effort: float | None) -> dict[str, float]:
    """Note sur 100 d'une niche à essayer, avec ses quatre parts (0 → 1) pour l'afficher :
    demande (vues des Shorts du mois), élan (phase), porte ouverte (tubes faits par de petites ou nouvelles chaînes),
    faisabilité (effort moyen de ses vidéos pour nos recettes)."""
    demand = _demand(month.median_views if month else None)
    momentum = PHASE_MOMENTUM.get(phase, 0.5)
    open_ = month.open_share if month and month.open_share is not None else 0.3
    if effort is None:
        feas = 0.5
    else:
        lo, hi = math.floor(effort), math.ceil(effort)
        feas = EFFORT_FEASIBILITY.get(lo, 0.5) + (EFFORT_FEASIBILITY.get(hi, 0.5) - EFFORT_FEASIBILITY.get(lo, 0.5)) * (
            effort - lo
        )
    total = 100 * (0.35 * demand + 0.25 * momentum + 0.2 * open_ + 0.2 * feas)
    return {
        "score": round(total),
        "demand": round(demand, 2),
        "momentum": round(momentum, 2),
        "open": round(open_, 2),
        "feasibility": round(feas, 2),
    }


def remake_score(v: ShortVideo, now: datetime, effort: int | None) -> float:
    """Classement des vidéos à reproduire : surperformance (log), vitesse, fraîcheur, faisabilité. Sans unité."""
    ratio, _ = outlier(v)
    over = math.log10(max(ratio or 1.0, 1.0)) / 2  # × 100 → 1
    speed = _demand(views_per_day(v, now) * 7)  # vues d'une semaine à ce rythme
    fresh = max(0.0, 1 - age_days(v.published_at, now) / 120)
    feas = EFFORT_FEASIBILITY.get(effort, 0.5) if effort is not None else 0.5
    return round(100 * (0.35 * min(over, 1.0) + 0.25 * speed + 0.15 * fresh + 0.25 * feas), 1)


def mostly_latin(text: str) -> bool:
    """Titre écrit surtout en alphabet latin (anglais, français, espagnol…) : une vidéo en hindi ou en bengali se refait
    mal en français. Les émojis et les chiffres ne comptent pas."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    return sum(1 for c in letters if ord(c) < 0x250) / len(letters) >= 0.6


def as_utc(s: str | datetime | None) -> datetime | None:
    """Date de l'API (« 2026-09-28T17:04:11Z ») → datetime UTC."""
    if s is None or isinstance(s, datetime):
        return s
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)
