"""Réinventer une scène du storyboard (worker/reinvent.py, docs/27) : le scénariste réécrit une seule scène, raccord
avec les autres, puis le step storyboard refait ses images.

Base, ComfyUI et LLM remplacés par des doublures : on vérifie la mécanique, pas les modèles."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from worker import reinvent as rv
from worker.config import Settings
from worker.models import Job, SceneRewrite, ScriptV1
from worker.recipes import normalize_script
from worker.steps import storyboard as sb
from worker.steps.base import Context

MIRROR = "a large vertical silver-framed mirror on a white wall, polished concrete floor"
PIVOT = "Detailed close-up of a hidden hydraulic pivot mechanism embedded in the wooden floor, brushed steel, warm lighting"
HINGE = f"Close-up of the edge of {MIRROR}, the mirror swung half open on a brushed steel vertical axis, a lit closet behind"


def _mirror() -> ScriptV1:
    """Le storyboard du 28/09 (production 825eda53) : scènes numérotées à partir de 1, la 4 hors sujet."""
    rows = [
        ("hook", f"Minimalist hallway in a luxury apartment, {MIRROR}", "Personne ne pousse jamais ce miroir."),
        ("setup", "Close-up of the polished silver frame of the mirror", "Et ce mur semble totalement solide."),
        ("reveal", "Interior of a hidden luxury walk-in closet, custom wooden shelves", "Pourtant une pièce entière se cache derrière."),
        ("escalation", PIVOT, "Un pivot invisible supporte tout le poids."),
        ("payoff", "Wide shot of a fully organized luxury dressing room", "10 mètres carrés de rangement sur mesure."),
        ("loop", f"Minimalist hallway in a luxury apartment, {MIRROR}", "Personne ne pousse jamais ce miroir."),
    ]
    scenes = [{"index": i + 1, "role": role, "duration_s": 5, "visual_prompt": vis, "motion_prompt": "slow push-in",
               "narration": {"fr": nar}} for i, (role, vis, nar) in enumerate(rows)]
    return ScriptV1.model_validate({"scenes": scenes, "metadata": {"fr": {"title": "t", "description": "d"}},
                                    "loop_note": "retour au miroir"})


GOOD = {
    "idea": "Gros plan sur la tranche du miroir entrouvert : l'axe en acier apparaît",
    "scene": {"visual_prompt": HINGE, "motion_prompt": "the mirror slowly swings further open on its axis",
              "narration": {"fr": "Le miroir tourne sur un axe d'acier caché dans sa tranche."},
              "on_screen_text": {"fr": "Axe caché"}},
}


class FakeWriter:
    """Le scénariste : renvoie les réponses prévues, dans l'ordre, et garde les messages reçus."""

    def __init__(self, *answers: dict[str, Any]) -> None:
        self.answers, self.calls = list(answers), []

    def complete_json(self, system: str, user: str, schema: Any, images: Any = ()) -> Any:
        self.calls.append((system, user))
        return schema.model_validate(self.answers.pop(0))


class FakeDb:
    def __init__(self, script: ScriptV1, recipe: str = "story", fmt: str = "A_voiceover", jobs: list[Any] | None = None,
                 assets: list[dict[str, Any]] | None = None) -> None:
        self.script, self.recipe, self.fmt = script, recipe, fmt
        self.jobs = jobs or []  # payload « reinvented » des jobs précédents
        self.assets = assets or []
        self.saved: ScriptV1 | None = None
        self.narration: dict[Any, Any] = {}
        self.deleted: list[int] = []
        self.payloads: list[Any] = []
        self.status: str | None = None
        self.alerts: list[tuple[str, str]] = []
        self.logs: list[str] = []
        self.stopped = False  # « Arrêter » cliqué dans Création : le job n'est plus « running »

    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        if "series_brief" in sql:
            return {"format": self.fmt, "target_duration_s": 30, "title": "Le miroir qui ouvre sur un dressing secret",
                    "hook": "Personne ne pousse ce miroir", "premise": "Un miroir cache un dressing", "angle": "secret",
                    "visual_beats": ["miroir", "dressing"], "facts": [], "sources": [], "series_name": "Maisons de rêve",
                    "series_brief": "Passages secrets"}
        if "from productions p" in sql and "p.script" in sql:
            return {"script": self.script.model_dump(), "style_preset": None, "image_workflow": "zimage_turbo", "title": "Le miroir"}
        if "coalesce(s.recipe" in sql:
            return {"recipe": self.recipe}
        if "count(*)" in sql:
            return {"n": sum(a["scene_index"] == params[1] for a in self.assets)}
        if "selected order by" in sql:
            rows = [a for a in self.assets if a["scene_index"] == params[1] and a["selected"]]
            return {"local_path": rows[-1]["local_path"]} if rows else None
        return None  # prompt_templates : le texte du code

    def fetch_all(self, sql: str, params: Any = None) -> list[dict]:
        if "from videos" in sql:
            return [{"id": "v1", "lang": "fr"}]
        if "payload->'reinvented'" in sql:
            return [{"done": j} for j in self.jobs]
        return []

    def execute(self, sql: str, params: Any = None) -> int:
        if sql.startswith("update productions set script"):
            self.saved = self.script = ScriptV1.model_validate(params[0].obj)
        elif sql.startswith("update videos set narration_text"):
            self.narration[params[1]] = params[0]
        elif sql.startswith("delete from assets"):
            self.deleted = list(params[1])
            self.assets = [a for a in self.assets if a["scene_index"] not in params[1]]
        elif sql.startswith("update jobs set payload"):
            self.payloads.append(params[0].obj)
        elif "set selected = (id = %s)" in sql:
            if "from jobs" in sql and self.stopped:
                return 0
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


