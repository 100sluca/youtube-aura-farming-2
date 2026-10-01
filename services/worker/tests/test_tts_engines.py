"""Moteurs de voix (providers/tts.py, docs/18-voix.md) : notation « moteur:voix », choix du moteur, protocole des
scripts lancés dans l'environnement Python d'un moteur, essai de voix (step voice_preview)."""

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from worker.models import Job
from worker.providers import tts
from worker.providers.tts import RUNNERS_DIR, KokoroTTS, VenvTTS, get_engine, resolve_voice, split_voice, voice_entry
from worker.providers.video import load_catalog
from worker.steps.base import Context
from worker.steps.voice_preview import SAMPLES, VoicePreviewStep

WF_DIR = Path(__file__).parents[1] / "workflows"


def _settings(tmp_path, **extra):
    return SimpleNamespace(
        **{
            "kokoro_voice_fr": "ff_siwis",
            "kokoro_voice_en": "af_heart",
            "kokoro_speed": 1.05,
            "kokoro_model_path": tmp_path / "k.onnx",
            "kokoro_voices_path": tmp_path / "v.bin",
            "yt2_home": tmp_path,
            "data_dir": tmp_path / "data",
            "comfy_workflow_dir": WF_DIR,
            "comfy_base_url": "http://127.0.0.1:1",
            "dry_run": False,
            **extra,
        }
    )


def test_split_voice_keeps_old_kokoro_names():
    assert split_voice("ff_siwis") == ("kokoro", "ff_siwis")
    assert split_voice("kokoro:af_heart") == ("kokoro", "af_heart")
    assert split_voice(" moteur:voix_fr ") == ("moteur", "voix_fr")


def test_resolve_voice_legacy_value_and_env_default(tmp_path):
    engine, voice = resolve_voice(_settings(tmp_path), {"fr": "ff_siwis"}, "fr")
    assert isinstance(engine, KokoroTTS) and voice == "ff_siwis"
    engine, voice = resolve_voice(_settings(tmp_path), {}, "en")
    assert engine.name == "kokoro" and voice == "af_heart"


def test_unknown_engine_is_explicit(tmp_path):
    with pytest.raises(ValueError, match="inconnu"):
        get_engine(_settings(tmp_path), "nexistepas")


def test_catalog_voices_point_to_declared_engines():
    cat = load_catalog(WF_DIR)
    engines = cat.get("tts") or {}
    assert "kokoro" in engines
    for lang in ("fr", "en"):
        assert cat["voices"][lang], lang
        for v in cat["voices"][lang]:
            engine, name = split_voice(v["id"])
            assert name and engine in engines, v
            assert v.get("label"), v
            assert voice_entry(cat, v["id"]) is v
    for name, spec in engines.items():
        assert spec.get("label") and spec.get("license") and "publishable" in spec, name
        if spec.get("runtime") == "venv":
            assert (RUNNERS_DIR / spec.get("runner", f"{name}.py")).exists(), name


FAKE_RUNNER = """
import sys
sys.path.insert(0, {runners!r})
import numpy as np
from _common import run

def synth(req, text):
    assert req["voice"] == "la" and req["lang"] == "fr"
    t = np.arange(int(24000 * 0.01 * len(text))) / 24000
    return 0.3 * np.sin(2 * np.pi * req["voice_params"]["hz"] * t), 24000

run(synth, speed_applied=True)
"""


def _fake_engine(tmp_path, source: str, name: str = "faux") -> VenvTTS:
    runner = tmp_path / f"{name}.py"
    runner.write_text(source, encoding="utf-8")
    spec = {"runtime": "venv", "python": sys.executable, "runner": str(runner), "gpu": False, "label": name}
    catalog = {"tts": {name: spec}, "voices": {"fr": [{"id": f"{name}:la", "label": "La", "params": {"hz": 440}}]}}
    return VenvTTS(_settings(tmp_path), name, spec, catalog)


