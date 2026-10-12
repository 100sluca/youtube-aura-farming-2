"""Variante d'accroche (docs/49, worker/hookvariant.py), page du sujet ajoutée au dossier et rétention posée sur les
phrases dites (worker/metrics.py)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.test_storycraft import _draft, _shots
from tests.test_tts_engines import RUNNERS_DIR
from worker.hookvariant import check_texts, link_file, variant_script
from worker.metrics import retention_by_scene, retention_drops
from worker.sources import wikipedia
from worker.storycraft import build_script, scene_seconds, split_scenes
from worker.storytelling import said_words

HOOK = "Ce phare tient debout depuis 130 ans sans un seul gardien voyant."
PROMISE = "Pourtant, une nuit lui a tout pris."


def _script():
    d = _draft()
    return build_script(d, split_scenes(d, "fr"), _shots(len(split_scenes(d, "fr"))), "fr", ["fr"], title="Le gardien")


def test_variant_changes_only_the_opening():
    script = _script()
    out = variant_script(script, "fr", HOOK, PROMISE, "Le phare sans yeux", "Le phare sans yeux 🌊", on_screen="")
    assert out.scenes[0].narration["fr"] == HOOK
    assert out.scenes[1].narration["fr"] == PROMISE
    assert out.scenes[0].on_screen_text == {}  # "" : plus de texte gravé sur l'accroche
    assert out.scenes[0].duration_s == scene_seconds(len(said_words(HOOK, "fr")))
    assert [s.narration for s in out.scenes[2:]] == [s.narration for s in script.scenes[2:]]
    assert [s.visual_prompt for s in out.scenes] == [s.visual_prompt for s in script.scenes]
    assert out.story.beats[0].text == HOOK and out.story.beats[1].text == PROMISE
    assert out.hook_title["fr"] == "Le phare sans yeux"
    assert out.metadata["fr"].title == "Le phare sans yeux 🌊"
    assert script.scenes[0].narration["fr"] != HOOK  # le script d'origine ne bouge pas


def test_variant_keeps_the_on_screen_text_unless_asked():
    script = _script()
    kept = variant_script(script, "fr", HOOK, PROMISE, "Le phare sans yeux", "t")
    assert kept.scenes[0].on_screen_text == script.scenes[0].on_screen_text
    other = variant_script(script, "fr", HOOK, PROMISE, "Le phare sans yeux", "t", on_screen="130 ANS")
    assert other.scenes[0].on_screen_text == {"fr": "130 ANS"}


def test_variant_needs_a_story_opening():
    script = _script().model_copy(update={"story": None})
    with pytest.raises(ValueError):
        variant_script(script, "fr", HOOK, PROMISE, "Le phare sans yeux", "t")


def test_check_texts_flags_a_long_opening():
    assert check_texts(HOOK, PROMISE, "Le phare sans yeux") == []
    long = check_texts(HOOK + " Et il voit tout, même les étoiles du ciel.", PROMISE, "Le phare sans yeux")
    assert any("accroche" in i for i in long)


def test_link_file_shares_the_bytes(tmp_path: Path):
    src = tmp_path / "a" / "clip.mp4"
    src.parent.mkdir()
    src.write_bytes(b"x" * 10)
    dst = link_file(src, tmp_path / "b" / "clips" / "clip.mp4")
    assert dst.read_bytes() == src.read_bytes()
    src.unlink()  # effacer l'originale ne casse pas la variante
    assert dst.exists()


@pytest.mark.parametrize("original_voice", ["qwen3:mystere", "qwen3:serena"])
def test_variant_says_again_only_the_new_opening(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, original_voice: str):
    """02/10, Lukangol : une nouvelle accroche faisait redire les 19 plans. Les plans dont le texte n'a pas changé
    reprennent la voix de l'originale, découpée dans sa piste, sans que l'accroche plus longue déborde sur la suite ;
    une originale dite par une autre voix est redite en entier (le timbre changerait en cours de vidéo)."""
    np = pytest.importorskip("numpy")
    sf = pytest.importorskip("soundfile")
    from worker.steps import tts as tts_step
    from worker.timeline import SceneSpeech, mix_speech, plan_timeline

    rate, script = 24000, _script()
    promise = "Mais une seule nuit a suffi à tout lui prendre."
    variant = variant_script(script, "fr", HOOK, promise, "Le phare sans yeux", "t")
    # l'originale : chaque plan dit à son propre niveau, pour le reconnaître dans la piste de la variante
    level = {s.index: round(0.1 + 0.02 * s.index, 2) for s in script.scenes}
    old = {s.index: np.full(int(rate * 0.8), level[s.index], dtype=np.float32) for s in script.scenes}
    timeline = plan_timeline([SceneSpeech(s.index, s.duration_s, s.narration["fr"], 0.8) for s in script.scenes], "fr")
    (tmp_path / "videos" / "orig").mkdir(parents=True)
    sf.write(str(tmp_path / "videos" / "orig" / "narration.wav"), mix_speech(timeline, old, rate), rate)

    asked: list[str] = []

    def speak_many(texts: list[str], **kw: Any) -> list[Any]:
        asked.extend(texts)
        return [SimpleNamespace(samples=np.full(rate * 6, 0.5, dtype=np.float32), rate=rate) for _ in texts]

    monkeypatch.setattr(
        tts_step, "resolve_voice", lambda s, v, lang: (SimpleNamespace(name="qwen3", speak_many=speak_many), "mystere")
    )
    saved: list[Any] = []

    class Db:
        def fetch_one(self, sql: str, params: Any = None) -> dict:
            if "from jobs" in sql:  # le job voix de l'originale
                return {"result": {"voice": original_voice, "spoken_by": "qwen3"}}
            if "recipe" in sql:
                return {"recipe": "story"}
            if "voice_speed" in sql:  # la variante
                return {
                    "lang": "fr",
                    "timeline": None,
                    "production_id": "p",
                    "script": variant.model_dump(mode="json"),
                    "voice_speed": 1,
                }
            return {"lang": "fr", "timeline": timeline.model_dump(), "script": script.model_dump(mode="json")}

        def add_asset(self, **cols: Any) -> str:
            return "a"

        def execute(self, sql: str, params: Any = None) -> int:
            saved.append(params)
            return 1

    out = tmp_path / "videos" / "variante"
    out.mkdir()
    ctx = SimpleNamespace(
        job=SimpleNamespace(id="j", video_id="variante", payload={"voice": "qwen3:mystere", "voices_from": "orig"}),
        db=Db(),
        settings=SimpleNamespace(dry_run=False, kokoro_speed=1.0, data_dir=tmp_path),
        video_dir=lambda vid: out,
        progress=lambda *a: None,
        log=lambda *a, **k: None,
    )
    result = tts_step.TTSStep().run(ctx)
    if original_voice != "qwen3:mystere":
        assert asked == [s.narration["fr"].strip() for s in variant.scenes] and "kept_scenes" not in result
        return
    assert asked == [HOOK, promise] and result["kept_scenes"] == [s.index for s in script.scenes[2:]]
    assert 0 in result["stretched_scenes"]  # 6 s de voix : le plan de l'accroche s'allonge, le suivant attend
    new = saved[-1][2].obj  # videos.timeline de la variante
    track, _ = sf.read(str(out / "narration.wav"), dtype="float32")
    for a, b in zip(new["scenes"], new["scenes"][1:], strict=False):
        assert a["speech_end"] <= b["start"]  # chaque voix finit avant le plan suivant
    for sc in new["scenes"]:
        said = track[int(sc["speech_start"] * rate) + 10 : int(sc["speech_end"] * rate) - 10]
        want = 0.5 if sc["index"] < 2 else level[sc["index"]]
        assert said.mean() == pytest.approx(want, abs=2e-3)


def test_retention_is_read_sentence_by_sentence():
    curve = [{"t": 0.0, "w": 1.0}, {"t": 0.1, "w": 0.7}, {"t": 0.5, "w": 0.6}, {"t": 0.6, "w": 0.4}, {"t": 1.0, "w": 0.35}]
    scenes = [
        {"start": 0, "duration": 3, "words": [{"text": "Accroche"}]},
        {"start": 3, "duration": 12, "words": [{"text": "Contexte"}]},
        {"start": 15, "duration": 3, "words": [{"text": "Berbères"}]},
        {"start": 18, "duration": 12, "words": [{"text": "Fin"}]},
    ]
    rows = retention_by_scene(curve, 30.0, scenes)
    assert [r["text"] for r in rows] == ["Accroche", "Contexte", "Berbères", "Fin"]
    assert rows[0]["before"] == 100.0 and rows[0]["after"] == 70.0
    drops = retention_drops(rows, n=2)
    assert [d["text"] for d in drops] == ["Accroche", "Berbères"]  # les pertes les plus rapides, dans l'ordre
    assert retention_by_scene([], 30.0, scenes) == [] and retention_by_scene(curve, None, scenes) == []


class _Client:
    def search(self, query: str, limit: int = 8) -> list[str]:
        assert query == "Zraoua"
        return ["Liste de villes fantômes", "Matmata", "Zraoua"]


def test_subject_page_skips_lists_and_unrelated_pages():
    title = "Zraoua : le village berbère accroché au vide depuis 2000 ans"
    assert wikipedia.subject_page(_Client(), title, ["Liste de villes fantômes"]) == "Zraoua"  # type: ignore[arg-type]


def test_gemini_is_told_the_language_and_drops_an_unknown_field(monkeypatch: pytest.MonkeyPatch):
    """Gemini disait parfois une réplique française en anglais : la langue part dans le style et dans speech_config ;
    un 400 sur ce champ le retire et rejoue l'appel (docs/49 §5)."""
    pytest.importorskip("numpy")
    monkeypatch.syspath_prepend(str(RUNNERS_DIR))
    import gemini_tts
    import httpx

    sent: list[dict] = []

    class Resp:
        def __init__(self, code: int, text: str = "") -> None:
            self.status_code, self.text = code, text

        def json(self) -> dict:
            return {}

    def fake_post(url: str, headers: dict, json: dict, timeout: int):  # noqa: A002
        sent.append(json)
        speech = json["generation_config"]["speech_config"][0]
        return Resp(400, 'Unknown name "language"') if "language" in speech else Resp(200)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(gemini_tts, "_audio", lambda data: ("audio", 24000))
    monkeypatch.setattr(gemini_tts.time, "sleep", lambda s: None)
    for k, v in {
        "keys": ["k"],
        "model": "m",
        "voice": "Charon",
        "persona": "",
        "lang": "fr",
        "lang_field": True,
        "dead": set(),
    }.items():
        monkeypatch.setitem(gemini_tts.STATE, k, v)
    monkeypatch.setitem(gemini_tts.STATE, "last", 0.0)
    assert "Speak French" in gemini_tts.style("calm")
    assert gemini_tts._call("Bonjour.", gemini_tts.style("calm")) == ("audio", 24000)
    assert sent[0]["generation_config"]["speech_config"][0]["language"] == "fr-FR"
    assert "language" not in sent[1]["generation_config"]["speech_config"][0]
    assert gemini_tts.STATE["lang_field"] is False