# ---- La réécriture ------------------------------------------------------------------------------------------------


def test_only_the_scene_changes_and_it_keeps_its_place_in_the_story():
    script, writer = _mirror(), FakeWriter(GOOD)
    new, entry = rv.reinvent_scene(FakeDb(script), writer, "p1", script, "story", 4, "le pivot n'a rien à voir avec le miroir")
    scene = new.scenes[3]
    assert scene.visual_prompt == HINGE and scene.narration == {"fr": "Le miroir tourne sur un axe d'acier caché dans sa tranche."}
    assert (scene.index, scene.role, scene.duration_s, scene.continues_previous) == (4, "escalation", 5, False)
    assert [s.model_dump() for k, s in enumerate(new.scenes) if k != 3] == [s.model_dump() for k, s in enumerate(script.scenes) if k != 3]
    assert entry["shot"] == 4 and entry["idea"].startswith("Gros plan") and entry["issues"] == []
    assert entry["before"]["visual_prompt"] == PIVOT and entry["after"]["visual_prompt"] == HINGE
    assert len(writer.calls) == 1


def test_the_writer_gets_the_script_the_note_and_the_versions_already_rejected():
    script = _mirror()
    earlier = [{"scene": 4, "idea": "…", "before": {"visual_prompt": "A steel hinge alone on a grey background", "narration": {"fr": "Tout tient sur un axe."}}},
               {"scene": 2, "before": {"visual_prompt": "autre scène"}}]
    writer = FakeWriter(GOOD)
    rv.reinvent_scene(FakeDb(script, jobs=[earlier]), writer, "p1", script, "story", 4, "montrer le miroir qui pivote")
    system, user = writer.calls[0]
    assert system == rv.REWRITE_PROMPT
    assert "CE QU'EN DIT LUCA : « montrer le miroir qui pivote »" in user
    assert ">>> Scène 4 [escalation, 5 s] À RÉINVENTER" in user and "Scène 5 [payoff, 5 s]" in user
    assert "version écartée 1 : image « A steel hinge alone on a grey background » ; narration « Tout tient sur un axe. »" in user
    assert f"version actuelle : image « {PIVOT} »" in user and "autre scène" not in user
    assert "narration de 10 à 15 mots" in user and "RÈGLES DU RÉCIT" in user and "Maisons de rêve" in user
    assert "RÈGLES DE L'IMAGE" in user and "RÉCIT : tu écris AUSSI la narration" in user  # récit : docs/37
    # consignes du réalisateur des récits (script_shots), sans sa consigne de réponse : une seule scène est attendue
    assert "CONSIGNES DU SCÉNARISTE" in user and "Tu es le réalisateur" in user and "conforme à ShotList" not in user


def test_without_a_note_the_writer_is_told_the_scene_is_off_topic():
    script, writer = _mirror(), FakeWriter(GOOD)
    rv.reinvent_scene(FakeDb(script), writer, "p1", script, "story", 4)
    assert f"POURQUOI : {rv.DEFAULT_REASON}" in writer.calls[0][1]


