"""Storyboard des formats visuels (docs/15 §10) : ordre des retouches, contrôle par vision, revue humaine.

Base, ComfyUI et LLM remplacés par des doublures : on vérifie la mécanique du step, pas les modèles."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from worker.config import Settings
from worker.keyframe_qc import KeyframeVerdict, requirements
from worker.models import Job, ScriptV1
from worker.recipes import normalize_script
from worker.steps import storyboard as sb
from worker.steps.base import Context


class FakeDb:
    def __init__(self, script: ScriptV1, recipe: str) -> None:
        self.script, self.recipe = script, recipe
        self.assets: list[dict[str, Any]] = []
        self.status: str | None = None
        self.alerts: list[tuple[str, str]] = []
        self.logs: list[str] = []

    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        if "from productions p" in sql and "p.script" in sql:
            return {"script": self.script.model_dump(), "style_preset": "timelapse_site", "image_workflow": "zimage_turbo", "title": "t"}
        if "coalesce(s.recipe" in sql:
            return {"recipe": self.recipe}
        if "count(*)" in sql:
            return {"n": sum(a["scene_index"] == params[1] for a in self.assets)}
        if "selected order by" in sql:
            rows = [a for a in self.assets if a["scene_index"] == params[1] and a["selected"]]
            return {"local_path": rows[-1]["local_path"]} if rows else None
        return None

    def fetch_all(self, sql: str, params: Any = None) -> list[dict]:
        return []

    def execute(self, sql: str, params: Any = None) -> int:
        if "set selected = (id = %s)" in sql:  # l'image retenue de la scène, et elle seule
            for a in self.assets:
                if a["scene_index"] == params[2]:
                    a["selected"] = a["id"] == params[0]
        return 1

    def add_asset(self, **cols: Any) -> uuid.UUID:
        aid = uuid.uuid4()
        self.assets.append({"id": aid, **cols})
        return aid

    def heartbeat(self, *a: Any, **k: Any) -> bool:
        return True

    def log(self, job_id: Any, level: str, message: str, data: Any = None) -> None:
        self.logs.append(message)

    def set_status(self, table: str, id_: Any, status: str, error: str | None = None) -> None:
        self.status = status

    def alert(self, severity: str, title: str, body: str | None = None, **refs: Any) -> uuid.UUID:
        self.alerts.append((title, body or ""))
        return uuid.uuid4()


class FakeImage:
    calls: list[str] = []

    def __init__(self, settings: Any, workflow: str | None = None) -> None:
        self.name, self.width, self.height = "fake_image", 768, 1344

    def generate(self, *, prompt: str, style_preset: Any, out_path: Path, seed: int, dry_run: bool = False) -> Path:
        FakeImage.calls.append(f"gen:{out_path.name.split('_')[1]}")
        out_path.write_bytes(b"png")
        return out_path


class FakeEditor:
    def __init__(self, settings: Any) -> None:
        self.name, self.width, self.height, self.fallback_reason = "fake_edit", 768, 1344, None
        self.client = type("C", (), {"free": lambda self: None})()

    def edit(self, *, image_path: Path, instruction: str, description: str, style_preset: Any, out_path: Path, seed: int,
             dry_run: bool = False) -> Path:
        FakeImage.calls.append(f"edit:{out_path.name.split('_')[1]}<{image_path.name.split('_')[1]}")
        out_path.write_bytes(b"png")
        return out_path


class FakeVision:
    """Refuse la première image de chaque scène listée dans `refuse`, accepte tout le reste."""

    def __init__(self, refuse: set[int] = frozenset(), always: set[int] = frozenset()) -> None:
        self.refuse, self.always, self.seen = set(refuse), set(always), []

    def complete_json(self, system: str, user: str, schema: Any, images: Any = ()) -> KeyframeVerdict:
        scene = int(Path(images[0]).name.split("_")[1])
        self.seen.append((scene, len(images)))
        if scene in self.always or scene in self.refuse:
            self.refuse.discard(scene)
            return KeyframeVerdict(ok=False, problems=[f"scène {scene} : bâtiment coupé par le bord"])
        return KeyframeVerdict(ok=True)


def _timelapse(n: int = 5) -> ScriptV1:
    scenes = [{"index": i, "duration_s": 1.5, "visual_prompt": f"stage {i}", "motion_prompt": "build",
               "edit_prompt": f"Remove part {i}", "on_screen_text": {"fr": f"Jour {i * 10 + 1}"}} for i in range(n)]
    return normalize_script(ScriptV1.model_validate({"scenes": scenes, "metadata": {"fr": {"title": "t", "description": "d"}},
                                                     "hook_title": {"fr": "Regarde ce chantier fou"}}), "timelapse")


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: ScriptV1, vision: FakeVision | None, **settings: Any):
    FakeImage.calls = []
    monkeypatch.setattr(sb, "ComfyImage", FakeImage)
    monkeypatch.setattr(sb, "ComfyImageEdit", FakeEditor)
    monkeypatch.setattr(sb, "get_vision_llm", lambda s, d: vision)
    monkeypatch.setattr(sb, "build_sheet", lambda *a, **k: None)
    monkeypatch.setattr(sb, "enqueue_render_dag", lambda *a, **k: {"clips": len(script.scenes)})
    monkeypatch.setattr(sb, "load_generation_config", lambda s, d: type("G", (), {"image_workflow": "zimage_turbo", "storyboard_candidates": 2})())
    db = FakeDb(script, "timelapse")
    cfg = Settings(database_url="postgresql://x", supabase_url="http://x", supabase_service_role_key="x", data_dir=tmp_path,
                   **settings)
    job = Job(id=uuid.uuid4(), type="storyboard", status="running", priority=90, production_id=uuid.uuid4(), payload={},
              created_at=datetime.now(UTC))
    out = sb.StoryboardStep().run(Context(job=job, db=db, settings=cfg))  # type: ignore[arg-type]
    return db, out


def test_the_finished_building_is_made_first_then_each_stage_backwards(tmp_path, monkeypatch):
    s = _timelapse(5)  # étapes 0-2, fini 3, crépuscule 4
    db, out = _run(tmp_path, monkeypatch, s, FakeVision())
    assert FakeImage.calls == ["gen:03", "edit:02<03", "edit:01<02", "edit:00<01", "edit:04<03"]
    assert out["review"] and db.status == "storyboard_review"  # Luca valide le storyboard lui-même (défaut)
    assert out["qc"] == {"checked": True, "refused": {}}
    assert all(a["meta"]["qc"]["ok"] for a in db.assets) and sum(a["selected"] for a in db.assets) == 5


def test_a_refused_image_is_redone_before_the_stages_that_derive_from_it(tmp_path, monkeypatch):
    vision = FakeVision(refuse={3})
    db, out = _run(tmp_path, monkeypatch, _timelapse(5), vision)
    assert FakeImage.calls[:3] == ["gen:03", "gen:03", "edit:02<03"]  # le fini est refait avant de remonter le temps
    kept = [a for a in db.assets if a["scene_index"] == 3]
    assert [a["meta"]["qc"]["ok"] for a in kept] == [False, True] and [a["selected"] for a in kept] == [False, True]
    assert (3, 1) in vision.seen and (2, 2) in vision.seen  # une retouche est jugée avec l'image qu'elle retouche


def test_images_still_refused_go_to_human_review_with_the_problems(tmp_path, monkeypatch):
    db, out = _run(tmp_path, monkeypatch, _timelapse(5), FakeVision(always={1}), storyboard_autopass=True)
    assert FakeImage.calls.count("edit:01<02") == 3  # 1 + 2 essais
    assert out["review"] and out["qc"]["refused"] == {1: ["scène 1 : bâtiment coupé par le bord"]}
    assert "bâtiment coupé" in db.alerts[0][1]
    assert [a["selected"] for a in db.assets if a["scene_index"] == 1] == [False, False, True]  # le dernier essai


def test_autopass_is_opt_in_and_needs_a_complete_check(tmp_path, monkeypatch):
    db, out = _run(tmp_path, monkeypatch, _timelapse(5), FakeVision(), storyboard_autopass=True)
    assert not out["review"] and out["clips"] == 5 and db.status is None  # tout passe : le rendu part seul
    db, out = _run(tmp_path, monkeypatch, _timelapse(5), None, storyboard_autopass=True)
    assert out["review"] and out["qc"] == {"checked": False}  # pas de modèle de vision : revue humaine


def test_requirements_follow_the_recipe():
    s = _timelapse(5)
    assert any("ENTIÈRE" in r for r in requirements(s, 3, "timelapse"))
    assert any("MOINS avancée" in r for r in requirements(s, 1, "timelapse"))
    assert any("crépuscule" in r for r in requirements(s, 4, "timelapse"))
    tour = normalize_script(ScriptV1.model_validate({
        "scenes": [{"index": i, "duration_s": 3.5, "visual_prompt": f"room {i}"} for i in range(6)],
        "metadata": {"fr": {"title": "t", "description": "d"}}}), "tour")
    assert any("L'INTÉRIEUR" in r for r in requirements(tour, 2, "tour"))
    assert not any("L'INTÉRIEUR" in r for r in requirements(tour, 0, "tour"))  # l'arrivée est dehors
    assert all(any("Aucune personne" in r for r in requirements(tour, i, "tour")) for i in range(6))


def test_vision_overload_is_retried_patiently(monkeypatch):
    from worker import keyframe_qc as kq

    monkeypatch.setattr(kq, "PATIENCE_S", (0, 0))
    calls = []

    class Busy:
        def complete_json(self, system, user, schema, images=()):
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("Server error '503 Service Unavailable'")
            return KeyframeVerdict(ok=True)

    assert kq._ask(Busy(), "s", "u", []).ok and len(calls) == 3  # deux 503, puis la réponse

    class Broken:
        def complete_json(self, system, user, schema, images=()):
            raise ValueError("réponse sans JSON")

    with pytest.raises(ValueError):  # une vraie erreur n'est pas réessayée
        kq._ask(Broken(), "s", "u", [])