def test_a_line_said_in_english_is_doubtful():
    """Lettre à lettre, « Attention, the ego has arrived » ressemblait à « Attention ! L'égout est arrivé ! » ; mot à
    mot, non (Retoucher → Plans, docs/49 §7)."""
    from worker.takes import TAKE_OK, said_ratio

    assert said_ratio("Attention ! L'égout est arrivé !", "Attention, the ego has arrived.") < TAKE_OK
    assert said_ratio("Madame… j'ai vu Durian près de votre bureau.", "Madame, Javu Dorian in front of your bureau.") < TAKE_OK
    assert (
        said_ratio("Maman a dit : sois gentil, ils finiront par t'aimer.", "Maman a dit, sois gentil, ils finiront par t 'aimer.")
        == 1.0
    )
    assert said_ratio("Elle préfère le puant ? Il va le payer.", "Elle préfère le puant et il va le payer.") >= TAKE_OK


def test_rewrite_lint_counts_words_per_clip():
    from worker.rewrite import SceneText, Shot, StoryRewrite, lint_rewrite

    shots = [Shot(i, 5.2, "un mur", "", 8) for i in range(5)]
    texts = [
        ("hook", "Ce mur cache un trésor que personne ne devait jamais retrouver ici."),
        ("promise", "Pourtant, ils ne finiront jamais."),
        ("context", "En 1937, deux archéologues fouillent."),
        ("conflict", "Mais la guerre arrive."),
    ]
    rw = StoryRewrite(scenes=[SceneText(index=i, part=p, text=t) for i, (p, t) in enumerate(texts)])
    issues = lint_rewrite(rw, shots, "fr", 20)
    assert any("scènes sans texte : 4" in i for i in issues)
    rw.scenes.append(SceneText(index=4, part="ending", text="Ils ne reviennent jamais."))
    issues = lint_rewrite(rw, shots, "fr", 20)
    assert any("trop long pour le clip : scène 0" in i for i in issues)
    assert not any("scènes sans texte" in i for i in issues)