def test_a_new_problem_sends_the_scene_back_once():
    script = _mirror()
    same = {"idea": "le même", "scene": {"visual_prompt": PIVOT + ".", "narration": {"fr": "Un pivot invisible porte tout le poids."}}}
    writer = FakeWriter(same, GOOD)
    new, entry = rv.reinvent_scene(FakeDb(script), writer, "p1", script, "story", 4)
    assert len(writer.calls) == 2 and new.scenes[3].visual_prompt == HINGE and entry["issues"] == []
    assert "même image qu'une version écartée" in writer.calls[1][1] and "Scène proposée" in writer.calls[1][1]


def test_the_best_answer_is_kept_when_the_retry_is_not_better():
    script = _mirror()
    long = {"idea": "trop bavard", "scene": {"visual_prompt": HINGE, "narration": {"fr": " ".join(["mot"] * 30) + "."}}}
    writer = FakeWriter(long, long)
    new, entry = rv.reinvent_scene(FakeDb(script), writer, "p1", script, "story", 4)
    assert len(writer.calls) == 2 and entry["issues"] and "30 mots" in entry["issues"][0]
    assert new.scenes[3].visual_prompt == HINGE  # gardée malgré tout : Luca juge sur l'image


def test_global_issues_whose_numbers_move_are_not_new():
    before = ["[fr] narration trop maigre : 40 mots pour 30 s, au moins 63", "[fr] scène 5 : phrase de 20 mots, 18 au plus"]
    after = ["[fr] narration trop maigre : 43 mots pour 30 s, au moins 63", "[fr] scène 5 : phrase de 20 mots, 18 au plus",
             "[fr] scène 4 : 17 mots pour 5 s, 15 au plus", "2 scènes carte (scènes 2, 4) : une seule par Short"]
    assert rv.new_issues(before, after, 4) == after[2:]


def test_a_flat_answer_and_a_plain_narration_are_accepted():
    answer = SceneRewrite.model_validate({"idea": "x", "visual_prompt": HINGE, "narration": "Le miroir tourne."})
    assert answer.scene.visual_prompt == HINGE and answer.scene.narration == {"fr": "Le miroir tourne."}


def test_a_passage_or_an_unknown_scene_cannot_be_reinvented():
    script = _mirror()
    with pytest.raises(ValueError, match="scène 9"):
        rv.reinvent_scene(FakeDb(script), FakeWriter(GOOD), "p1", script, "story", 9)


def test_a_room_of_a_tour_keeps_the_path_of_the_visit():
    rooms = [{"index": i, "duration_s": 3.5, "visual_prompt": f"room {i}", "motion_prompt": "glide forward", "sfx": "birds",
              "leads_to": f"a wide opening onto room {i + 1}", "floor": 0} for i in range(4)]
    tour = normalize_script(ScriptV1.model_validate({"scenes": rooms, "metadata": {"fr": {"title": "t", "description": "d"}},
                                                     "design_bible": "white oak, travertine", "view": "the sea"}), "tour")
    assert [s.passage for s in tour.scenes] == [False, True, False, True, False, True, False]
    draft = SceneRewrite.model_validate({"idea": "Bibliothèque", "scene": {
        "visual_prompt": "A double-height library with oak shelves", "leads_to": "on the left, a glass door onto room 3",
        "narration": {"fr": "rien"}}}).scene
    new = rv.apply_rewrite(tour, 2, draft, "tour")
    assert [s.index for s in new.scenes] == list(range(7)) and new.scenes[2].visual_prompt.startswith("A double-height")
    assert new.scenes[2].narration == {} and new.scenes[2].floor == 0 and new.scenes[2].sfx == "birds"
    assert "glass door onto room 3" in new.scenes[3].visual_prompt  # le passage suit la nouvelle ouverture
    assert new.scenes[1].visual_prompt == tour.scenes[1].visual_prompt  # on y arrive toujours par la même


def test_shot_numbers_are_the_ones_luca_sees():
    script = _mirror()  # scènes numérotées à partir de 1
    assert [rv.shot_number(script, s.index) for s in script.scenes] == [1, 2, 3, 4, 5, 6]


# ---- Dans le step storyboard ------------------------------------------------------------------------------------


class FakeImage:
    calls: list[str] = []
    broken = False

    def __init__(self, settings: Any, workflow: str | None = None) -> None:
        self.name, self.width, self.height = "fake_image", 768, 1344

    def generate(self, *, prompt: str, style_preset: Any, out_path: Path, seed: int, dry_run: bool = False) -> Path:
        if FakeImage.broken:
            raise ConnectionError("ComfyUI éteint")
        FakeImage.calls.append(f"{out_path.name.split('_')[1]}:{prompt[:20]}")
        out_path.write_bytes(b"png")
        return out_path