def test_venv_engine_runs_all_texts_in_one_process(tmp_path):
    engine = _fake_engine(tmp_path, FAKE_RUNNER.format(runners=str(RUNNERS_DIR)))
    seen: list[int] = []
    texts = ["bonjour", "au revoir tout le monde"]
    out = engine.speak_many(texts, voice="la", lang="fr", speed=1.1, on_progress=lambda pct, _label: seen.append(pct))
    assert [round(sp.duration_s, 2) for sp in out] == [round(0.01 * len(t), 2) for t in texts]
    assert all(sp.rate == 24000 and sp.voice == "la" for sp in out)
    assert seen[-1] == 100
    assert not list((tmp_path / "data" / "tmp").iterdir())  # dossier de travail effacé


TONE_RUNNER = """
import sys
sys.path.insert(0, {runners!r})
import numpy as np
from _common import run

def synth(req, text, tone):
    # une seconde par lettre du ton : on retrouve le ton reçu à la durée
    return np.zeros(24000 * len(tone), dtype=np.float32) + 0.1, 24000

run(synth, speed_applied=True)
"""


def test_tones_reach_an_emotion_engine_and_timings_come_back(tmp_path):
    """Le ton de chaque réplique va au script d'un moteur qui sait jouer une émotion (docs/41) ; un ton manquant est une
    chaîne vide ; le moteur rend son temps de chargement et le temps de chaque texte (banc d'essai)."""
    engine = _fake_engine(tmp_path, TONE_RUNNER.format(runners=str(RUNNERS_DIR)), name="emo")
    out = engine.speak_many(["a", "b", "c"], voice="la", lang="fr", speed=1.0, tones=["cri", "  chut  "])
    assert [round(sp.duration_s) for sp in out] == [3, 4, 0]
    assert engine.last_result["load_s"] >= 0 and len(engine.last_result["times"]) == 3


TARGET_RUNNER = """
import sys
sys.path.insert(0, {runners!r})
import numpy as np
from _common import run

def synth(req, text, tone, target):
    # la durée visée devient la durée du son : on la retrouve à l'arrivée
    return np.zeros(int(24000 * (target or 0.5)), dtype=np.float32) + 0.1, 24000

run(synth, speed_applied=True)
"""


def test_mouth_targets_reach_an_engine_that_paces_itself(tmp_path):
    """Durée de la bouche de chaque réplique (docs/41 §8) : un script à 4 paramètres la reçoit, None si inconnue."""
    engine = _fake_engine(tmp_path, TARGET_RUNNER.format(runners=str(RUNNERS_DIR)), name="rythme")
    out = engine.speak_many(["a", "b"], voice="la", lang="fr", speed=1.0, targets=[2.0, None])
    assert [round(sp.duration_s, 1) for sp in out] == [2.0, 0.5]


def test_gemini_retakes_a_line_too_long_for_the_mouth(monkeypatch):
    """Une prise trop longue pour la bouche (×0,53 : au-delà du ×0,8 du calage) est refaite avec une consigne de débit ;
    la prise qui tient dans la bouche est gardée."""
    np = pytest.importorskip("numpy")
    monkeypatch.syspath_prepend(str(RUNNERS_DIR))
    import gemini_tts

    durations = iter([6.0, 3.4])
    styles: list[str] = []

    def fake_call(text: str, instruction: str):
        styles.append(instruction)
        return np.full(int(24000 * next(durations)), 0.3, dtype=np.float32), 24000

    monkeypatch.setattr(gemini_tts, "_call", fake_call)
    monkeypatch.setitem(gemini_tts.STATE, "persona", "")
    monkeypatch.setitem(gemini_tts.STATE, "speed", 1.0)
    audio, rate = gemini_tts.synthesize({}, "Je l'ai rendue ! À vous !", "desperate, crying", 3.2)
    assert len(audio) / rate == pytest.approx(3.4)
    assert styles[0] == "desperate, crying" and "faster" in styles[1] and "3.2 seconds" in styles[1]
    assert len(styles) == 2  # ×0,94 : dans la bouche, pas de 3e prise


def test_an_engine_can_reuse_the_voices_of_another(tmp_path):
    """« voices_from » : un moteur reprend les paramètres des voix d'un autre (les voix Qwen dessinées)."""
    runner = tmp_path / "copie.py"
    runner.write_text(FAKE_RUNNER.format(runners=str(RUNNERS_DIR)), encoding="utf-8")
    spec = {"runtime": "venv", "python": sys.executable, "runner": str(runner), "gpu": False, "voices_from": "faux"}
    catalog = {"tts": {"copie": spec}, "voices": {"fr": [{"id": "faux:la", "label": "La", "params": {"hz": 220}}]}}
    [sp] = VenvTTS(_settings(tmp_path), "copie", spec, catalog).speak_many(["bonjour"], voice="la", lang="fr", speed=1.0)
    assert round(sp.duration_s, 2) == 0.07


