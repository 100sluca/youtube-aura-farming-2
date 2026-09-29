"""Le conteur des récits (docs/37, worker/storycraft.py) : l'histoire écrite en entier, son correcteur, le découpage en
scènes sans changer un mot, l'assemblage avec les plans du réalisateur, et le déroulé complet de l'étape script
(conteur → relecteur → réécriture → réalisateur). Base et LLM remplacés par des doublures."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from worker import reinvent
from worker.config import Settings
from worker.models import Job, ScriptReview, ShotList, StoryDraft
from worker.prompts import code_prompts
from worker.steps import script as script_step
from worker.steps.base import Context
from worker.storycraft import (
    SCENE_WORDS_MAX,
    build_script,
    lint_story,
    missing_shots,
    normalize_draft,
    scene_seconds,
    split_scenes,
    story_listing,
    story_words,
    told_story,
    word_budget,
)
from worker.storytelling import lint_script, said_words, sentences

TARGET = 40  # une histoire courte suffit aux tests : 116 mots visés (99 à 130)

# Histoire inventée pour les tests (aucun fait réel) : accroche, promesse, contexte, conflit, renversement, réponse, chute
BEATS = [
    ("hook", "Ce gardien de phare a sauvé 300 navires sans jamais voir la mer.", "Un vieux phare sur un rocher, la nuit"),
    ("promise", "Pourtant, une nuit lui a tout pris.", "La lampe du phare vacille"),
    (
        "context",
        "Alors tout commence en 1890, sur un rocher battu par les vents. Paul est aveugle depuis l'enfance. "
        "Il veut une chose : garder la lampe allumée, chaque nuit, pour que son frère rentre du large.",
        "Un homme aveugle monte l'escalier du phare",
    ),
    (
        "conflict",
        "Mais une tempête noie le village en une heure. Le feu s'éteint. Donc Paul grimpe les 120 marches à "
        "tâtons, une allumette entre les dents. Personne ne l'aide.",
        "La tempête frappe le phare",
    ),
    ("twist", "Sauf qu'au sommet, la lampe n'a plus de verre, et le vent souffle chaque flamme.", "La vitre brisée"),
    (
        "payoff",
        "Alors il colle son propre corps contre la vitre brisée toute la nuit. À l'aube, 12 bateaux rentrent.",
        "Des bateaux rentrent au port à l'aube",
    ),
    ("ending", "Son frère n'était pas dedans.", "Le rocher vide au matin"),
]


def _draft(beats: list[tuple[str, str, str]] = BEATS, **overrides: Any) -> StoryDraft:
    data: dict[str, Any] = {
        "central_idea": "Il sauve tout le monde, sauf celui pour qui il le faisait.",
        "engine": "ironie",
        "protagonist": "Paul, gardien aveugle, veut ramener son frère",
        "stakes": "son frère perdu en mer",
        "ending": "Son frère n'était pas dedans.",
        "beats": [{"part": p, "text": t, "show": v} for p, t, v in beats],
        "hook_title": {"fr": "Il n'a jamais vu la mer"},
    }
    return StoryDraft.model_validate({**data, **overrides})


def _shots(n: int, skip: set[int] | None = None, map_at: int | None = None) -> ShotList:
    shots = []
    for i in range(n):
        if skip and i in skip:
            continue
        shot: dict[str, Any] = {
            "index": i,
            "visual_prompt": f"shot {i}, lighthouse on a rock, 1890",
            "motion_prompt": "slow push in",
            "continues_previous": True,
            "on_screen_text": {"fr": "300 navires"} if i == 0 else {},
        }
        if map_at is not None and i in (map_at, map_at + 2):  # deux cartes proposées : seule la première reste
            shot["map"] = {"place": "Phare du Créach", "context": ["Bretagne"]}
        shots.append(shot)
    return ShotList.model_validate(
        {
            "shots": shots,
            "loop_note": "retour au phare",
            "music_mood": "emotional",
            "design_bible": "1890 Brittany, stormy blue light",
            "metadata": {"fr": {"title": "Le gardien", "description": "d", "tags": ["phare"]}},
        }
    )


# ---------------------------------------------------------------------------
# Budget, nettoyage, correcteur
# ---------------------------------------------------------------------------


def test_budget_follows_the_target_duration():
    lo, aim, hi = word_budget(75)
    assert (lo, aim, hi) == (185, 218, 244)  # 1 min 15 : environ 218 mots dits
    assert word_budget(TARGET) == (99, 116, 130)


def test_the_test_story_is_clean():
    d = normalize_draft(_draft())
    assert story_words(d) == 125
    assert lint_story(d, "fr", TARGET) == []


def test_normalize_writes_numbers_in_digits_and_cleans_the_title():
    d = normalize_draft(
        _draft(
            beats=[("hook", "  Ce  phare a sauvé trois cents navires. ", "v"), *BEATS[1:]],
            hook_title={"fr": "« Il n'a jamais vu la mer ». #phare"},
        )
    )
    assert d.beats[0].text == "Ce phare a sauvé 300 navires."
    assert d.hook_title["fr"] == "Il n'a jamais vu la mer"


def test_lint_story_catches_what_makes_a_list_of_facts():
    flat = [
        ("hook", "En 1937, des archéologues trouvent une cache secrète en Afghanistan pleine de trésors.", "v"),
        (
            "context",
            "La cache contient des ivoires. Et ensuite ils trouvent des verres romains. Puis ils trouvent des laques "
            "chinoises venues de très loin.",
            "v",
        ),
        ("context", "Les archéologues notent tout dans un carnet.", "v"),
        ("payoff", "Les pièces vont au musée de Kaboul et au musée de Paris en 1938 après un partage.", "v"),
    ]
    issues = lint_story(normalize_draft(_draft(beats=flat, hook_title={})), "fr", 75)
    text = " | ".join(issues)
    for expected in ("chute", "promesse", "conflit", "et ensuite", "hook_title manquant", "mots dits pour 75 s"):
        assert expected in text, expected


def test_lint_story_measures_hook_rhythm_ending_and_numbers():
    long_hook = [
        ("hook", "Ce gardien de phare a sauvé des centaines de navires perdus sans jamais voir la mer de ses yeux.", "v"),
        *BEATS[1:],
    ]
    assert any("accroche de" in i for i in lint_story(_draft(beats=long_hook), "fr", TARGET))
    monotone = [(p, " ".join(["Le gardien monte encore les marches du phare dans la nuit noire."] * 2), v) for p, _, v in BEATS]
    assert any("rythme monotone" in i for i in lint_story(_draft(beats=monotone), "fr", TARGET))
    long_end = [*BEATS[:-1], ("ending", "Et son frère, lui, n'est jamais revenu de la mer ce soir-là, ni les suivants.", "v")]
    assert any("chute de" in i for i in lint_story(_draft(beats=long_end), "fr", TARGET))
    dates = [*BEATS[:3], ("conflict", "En 1891, 1892, 1893, 1894 et 1895, cinq tempêtes frappent.", "v"), *BEATS[4:]]
    assert any("nombres dans le récit" in i for i in lint_story(_draft(beats=dates), "fr", TARGET))
    late = [
        BEATS[0],
        (
            "promise",
            "Pourtant, une nuit lui a tout pris. Personne ne sait vraiment comment, ni pourquoi, ni "
            "qui aurait pu l'aider ce soir-là.",
            "v",
        ),
        *BEATS[2:],
    ]
    issues = lint_story(_draft(beats=late), "fr", TARGET)
    assert any("accroche et promesse" in i for i in issues)
    assert all("hook" not in i or "accroche" in i for i in issues)


def test_story_only_issues_leave_out_what_lint_script_checks():
    long_hook = [
        ("hook", "Ce gardien de phare a sauvé des centaines de navires perdus sans jamais voir la mer de ses yeux.", "v"),
        *BEATS[1:],
    ]
    only = lint_story(_draft(beats=long_hook), "fr", TARGET, shared=False)
    assert not any("accroche de" in i for i in only)  # lint_script le dira sur la scène 1


# ---------------------------------------------------------------------------
# Découpage et assemblage
# ---------------------------------------------------------------------------


def test_split_keeps_every_word_and_never_crosses_two_beats():
    d = normalize_draft(_draft())
    chunks = split_scenes(d)
    assert " ".join(c.text for c in chunks) == " ".join(b.text for b in d.beats)  # mot pour mot
    assert chunks[0].text == BEATS[0][1] and chunks[0].role == "hook"  # l'accroche seule
    assert chunks[1].part == "promise" and chunks[1].role == "setup"
    assert chunks[2].part == "context" and chunks[2].role == "reveal"  # première réponse, avant 12 s
    assert chunks[-1].role == "loop" and chunks[-1].text == "Son frère n'était pas dedans."
    for c in chunks:
        assert c.text in d.beats[c.beat].text
        assert c.said <= SCENE_WORDS_MAX or len(sentences(c.text)) == 1
        assert c.duration_s == scene_seconds(c.said)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_scene_length_follows_the_voice():
    assert scene_seconds(15) == 5.2  # 15 mots à 3,2 mots/s + 0,45 s de silence, au dixième supérieur
    assert scene_seconds(3) == 2.0  # jamais moins de 2 s
    assert scene_seconds(40) == 8.0  # jamais plus de 8 s (ScriptScene)
    for n in range(4, 21):  # le correcteur (3 mots par seconde) accepte toujours la durée calculée
        assert n <= int(scene_seconds(n) * 3)


def test_build_script_keeps_the_story_word_for_word():
    d = normalize_draft(_draft())
    chunks = split_scenes(d)
    script = build_script(d, chunks, _shots(len(chunks), map_at=2), "fr", ["fr"], title="Le gardien")
    assert [s.narration["fr"] for s in script.scenes] == [c.text for c in chunks]
    assert script.story == d and script.hook_title == {"fr": "Il n'a jamais vu la mer"}
    assert [s.is_map for s in script.scenes].count(True) == 1 and script.scenes[2].is_map
    assert script.scenes[0].continues_previous is False and script.scenes[-1].continues_previous is False
    assert script.scenes[0].on_screen_text == {"fr": "300 navires"}
    assert script.design_bible and script.music_mood == "emotional" and script.loop_note == "retour au phare"
    assert lint_script(script, ["fr"], TARGET) == []


def test_a_map_on_the_hook_moves_to_the_context():
    d = normalize_draft(_draft())
    chunks = split_scenes(d)
    script = build_script(d, chunks, _shots(len(chunks), map_at=0), "fr", ["fr"])  # cartes proposées aux scènes 0 et 2
    assert not script.scenes[0].is_map and script.scenes[2].is_map  # l'accroche montre le sujet, la carte situe
    only_hook = _shots(len(chunks))
    only_hook.shots[0].map = (
        only_hook.shots[0].map
        or type(only_hook.shots[0]).model_validate({"index": 0, "visual_prompt": "v", "map": {"place": "Phare du Créach"}}).map
    )
    moved = build_script(d, chunks, only_hook, "fr", ["fr"])
    assert [s.index for s in moved.scenes if s.is_map] == [chunks[2].index] and chunks[2].role == "reveal"


def test_a_missing_shot_falls_back_on_what_the_storyteller_wanted_to_show():
    d = normalize_draft(_draft())
    chunks = split_scenes(d)
    shots = _shots(len(chunks), skip={3})
    assert missing_shots(chunks, shots) == [3]
    long_text = shots.model_copy(update={"metadata": {}})
    long_text.shots[0].on_screen_text = {"fr": "trois cents navires sauvés en une seule nuit"}
    script = build_script(d, chunks, long_text, "fr", ["fr"], title="Le gardien")
    assert script.scenes[3].visual_prompt == chunks[3].show
    assert script.scenes[0].on_screen_text == {}  # plus de 5 mots : retiré
    assert script.metadata["fr"].title == "Il n'a jamais vu la mer"


def test_listings_and_published_examples():
    d = normalize_draft(_draft())
    listing = story_listing(d)
    assert "Dernière phrase, écrite en premier : Son frère n'était pas dedans." in listing and "[contexte]" in listing
    chunks = split_scenes(d)
    script = build_script(d, chunks, _shots(len(chunks)), "fr", ["fr"])
    assert told_story(script.model_dump()) == " ".join(b.text for b in d.beats)
    old = {"scenes": [{"narration": {"fr": "Une phrase."}}, {"narration": {"fr": "Une autre."}}]}
    assert told_story(old) == "Une phrase. Une autre." and told_story(None) == ""


def test_the_story_is_split_again_when_it_is_too_long():
    many = [("hook", BEATS[0][1], "v"), ("promise", BEATS[1][1], "v")]
    many += [("conflict", "Mais le vent revient. Donc il remonte.", "v") for _ in range(15)]
    many += [("ending", "Son frère n'était pas dedans.", "v")]
    chunks = split_scenes(_draft(beats=many))
    assert len(chunks) <= 24


# ---------------------------------------------------------------------------
# Déroulé de l'étape script : conteur → relecteur → réécriture → réalisateur
# ---------------------------------------------------------------------------


class FakeDb:
    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        return None  # ni prompt en base, ni série

    def fetch_all(self, sql: str, params: Any = None) -> list[dict]:
        return []

    def heartbeat(self, *a: Any) -> None:
        pass

    def log(self, job_id: Any, level: str, message: str, data: Any) -> None:
        pass


class StoryLlm:
    """Premier récit plat (une liste de faits), relecture qui le refuse ou l'accepte, réécriture qui raconte ; le
    réalisateur peut oublier une scène la première fois."""

    def __init__(
        self, review: ScriptReview | Exception | list[ScriptReview], flat_first: bool = True, forget: set[int] | None = None
    ) -> None:
        self.reviews = review if isinstance(review, list) else [review]
        self.flat_first, self.forget, self.calls = flat_first, forget, []

    def complete_json(self, system: str, user: str, schema: type) -> Any:
        self.calls.append((schema.__name__, user))
        if schema is ScriptReview:  # une relecture par réponse de la liste ; la dernière se répète
            review = self.reviews.pop(0) if len(self.reviews) > 1 else self.reviews[0]
            if isinstance(review, Exception):
                raise review
            return review
        if schema is StoryDraft:
            writes = sum(1 for name, _ in self.calls if name == "StoryDraft")
            if writes == 1 and self.flat_first:
                flat = [*BEATS[:3], ("conflict", "Et ensuite une tempête arrive. Puis le feu s'éteint.", "v"), *BEATS[4:]]
                return _draft(beats=flat)
            return _draft()
        assert schema is ShotList
        n = len(split_scenes(normalize_draft(_draft())))
        first = sum(1 for name, _ in self.calls if name == "ShotList") == 1
        return _shots(n, skip=self.forget if first else None)


def _prod() -> dict[str, Any]:
    return {
        "concept_id": None,
        "title": "Le gardien",
        "hook": "h",
        "angle": None,
        "premise": "p",
        "category": "history",
        "visual_beats": [],
        "facts": [{"claim": "Le phare est allumé en 1890", "source": 0}],
        "sources": [{"title": "Phare", "url": "u", "lang": "fr", "kind": "wikipedia"}],
        "target_duration_s": TARGET,
        "format": "A_voiceover",
        "style_preset": "history_cinematic",
    }


def _ctx(tmp_path: Path) -> Context:
    job = Job(id=uuid.uuid4(), type="script", status="running", priority=100, created_at=datetime.now(UTC))
    settings = Settings(database_url="postgresql://x", supabase_url="http://x", supabase_service_role_key="x", data_dir=tmp_path)
    return Context(job=job, db=FakeDb(), settings=settings)  # type: ignore[arg-type]


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, llm: StoryLlm) -> tuple[Any, list[str]]:
    monkeypatch.setattr(script_step, "get_llm", lambda s, d, writer=False: llm)
    monkeypatch.setattr(script_step, "source_dossier", lambda *a, **k: "[1] Phare — la tempête de 1890")
    script, issues, _ = script_step.ScriptStep()._write(_ctx(tmp_path), _prod(), ["fr"])
    return script, issues


def test_review_problems_send_the_story_back_and_the_rewrite_is_read_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    refused = ScriptReview(ok=False, problems=["temps 4 : les faits sont juxtaposés, relie la tempête au feu par « donc »"])
    llm = StoryLlm([refused, ScriptReview(ok=True)])
    script, issues = _run(tmp_path, monkeypatch, llm)
    names = [n for n, _ in llm.calls]
    assert names == ["StoryDraft", "ScriptReview", "StoryDraft", "ScriptReview", "ShotList"]
    assert "DOSSIER" in llm.calls[0][1] and "DURÉE VISÉE : 40 s" in llm.calls[0][1] and "RÈGLES DU RÉCIT" in llm.calls[0][1]
    assert "relie la tempête au feu" in llm.calls[2][1] and "et ensuite" in llm.calls[2][1]  # relecture et correcteur
    assert "HISTOIRE À RELIRE" in llm.calls[1][1] and "HISTOIRE À RELIRE" in llm.calls[3][1]  # la réécriture est relue
    assert "SCÈNES À FILMER" in llm.calls[4][1]
    assert issues == [] and script.story is not None
    assert " ".join(s.narration["fr"] for s in script.scenes) == " ".join(t for _, t, _ in BEATS)


def test_two_rewrites_at_most_the_second_is_not_read_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    llm = StoryLlm(ScriptReview(ok=False, problems=["temps 3 : un détail inventé (« il pleurait »), le dossier ne le dit pas"]))
    _run(tmp_path, monkeypatch, llm)
    assert [n for n, _ in llm.calls] == ["StoryDraft", "ScriptReview", "StoryDraft", "ScriptReview", "StoryDraft", "ShotList"]
    assert "il pleurait" in llm.calls[4][1]  # la 2e réécriture reçoit la 2e relecture


def test_measurable_issues_alone_get_a_form_only_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    llm = StoryLlm(ScriptReview(ok=True))  # le fond est validé, le premier récit garde « et ensuite »
    _, issues = _run(tmp_path, monkeypatch, llm)
    assert [n for n, _ in llm.calls] == ["StoryDraft", "ScriptReview", "StoryDraft", "ShotList"] and issues == []
    assert "écarts de FORME" in llm.calls[2][1] and "sans toucher au fond" in llm.calls[2][1] and "et ensuite" in llm.calls[2][1]


def test_an_approving_or_failing_review_keeps_a_clean_story(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for review in (ScriptReview(ok=True, problems=["détail"]), RuntimeError("quota")):
        llm = StoryLlm(review, flat_first=False)
        _, issues = _run(tmp_path, monkeypatch, llm)
        assert [n for n, _ in llm.calls] == ["StoryDraft", "ScriptReview", "ShotList"] and issues == []


def test_a_forgotten_scene_is_asked_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    llm = StoryLlm(ScriptReview(ok=True), flat_first=False, forget={4})
    script, _ = _run(tmp_path, monkeypatch, llm)
    assert [n for n, _ in llm.calls] == ["StoryDraft", "ScriptReview", "ShotList", "ShotList"]
    assert "oublie les scènes [4]" in llm.calls[-1][1] and script.scenes[4].visual_prompt.startswith("shot 4")


class Model:
    """Un choix de la chaîne d'écriture : répond, ou échoue (erreur non passagère : pas de second tour)."""

    def __init__(self, model: str, ok: bool = True) -> None:
        self.name, self.model, self.ok, self.calls = "gemini", model, ok, 0

    def complete_json(self, system: str, user: str, schema: type) -> Any:
        self.calls += 1
        if not self.ok:
            raise ValueError("réponse illisible")
        return ScriptReview(ok=True)