def _step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db: FakeDb, payload: dict[str, Any], writer: FakeWriter | None = None):
    FakeImage.calls = []
    monkeypatch.setattr(sb, "ComfyImage", FakeImage)
    monkeypatch.setattr(sb, "get_llm", lambda s, d, writer_=None, **k: writer)
    monkeypatch.setattr(sb, "build_sheet", lambda *a, **k: None)
    monkeypatch.setattr(sb, "load_generation_config", lambda s, d: type("G", (), {"image_workflow": "zimage_turbo", "storyboard_candidates": 2})())
    cfg = Settings(database_url="postgresql://x", supabase_url="http://x", supabase_service_role_key="x", data_dir=tmp_path)
    job = Job(id=uuid.uuid4(), type="storyboard", status="running", priority=80, production_id=uuid.uuid4(), payload=payload,
              created_at=datetime.now(UTC))
    return sb.StoryboardStep().run(Context(job=job, db=db, settings=cfg))  # type: ignore[arg-type]


def _board(script: ScriptV1) -> list[dict[str, Any]]:
    return [{"id": uuid.uuid4(), "scene_index": s.index, "selected": k == 0, "local_path": f"old_{s.index}_{k}.png"}
            for s in script.scenes for k in range(2)]


def test_the_step_rewrites_the_scene_then_redraws_only_it(tmp_path, monkeypatch):
    script = _mirror()
    db, writer = FakeDb(script, assets=_board(script)), FakeWriter(GOOD)
    out = _step(tmp_path, monkeypatch, db, {"scenes": [4], "reinvent": True, "note": "hors sujet"}, writer)
    assert db.saved is not None and db.saved.scenes[3].visual_prompt == HINGE
    assert "Le miroir tourne sur un axe" in db.narration["v1"]
    assert db.deleted == [4] and FakeImage.calls == [f"04:{HINGE[:20]}"] * 2  # deux candidates, du nouveau prompt
    fours = [a for a in db.assets if a["scene_index"] == 4]
    assert len(fours) == 2 and [a["selected"] for a in fours] == [True, False] and all(a["meta"]["prompt"] == HINGE for a in fours)
    assert db.payloads[0][0]["scene"] == 4 and db.payloads[0][0]["note"] == "hors sujet"
    assert out["review"] and db.status == "storyboard_review" and out["reinvented"][0]["idea"].startswith("Gros plan")
    assert "Scène 4 réinventée : Gros plan" in db.alerts[0][1]


def test_a_retry_after_an_image_failure_does_not_rewrite_again(tmp_path, monkeypatch):
    script = _mirror()
    db, writer = FakeDb(script, assets=_board(script)), FakeWriter(GOOD)
    FakeImage.broken = True
    try:
        with pytest.raises(ConnectionError):
            _step(tmp_path, monkeypatch, db, {"scenes": [4], "reinvent": True}, writer)
    finally:
        FakeImage.broken = False
    assert db.saved is not None and len(writer.calls) == 1 and db.payloads  # la réécriture est gardée
    out = _step(tmp_path, monkeypatch, db, {"scenes": [4], "reinvented": db.payloads[0]}, writer)
    assert len(writer.calls) == 1 and len(FakeImage.calls) == 2 and out["reinvented"][0]["scene"] == 4


def test_a_failed_redo_keeps_the_image_chosen_before(tmp_path, monkeypatch):
    script = _mirror()
    db = FakeDb(script, assets=_board(script))
    FakeImage.broken = True
    try:
        with pytest.raises(ConnectionError):
            _step(tmp_path, monkeypatch, db, {"scenes": [2]})
    finally:
        FakeImage.broken = False
    assert [a["selected"] for a in db.assets if a["scene_index"] == 2] == [True, False]  # Refaire du 28/09, ComfyUI éteint


def test_a_redo_stopped_from_creation_keeps_the_images_on_screen(tmp_path, monkeypatch):
    from worker import cancel

    script = _mirror()
    db = FakeDb(script, assets=_board(script))
    db.stopped = True  # Luca a cliqué « Arrêter » pendant que la nouvelle image se faisait
    with pytest.raises(cancel.JobCancelled):
        _step(tmp_path, monkeypatch, db, {"scenes": [2], "reason": "lunettes en trop"})
    twos = [a for a in db.assets if a["scene_index"] == 2]
    assert [a["selected"] for a in twos] == [True, False, False]  # la nouvelle image reste au choix, l'ancienne est retenue
    assert db.status is None  # la revue continue telle quelle
