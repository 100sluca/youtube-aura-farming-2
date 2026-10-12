"""Page Recherche (docs/60-recherche-niches.md) : vitesse, surperformance, niches et leur cycle de vie."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from worker import research as r
from worker.research import ShortVideo, WindowStats

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def vid(i: int, views: int, days: float, *, ch: str | None = None, subs: int | None = 50_000, **kw) -> ShortVideo:
    return ShortVideo(
        external_id=f"v{i}",
        title=f"vidéo {i}",
        channel_id=ch or f"c{i}",
        published_at=NOW - timedelta(days=days),
        views=views,
        channel_subs=subs,
        **kw,
    )


def test_speed_and_outlier():
    v = vid(1, 2_000_000, 4, subs=20_000)
    assert r.views_per_day(v, NOW) == pytest.approx(500_000)
    assert r.outlier(v) == (100.0, "abonnés")
    assert r.outlier(vid(2, 30_000, 1, subs=12)) == (30.0, "abonnés")  # 1 000 abonnés au moins
    assert r.outlier(vid(3, 900_000, 3, channel_median=30_000)) == (30.0, "chaîne")  # la médiane de la chaîne d'abord
    assert r.outlier(vid(4, 10, 1, subs=None)) == (None, None)
    assert r.views_per_day(vid(5, 100, 0), NOW) == pytest.approx(2_400)  # une heure au moins


def test_channel_median_skips_fresh_shorts():
    shorts = [(NOW - timedelta(days=d), v) for d, v in ((10, 100), (9, 200), (8, 300), (7, 400), (6, 500), (0.5, 9_999))]
    assert r.channel_median(shorts, NOW) == 300
    assert r.channel_median(shorts[:4], NOW) is None  # moins de 5 Shorts jugeables


def test_is_short_and_durations():
    assert r.parse_iso_duration("PT1M5S") == 65
    assert r.parse_iso_duration("PT59S") == 59
    assert r.parse_iso_duration("PT1H") == 3_600
    assert r.parse_iso_duration("P0D") == 0
    assert r.parse_iso_duration(None) is None
    assert r.is_short(65)
    assert not r.is_short(181)
    assert not r.is_short(0)
    assert not r.is_short(30, embed_w=480, embed_h=270)  # paysage
    assert r.is_short(30, embed_w=270, embed_h=480)


def test_window_stats_hits_open_and_concentration():
    videos = [
        vid(1, 5_000_000, 3, ch="A", subs=2_000_000),
        vid(2, 4_000_000, 2, ch="A", subs=2_000_000),
        vid(3, 900_000, 5, ch="B", subs=3_000),  # petite chaîne
        vid(4, 200_000, 1, ch="C", subs=500_000, channel_created_at=NOW - timedelta(days=40)),  # nouvelle chaîne
        vid(5, 50_000, 6, ch="D", subs=80_000),
    ]
    w = r.window_stats(videos, 7, NOW)
    assert (w.n, w.channels, w.hits, w.open_hits) == (5, 4, 4, 2)
    assert w.open_share == 0.5
    assert w.concentration == 1.0  # A, B, C : les 4 tubes
    assert w.median_views == 900_000
    assert WindowStats.from_json(w.to_json()) == w


def test_months_of_the_curve():
    assert r.last_months(NOW, 3) == ["2026-09", "2026-08", "2026-07"]
    assert r.last_months(datetime(2026, 1, 15, tzinfo=UTC), 2) == ["2025-12", "2025-11"]
    assert r.month_bounds("2026-12") == (datetime(2026, 12, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC))
    assert r.is_mature("2026-08", NOW)  # fini le 31/08, plus de 3 semaines
    assert not r.is_mature("2026-09", NOW)  # fini il y a 2 jours : vues pas encore tassées
    assert r.month_key(NOW) == "2026-10"


def month(median: float, hits: int = 0) -> WindowStats:
    return WindowStats(30, 50, 30, median, median / 30, int(median * 5), hits, 0, None, None)


def curve(*levels: float, hits: int = 3, first: int = 9) -> dict[str, WindowStats]:
    """Mois consécutifs se terminant en août 2026 (dernier mois jugeable au 02/10)."""
    keys = [f"2026-{m:02d}" for m in range(8 - len(levels) + 1, 9)]
    return {k: month(v, hits) for k, v in zip(keys, levels, strict=True)}


def test_phase_from_the_monthly_curve():
    assert r.niche_phase({}, [], NOW)[0] == "inconnue"
    assert r.niche_phase(curve(300e3, 300e3, 600e3, 800e3), [], NOW)[0] == "en hausse"
    assert r.niche_phase(curve(900e3, 800e3, 700e3, 300e3, 250e3), [], NOW)[0] == "en baisse"
    assert r.niche_phase(curve(500e3, 450e3, 520e3, 480e3, 510e3), [], NOW)[0] == "installée"
    # pic lointain : retombée de moitié depuis, même sans chute brutale ces derniers mois
    old_peak = {"2026-01": month(2e6, 9), **curve(700e3, 650e3, 600e3, 620e3, 640e3)}
    assert r.niche_phase(old_peak, [], NOW)[0] == "en baisse"
    empty = {k: month(20e3, 0) for k in curve(1, 1, 1, 1)}
    assert r.niche_phase(empty, [], NOW)[0] == "à vide"
    young = {
        **{k: month(50e3, 0) for k in ("2026-04", "2026-05", "2026-06")},
        "2026-07": month(900e3, 4),
        "2026-08": month(1.2e6, 6),
    }
    assert r.niche_phase(young, [], NOW)[0] == "émergente"
    assert r.niche_age_months(young, NOW) == 3
    assert r.niche_age_months(empty, NOW) is None


def week(hits: int, vpd: float) -> WindowStats:
    return WindowStats(7, 50, 30, 1e5, vpd, 1_000_000, hits, 0, None, None)


def test_phase_from_weekly_snapshots_while_the_curve_is_short():
    rising = [week(2, 10_000), week(2, 10_000), week(5, 30_000), week(6, 30_000)]
    assert r.niche_phase(curve(500e3, 600e3), rising, NOW)[0] == "en hausse"
    falling = [week(8, 50_000), week(7, 40_000), week(2, 10_000), week(1, 8_000)]
    assert r.niche_phase({}, falling, NOW)[0] == "en baisse"
    assert r.niche_phase({}, [week(3, 20_000)] * 4, NOW)[0] == "installée"
    assert r.niche_phase({}, [week(0, 0)] * 4, NOW)[0] == "à vide"
    # la courbe l'emporte dès 4 mois
    assert r.niche_phase(curve(900e3, 800e3, 300e3, 250e3), rising, NOW)[0] == "en baisse"


def test_scores():
    month = WindowStats(30, 50, 40, 2_000_000, 50_000, 30_000_000, 20, 10, 0.3, 4.0)
    hot = r.niche_score(month, "en hausse", 1.0)
    cold = r.niche_score(month, "en baisse", 4.5)
    assert hot["score"] > cold["score"]
    assert hot["feasibility"] == 1.0 and cold["feasibility"] == pytest.approx(0.15)
    assert 0 <= cold["score"] <= hot["score"] <= 100
    easy = r.remake_score(vid(1, 3_000_000, 3, subs=5_000), NOW, 1)
    hard = r.remake_score(vid(1, 3_000_000, 3, subs=5_000), NOW, 5)
    stale = r.remake_score(vid(1, 3_000_000, 200, subs=5_000), NOW, 1)
    assert easy > hard and easy > stale


def test_a_month_measured_on_too_few_shorts_is_not_trusted():
    # le 02/10 : « faits insolites » d'août, 3 Shorts d'une seule chaîne, 9,5 M de vues médianes
    assert not r.month_ok(WindowStats(30, 3, 1, 9.5e6, 1e5, 16_000_000, 3, 0, 1.0, 3.1))
    assert r.month_ok(month(500e3))


def test_momentum_is_judged_against_the_whole_market():
    # juillet-août 2026 : presque toutes les niches bondissent d'un coup ; une niche qui suit le marché est « installée »
    market = r.market_ratio([curve(100e3, 100e3, 100e3, 200e3, 200e3)] * 4 + [curve(100e3, 100e3, 100e3, 700e3, 700e3)])
    assert market == pytest.approx(2.0)
    follows = curve(100e3, 100e3, 100e3, 200e3, 200e3)
    assert r.niche_phase(follows, [], NOW)[0] == "en hausse"  # seule, elle a l'air de monter
    phase, reason = r.niche_phase(follows, [], NOW, market)
    assert phase == "installée" and "toutes les niches" in reason
    assert r.niche_phase(curve(100e3, 100e3, 100e3, 700e3, 700e3), [], NOW, market)[0] == "en hausse"
    assert r.niche_phase(curve(500e3, 500e3, 500e3, 400e3, 400e3), [], NOW, market)[0] == "en baisse"
    assert r.market_ratio([follows] * 4) is None  # moins de 5 niches : pas de marché


def test_titles_in_a_latin_alphabet():
    assert r.mostly_latin("I Built a Secret Underground Luxury Cabin in the Wild 🌲🏡")
    assert r.mostly_latin("Construction d'un abri souterrain : 852 jours")
    assert not r.mostly_latin("अमीरी का घमंड हार गया गरीब भाई के प्यार से🩷")
    assert not r.mostly_latin("২০২৭ সালে রোজা, ও ঈদ কবে হবে জেনে নিন!#shortsfeed")
    assert r.mostly_latin("🔥🔥🔥")


def test_discovery_seeds_are_unique_and_outside_our_niches():
    from worker.discovery_shorts import SEEDS, seed_slug

    keys = [k for k, *_ in SEEDS]
    assert len(keys) == len(set(keys)) and all(len(seed_slug(k)) <= 40 for k in keys)
    assert all(lang in ("en", "fr") and region in ("US", "FR") and q.strip() for _, _, q, lang, region in SEEDS)
    assert {"minecraft", "montres"} <= set(keys)
