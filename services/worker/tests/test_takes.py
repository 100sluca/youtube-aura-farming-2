"""Prises de voix de Retoucher → Plans (docs/49 §7) : ce que Luca a demandé le 01/10 devant « Tout le collège le
détestait ».

- Sa consigne (« plus moqueur ») n'arrivait jamais à Gemini : seul le relecteur de prononciation la lisait. Elle part
  maintenant avec le ton de la réplique, et la prise note la consigne de jeu reçue et le moteur qui a parlé.
- La voix du clip brut du plan 1 (celle du modèle vidéo) lui plaisait plus que toutes les prises : elle peut devenir une
  prise, coupée à ses paroles et mise au niveau des autres répliques.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from worker import lipsync, media, takes
from worker.models import ScriptV1
from worker.steps import tts as tts_step

CAST = [
    {"key": "pasteque", "name": "Pastèque", "voice": "a cocky teenage boy voice", "look": "a watermelon-headed teen"},
    {"key": "durian", "name": "Durian", "voice": "a shy boy voice", "look": "a spiky durian-headed boy"},
]


def _script() -> ScriptV1:
    scenes = [
        {
            "index": 0,
            "duration_s": 2.4,
            "visual_prompt": "hallway",
            "characters": ["pasteque", "durian"],
            "lines": [{"who": "pasteque", "text": "Attention ! L'égout est arrivé !", "tone": "loud, mocking"}],
        },
        {"index": 1, "duration_s": 3, "visual_prompt": "classroom door", "characters": ["durian"], "lines": []},
        {
            "index": 2,
            "duration_s": 3,
            "visual_prompt": "bench",
            "characters": ["durian"],
            "lines": [{"who": "durian", "text": "Pourquoi ?"}],
        },
        {"index": 3, "duration_s": 3, "visual_prompt": "yard", "characters": [], "lines": []},
    ]
    return ScriptV1.model_validate({"scenes": scenes, "cast": CAST, "metadata": {"fr": {"title": "t", "description": "d"}}})


class FakeDb:
    def __init__(self, retouch: dict[str, Any], clip: Path | None = None):
        self.retouch, self.clip = retouch, clip
        self.assets: list[dict[str, Any]] = []
        self.executed: list[tuple[str, Any]] = []

    def fetch_one(self, sql: str, params: Any = ()) -> dict[str, Any] | None:
        if "from videos" in sql:
            return {"retouch": self.retouch}
        if "from assets" in sql:
            return {"local_path": str(self.clip)} if self.clip else None
        return None

    def add_asset(self, **kw: Any) -> str:
        self.assets.append(kw)
        return f"asset-{len(self.assets)}"

    def execute(self, sql: str, params: Any = ()) -> int:
        self.executed.append((sql, params))
        return 1

    def saved_takes(self) -> dict[str, Any]:
        return json.loads(self.executed[-1][1][0])["takes"]


def _ctx(tmp_path: Path, db: FakeDb) -> Any:
    return SimpleNamespace(
        job=SimpleNamespace(id="job-1", video_id="vid", production_id="prod", payload={}),
        db=db,
        settings=SimpleNamespace(dry_run=False),
        video_dir=lambda vid: tmp_path,
        progress=lambda *a, **k: None,
        log=lambda *a, **k: None,
    )


def _tone(seconds: float, rate: int, amp: float) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_the_consigne_reaches_gemini_with_the_tone_and_the_take_says_what_it_received(tmp_path, monkeypatch):
    sent: dict[str, Any] = {}

    def fake_say(ctx, engines, acting, voice, lang, speed, texts, tones, personas, **kw):
        sent.update(engines=engines, texts=texts, tones=tones, personas=personas)
        tts_step._SPOKE[tts_step._job_key(ctx)] = "gemini"
        return [SimpleNamespace(samples=_tone(1.0, 24000, 0.2), rate=24000)]

    monkeypatch.setattr(takes, "tts_catalog", lambda s: {"acting": {"gemini": {"engine": "gemini", "persona": True}}})
    monkeypatch.setattr(takes, "acting_engines", lambda catalog, engine, acting: ["gemini", "qwen3_emotion"])
    monkeypatch.setattr(takes, "line_voice", lambda *a: "qwen3:perso_ado")
    monkeypatch.setattr(takes, "get_llm", lambda *a: object())
    monkeypatch.setattr(takes, "voice_direction", lambda llm, text, note: (text, 1.0))  # emotion : texte et débit inchangés
    monkeypatch.setattr(takes, "transcribe", lambda s, files, lang: [{"text": "Attention, l'égout est arrivé.", "words": []}])
    monkeypatch.setattr(tts_step, "_say", fake_say)
    monkeypatch.setattr(tts_step, "mouth_targets", lambda *a: {})
    db = FakeDb({})

    out = takes.make_takes(_ctx(tmp_path, db), _script(), "fr", 1.0, {0: "plus moqueur, plus fort", 1: "des rires"}, "gemini")

    assert out["takes"] == [0]  # le plan sans réplique n'a rien à redire
    assert sent["tones"] == ["loud, mocking; plus moqueur, plus fort"]
    assert sent["personas"] == ["a cocky teenage boy voice"]
    take = db.saved_takes()["0"]
    assert take["direction"] == "a cocky teenage boy voice; loud, mocking; plus moqueur, plus fort"
    assert take["engine"] == "gemini" and take["keep"] is None and take["ratio"] == 1.0


def test_a_local_voice_that_cannot_act_keeps_the_written_tone(tmp_path, monkeypatch):
    sent: dict[str, Any] = {}

    def fake_say(ctx, engines, acting, voice, lang, speed, texts, tones, personas, **kw):
        sent.update(tones=tones)
        return [SimpleNamespace(samples=_tone(1.0, 24000, 0.2), rate=24000)]

    monkeypatch.setattr(takes, "tts_catalog", lambda s: {"acting": {"qwen3_emotion": {"engine": "qwen3_emotion"}}})
    monkeypatch.setattr(takes, "acting_engines", lambda catalog, engine, acting: ["qwen3_emotion"])
    monkeypatch.setattr(takes, "line_voice", lambda *a: "qwen3:perso_ado")
    monkeypatch.setattr(takes, "get_llm", lambda *a: object())
    monkeypatch.setattr(takes, "voice_direction", lambda llm, text, note: (text, 1.0))
    monkeypatch.setattr(takes, "transcribe", lambda s, files, lang: [{"text": "Attention, l'égout est arrivé.", "words": []}])
    monkeypatch.setattr(tts_step, "_say", fake_say)
    monkeypatch.setattr(tts_step, "mouth_targets", lambda *a: {})
    db = FakeDb({})

    takes.make_takes(_ctx(tmp_path, db), _script(), "fr", 1.0, {0: "plus moqueur"}, "qwen3_emotion")

    assert sent["tones"] == ["loud, mocking"]
    assert db.saved_takes()["0"]["direction"] == "loud, mocking"


def test_the_clip_voice_becomes_a_take_cut_to_its_words_at_the_level_of_the_other_lines(tmp_path, monkeypatch):
    clip = tmp_path / "scene_00.mp4"
    clip.write_bytes(b"clip")

    def fake_ffmpeg(cmd: list[str], cwd: Any = None, timeout: int = 0) -> None:
        # 2 s de clip : silence, la réplique entre 0,5 et 1,5 s (faible), silence
        x = np.zeros(2 * 48000, dtype=np.float32)
        x[24000:72000] = _tone(1.0, 48000, 0.05)
        sf.write(cmd[-1], x, 48000)

    words = [{"w": "Attention", "start": 0.5, "end": 0.9, "p": 0.9}, {"w": "arrivé", "start": 1.2, "end": 1.5, "p": 0.9}]
    monkeypatch.setattr(media, "run", fake_ffmpeg)
    monkeypatch.setattr(
        takes, "transcribe", lambda s, files, lang: [{"text": "Attention ! L'égout est arrivé !", "words": words}]
    )
    other_line = _tone(1.0, 24000, 0.2)  # les répliques de la vidéo : RMS ≈ 0,141
    monkeypatch.setattr(lipsync, "cached_lines", lambda s, vid: ({0: other_line, 2: other_line}, 24000, None))
    db = FakeDb({"takes": {"5": {"asset_id": "a5", "keep": True}}}, clip=clip)

    out = takes.clip_takes(_ctx(tmp_path, db), _script(), "fr", [0, 1])

    assert out["clip_takes"] == [0] and out["skipped"] == {"1": "plan sans réplique"}
    saved = db.saved_takes()
    assert saved["5"] == {"asset_id": "a5", "keep": True}  # les autres prises restent
    take = saved["0"]
    assert take["source"] == "clip" and take["keep"] is None and take["ratio"] == 1.0
    assert take["note"] == takes.CLIP_NOTE and take["said"] == "Attention ! L'égout est arrivé !"
    x, sr = sf.read(db.assets[0]["local_path"], dtype="float32")
    assert abs(len(x) / sr - (1.5 + 0.25 - (0.5 - 0.08))) < 0.01  # de la première à la dernière parole
    level = takes.voiced_rms(x, sr)
    assert level is not None and abs(level - takes.voiced_rms(other_line, 24000)) < 0.01


def test_a_clip_without_speech_is_not_a_take(tmp_path, monkeypatch):
    clip = tmp_path / "scene_00.mp4"
    clip.write_bytes(b"clip")
    monkeypatch.setattr(
        media, "run", lambda cmd, cwd=None, timeout=0: sf.write(cmd[-1], np.zeros(48000, dtype=np.float32), 48000)
    )
    monkeypatch.setattr(takes, "transcribe", lambda s, files, lang: [{"text": "", "words": []}])
    monkeypatch.setattr(lipsync, "cached_lines", lambda s, vid: None)
    db = FakeDb({}, clip=clip)
    with pytest.raises(RuntimeError, match="plan 1 : personne ne parle dans le clip"):
        takes.clip_takes(_ctx(tmp_path, db), _script(), "fr", [0])
    assert not db.assets and not db.executed
