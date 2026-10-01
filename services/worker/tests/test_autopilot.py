"""Pilote automatique (docs/46) : storyboard sans revue humaine, 4 essais par image au plus, et pas du pilote."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from test_storyboard_formats import FakeDb, FakeImage, FakeVision, _run

from worker import autopilot
from worker.keyframe_qc import continuity_requirements
from worker.models import ScriptV1


def _story(n: int = 4) -> ScriptV1:
    return ScriptV1.model_validate(
        {
            "scenes": [
                {"index": i, "duration_s": 4, "visual_prompt": f"plan {i}", "narration": {"fr": f"phrase {i}"}} for i in range(n)
            ],
            "metadata": {"fr": {"title": "t", "description": "d"}},
        }
    )


class AutopilotDb(FakeDb):
    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        row = super().fetch_one(sql, params)
        if row is not None and "p.autopilot" in sql:
            return {**row, "autopilot": True}
        if "coalesce(s.recipe" in sql:
            return {"recipe": "story"}
        return row


def _autopilot_run(tmp_path: Path, monkeypatch: Any, vision: FakeVision | None):
    import test_storyboard_formats as t

    monkeypatch.setattr(t, "FakeDb", AutopilotDb)
    return _run(tmp_path, monkeypatch, _story(4), vision)


def test_autopilot_story_is_checked_for_continuity_and_never_waits_for_luca(tmp_path, monkeypatch):
    vision = FakeVision(refuse={1})
    db, out = _autopilot_run(tmp_path, monkeypatch, vision)
    assert FakeImage.calls == ["gen:00", "gen:01", "gen:01", "gen:02", "gen:03"]  # une image par plan, la refusée refaite
    assert not out["review"] and out["clips"] == 4 and db.status is None and not db.alerts
    assert (0, 1) in vision.seen and (1, 2) in vision.seen  # le plan 1 est jugé avec l'image retenue du plan 0


def test_autopilot_gives_up_after_4_tries_and_renders_anyway(tmp_path, monkeypatch):
    db, out = _autopilot_run(tmp_path, monkeypatch, FakeVision(always={2}))
    assert FakeImage.calls.count("gen:02") == 4  # 4 essais au plus, pas de boucle sans fin
    assert not out["review"] and out["qc"]["refused"] == {2: ["scène 2 : bâtiment coupé par le bord"]}
    assert [a["selected"] for a in db.assets if a["scene_index"] == 2] == [False, False, False, True]


def test_autopilot_renders_even_without_a_vision_model(tmp_path, monkeypatch):
    db, out = _autopilot_run(tmp_path, monkeypatch, None)
    assert not out["review"] and FakeImage.calls == ["gen:00", "gen:01", "gen:02", "gen:03"]


def test_continuity_requirements_compare_with_the_previous_shot():
    s = _story(4)
    assert not any("image 2" in r for r in continuity_requirements(s, 0, None))
    assert any("NORMAL" in r for r in continuity_requirements(s, 1, 0))


class TickDb:
    """Base du pas du pilote : réglage, productions du pilote, meilleure idée, tâches d'idées."""

    def __init__(self, value: dict[str, Any], prods: list[dict[str, Any]], concept: dict[str, Any] | None) -> None:
        self.value, self.prods, self.concept = value, prods, concept
        self.enqueued: list[tuple[str, dict]] = []
        self.alerts: list[str] = []
        self.marked: list[Any] = []

    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        if "from app_settings" in sql:
            return {"value": self.value}
        if "from series" in sql:
            return {"id": uuid.uuid4(), "slug": "karma_fruits", "name": "Le Karma des Fruits"}
        if "from concepts" in sql:
            return self.concept
        if "count(*)" in sql:
            return {"n": 0}
        return None

    def fetch_all(self, sql: str, params: Any = None) -> list[dict]:
        return self.prods

    def execute(self, sql: str, params: Any = None) -> int:
        if "insert into app_settings" in sql:
            self.value = params[1].obj
        if "set autopilot = true" in sql:
            self.marked.append(params[0])
        return 1

    def enqueue(self, type_: str, **kw: Any) -> uuid.UUID:
        self.enqueued.append((type_, kw.get("payload") or {}))
        return uuid.uuid4()

    def alert(self, severity: str, title: str, body: str | None = None, **refs: Any) -> uuid.UUID:
        self.alerts.append(title)
        return uuid.uuid4()


ON = {"enabled": True, "series": "karma_fruits", "target": 2, "started_at": "2026-09-30T10:00:00+00:00"}


def _series(monkeypatch: Any) -> None:
    from worker.series import Series

    s = Series(
        id=uuid.uuid4(),
        slug="karma_fruits",
        name="Le Karma des Fruits",
        source="llm",
        source_config={},
        brief="",
        categories=[],
        style_preset=None,
        format="A_voiceover",
        target_duration_s=60,
        subtitle_profile=None,
        music_moods=[],
        video_provider=None,
        weight=1.0,
        is_active=True,
        channel_id=None,
    )
    monkeypatch.setattr(autopilot, "get_series", lambda db, slug: s)


def test_tick_asks_for_ideas_then_produces_the_best_one(monkeypatch):
    _series(monkeypatch)
    db = TickDb(dict(ON), [], None)
    assert autopilot.tick(db) == "idées demandées"
    assert db.enqueued[0][0] == "ideate" and db.enqueued[0][1]["autopilot"] is True
    pid = uuid.uuid4()
    monkeypatch.setattr(autopilot, "create_production", lambda db, cid, **k: (pid, True))
    db.concept = {"id": uuid.uuid4(), "title": "La poire avare", "score": 9}
    assert autopilot.tick(db) == "production lancée" and db.marked == [pid]


def test_tick_waits_for_the_video_in_progress_and_stops_when_done(monkeypatch):
    _series(monkeypatch)
    db = TickDb(dict(ON), [{"id": 1, "status": "generating", "busy": True}], {"id": 2, "title": "x", "score": 1})
    assert autopilot.tick(db) == "en route"
    db.prods = [{"id": 1, "status": "ready", "busy": False}, {"id": 2, "status": "ready", "busy": False}]
    assert autopilot.tick(db) == "terminé" and db.value["enabled"] is False and db.alerts
    assert autopilot.tick(db) == "coupé"


def test_tick_stops_after_too_many_failures(monkeypatch):
    _series(monkeypatch)
    prods = [{"id": i, "status": "failed", "busy": False} for i in range(3)]
    db = TickDb(dict(ON), prods, {"id": 9, "title": "x", "score": 1})
    assert autopilot.tick(db) == "trop d'échecs" and db.value["enabled"] is False


def test_a_slow_acted_narration_is_sped_up_within_limits():
    from worker.steps.tts import BRISK_MAX, brisk_factor

    assert brisk_factor(75, 71) == 1.0  # dans les 110 % : rien
    assert abs(brisk_factor(85, 71) - 85 / 71) < 1e-9
    assert brisk_factor(122, 71) == BRISK_MAX  # jamais plus vite que ×1,35


def test_tempo_shortens_the_voice():
    import shutil

    import numpy as np
    import pytest

    from worker.steps.tts import tempo

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg absent")
    x = np.sin(np.linspace(0, 2000, 24000)).astype(np.float32)
    y = tempo(x, 24000, 1.25)
    assert abs(len(y) - 24000 / 1.25) < 600
