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
