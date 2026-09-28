"""Gestionnaire de tâches (docs/16 §4) : arrêt d'un job depuis le dashboard, import de l'historique d'une chaîne."""

import threading
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from worker import cancel, main
from worker.models import Job
from worker.providers.video import ComfyClient
from worker.steps.import_channel import imported_video, parse_iso_duration


class FakeDb:
    """Juste ce que run_job utilise : statut du job, battement, fin, échec, journal."""

    def __init__(self, status="running"):
        self.status = status
        self.completed = False
        self.failed: str | None = None
        self.logs: list[str] = []

    def job_status(self, job_id):
        return self.status

    def heartbeat(self, job_id, progress=None, label=None):
        return self.status == "running"

    def complete(self, job_id, result=None):
        self.completed = self.status == "running"
        return self.completed

    def fail(self, job_id, error):
        self.failed = error

    def log(self, job_id, level, message, data=None):
        self.logs.append(message)


def make_job(type_="generate_clip"):
    return Job(id=uuid4(), type=type_, status="running", priority=100, created_at=datetime.now(UTC))


def run_with_step(monkeypatch, db, step_run):
    step = SimpleNamespace(run=step_run, lane="gpu")
    monkeypatch.setitem(main.REGISTRY, "generate_clip", step)
    main.run_job(make_job(), db, SimpleNamespace())


def test_stopped_job_is_not_counted_as_failure(monkeypatch):
    db = FakeDb(status="cancelled")

    def step(ctx):
        raise RuntimeError("ComfyUI : exécution en erreur : interrupted")

    run_with_step(monkeypatch, db, step)
    assert db.failed is None and "Arrêtée depuis le dashboard" in db.logs


def test_real_failure_still_fails(monkeypatch):
    db = FakeDb()

    def step(ctx):
        raise RuntimeError("VRAM saturée")

    run_with_step(monkeypatch, db, step)
    assert db.failed and "VRAM saturée" in db.failed


def test_job_stopped_during_llm_call_stays_cancelled(monkeypatch):
    db = FakeDb()

    def step(ctx):
        db.status = "cancelled"  # arrêt pendant l'appel : le step va quand même au bout
        return {"ok": True}

    run_with_step(monkeypatch, db, step)
    assert not db.completed and db.failed is None


def test_progress_raises_once_stopped():
    flag = threading.Event()
    cancel.bind(flag)
    try:
        cancel.check()  # rien tant que le drapeau est baissé
        flag.set()
        with pytest.raises(cancel.JobCancelled):
            cancel.check()
    finally:
        cancel.bind(None)
    cancel.check()  # thread détaché : plus d'arrêt


def test_comfy_wait_cancels_the_prompt(monkeypatch):
    posts: list[str] = []

    class Resp:
        status_code = 200

        def json(self):
            return {}

    monkeypatch.setattr("worker.providers.video.httpx.post", lambda url, **kw: posts.append(url) or Resp())
    monkeypatch.setattr("worker.providers.video.httpx.get", lambda url, **kw: Resp())
    flag = threading.Event()
    flag.set()
    cancel.bind(flag)
    try:
        with pytest.raises(cancel.JobCancelled):
            ComfyClient("http://comfy").wait("abc", lambda pct: None)
    finally:
        cancel.bind(None)
    assert posts == ["http://comfy/api/jobs/abc/cancel"]


def test_parse_iso_duration():
    assert parse_iso_duration("PT59S") == 59
    assert parse_iso_duration("PT1M5S") == 65
    assert parse_iso_duration("PT1H2M3S") == 3723
    assert parse_iso_duration("P1DT1S") == 86401
    assert parse_iso_duration("P0D") == 0
    assert parse_iso_duration(None) is None
    assert parse_iso_duration("PT") is None and parse_iso_duration("abc") is None


def test_imported_video_mapping():
    item = {
        "id": "yt123",
        "snippet": {
            "title": "Ma cabane",
            "description": "desc",
            "tags": ["a", "b"],
            "publishedAt": "2026-05-01T10:00:00Z",
            "thumbnails": {"default": {"url": "d.jpg"}, "high": {"url": "h.jpg"}},
        },
        "contentDetails": {"duration": "PT42S"},
        "statistics": {"viewCount": "1200", "likeCount": "30"},
        "status": {"privacyStatus": "public"},
    }
    v = imported_video(item)
    assert v["status"] == "published" and v["duration_s"] == 42 and v["thumbnail_url"] == "h.jpg"
    assert v["views"] == 1200 and v["likes"] == 30 and v["comments"] == 0
    assert v["published_at"] == "2026-05-01T10:00:00Z"

    scheduled = imported_video({**item, "status": {"privacyStatus": "private", "publishAt": "2026-10-01T09:00:00Z"}})
    assert scheduled["status"] == "scheduled" and scheduled["published_at"] is None
    assert imported_video({**item, "status": {"privacyStatus": "private"}})["status"] == "unpublished"
