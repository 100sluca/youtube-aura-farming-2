"""Plans d'un drame (docs/38 §5-6) : le modèle vidéo sait qui parle (personnages décrits par ce qui se voit et par leur
place dans l'image, les autres se taisent), le contrôle vérifie la bonne bouche, et une correction de Luca pour un plan
(Retoucher → Plans) devient une note de réalisation pour le clip ou une nouvelle prise de sa seule réplique.

« Mamie Pomme » (29/09) : sur 5 plans à deux personnages, H3 a fait parler la mère 4 fois au lieu de l'ananas, du
citron ou du fils (contrôle Gemini) ; le prompt ne les nommait que par leur nom."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from worker import drama, speaker
from worker.keyframe_qc import NO_NEW_TEXT, clip_requirements
from worker.models import CastMember, ScriptV1

CAST = [
    {"key": "mamie_pomme", "name": "Mamie Pomme", "voice": "a warm fragile elderly female voice", "tts_voice": "qwen3:perso_mamie",
     "look": "a poor 70-year-old seamstress whose whole head is a wrinkled red-brown baked apple with a short stem, kind tired "
             "eyes behind round glasses, a flowered headscarf, a worn beige cardigan over a simple grey dress"},
    {"key": "ananas", "name": "Monsieur Ananas", "voice": "a deep powerful male voice in his sixties", "tts_voice": "qwen3:perso_papi",
     "look": "the richest man in town, about 60, whose whole head is a golden pineapple with a proud spiky leafy crown, deep "
             "kind eyes, a white tuxedo with a black bow tie, broad shoulders"},
]


def _script() -> ScriptV1:
    scenes = [
        {"index": 0, "duration_s": 4, "visual_prompt": "shot 0", "motion_prompt": "He gently holds her hands, slow push-in",
         "characters": ["mamie_pomme", "ananas"], "lines": [{"who": "ananas", "text": "C'est vous… la couturière ?", "tone": "whispering"}]},
        {"index": 1, "duration_s": 3, "visual_prompt": "shot 1", "motion_prompt": "She lowers her eyes",
         "characters": ["mamie_pomme"], "lines": [{"who": "mamie_pomme", "text": "Oui.", "tone": "trembling"}]},
        {"index": 2, "duration_s": 3, "visual_prompt": "shot 2", "motion_prompt": "Guests turn around", "characters": ["ananas"]},
        {"index": 3, "duration_s": 3, "visual_prompt": "shot 3", "motion_prompt": "Snow falls", "characters": []},
    ]
    return drama.normalize(ScriptV1.model_validate({"scenes": scenes, "cast": CAST,
                                                     "metadata": {"fr": {"title": "t", "description": "d"}}}))


def test_characters_are_described_by_what_the_video_model_sees():
    pomme, ananas = (CastMember.model_validate(c) for c in CAST)
    assert speaker.visual_tag(pomme) == ("a poor 70-year-old seamstress whose whole head is a wrinkled red-brown baked apple "
                                         "with a short stem, a flowered headscarf")
    assert speaker.visual_tag(ananas).endswith("proud spiky leafy crown, a white tuxedo with a black bow tie")
    assert speaker.visual_tag(CastMember(key="x", name="X", look="")) == "X"


def test_the_clip_prompt_says_who_speaks_where_and_who_stays_silent():
    s = _script()
    where = {"ananas": "on the left, kneeling down", "mamie_pomme": "on the right"}
    p = drama.clip_prompt(s, 0, "fr", "pixar_fruit", where)
    assert "Characters in this shot: Monsieur Ananas is the richest man in town" in p  # celui qui parle d'abord
    assert "a white tuxedo with a black bow tie, on the left, kneeling down; Mamie Pomme is a poor 70-year-old" in p
    assert 'Monsieur Ananas says in French, in a deep powerful male voice in his sixties, whispering: "C\'est vous… la couturière ?"' in p
    assert "Only Monsieur Ananas speaks, lips moving with the words. Mamie Pomme keeps their mouth closed and only listens." in p
    assert p.endswith("no subtitles, no captions.")
    alone = drama.clip_prompt(s, 1, "fr", "pixar_fruit")
    assert "Characters in this shot: Mamie Pomme is" in alone and "keeps their mouth closed" not in alone
    with_note = drama.clip_prompt(s, 0, "fr", "pixar_fruit", where, note="The pineapple man on the left speaks.")
    assert with_note.endswith("no captions. The pineapple man on the left speaks.")
    assert "Nobody speaks" in drama.clip_prompt(s, 3, "fr", "pixar_fruit") and "Characters in this shot" not in drama.clip_prompt(s, 3, "fr")


def test_the_clip_check_asks_for_the_right_mouth_when_two_are_in_the_shot():
    s = _script()
    reqs = clip_requirements(s, 0, "drama")
    assert reqs[0] == NO_NEW_TEXT and reqs[1].startswith("C'est Monsieur Ananas (the richest man in town")
    assert "Mamie Pomme (a poor 70-year-old seamstress" in reqs[1] and "garde la bouche fermée" in reqs[1]
    assert clip_requirements(s, 1, "drama") == [NO_NEW_TEXT]  # seule à l'image
    assert clip_requirements(s, 2, "drama") == [NO_NEW_TEXT]  # sans réplique


class FakeLLM:
    def __init__(self, answer: Any) -> None:
        self.answer, self.calls = answer, []

    def complete_json(self, system: str, user: str, schema: type, images: Any = ()) -> Any:
        self.calls.append((system, user, list(images)))
        if isinstance(self.answer, Exception):
            raise self.answer
        return schema.model_validate(self.answer)


def test_places_and_director_notes_come_from_the_vision_model(tmp_path):
    s = _script()
    image = tmp_path / "start.png"
    image.write_bytes(b"png")
    members = speaker.shot_members(s, s.scenes[0])
    llm = FakeLLM({"characters": [{"key": "ananas", "where": "on the left, kneeling"}, {"key": "intrus", "where": "left"},
                                  {"key": "mamie_pomme", "where": "on the right."}]})
    assert speaker.locate(llm, image, members) == {"ananas": "on the left, kneeling", "mamie_pomme": "on the right"}
    assert llm.calls[0][2] == [image]  # Gemini regarde l'image de départ
    assert speaker.locate(llm, image, members[:1]) == {}  # un seul personnage : rien à situer
    assert speaker.locate(FakeLLM(RuntimeError("quota")), image, members) == {}  # une aide, jamais bloquante
    note = speaker.director_note(FakeLLM({"note": "The pineapple man on the left speaks;  the apple woman stays silent."}),
                                 s, s.scenes[0], "c'est l'ananas qui parle, pas la mère", image)
    assert note == "The pineapple man on the left speaks; the apple woman stays silent."
    fallback = speaker.director_note(FakeLLM(RuntimeError("hors ligne")), s, s.scenes[0], "c'est l'ananas qui parle")
    assert fallback == "Director's note (in French): c'est l'ananas qui parle"
    assert speaker.director_note(llm, s, s.scenes[0], "   ") == ""


def test_a_voice_note_can_change_pronunciation_and_pace_only():
    assert speaker.voice_direction(FakeLLM({"spoken": "Mais… je suis ta mère, A-pi.", "speed": 0.9}),
                                   "Mais… je suis ta mère, Api.", "dis A-pi, plus lentement") == ("Mais… je suis ta mère, A-pi.", 0.9)
    assert speaker.voice_direction(FakeLLM(RuntimeError("x")), "Oui.", "plus vite") == ("Oui.", 1.0)
    assert speaker.voice_direction(None, "Oui.", "plus vite") == ("Oui.", 1.0)


def test_a_retake_says_one_line_again_and_keeps_the_others(tmp_path, monkeypatch):
    """Retoucher → Plans → Nouvelle prise de voix : seule la réplique du plan est redite (une autre graine), les autres
    viennent des répliques découpées au dernier calage ; la piste et la timeline de l'étape voix sont refaites."""
    np = pytest.importorskip("numpy")
    sf = pytest.importorskip("soundfile")
    from worker.models import NarrationTimeline
    from worker.providers.tts import Speech
    from worker.steps import tts as tts_step

    s = _script()
    rate = 24000
    old = {0: np.full(rate, 0.1, dtype="float32"), 1: np.full(rate // 2, 0.3, dtype="float32")}
    monkeypatch.setattr(tts_step, "cached_lines", lambda settings, vid: (dict(old), rate, NarrationTimeline(lang="fr", scenes=[])))
    monkeypatch.setattr(tts_step, "tts_catalog", lambda settings: {"voices": {"fr": [{"id": "qwen3:perso_mamie"}, {"id": "qwen3:perso_papi"}]}})
    monkeypatch.setattr(tts_step, "get_llm", lambda settings, db: FakeLLM({"spoken": "C'est vous… la cou-tu-rière ?", "speed": 1.1}))
    calls: list[dict[str, Any]] = []

    class Engine:
        def speak_many(self, texts: list[str], *, voice: str, lang: str, speed: float, seed: int | None = None) -> list[Speech]:
            calls.append({"texts": texts, "voice": voice, "speed": speed, "seed": seed})
            return [Speech(samples=np.full(int(rate * 1.5), 0.2, dtype="float32"), rate=rate, voice=voice)]

    monkeypatch.setattr(tts_step, "get_engine", lambda settings, engine: Engine())
    saved: list[Any] = []

    class Db:
        def fetch_one(self, sql: str, params: Any = None) -> dict:
            if "tts_provider" in sql and "script" not in sql:
                return {"tts_provider": "drama", "tts_voice": "mamie_pomme=qwen3:perso_mamie, ananas=qwen3:perso_papi"}
            return {"lang": "fr", "timeline": {"lang": "fr", "scenes": []}, "production_id": "p", "script": s.model_dump(),
                    "voice_speed": 1.0}

        def add_asset(self, **cols: Any) -> str:
            return "a"

        def execute(self, sql: str, params: Any = None) -> int:
            saved.append(params)
            return 1

    (tmp_path / "narration.wav").write_bytes(b"old")
    ctx = SimpleNamespace(job=SimpleNamespace(video_id="v", payload={"scene": 0, "take": 2, "note": "prononce couturière en détachant"}),
                          db=Db(), settings=SimpleNamespace(dry_run=False, kokoro_speed=1.0), video_dir=lambda vid: tmp_path,
                          progress=lambda *a: None, log=lambda *a, **k: None)
    result = tts_step.TTSStep().run(ctx)
    assert calls == [{"texts": ["C'est vous… la cou-tu-rière ?"], "voice": "perso_papi", "speed": 1.1, "seed": 1234 + 2000}]
    assert result["scene"] == 0 and result["take"] == 2 and result["voice"] == "qwen3:perso_papi"
    audio, r = sf.read(str(tmp_path / "narration.wav"))
    tl = NarrationTimeline.model_validate(saved[-1][2].obj)  # videos.timeline : celle de l'étape voix, refaite
    first, second = tl.scenes[0], tl.scenes[1]
    assert first.speech_end - first.speech_start == pytest.approx(1.5, abs=0.02)  # la nouvelle prise
    assert second.speech_end - second.speech_start == pytest.approx(0.5, abs=0.02)  # l'ancienne réplique, inchangée
    assert r == rate and len(audio) / rate == pytest.approx(tl.duration_s, abs=0.05)
    assert saved[-1][0] == "drama"  # la voix des personnages reste notée telle quelle


def test_a_retake_needs_the_lines_of_the_last_sync(tmp_path, monkeypatch):
    from worker.steps import tts as tts_step

    s = _script()
    monkeypatch.setattr(tts_step, "cached_lines", lambda settings, vid: None)

    class Db:
        def fetch_one(self, sql: str, params: Any = None) -> dict:
            return {"lang": "fr", "timeline": {"lang": "fr", "scenes": []}, "production_id": "p", "script": s.model_dump(), "voice_speed": 1.0}

    ctx = SimpleNamespace(job=SimpleNamespace(video_id="v", payload={"scene": 0}), db=Db(),
                          settings=SimpleNamespace(dry_run=False, kokoro_speed=1.0), video_dir=lambda vid: tmp_path,
                          progress=lambda *a: None, log=lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="Refaire la vidéo"):
        tts_step.TTSStep().run(ctx)