def test_the_storyteller_writes_with_strong_models_only():
    from worker.providers.llm import FallbackLLM

    strong, lite = Model("gemini-3.8-flash"), Model("gemini-3.5-flash-lite")
    chain = FallbackLLM([strong, lite])
    teller = script_step.strong_writers(chain)
    assert [p.model for p in teller.chain] == ["gemini-3.8-flash"]  # type: ignore[attr-defined]
    only_lite = FallbackLLM([Model("gemini-3.5-flash-lite")])
    assert script_step.strong_writers(only_lite) is only_lite  # rien d'autre : on garde le secours
    fake = StoryLlm(ScriptReview(ok=True))
    assert script_step.strong_writers(fake) is fake  # doublure sans chaîne


def test_the_storyteller_waits_for_a_strong_model_then_settles(tmp_path: Path):
    from datetime import timedelta

    from worker.postpone import Postpone
    from worker.providers.llm import FallbackLLM

    down, lite = Model("gemini-3.8-flash", ok=False), Model("gemini-3.5-flash-lite")
    chain = FallbackLLM([down, lite])
    ctx = _ctx(tmp_path)
    ask = script_step.ScriptStep._asker(ctx, script_step.strong_writers(chain), chain)
    with pytest.raises(Postpone) as later:
        ask("s", "u", ScriptReview)
    assert later.value.delay_s == script_step.STRONG_WAIT_S and lite.calls == 0  # le secours n'a pas écrit
    ctx.job.created_at -= script_step.STRONG_WAIT_MAX + timedelta(minutes=1)  # 12 h d'attente : on se contente du secours
    assert ask("s", "u", ScriptReview).ok and lite.calls == 1


def test_a_real_count_of_said_words():
    # « 1890 » se dit « mille huit cent quatre-vingt-dix » : 4 mots, comptés par le correcteur comme par la voix
    assert len(said_words("en 1890")) == 5


# ---------------------------------------------------------------------------
# Scène réinventée d'un récit : les consignes du réalisateur, sans sa consigne de réponse
# ---------------------------------------------------------------------------


def test_scene_rewrite_reads_the_director_without_his_answer_format():
    shots = code_prompts()["script_shots"]
    kept = reinvent._WHOLE_SCRIPT.sub("", shots).strip()
    assert "Réponds uniquement" not in kept and "visual_prompt" in kept
    drama = reinvent._WHOLE_SCRIPT.sub("", code_prompts()["script_drama"]).strip()
    assert not drama.endswith("ScriptV1.") and "DISTRIBUTION" in drama
    assert "RÉCIT : tu écris AUSSI la narration" in reinvent.FORMAT_HINTS["story"]
