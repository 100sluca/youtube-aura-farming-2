"""Mes scénarios (docs/59) : le scénario de Luca mis en forme par l'équipe (metteur en scène, scénariste, relecteur de
fidélité), puis fabriqué comme un drame."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from worker import scenario
from worker.config import Settings
from worker.drama import CLIP_STYLE, FILM, sheet_prompt
from worker.models import CastMember, Job, ScriptReview, ScriptV1
from worker.prompts import code_prompts
from worker.providers.video import REAL_NEGATIVE, REAL_STYLES, STYLE_PRESETS
from worker.steps import script as script_step
from worker.steps.base import Context

DOG = CastMember(
    key="rex",
    name="Rex",
    role="le chien sournois",
    look="a fluffy golden retriever dog with a cream coat, brown eyes, a red collar and a slightly guilty smile",
    voice="does not speak",
)
OWNER = CastMember(
    key="paul",
    name="Paul",
    role="le maître",
    look="a man in his thirties with short brown hair, a beard, a grey hoodie and jeans, barefoot",
    voice="a calm male voice in his thirties",
)
TEXT = (
    "Chien dans un canapé, immobile, qui suit son maître des yeux. Le maître range son gâteau au frigo puis part. "
    "Dès qu'il a le dos tourné, le chien ouvre le frigo, croque dedans, cache les indices et retourne sur le canapé."
)


def _scene(i: int, chars: list[str] | None = None, line: tuple[str, str] | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "index": i,
        "duration_s": 3.5,
        "visual_prompt": f"Rex on the grey sofa in the bright living room, shot {i}",
        "motion_prompt": "the dog's head stays still, only its eyes move",
        "characters": chars if chars is not None else ["rex"],
        "lines": [{"who": line[0], "text": line[1], "tone": "angry"}] if line else [],
        **extra,
    }


def _script(scenes: list[dict[str, Any]] | None = None, cast: list[CastMember] | None = None) -> ScriptV1:
    return ScriptV1.model_validate(
        {
            "scenes": scenes if scenes is not None else [_scene(i) for i in range(12)],
            "cast": [m.model_dump() for m in (cast if cast is not None else [DOG, OWNER])],
            "metadata": {"fr": {"title": "t", "description": "d"}},
            "hook_title": {"fr": "Il a tout vu, il ne dira rien"},
        }
    )


def _plan(**extra: Any) -> scenario.ScenarioPlan:
    data: dict[str, Any] = {
        "title": "Le chien et le gâteau",
        "speech": "muet",
        "duration_s": 42,
        "cast": [DOG.model_dump(), OWNER.model_dump()],
        "beats": [
            {"what": "Rex suit Paul des yeux", "from_text": "qui suit son maître des yeux"},
            {"what": "Rex vole le gâteau", "from_text": "le chien ouvre le frigo, croque dedans"},
        ],
        **extra,
    }
    return scenario.ScenarioPlan.model_validate(data)


# ---------------------------------------------------------------------------
# Mise en scène : ce que Luca impose l'emporte
# ---------------------------------------------------------------------------


def test_luca_s_choices_win_over_the_director_s():
    brief = scenario.ScenarioBrief(
        text=TEXT, title="Le casse du frigo", style="cinematic_real", speech="repliques", duration_s=200
    )
    plan = scenario.settle(_plan(style="pixar_fruit", speech="dialogues"), brief)
    assert (plan.style, plan.speech, plan.duration_s, plan.title) == ("cinematic_real", "repliques", 90, "Le casse du frigo")
    free = scenario.settle(_plan(style="anime", duration_s=5), scenario.ScenarioBrief(text=TEXT))
    assert (free.style, free.speech, free.duration_s) == (scenario.STYLE_DEFAULT, "muet", 20)
    assert "aucun, l'équipe décide" in scenario.brief_text(scenario.ScenarioBrief(text=TEXT))
    assert "style imposé : cinematic_real" in scenario.brief_text(brief) and TEXT in scenario.brief_text(brief)


def test_a_character_keeps_his_first_name_only():
    names = ["Biscuit le chien", "Hugo, le maître", "Lila l'enfant", "Paul Lefèvre", "Le chien", "Léa"]
    cast = [DOG.model_copy(update={"name": n, "key": ""}) for n in names]
    plan = scenario.settle(_plan(cast=[m.model_dump() for m in cast]), scenario.ScenarioBrief(text=TEXT))
    assert [m.name for m in plan.cast] == ["Biscuit", "Hugo", "Lila", "Paul Lefèvre", "Le chien", "Léa"]
    assert [m.key for m in plan.cast][:3] == ["biscuit", "hugo", "lila"]


def test_speech_is_read_loosely():
    assert _plan(speech="Quelques répliques").speech == "repliques"
    assert _plan(speech="dialogue").speech == "dialogues"
    assert _plan(speech="sans paroles").speech == "muet"


def test_every_style_offered_exists_and_real_footage_is_filmed_not_animated():
    assert set(scenario.STYLES) <= set(STYLE_PRESETS)
    assert "cinematic_real" in REAL_STYLES and "cartoon" in REAL_NEGATIVE and "people faces" not in REAL_NEGATIVE
    assert CLIP_STYLE["cinematic_real"] == "realistic_motion" and "live-action" in FILM["cinematic_real"]


# ---------------------------------------------------------------------------
# Normalisation et correcteur
# ---------------------------------------------------------------------------


def test_a_silent_scenario_has_no_line_and_keeps_the_director_s_looks():
    short = DOG.model_copy(update={"look": "a dog"})
    s = scenario.normalize(_script([_scene(i, line=("rex", "Ouaf ouaf")) for i in range(8)], cast=[short, OWNER]), _plan())
    assert all(not sc.lines and not sc.narration for sc in s.scenes)
    assert s.member("rex").look == DOG.look + scenario.REAL_ANIMAL  # apparence complète, à quatre pattes
    assert scenario.lint(s, ["fr"], 28, "muet") == []  # aucune part de plans dialogués exigée


def test_a_real_dog_stays_on_all_four_paws_on_its_sheet():
    dog = scenario.four_legs("A small Jack Russell terrier with white fur and a red collar.", "pixar_human")
    assert dog.endswith("never standing upright") and scenario.four_legs(dog, "pixar_human") == dog
    sheet = sheet_prompt(DOG.model_copy(update={"look": dog}))
    assert "on all four paws" in sheet and "to shoes" not in sheet
    # animaux humanisés (style DreamWorks, habillés) et humains : la fiche debout d'un drame
    assert scenario.four_legs("A golden retriever dog", "dreamworks_animal") == "A golden retriever dog"
    assert scenario.four_legs("A fox wearing a green jacket", "pixar_human") == "A fox wearing a green jacket"
    assert "to shoes" in sheet_prompt(OWNER) and scenario.four_legs(OWNER.look, "pixar_human") == OWNER.look
    s = scenario.normalize(_script(), _plan())
    assert "on all four paws" in s.member("rex").look and s.member("paul").look == OWNER.look


def test_real_footage_is_the_default_and_drops_cartoon_words():
    assert scenario.STYLE_DEFAULT == "cinematic_real" and next(iter(scenario.STYLES)) == "cinematic_real"
    look = "A small Jack Russell terrier with very large, highly expressive cartoon-like eyes and a red collar"
    assert (
        scenario.real_look(look, "cinematic_real")
        == "A small Jack Russell terrier with very large, highly expressive eyes and a red collar"
    )
    assert scenario.real_look(look, "pixar_human") == look
    photo = sheet_prompt(OWNER, "cinematic_real")
    assert photo.startswith("Reference photograph") and "to feet" in photo
    assert sheet_prompt(OWNER, "pixar_human").startswith("Character design reference sheet")


def test_lint_catches_what_breaks_the_making():
    scenes = [_scene(0, ["rex", "inconnu"]), *[_scene(i) for i in range(1, 4)]]
    scenes += [
        _scene(i, ["paul"], line=("paul", "Qui a mangé mon gros gâteau au chocolat ce matin dans la cuisine ?"))
        for i in range(4, 9)
    ]
    s = scenario.normalize(_script(scenes), _plan(speech="repliques"))
    issues = scenario.lint(s, ["fr"], 30, "repliques")
    assert any("inconnu" in i for i in issues)
    assert any("réplique de 13 mots" in i for i in issues)
    assert any("« quelques répliques » = 4 au plus" in i for i in issues)
    few = scenario.normalize(_script([_scene(i) for i in range(3)]), _plan())
    assert any("3 plans" in i for i in scenario.lint(few, ["fr"], None, "muet"))


def test_the_listing_read_by_the_reviewer_says_who_is_on_screen_and_who_speaks():
    s = scenario.normalize(
        _script([_scene(0, ["rex", "paul"], line=("paul", "Rex ?")), *[_scene(i) for i in range(1, 6)]]),
        _plan(speech="repliques"),
    )
    text = scenario.script_listing(s)
    assert "Plan 1" in text and "à l'image : Paul, Rex" in text and "réplique : Paul : Rex ?" in text and "sans réplique" in text


def test_the_team_s_prompts_are_editable_in_the_agents_tab():
    prompts = code_prompts()
    assert prompts["scenario_adapt"] == scenario.ADAPT_PROMPT and prompts["script_scenario"] == scenario.SCRIPT_PROMPT
    assert prompts["scenario_review"] == scenario.REVIEW_PROMPT
    assert "from_text" in scenario.ADAPT_PROMPT and "LUCA (son texte d'origine est fourni" in scenario.REVIEW_PROMPT


# ---------------------------------------------------------------------------
# Déroulé de l'étape script : metteur en scène → scénariste → relecteur → réécriture
# ---------------------------------------------------------------------------


class FakeDb:
    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []

    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        return None

    def fetch_all(self, sql: str, params: Any = None) -> list[dict]:
        return []

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))

    def heartbeat(self, *a: Any) -> None:
        pass

    def log(self, job_id: Any, level: str, message: str, data: Any) -> None:
        pass


class TeamLlm:
    def __init__(self, reviews: list[ScriptReview], first: ScriptV1, then: ScriptV1, plan: scenario.ScenarioPlan) -> None:
        self.reviews, self.first, self.then, self.plan, self.calls = reviews, first, then, plan, []

    def complete_json(self, system: str, user: str, schema: type) -> Any:
        self.calls.append((schema.__name__, user))
        if schema is scenario.ScenarioPlan:
            return self.plan
        if schema is ScriptReview:
            return self.reviews.pop(0) if len(self.reviews) > 1 else self.reviews[0]
        assert schema is ScriptV1
        return self.first if sum(1 for n, _ in self.calls if n == "ScriptV1") == 1 else self.then


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, llm: TeamLlm, brief: dict[str, Any]) -> tuple[Any, list[str], FakeDb]:
    monkeypatch.setattr(script_step, "get_llm", lambda s, d, writer=False: llm)
    monkeypatch.setattr(script_step, "tts_catalog", lambda s: {})
    db = FakeDb()
    job = Job(id=uuid.uuid4(), type="script", status="running", priority=50, created_at=datetime.now(UTC))
    settings = Settings(database_url="postgresql://x", supabase_url="http://x", supabase_service_role_key="x", data_dir=tmp_path)
    ctx = Context(job=job, db=db, settings=settings)  # type: ignore[arg-type]
    prod = {
        "id": uuid.uuid4(),
        "concept_id": uuid.uuid4(),
        "scenario": brief,
        "format": "B_visual",
        "style_preset": "pixar_human",
    }
    script, issues, _ = script_step.ScriptStep()._write(ctx, prod, ["fr"])
    return script, issues, db


def test_the_team_reads_luca_s_text_rewrites_once_and_poses_the_style(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    refused = ScriptReview(ok=False, problems=["le chien qui cache les indices (scénario) n'est pas montré"])
    first = _script([_scene(i) for i in range(12)])
    llm = TeamLlm([refused, ScriptReview(ok=True)], first, first, _plan(style="cinematic_real"))
    script, issues, db = _run(tmp_path, monkeypatch, llm, {"text": TEXT, "style": "auto", "speech": "auto"})
    assert [n for n, _ in llm.calls] == ["ScenarioPlan", "ScriptV1", "ScriptReview", "ScriptV1", "ScriptReview"]
    assert TEXT in llm.calls[0][1] and "STYLES VISUELS" in llm.calls[0][1]
    assert "MISE EN SCÈNE" in llm.calls[1][1] and TEXT in llm.calls[1][1] and "VOIX DE SYNTHÈSE" not in llm.calls[1][1]
    assert "SCRIPT À RELIRE" in llm.calls[2][1] and "cache les indices" in llm.calls[3][1]
    assert issues == [] and len(script.scenes) == 12
    updates = " ".join(sql for sql, _ in db.executed)
    assert "update concepts" in updates and "update productions set style_preset" in updates
    style = next(p for sql, p in db.executed if "style_preset" in sql)
    assert style[:2] == ("cinematic_real", 42)
    plan = next(p for sql, p in db.executed if "update concepts" in sql)[2].obj["plan"]
    assert plan["title"] == "Le chien et le gâteau" and plan["beats"][0]["from_text"]


def test_an_approved_clean_script_is_not_rewritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    first = _script([_scene(i) for i in range(12)])
    llm = TeamLlm([ScriptReview(ok=True)], first, first, _plan())
    _, issues, _ = _run(tmp_path, monkeypatch, llm, {"text": TEXT})
    assert [n for n, _ in llm.calls] == ["ScenarioPlan", "ScriptV1", "ScriptReview"] and issues == []


def test_a_worse_form_only_rewrite_is_dropped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    first = _script([_scene(i) for i in range(4)])  # trop peu de plans : le correcteur demande une reprise
    worse = _script([_scene(i, ["rex", "x", "y"]) for i in range(4)])
    llm = TeamLlm([ScriptReview(ok=True)], first, worse, _plan())
    script, issues, _ = _run(tmp_path, monkeypatch, llm, {"text": TEXT})
    assert [n for n, _ in llm.calls] == ["ScenarioPlan", "ScriptV1", "ScriptReview", "ScriptV1"]
    assert all(sc.characters == ["rex"] for sc in script.scenes) and any("4 plans" in i for i in issues)
