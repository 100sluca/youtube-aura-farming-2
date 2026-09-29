"""Statistiques du Dashboard et agent analyste (docs/25-dashboard-statistiques.md) : relevés, notes, garde-fous."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from worker import performance as perf
from worker.lessons import lessons_text
from worker.metrics import retention_at, retention_summary, views_at
from worker.performance import (
    Experiment,
    LessonProposal,
    Pattern,
    PerformanceReport,
    VideoDiagnosis,
    VideoFacts,
    build_message,
    clean_report,
    compute_performance,
    confidence_cap,
    description_head,
    facts_from_row,
    hashtags_of,
    rank,
    script_features,
)
from worker.scheduler import enqueue_sync

T0 = datetime(2026, 9, 26, 11, 0, tzinfo=UTC)


# ---- Relevés horaires --------------------------------------------------------------------------------------------


def test_views_at_interpolates_between_close_snapshots():
    snaps = [(T0 + timedelta(hours=h), v) for h, v in ((23, 900), (25, 1100))]
    assert views_at(snaps, T0, T0 + timedelta(hours=24), timedelta(hours=6)) == 1000
    assert views_at(snaps, T0, T0 + timedelta(hours=23), timedelta(hours=6)) == 900  # relevé exact


def test_views_at_refuses_a_gap_and_counts_publication_as_zero():
    far = [(T0 + timedelta(hours=10), 100), (T0 + timedelta(hours=40), 900)]
    assert views_at(far, T0, T0 + timedelta(hours=24), timedelta(hours=6)) is None  # worker arrêté entre-temps
    first = [(T0 + timedelta(hours=2), 200)]
    assert views_at(first, T0, T0 + timedelta(hours=1), timedelta(hours=6)) == 100  # depuis la mise en ligne (0 vue)
    assert views_at(first, T0, T0 + timedelta(hours=5), timedelta(hours=6)) is None  # pas encore de relevé après
    assert views_at([], T0, T0 - timedelta(hours=1), timedelta(hours=6)) is None  # avant la mise en ligne


def test_retention_hook_and_end():
    curve = [{"t": 0.01, "w": 1.1}, {"t": 0.1, "w": 0.9}, {"t": 0.2, "w": 0.7}, {"t": 1.0, "w": 0.3}]
    assert retention_at(curve, 0.15) == pytest.approx(80.0)
    hook, end = retention_summary(curve, 20.0)  # 3 s d'une vidéo de 20 s = 15 %
    assert hook == pytest.approx(80.0) and end == pytest.approx(30.0)
    assert retention_summary(curve, None)[0] == pytest.approx(80.0)  # durée inconnue : 15 %
    assert retention_summary([], 20.0) == (None, None)
    assert retention_at(curve, 0.0) == pytest.approx(110.0)  # revisionnages : au-delà de 100 %


# ---- Fiche d'une vidéo -------------------------------------------------------------------------------------------

SCRIPT = {
    "hook_title": {"fr": "Tu paierais combien pour cette villa ?", "en": "How much?"},
    "music_mood": "luxury",
    "scenes": [
        {
            "duration_s": 4.0,
            "visual_prompt": "Exterior view of a cave villa",
            "on_screen_text": {"fr": "Entrée · Santorin"},
            "narration": {},
        },
        {"duration_s": 1.2, "visual_prompt": "Passage", "on_screen_text": {}, "narration": {}},
        {
            "duration_s": 4.0,
            "visual_prompt": "Vaulted living room",
            "on_screen_text": {"fr": "Salon · 45 m²"},
            "narration": {"fr": ""},
        },
    ],
}


def test_script_features_and_description():
    f = script_features(SCRIPT, "fr")
    assert f["hook_title"] == "Tu paierais combien pour cette villa ?"
    assert f["on_screen"] == ["Entrée · Santorin", "Salon · 45 m²"] and f["narration"] == []
    assert f["shots"] == 3 and f["avg_shot_s"] == pytest.approx(3.1) and f["music"] == "luxury"
    assert f["first_shot"] == "Exterior view of a cave villa"
    assert script_features(None, "fr") == {}
    desc = "Tu paierais combien ?\n\nDécouvre la Villa Ocre.\n\n#santorin #luxe #Santorin\n\nLieu imaginaire : images IA."
    assert hashtags_of(desc) == ["#santorin", "#luxe"]
    assert description_head(desc) == "Tu paierais combien ? Découvre la Villa Ocre."


def _row(title: str, views: int, age_h: float, **kw: Any) -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "title": title,
        "origin": kw.pop("origin", "app"),
        "published_at": NOW - timedelta(hours=age_h),
        "views": views,
        "likes": views // 50,
        "comments": 0,
        "lang": "fr",
        "recipe": kw.pop("recipe", "tour"),
        "series_name": "Visites de luxe",
        "duration_s": 36.2,
        "description": "Une villa.\n#luxe",
        "script": SCRIPT,
        "video_provider": "gemini_web",
        **kw,
    }


NOW = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)


def _videos() -> list[VideoFacts]:
    rows = [
        _row("Refuge sur une falaise", 1247, 50, origin="imported", recipe=None, script=None, description=None),
        _row("Villa Santorin", 102, 47),
        _row("Chalet face au pic", 42, 42),
        _row("Chalet 12 M€", 15, 26, origin="imported", recipe=None, script=None),
        _row("Home cinéma", 3, 2, recipe="timelapse"),
    ]
    return [facts_from_row(r, NOW) for r in rows]


def test_rank_scores_against_the_median_and_keeps_young_videos_apart():
    videos = _videos()
    out = rank(videos)
    by_title = {v.title: v for v in videos}
    assert out["judged"] == 4 and out["median_views"] == pytest.approx(72.0)  # (102 + 42) / 2
    assert by_title["Refuge sur une falaise"].verdict == "top" and by_title["Refuge sur une falaise"].ref == "V1"
    assert by_title["Villa Santorin"].verdict == "moyen"  # 2e sur 4 : pas dans le premier tiers
    assert by_title["Chalet 12 M€"].verdict == "flop" and by_title["Chalet 12 M€"].score == pytest.approx(0.21)
    assert by_title["Home cinéma"].verdict == "trop récente" and by_title["Home cinéma"].ref == "V5"


def test_rank_does_not_call_close_videos_top_or_flop():
    videos = [facts_from_row(_row(f"V{i}", v, 60), NOW) for i, v in enumerate((100, 98, 97))]
    rank(videos)
    assert {v.verdict for v in videos} == {"moyen"}


def test_rank_uses_views_at_seven_days_for_older_videos():
    old = facts_from_row(_row("Ancienne", 5000, 24 * 20, views_7d=400), NOW)
    new = facts_from_row(_row("Récente", 450, 60), NOW)
    rank([old, new])
    assert old.comparable_views == 400 and new.comparable_views == 450


def test_breakdowns_and_message():
    videos = _videos()
    stats = compute_performance(videos)
    assert stats["judged"] == 4 and [v["ref"] for v in stats["videos"]] == ["V1", "V2", "V3", "V4", "V5"]
    formats = {g["value"]: g for g in stats["groups"]["format"]}
    assert formats["visite de maison de luxe"]["n"] == 2 and formats["visite de maison de luxe"]["confidence"] == "faible"
    msg = build_message("Arzak Parker", videos, stats, [{"target": "seo", "recipe": None, "rule": "Mets un prix dans le titre."}])
    assert "V1 · TOP" in msg and "TROP RÉCENTE" in msg and "Titre d'accroche affiché : « Tu paierais combien" in msg
    assert "Mets un prix dans le titre." in msg and "mise en ligne à la main" in msg


# ---- Garde-fous de l'analyste ------------------------------------------------------------------------------------


def test_clean_report_maps_refs_normalizes_and_caps():
    videos = _videos()
    stats = compute_performance(videos)
    raw = PerformanceReport(
        summary=" Le chantier en accéléré écrase les visites. ",
        videos=[
            VideoDiagnosis(ref="v1", why="L'image change chaque seconde.", worked=["rythme"], missed=[]),
            VideoDiagnosis(ref="V1", why="doublon"),
            VideoDiagnosis(ref="V9", why="inconnue"),
        ],
        patterns=[Pattern(finding="Rythme", evidence="1 247 contre 72", confidence="bonne")] * 7,
        lessons=[
            LessonProposal(
                target="Script", recipe="visite", rule="Change de plan toutes les secondes.", why="V1", confidence="bonne"
            ),
            LessonProposal(target="montage", recipe="tous", rule="Coupe les visites à 20 s.", why="V2"),
            LessonProposal(target="script", rule="change de plan toutes les secondes !", why="doublon"),
            LessonProposal(target="seo", rule="Mets un prix dans le titre.", why="déjà en service"),
            LessonProposal(target="marketing", rule="Achète de la pub.", why="cible inconnue"),
        ],
        experiments=[Experiment(hypothesis="h", test="t")] * 5,
    )
    report, lessons = clean_report(raw, videos, ["Mets un prix dans le titre."], stats["judged"])
    assert report["summary"] == "Le chantier en accéléré écrase les visites."
    assert [d["ref"] for d in report["videos"]] == ["V1"] and report["videos"][0]["verdict"] == "top"
    assert len(report["patterns"]) == 5 and report["patterns"][0]["confidence"] == "moyenne"  # 4 vidéos jugées
    assert len(report["experiments"]) == 3
    assert [(x.target, x.recipe, x.confidence) for x in lessons] == [
        ("script", "tour", "moyenne"),
        ("production", None, "faible"),
    ]
    assert confidence_cap(2) == "faible" and confidence_cap(12) == "bonne"


# ---- Leçons servies aux agents -----------------------------------------------------------------------------------


class LessonDb:
    def __init__(self, rows: list[dict[str, Any]] | None = None, fail: bool = False) -> None:
        self.rows = rows or []
        self.fail = fail
        self.params: Any = None

    def fetch_all(self, sql: str, params: Any = None) -> list[dict[str, Any]]:
        if self.fail:
            raise RuntimeError("relation performance_lessons does not exist")
        self.params = params
        return self.rows


def test_lessons_text_lists_active_rules_and_never_breaks_an_agent():
    db = LessonDb([{"rule": "Ouvre sur le résultat final."}, {"rule": "Un plan par seconde."}])
    text = lessons_text(db, "script", channel_id=None, recipe="timelapse")
    assert text.startswith("LEÇONS TIRÉES DES VIDÉOS PUBLIÉES") and "- Un plan par seconde." in text
    assert db.params[0] == "script" and db.params[3] == "timelapse"
    assert lessons_text(LessonDb([]), "seo") == ""
    assert lessons_text(LessonDb(fail=True), "idea") == ""


# ---- Planificateur -------------------------------------------------------------------------------------------------


class QueueDb:
    def __init__(self, busy: bool) -> None:
        self.busy, self.enqueued, self.statuses = busy, [], None

    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        self.statuses = params[1]
        return {"x": 1} if self.busy else None

    def enqueue(self, type_: str, **kw: Any) -> None:
        self.enqueued.append((type_, kw))


def test_enqueue_sync_skips_a_pending_job():
    db = QueueDb(busy=False)
    assert enqueue_sync(db, "c1", {"scope": "counters"}, priority=85)
    assert db.statuses == ["queued", "running"] and db.enqueued[0][1]["payload"] == {"scope": "counters"}
    full = QueueDb(busy=False)
    enqueue_sync(full, "c1", {"days": 7}, priority=80)
    assert full.statuses == ["queued"]  # une synchro complète attend derrière une synchro qui tourne
    assert not enqueue_sync(QueueDb(busy=True), "c1", {"days": 7}, priority=80)


# ---- Le step, de bout en bout (base et LLM factices) --------------------------------------------------------------


class StepDb:
    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []

    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        if "from channels" in sql:
            return {"name": "Arzak Parker", "id": "c1"}
        if "insert into performance_reports" in sql:
            self.executed.append((sql, params))
            return {"id": "r1"}
        return None

    def fetch_all(self, sql: str, params: Any = None) -> list[dict[str, Any]]:
        return []  # aucune leçon en service

    def execute(self, sql: str, params: Any = None) -> int:
        self.executed.append((sql, params))
        return 1

    def heartbeat(self, *a: Any, **k: Any) -> None: ...

    def alert(self, *a: Any, **k: Any) -> None:
        self.executed.append(("alert", a))


def test_analyze_step_stores_the_report_and_proposed_lessons(monkeypatch):
    from worker.steps import analyze as step_mod
    from worker.steps.base import Context

    videos = _videos()
    monkeypatch.setattr(step_mod, "load_facts", lambda db, cid, days: videos)
    monkeypatch.setattr(step_mod, "prompt_text", lambda db, key, default: default)

    class FakeLlm:
        def complete_json(self, system: str, user: str, schema: Any) -> PerformanceReport:
            assert "V1 · TOP" in user and "PerformanceReport" in system
            return PerformanceReport(
                summary="ok",
                videos=[VideoDiagnosis(ref="V1", why="rythme")],
                lessons=[LessonProposal(target="idea", rule="Privilégie les chantiers en accéléré.", why="×17")],
            )

    monkeypatch.setattr(step_mod, "get_llm", lambda settings, db, writer=False: FakeLlm())
    monkeypatch.setattr(step_mod, "sees_images", lambda provider: False)  # aucun modèle qui voit : texte seul
    db = StepDb()
    job = type("J", (), {"channel_id": "c1", "payload": {}, "id": "j1"})()
    ctx = Context(job=job, db=db, settings=None)  # type: ignore[arg-type]
    monkeypatch.setattr(Context, "progress", lambda self, pct, label=None: None)
    out = step_mod.AnalyzeStep().run(ctx)
    assert out == {"videos": 5, "judged": 4, "lessons": 1, "report": "r1"}
    sqls = [s for s, _ in db.executed]
    assert any("status = 'superseded'" in s for s in sqls)
    lesson = next(p for s, p in db.executed if "insert into performance_lessons" in s)
    assert lesson[2:5] == ("idea", None, "Privilégie les chantiers en accéléré.")
    assert perf.MIN_AGE_H == 24.0


def test_analyze_step_shows_the_videos_to_a_vision_model(monkeypatch, tmp_path):
    from worker.steps import analyze as step_mod
    from worker.steps.base import Context

    videos = _videos()
    monkeypatch.setattr(step_mod, "load_facts", lambda db, cid, days: videos)
    monkeypatch.setattr(step_mod, "prompt_text", lambda db, key, default: default)
    sheet = tmp_path / "sheet.jpg"
    sheet.write_bytes(b"jpg")
    monkeypatch.setattr(step_mod, "video_sheet", lambda db, data_dir, vid: sheet)
    seen: dict[str, Any] = {}

    class Vision:
        def complete_json(self, system: str, user: str, schema: Any, images: Any = ()) -> PerformanceReport:
            assert images, "le texte seul ne sert qu'en repli"
            seen["images"], seen["user"] = list(images), user
            return PerformanceReport(summary="vu", videos=[VideoDiagnosis(ref="V1", why="on voit le chantier avancer")])

    def fake_llm(settings: Any, db: Any, writer: bool = False) -> Vision:
        seen["writer"] = writer
        return Vision()

    monkeypatch.setattr(step_mod, "get_llm", fake_llm)
    monkeypatch.setattr(step_mod, "sees_images", lambda provider: True)
    monkeypatch.setattr(Context, "progress", lambda self, pct, label=None: None)
    job = type("J", (), {"channel_id": "c1", "payload": {}, "id": "j1"})()
    settings = type("S", (), {"data_dir": tmp_path})()
    out = step_mod.AnalyzeStep().run(Context(job=job, db=StepDb(), settings=settings))  # type: ignore[arg-type]
    assert out["judged"] == 4 and len(seen["images"]) == 4  # les 4 vidéos jugées, pas la trop récente
    assert "IMAGES JOINTES" in seen["user"] and "V1, V2, V3, V4" in seen["user"]
    assert seen["writer"] is True  # le modèle d'écriture, plus fort, d'abord


def test_stats_jobs_have_their_own_lane():
    """« Actualiser » et « Analyser » ne doivent pas attendre la fin d'un clip GPU (worker/main.py)."""
    from typing import get_args

    from worker.config import Settings
    from worker.main import STATS_TYPES
    from worker.models import JobType
    from worker.steps import REGISTRY

    assert set(STATS_TYPES) <= set(get_args(JobType))
    assert all(REGISTRY[t].lane == "io" for t in STATS_TYPES)
    assert set(STATS_TYPES) <= set(Settings.model_fields["worker_job_types"].default.split(","))


def test_frames_helpers():
    from PIL import Image

    from worker.analysis_frames import center_crop_916, frame_times
    from worker.performance import sheet_candidates

    assert frame_times(20.0) == [0.5, 2.5, 10.0, 18.0]
    assert frame_times(2.0) == [0.5, 1.0, 1.8, 1.9]  # vidéo très courte : 2,5 s ramené avant la fin
    assert frame_times(None) == [0.5, 2.5, 10.0, 18.0]  # durée inconnue : 20 s
    crop = center_crop_916(Image.new("RGB", (640, 480)))
    assert crop.size == (270, 480)
    many = [facts_from_row(_row(f"V{i}", 100 * (12 - i), 60), NOW) for i in range(12)]
    rank(many)
    picked = sheet_candidates(many)
    assert [v.ref for v in picked] == ["V1", "V2", "V3", "V4", "V9", "V10", "V11", "V12"]
