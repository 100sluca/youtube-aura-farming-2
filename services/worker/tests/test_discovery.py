"""Recherche → Découverte (docs/63 §9) : catégories, estimation du revenu, durées, rotation des sujets de départ."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from worker.discovery import RPM, SEEDS, SHORTS_RPM, category_of, estimate, iso_duration_s, months_since, next_seeds


def test_category_of_maps_loose_names() -> None:
    assert category_of("mystere") == "mystere_crime"
    assert category_of("histoire") == "histoire"
    assert category_of("Argent") == "argent_business"
    assert category_of("rien") == "divertissement"
    assert category_of(None) == "divertissement"


def test_estimate_uses_language_and_format() -> None:
    monthly, rpm, revenue = estimate(1_200_000, 4.0, "histoire", "fr", "long")
    assert monthly == 300_000 and rpm == RPM["histoire"][0] and revenue == round(300 * RPM["histoire"][0], 2)
    _, rpm_en, _ = estimate(1_200_000, 4.0, "histoire", "en", "long")
    assert rpm_en == RPM["histoire"][1]
    _, rpm_short, _ = estimate(1_200_000, 4.0, "histoire", "fr", "short")
    assert rpm_short == SHORTS_RPM[0]


def test_iso_duration_and_age() -> None:
    assert iso_duration_s("PT1H2M3S") == 3723
    assert iso_duration_s("PT45S") == 45
    now = datetime(2026, 10, 4, tzinfo=UTC)
    assert round(months_since("2026-07-04T00:00:00Z", now), 1) == 3.0
    assert months_since(None, now) == 24.0


class FakeDb:
    def __init__(self, runs: dict[str, datetime]) -> None:
        self.runs = runs

    def fetch_all(self, sql: str, params: object = None) -> list[dict]:
        return [{"seed": k, "run_at": v} for k, v in self.runs.items()]


def test_next_seeds_rotate_never_used_first() -> None:
    now = datetime(2026, 10, 4, tzinfo=UTC)
    first, second = SEEDS[0][0], SEEDS[1][0]
    db = FakeDb({first: now - timedelta(days=1), second: now - timedelta(days=30)})
    chosen = [s[0] for s in next_seeds(db, len(SEEDS), now)]
    assert first not in chosen  # passé hier : au repos
    assert chosen[-1] == second  # le plus ancien des déjà passés vient après tous les jamais passés
