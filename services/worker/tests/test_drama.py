"""Recette « drame » (worker/drama.py, docs/35) : personnages et répliques, correcteur, prompts d'image avec les fiches en
références, prompt du clip qui fait parler le personnage, sous-titres calés sur la voix entendue, voix constantes, et
le storyboard qui fait les fiches avant les plans. Base, ComfyUI et LLM remplacés par des doublures."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from worker import drama
from worker.config import Settings
from worker.models import CastMember, Job, SceneDraft, ScriptV1
from worker.prompts import code_prompts
from worker.providers.video import add_references, supports_references
from worker.recipes import has_prompt, lint_recipe_script, montage_format, normalize_script
from worker.reinvent import apply_rewrite
from worker.steps import storyboard as sb
from worker.steps.base import Context

WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"

CAST = [
    {
        "key": "Kiwi",
        "name": "Kiwi",
        "role": "victime",
        "voice": "a soft trembling young male voice",
        "look": "a young taxi driver whose head is a round brown fuzzy kiwi fruit, tired green eyes, worn grey hoodie, flat cap",
    },
    {
        "key": "prune",
        "name": "Prune",
        "role": "méchant",
        "voice": "a sweet fake male voice of a butler in his thirties",
        "look": "a tall thin butler whose head is a glossy dark violet plum with a short stem, thin mustache, black tailcoat",
    },
    {
        "key": "madame_figue",
        "name": "Madame Figue",
        "role": "juge",
        "voice": "a warm elderly female voice",
        "look": "an elderly rich widow whose head is a deep purple fig with a curled stem, round gold glasses, pearl necklace",
    },
]


def _scene(i: int, who: str | None = None, text: str = "", chars: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "index": i,
        "duration_s": 4,
        "visual_prompt": f"shot {i}",
        "motion_prompt": f"move {i}",
        "characters": chars if chars is not None else ([who] if who else []),
        "lines": [{"who": who, "text": text, "tone": "trembling"}] if who else [],
        **extra,
    }


def _script(scenes: list[dict[str, Any]] | None = None, cast: list[dict[str, Any]] | None = None) -> ScriptV1:
    scenes = (
        scenes
        if scenes is not None
        else [_scene(i, ["Kiwi", "prune", "madame_figue"][i % 3], "Cinquante mille euros. Je vais le rendre.") for i in range(16)]
    )
    scenes = scenes + [_scene(100 + k) for k in range(4 - len(scenes))]  # ScriptV1 : 4 scènes au moins (plans muets)
    return ScriptV1.model_validate(
        {
            "scenes": scenes,
            "cast": cast if cast is not None else CAST,
            "metadata": {"fr": {"title": "t", "description": "d"}},
            "hook_title": {"fr": "Elle oublie 50 000 € dans un taxi"},
        }
    )


def test_drama_is_a_recipe_with_its_own_writer_and_is_edited_like_a_story():
    assert has_prompt("drama") and has_prompt("tour") and not has_prompt("story")
    assert montage_format("drama") == "story" and montage_format("tour") == "tour" and montage_format(None) == "story"
    prompts = code_prompts()
    assert "script_drama" in prompts and "guide_drama" in prompts and "tts_voice" in prompts["script_drama"]


def test_normalize_resolves_characters_merges_a_speakers_lines_and_times_the_scene():
    s = _script(
        [
            {
                "index": 7,
                "duration_s": 8,
                "visual_prompt": "v",
                "characters": "Madame Figue, prune",
                "lines": [{"who": "Kiwi", "text": "Cinquante mille."}, {"who": "kiwi", "text": "Je le rends."}],
            },
            {"index": 8, "duration_s": 7, "visual_prompt": "v", "characters": [], "lines": []},
        ]
    )
    n = normalize_script(s, "drama")
    first, second = n.scenes[:2]
    assert [m.key for m in n.cast] == ["kiwi", "prune", "madame_figue"]
    assert first.index == 0 and first.characters == ["kiwi", "madame_figue", "prune"]  # celui qui parle d'abord, 3 au plus
    # nombres en chiffres à l'écran, groupés par une espace insécable (docs/33)
    assert len(first.lines) == 1 and first.lines[0].text == "50\xa0000. Je le rends."
    assert first.duration_s == pytest.approx(0.8 + 5 / drama.DIALOGUE_WPS)
    # ce qui est dit et écrit : la réplique seule, jamais « Kiwi : » (règle de Luca, 29/09) ; qui parle reste dans lines
    assert first.narration["fr"] == "50\xa0000. Je le rends."
    assert drama.speaker_line(n, first) == "Kiwi : 50\xa0000. Je le rends." and drama.speaker_line(n, second) == ""
    assert second.duration_s == drama.CLIP_S and second.narration == {} and not second.continues_previous


def test_a_speaker_label_copied_into_a_line_is_never_said_nor_written():
    s = normalize_script(
        _script(
            [
                _scene(0, "kiwi", "Kiwi : Je vais le rendre."),
                _scene(1, "madame_figue", "MADAME (off) : « Personne ne le saura. »"),
                _scene(2, "prune", "Maman a dit : sois gentil."),  # pas une étiquette : « Maman a dit » n'est personne
            ]
        ),
        "drama",
    )
    assert [sc.lines[0].text for sc in s.scenes[:3]] == [
        "Je vais le rendre.",
        "Personne ne le saura.",
        "Maman a dit : sois gentil.",
    ]
    assert s.scenes[0].narration["fr"] == "Je vais le rendre."


def test_a_good_drama_passes_the_linter():
    s = normalize_script(_script(), "drama")
    assert lint_recipe_script(s, "drama", ["fr"], 70) == []


def test_the_linter_catches_what_breaks_a_drama():
    scenes = [
        _scene(0, "kiwi", " ".join(["mot"] * 13)),
        _scene(1, "inconnu", "Qui suis-je ?"),
        {
            **_scene(2),
            "lines": [{"who": "kiwi", "text": "Oui."}, {"who": "prune", "text": "Non."}],
            "characters": ["kiwi", "prune"],
        },
        _scene(3),
        _scene(4),
        _scene(5),
    ]
    cast = [{**CAST[0], "voice": ""}, {**CAST[1], "look": "a plum"}]
    issues = drama.lint(drama.normalize(_script(scenes, cast)), ["fr"], 70)
    text = " | ".join(issues)
    for expected in (
        "6 scènes",
        "personnage Prune : look trop court",
        "voice manquante",
        "réplique de 13 mots",
        "absents du cast ['inconnu']",
        "plusieurs personnages parlent",
        "répliques sur 3 plans sur 6",
        "durée",
    ):
        assert expected in text, expected


def test_scene_prompt_cites_the_reference_sheets_or_describes_the_characters():
    s = drama.normalize(_script([_scene(0, "kiwi", "Non.", chars=["kiwi", "prune"])]))
    with_refs = drama.scene_prompt(s, 0, ["kiwi", "prune"])
    assert "Use <image1>, <image2> only as character references" in with_refs
    assert "Kiwi is the character of <image1>; Prune is the character of <image2>" in with_refs
    assert "glasses" not in with_refs  # un accessoire nommé dans la consigne apparaît sur tout le monde
    assert "half as tall" not in with_refs  # des adultes : pas d'indication de taille
    pup = CastMember(key="tom", name="Tom", look="an anthropomorphic golden retriever puppy, about 8 years old, red cap")
    s.cast.append(pup)
    assert "Tom is the character of <image2>, a small child about half as tall as the adults" in drama.scene_prompt(
        s, 0, ["kiwi", "tom"]
    )
    alone = drama.scene_prompt(s, 0)
    assert alone.startswith("shot 0. Characters: Kiwi: a young taxi driver") and "Prune: a tall thin butler" in alone
    assert drama.sheet_prompt(s.cast[0]).startswith("Character design reference sheet")


def test_clip_prompt_makes_the_character_say_the_line_in_words():
    s = drama.normalize(_script([_scene(0, "kiwi", "Cinquante mille euros."), _scene(1)]))
    p = drama.clip_prompt(s, 0, "fr", "pixar_fruit")
    assert p.startswith("3D animated Pixar-style film with anthropomorphic fruit characters. move 0.")
    assert 'Kiwi says in French, in a soft trembling young male voice: "cinquante mille euros."' in p  # ton déjà dans la voix
    assert "Nobody speaks" in drama.clip_prompt(s, 1, "fr", "pixar_fruit")
    s.scenes[0].lines[0].tone = "Trembling, stunned whisper."
    assert 'young male voice, stunned whisper: "' in drama.clip_prompt(s, 0, "fr", "pixar_fruit")


def test_heard_words_are_glued_like_the_script_and_timed_on_the_voice():
    heard = [
        {"w": "Ah", "start": 0.0, "end": 0.4},
        {"w": "50", "start": 0.9, "end": 1.3},
        {"w": "000", "start": 1.3, "end": 1.85},
        {"w": "L", "start": 2.2, "end": 2.3},
        {"w": "'opération", "start": 2.3, "end": 3.0},
        {"w": "coûte", "start": 3.88, "end": 4.14},
        {"w": "30", "start": 4.14, "end": 4.42},
    ]
    text = "50 000… L'opération en coûte 30 ?"
    assert drama.heard_ratio(text, "Ah ! 50 000 ! L 'opération en coûte 30 !") > 0.9
    words = drama.align_words(text, heard, "fr", 10.0)
    assert [w.text for w in words] == ["50 000…", "L'opération", "en", "coûte", "30 ?"]
    assert words[0].start == 10.9 and words[1].start == 12.2 and 13.0 <= words[2].start < words[3].start == 13.88
    far = drama.align_words("Rien à voir avec ça", heard, "fr")  # transcription sans rapport : répartie sur la voix
    assert far[0].start == 0.0 and far[-1].end == pytest.approx(4.42, abs=0.01)


def test_dialogue_timeline_stretches_a_scene_to_its_last_word_but_never_past_its_clip():
    s = drama.normalize(_script([_scene(0, "kiwi", "Oui."), _scene(1), _scene(2, "prune", "Non merci.")]))
    heard = {"words": [{"w": "Oui", "start": 0.3, "end": 2.9}]}
    tl = drama.dialogue_timeline(
        s, "fr", [{"duration": 5.17, "dialogue": heard}, {"duration": 5.17}, {"duration": 3.0}, {"duration": 5.17}]
    )
    a, b, c, _ = tl.scenes
    assert a.duration == pytest.approx(2.9 + drama.TAIL_S) and a.words[0].start == 0.3 and tl.aligner == "whisper"
    assert b.start == pytest.approx(a.duration) and b.words == []
    assert c.duration <= 3.0 and c.words and c.words[0].start >= c.start  # sans transcription : réplique répartie


def test_voices_follow_the_writer_then_the_description_and_are_not_shared():
    cast = [
        CastMember(key="a", name="A", look="x", voice="a warm elderly female voice"),
        CastMember(key="b", name="B", look="x", voice="an authoritative rich boss", tts_voice="qwen3:perso_mamie"),
        CastMember(key="c", name="C", look="x", voice="a shy ten-year-old girl"),
    ]
    available = ["qwen3:perso_mamie", "qwen3:perso_patron", "qwen3:perso_fillette", "qwen3:perso_jeune_femme"]
    voices = drama.assign_voices(cast, available)
    assert voices == {"b": "qwen3:perso_mamie", "a": "qwen3:perso_jeune_femme", "c": "qwen3:perso_fillette"}
    catalog = json.loads((WORKFLOWS / "catalog.json").read_text(encoding="utf-8"))
    listed = drama.character_voices(catalog, "fr")
    assert next(iter(listed)).startswith("qwen3:perso_") and "qwen3:narrateur" in listed
    assert "tts_voice" in drama.voices_brief(listed)


def test_qwen_image_21_takes_reference_images():
    wf = json.loads((WORKFLOWS / "qwen_image_21.json").read_text(encoding="utf-8"))
    assert supports_references(wf)
    add_references(wf, ["a.png", "b.png"])
    enc = next(n for n in wf.values() if n["class_type"] == "TextEncodeQwenImage21")["inputs"]
    loaders = {k: n for k, n in wf.items() if n["class_type"] == "LoadImage"}
    assert enc["vae"] == ["3", 0] and enc["resolution"] == 768
    assert [loaders[enc["images.image_1"][0]]["inputs"]["image"], loaders[enc["images.image_2"][0]]["inputs"]["image"]] == [
        "a.png",
        "b.png",
    ]
    assert not supports_references(json.loads((WORKFLOWS / "zimage_turbo.json").read_text(encoding="utf-8")))


def test_reinventing_a_drama_scene_keeps_one_line_and_its_characters():
    s = drama.normalize(_script())
    draft = SceneDraft(
        visual_prompt="Kiwi, desperate, alone in a police cell",
        motion_prompt="a tear rolls down",
        characters=["kiwi"],
        lines=[{"who": "Kiwi", "text": "Pourquoi personne ne me croit ?"}],
    )
    out = apply_rewrite(s, 2, draft, "drama")
    assert out.scenes[2].characters == ["kiwi"] and out.scenes[2].lines[0].who == "kiwi"
    assert out.scenes[2].narration["fr"] == "Pourquoi personne ne me croit ?"


# ---------------------------------------------------------------------------
# Storyboard : les fiches des personnages d'abord, puis chaque plan avec les siennes en références
# ---------------------------------------------------------------------------


class FakeDb:
    def __init__(self, script: ScriptV1) -> None:
        self.script = script
        self.assets: list[dict[str, Any]] = []
        self.status: str | None = None

    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        if "from productions p" in sql and "p.script" in sql:
            return {
                "script": self.script.model_dump(),
                "style_preset": "pixar_fruit",
                "image_workflow": "qwen_image_21",
                "title": "t",
            }
        if "coalesce(s.recipe" in sql:
            return {"recipe": "drama"}
        if "kind = 'character'" in sql:
            rows = [a for a in self.assets if a["kind"] == "character" and a["meta"]["key"] == params[1] and a["selected"]]
            return {"local_path": rows[-1]["local_path"]} if rows else None
        if "count(*)" in sql:
            return {"n": sum(a["kind"] == "storyboard" and a["scene_index"] == params[1] for a in self.assets)}
        return None

    def fetch_all(self, sql: str, params: Any = None) -> list[dict]:
        return []

    def execute(self, sql: str, params: Any = None) -> int:
        if "kind = 'character'" in sql and "set selected" in sql:
            for a in self.assets:
                if a["kind"] == "character" and a["meta"]["key"] == params[2]:
                    a["selected"] = a["id"] == params[0]
        elif "set selected = (id = %s)" in sql:
            for a in self.assets:
                if a["kind"] == "storyboard" and a["scene_index"] == params[2]:
                    a["selected"] = a["id"] == params[0]
        return 1

    def add_asset(self, **cols: Any) -> uuid.UUID:
        aid = uuid.uuid4()
        self.assets.append({"id": aid, "scene_index": None, **cols})
        return aid

    def heartbeat(self, *a: Any, **k: Any) -> bool:
        return True

    def log(self, *a: Any, **k: Any) -> None:
        pass

    def set_status(self, table: str, id_: Any, status: str, error: str | None = None) -> None:
        self.status = status

    def alert(self, *a: Any, **k: Any) -> uuid.UUID:
        return uuid.uuid4()


class FakeImage:
    calls: list[tuple[str, list[str], str]] = []

    def __init__(self, settings: Any, workflow: str | None = None) -> None:
        self.name, self.width, self.height, self.references = "fake_qwen", 768, 1344, True

    def generate(
        self, *, prompt: str, style_preset: Any, out_path: Path, seed: int, dry_run: bool = False, refs: list[Path] | None = None
    ) -> Path:
        FakeImage.calls.append((out_path.name.rsplit("_", 1)[0], [p.name.rsplit("_", 1)[0] for p in refs or []], prompt))
        out_path.write_bytes(b"png")
        return out_path


def _storyboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: ScriptV1, payload: dict | None = None, db: FakeDb | None = None
) -> FakeDb:
    FakeImage.calls = []
    monkeypatch.setattr(sb, "ComfyImage", FakeImage)
    monkeypatch.setattr(sb, "build_sheet", lambda *a, **k: None)
    monkeypatch.setattr(
        sb,
        "load_generation_config",
        lambda s, d: type("G", (), {"image_workflow": "qwen_image_21", "storyboard_candidates": 1})(),
    )
    db = db or FakeDb(script)
    cfg = Settings(database_url="postgresql://x", supabase_url="http://x", supabase_service_role_key="x", data_dir=tmp_path)
    job = Job(
        id=uuid.uuid4(),
        type="storyboard",
        status="running",
        priority=90,
        production_id=uuid.uuid4(),
        payload=payload or {},
        created_at=datetime.now(UTC),
    )
    sb.StoryboardStep().run(Context(job=job, db=db, settings=cfg))  # type: ignore[arg-type]
    return db


def test_storyboard_makes_each_sheet_then_each_shot_with_its_characters_sheets(tmp_path, monkeypatch):
    s = drama.normalize(
        _script([_scene(0, "kiwi", "Oui.", chars=["kiwi", "prune"]), _scene(1, "madame_figue", "Non."), _scene(2)])
    )
    db = _storyboard(tmp_path, monkeypatch, s)
    names = [c[0] for c in FakeImage.calls]
    assert names == [
        "character_kiwi",
        "character_prune",
        "character_madame_figue",
        "scene_00",
        "scene_01",
        "scene_02",
        "scene_03",
    ]
    assert FakeImage.calls[3][1] == ["character_kiwi", "character_prune"] and "<image2>" in FakeImage.calls[3][2]
    assert FakeImage.calls[4][1] == ["character_madame_figue"] and FakeImage.calls[5][1] == []
    assert sum(a["kind"] == "character" and a["selected"] for a in db.assets) == 3
    assert db.status == "storyboard_review"  # Luca valide les personnages et les plans


def test_redoing_a_character_redoes_its_sheet_and_the_shots_where_it_appears(tmp_path, monkeypatch):
    s = drama.normalize(_script([_scene(0, "kiwi", "Oui."), _scene(1, "prune", "Non."), _scene(2, "kiwi", "Si.")]))
    db = _storyboard(tmp_path, monkeypatch, s)
    _storyboard(tmp_path, monkeypatch, s, {"characters": ["Kiwi"]}, db=db)
    assert [c[0] for c in FakeImage.calls] == ["character_kiwi", "scene_00", "scene_02"]


def test_constant_voices_say_each_line_with_its_characters_voice_on_one_track(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    sf = pytest.importorskip("soundfile")
    from types import SimpleNamespace

    from worker.providers.tts import Speech
    from worker.steps import tts as tts_step

    s = drama.normalize(
        _script(
            [
                _scene(0, "kiwi", "Cinquante mille euros."),
                _scene(1, "prune", "Personne ne saura."),
                _scene(2),
                _scene(3, "kiwi", "Je vais le rendre."),
            ]
        )
    )
    said: list[tuple[str, list[str]]] = []
    tones_seen: list[list[str]] = []

    class Engine:  # deux moteurs de fréquences différentes : la piste suit la première
        def __init__(self, rate: int) -> None:
            self.rate = rate

        def speak_many(
            self, texts: list[str], *, voice: str, lang: str, speed: float, tones: list[str] | None = None
        ) -> list[Speech]:
            said.append((voice, list(texts)))
            tones_seen.append(list(tones or []))
            return [
                Speech(samples=np.full(int(self.rate * 0.5), 0.2, dtype="float32"), rate=self.rate, voice=voice) for _ in texts
            ]

    catalog = {"voices": {"fr": [{"id": "qwen3:perso_humble"}, {"id": "qwen3:perso_patron"}, {"id": "qwen3:mystere"}]}}
    monkeypatch.setattr(tts_step, "recipe_for_production", lambda db, pid: "drama")
    monkeypatch.setattr(tts_step, "tts_catalog", lambda settings: catalog)
    monkeypatch.setattr(
        tts_step,
        "load_generation_config",
        lambda settings, db: SimpleNamespace(voices={"fr": "kokoro:ff_siwis"}, voice_acting="neutral"),
    )
    monkeypatch.setattr(tts_step, "get_engine", lambda settings, engine: Engine(24000 if not said else 22050))
    saved: list[Any] = []

    class Db:
        def fetch_one(self, sql: str, params: Any = None) -> dict:
            return {"lang": "fr", "timeline": None, "production_id": "p", "script": s.model_dump(), "voice_speed": 1.0}

        def add_asset(self, **cols: Any) -> str:
            return "a"

        def execute(self, sql: str, params: Any = None) -> int:
            saved.append(params)
            return 1

    ctx = SimpleNamespace(
        job=SimpleNamespace(video_id="v", payload={}),
        db=Db(),
        settings=SimpleNamespace(dry_run=False, kokoro_speed=1.0),
        video_dir=lambda vid: tmp_path,
        progress=lambda *a: None,
        log=lambda *a, **k: None,
    )
    result = tts_step.TTSStep().run(ctx)
    # chiffres à l'écran (normalize) ; le moteur les redit en lettres (providers/tts.py : spoken)
    assert said == [("perso_humble", ["50 000 euros.", "Je vais le rendre."]), ("mystere", ["Personne ne saura."])]
    assert tones_seen == [["trembling", "trembling"], ["trembling"]]  # le ton de chaque réplique va au moteur (docs/41)
    assert result["voices"] == {"kiwi": "qwen3:perso_humble", "prune": "qwen3:mystere", "madame_figue": "qwen3:perso_patron"}
    audio, rate = sf.read(str(tmp_path / "narration.wav"))
    assert rate == 24000 and len(audio) / rate == pytest.approx(result["duration_s"], abs=0.05)
    assert saved[-1][0] == "drama" and "kiwi=qwen3:perso_humble" in saved[-1][1]  # videos.tts_provider, tts_voice


def test_a_retouch_redoes_each_characters_voice_with_gemini(tmp_path, monkeypatch):
    """Retoucher → Voix → « Voix des personnages » (docs/41 §8) : payload voice = « acting:gemini ». Chaque personnage
    garde sa voix (la voix Qwen du script, dite par Gemini), avec la description du personnage devant le ton de la
    réplique et la durée de la bouche de son clip ; la voix est refaite même si elle existe déjà."""
    np = pytest.importorskip("numpy")
    pytest.importorskip("soundfile")
    from types import SimpleNamespace

    from worker.providers.tts import Speech
    from worker.steps import tts as tts_step

    s = drama.normalize(
        _script([_scene(0, "kiwi", "Cinquante mille euros."), _scene(1, "prune", "Personne ne saura."), _scene(2)])
    )
    calls: list[tuple[str, str, list[str], list[float | None]]] = []

    class Engine:
        def __init__(self, name: str) -> None:
            self.name = name

        def speak_many(self, texts, *, voice, lang, speed, tones=None, targets=None) -> list[Speech]:
            calls.append((self.name, voice, list(tones or []), list(targets or [])))
            return [Speech(samples=np.full(12000, 0.2, dtype="float32"), rate=24000, voice=voice) for _ in texts]

    acting = {"engine": "gemini", "from": "qwen3", "fallback": "qwen3_emotion", "persona": True, "narration": True}
    catalog = {
        "voices": {"fr": [{"id": "qwen3:perso_humble"}, {"id": "qwen3:perso_patron"}, {"id": "qwen3:mystere"}]},
        "acting": {"gemini": acting},
    }
    monkeypatch.setattr(tts_step, "recipe_for_production", lambda db, pid: "drama")
    monkeypatch.setattr(tts_step, "tts_catalog", lambda settings: catalog)
    monkeypatch.setattr(
        tts_step,
        "load_generation_config",
        lambda settings, db: SimpleNamespace(voices={"fr": "kokoro:ff_siwis"}, voice_acting="neutral"),
    )
    monkeypatch.setattr(tts_step, "get_engine", lambda settings, engine: Engine(engine))
    monkeypatch.setattr(tts_step, "mouth_targets", lambda db, pid, script, lang: {0: 1.8})
    (tmp_path / "narration.wav").write_bytes(b"old")

    class Db:
        def fetch_one(self, sql: str, params: Any = None) -> dict:
            return {
                "lang": "fr",
                "timeline": {"lang": "fr", "scenes": []},
                "production_id": "p",
                "retouch": {},
                "script": s.model_dump(),
                "voice_speed": 1.0,
            }

        def add_asset(self, **cols: Any) -> str:
            return "a"

        def execute(self, sql: str, params: Any = None) -> int:
            return 1

    ctx = SimpleNamespace(
        job=SimpleNamespace(video_id="v", production_id="p", payload={"voice": "acting:gemini", "retouch": True}),
        db=Db(),
        settings=SimpleNamespace(dry_run=False, kokoro_speed=1.0),
        video_dir=lambda vid: tmp_path,
        progress=lambda *a: None,
        log=lambda *a, **k: None,
    )
    result = tts_step.TTSStep().run(ctx)
    assert result["acting"] == "gemini" and result["voices"]["kiwi"] == "qwen3:perso_humble"
    by_voice = {voice: (name, tones, targets) for name, voice, tones, targets in calls}
    assert by_voice["perso_humble"] == ("gemini", ["a soft trembling young male voice; trembling"], [1.8])
    assert by_voice["mystere"][0] == "gemini" and by_voice["mystere"][2] == []  # pas de bouche connue : débit libre


def test_a_voice_retouch_says_and_writes_the_lines_alone_never_who_speaks(tmp_path, monkeypatch):
    """Bibliothèque → Retoucher → Voix (docs/34) sur un drame : une seule voix dit les répliques et les sous-titres (mots
    de la timeline) les écrivent, sans « Kiwi : » devant (règle de Luca, 29/09)."""
    np = pytest.importorskip("numpy")
    pytest.importorskip("soundfile")
    from types import SimpleNamespace

    from worker.providers.tts import Speech
    from worker.steps import tts as tts_step

    s = drama.normalize(_script([_scene(0, "kiwi", "Je vais le rendre."), _scene(1, "prune", "Personne ne saura."), _scene(2)]))
    said: list[str] = []

    class Engine:
        name = "kokoro"

        def speak_many(
            self, texts: list[str], *, voice: str, lang: str, speed: float, on_progress: Any = None, tones: Any = None
        ) -> list[Speech]:
            said.extend(texts)
            return [Speech(samples=np.full(12000, 0.2, dtype="float32"), rate=24000, voice=voice) for _ in texts]

    monkeypatch.setattr(tts_step, "recipe_for_production", lambda db, pid: "drama")
    monkeypatch.setattr(tts_step, "resolve_voice", lambda settings, voices, lang: (Engine(), voices[lang].split(":")[1]))
    saved: list[Any] = []

    class Db:
        def fetch_one(self, sql: str, params: Any = None) -> dict:
            return {"lang": "fr", "timeline": None, "production_id": "p", "script": s.model_dump(), "voice_speed": 1.0}

        def add_asset(self, **cols: Any) -> str:
            return "a"

        def execute(self, sql: str, params: Any = None) -> int:
            saved.append(params)
            return 1

    ctx = SimpleNamespace(
        job=SimpleNamespace(video_id="v", payload={"voice": "kokoro:ff_siwis"}),
        db=Db(),
        settings=SimpleNamespace(dry_run=False, kokoro_speed=1.0),
        video_dir=lambda vid: tmp_path,
        progress=lambda *a: None,
        log=lambda *a, **k: None,
    )
    result = tts_step.TTSStep().run(ctx)
    assert result["retouch"] and said == ["Je vais le rendre.", "Personne ne saura."]
    words = [w["text"] for sc in saved[-1][2].obj["scenes"] for w in sc["words"]]
    assert words and not {"Kiwi", "Kiwi :", "Prune", ":"} & set(words)