def test_voice_acting_routes_designed_voices_and_falls_back_locally(monkeypatch):
    """Jeu des voix (docs/41) : une voix Qwen dessinée passe au moteur du jeu, les autres gardent le leur ; Gemini qui
    échoue (quota) laisse la place à son repli local, avec les mêmes tons, sans la description du personnage."""
    from worker.providers.tts import acting_engines
    from worker.steps import tts as tts_step

    cat = load_catalog(WF_DIR)
    assert acting_engines(cat, "qwen3", "neutral") == ["qwen3"]
    assert acting_engines(cat, "qwen3", "qwen3_emotion") == ["qwen3_emotion"]
    assert acting_engines(cat, "kokoro", "qwen3_emotion") == ["kokoro"]
    assert acting_engines(cat, "qwen3", "gemini") == ["gemini", "qwen3_emotion"]
    for spec in cat["acting"].values():  # chaque jeu désigne des moteurs déclarés
        for name in (spec.get("engine"), spec.get("fallback")):
            assert not name or name in cat["tts"], name

    calls: list[tuple[str, list[str]]] = []

    class Engine:
        def __init__(self, name: str) -> None:
            self.name = name

        def speak_many(self, texts, *, voice, lang, speed, tones=None):
            calls.append((self.name, list(tones or [])))
            if self.name == "gemini":
                raise RuntimeError("429 quota")
            return ["ok"] * len(texts)

    monkeypatch.setattr(tts_step, "get_engine", lambda settings, name: Engine(name))
    logged: list[str] = []
    ctx = SimpleNamespace(settings=None, log=lambda event, **k: logged.append(event))
    engines, acting = ["gemini", "qwen3_emotion"], cat["acting"]["gemini"]
    out = tts_step._say(ctx, engines, acting, "perso_mamie", "fr", 1.0, ["Bonsoir."], ["icy"], ["an old lady"])
    assert out == ["ok"]
    assert calls == [("gemini", ["an old lady; icy"]), ("qwen3_emotion", ["icy"])]
    assert logged == ["tts.jeu_repli"]


def test_venv_engine_failure_reports_runner_error(tmp_path):
    engine = _fake_engine(tmp_path, "print('PROGRESS 0 1', flush=True)\nraise SystemExit('poids du modèle introuvables')\n")
    with pytest.raises(tts.TTSRunnerError, match="poids du modèle introuvables"):
        engine.speak_many(["x"], voice="la", lang="fr", speed=1.0)


def test_engine_not_installed_says_how_to_install(tmp_path):
    spec = {"runtime": "venv", "gpu": False}
    engine = VenvTTS(_settings(tmp_path), "absent", spec, {"tts": {"absent": spec}, "voices": {}})
    with pytest.raises(FileNotFoundError, match="install_tts.ps1"):
        engine.speak_many(["x"], voice="v", lang="fr", speed=1.0)


class FakeDb:
    def __init__(self):
        self.beats: list[tuple[int, str | None]] = []

    def heartbeat(self, job_id, pct=None, label=None):
        self.beats.append((pct, label))


def test_voice_preview_dry_run_writes_result(tmp_path):
    job = Job(
        id=uuid4(),
        type="voice_preview",
        status="running",
        priority=5,
        created_at=datetime.now(UTC),
        payload={"voice": "kokoro:ff_siwis", "lang": "fr", "text": "  "},
    )
    db = FakeDb()
    out = VoicePreviewStep().run(Context(job=job, db=db, settings=_settings(tmp_path, dry_run=True)))  # type: ignore[arg-type]
    assert out["voice"] == "kokoro:ff_siwis" and out["engine"] == "kokoro" and out["text"] == SAMPLES["fr"]
    assert Path(out["path"]).name == f"{job.id}.wav" and Path(out["path"]).parent.name == "voices"
    assert out["speed"] == 1.05 and db.beats
