"""Retouche d'une vidéo montée (worker/retouch.py, docs/34-retouche.md) : texte des sous-titres recalé sur la voix,
titre d'accroche, musique et niveaux imposés, voix imposée au step tts, retouche lue par le montage."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from worker.media import measure_loudness
from worker.models import ScriptV1
from worker.montage import AudioLayer, MontageTemplate
from worker.music import Track
from worker.numbers import NBSP
from worker.retouch import MusicChoice, Retouch, display_tokens, forced_music, load_retouch, retime
from worker.steps import assemble
from worker.subtitles import distribute_words
from worker.timeline import SceneSpeech, plan_timeline

CHALANDS = "Des chalands géants de treize cent cinquante tonnes traversent enfin l'Europe."


def test_display_tokens_keep_numbers_whole():
    assert display_tokens("de 1 350 tonnes") == ["de", f"1{NBSP}350", "tonnes"]
    assert display_tokens("plus de 2 milliards d'euros.") == ["plus", "de", f"2{NBSP}milliards", "d'euros."]
    assert display_tokens("  30 %  de\nplus ") == [f"30{NBSP}%", "de", "plus"]
    assert display_tokens("En 1992, 170 km.") == ["En", "1992,", f"170{NBSP}km."]
    assert display_tokens("") == []


def test_retime_rewritten_number_takes_the_time_of_the_spoken_words():
    words = distribute_words(CHALANDS, 1.0, 5.0)
    out = retime(words, "Des chalands géants de 1 350 tonnes traversent enfin l'Europe.")
    assert [w.text for w in out] == ["Des", "chalands", "géants", "de", f"1{NBSP}350", "tonnes", "traversent", "enfin", "l'Europe."]
    spoken = {w.text: w for w in words}
    assert (out[4].start, out[4].end) == (spoken["treize"].start, spoken["cinquante"].end)
    for w in out:  # mots inchangés : même temps que dans la voix
        if w.text in spoken:
            assert (w.start, w.end) == (spoken[w.text].start, spoken[w.text].end)


def test_retime_added_and_removed_words():
    words = distribute_words("Seize écluses permettent de franchir la ligne.", 0.0, 3.0)
    out = retime(words, "Enfin 16 écluses géantes permettent de franchir la ligne.")
    assert [w.text for w in out] == ["Enfin", "16", "écluses", "géantes", "permettent", "de", "franchir", "la", "ligne."]
    # ajouté en tête : partage le temps du premier mot dit ; au milieu : celui du mot d'avant
    assert out[0].start == words[0].start and out[1].end == pytest.approx(words[0].end)
    assert out[2].start == words[1].start and out[3].end == pytest.approx(words[1].end)
    assert all(a.start < a.end <= b.start + 1e-6 for a, b in zip(out, out[1:], strict=False))
    cut = retime(words, "Seize écluses franchissent la ligne.")
    assert [w.text for w in cut] == ["Seize", "écluses", "franchissent", "la", "ligne."]
    assert (cut[2].start, cut[2].end) == (words[2].start, words[4].end) and cut[-1].end == words[-1].end
    assert retime(words, "  ") == [] and retime([], "texte") == []


def test_subtitle_words_replaces_only_the_edited_scenes():
    a, b = distribute_words("Première scène ici.", 0, 2), distribute_words("Deuxième scène là.", 2, 4)
    out = Retouch(subtitles={"7": "Deuxième scène !"}).subtitle_words([a, b], [3, 7])
    assert out[0] == a and [w.text for w in out[1]] == ["Deuxième", "scène", "!"]
    assert Retouch(subtitles={"3": ""}).subtitle_words([a, b], [3, 7]) == [[], b]  # texte vidé : plus de sous-titre
    assert Retouch().subtitle_words([a, b], [3, 7]) == [a, b]


def test_audio_levels_hook_and_parts():
    base = AudioLayer()
    layer = Retouch(audio={"music_db": -16.0, "duck_db": 6.0}).audio_layer(base)
    assert (layer.music_db, layer.duck_db, layer.voice_db, layer.formats) == (-16.0, 6.0, base.voice_db, base.formats)
    assert Retouch(audio={"music_db": 5.0}).audio_layer(base) == base  # hors bornes (0 dB au plus) : le modèle
    assert Retouch().audio_layer(base) is base
    assert Retouch().hook("Auto") == "Auto" and not Retouch()
    r = Retouch(hook_title="  70 ans pour relier deux fleuves ", music=MusicChoice(track=None), voice="qwen3:serena")
    assert r.hook("Auto") == "70 ans pour relier deux fleuves" and r
    assert r.parts() == ["titre d'accroche", "musique", "voix"]


def test_forced_music_even_disabled_or_off_format(tmp_path: Path):
    t = Track(id="music_4", file="m.mp3", formats=("timelapse",), enabled=False, path=tmp_path / "m.mp3")
    track, why = forced_music([t], MusicChoice(track="music_4", start_s=12.5))  # type: ignore[misc]
    assert track is not None and track.id == "music_4" and track.start_s == 12.5 and "main" in why["reason"]
    assert forced_music([t], MusicChoice(track=None)) == (None, {"reason": "sans musique (retouche)"})
    assert forced_music([Track(id="gone", file="g.mp3")], MusicChoice(track="gone")) is None  # fichier retiré


class RowDb:
    def __init__(self, row: Any) -> None:
        self.row = row

    def fetch_one(self, sql: str, params: Any = None) -> Any:
        if isinstance(self.row, Exception):
            raise self.row
        return self.row


def test_load_retouch_tolerates_missing_column_and_bad_values():
    assert not load_retouch(RowDb({"retouch": None}), "v")
    assert load_retouch(RowDb({"retouch": {"hook_title": "Titre", "subtitles": {"0": "x"}}}), "v").hook_title == "Titre"
    assert not load_retouch(RowDb({"retouch": {"music": {"start_s": -3}}}), "v")  # illisible : ignorée
    assert not load_retouch(RowDb(RuntimeError("colonne absente")), "v")


# ---- Branchements : montage et voix --------------------------------------------------------------------------------


def _script() -> dict:
    texts = ["Soixante-dix ans de travaux.", CHALANDS, "Un canal pour relier deux fleuves.", "Inauguré en dix-neuf cent quatre-vingt-douze."]
    return {"scenes": [{"index": i, "duration_s": 5, "visual_prompt": "x", "narration": {"fr": t}} for i, t in enumerate(texts)],
            "metadata": {"fr": {"title": "Canal", "description": "d"}}, "hook_title": {"fr": "Soixante-dix ans de travaux"}}


class MontageDb:
    """Ce que prepare_video et choose_music demandent à la base."""

    def __init__(self, retouch: dict | None, tracks: list[dict] | None = None) -> None:
        tl = plan_timeline([SceneSpeech(i, 5.0, s["narration"]["fr"], 3.0) for i, s in enumerate(_script()["scenes"])], "fr")
        self.timeline, self.retouch, self.tracks = tl.model_dump(), retouch, tracks or []

    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        if "-> 'retouch'" in sql:
            return {"retouch": self.retouch}
        if "from videos v" in sql:
            return {"lang": "fr", "format": "A_voiceover", "timeline": self.timeline, "music_track": "music_3"}
        if "select script" in sql:
            return {"script": _script()}
        if "recipe" in sql:
            return {"recipe": "story"}
        return None

    def fetch_all(self, sql: str, params: Any = None) -> list[dict]:
        if "music_tracks" in sql:
            return self.tracks
        return [{"scene_index": i, "local_path": f"c{i}.mp4", "duration_s": 5.0, "provider": None} for i in range(4)]


def _settings(tmp_path: Path) -> Any:
    return SimpleNamespace(data_dir=tmp_path, effective_sfx_dir=tmp_path, effective_music_library_dir=tmp_path,
                           effective_music_dir=tmp_path, dry_run=True)


def test_prepare_video_applies_retouched_subtitles_and_keeps_the_automatic_text(tmp_path: Path):
    db = MontageDb({"subtitles": {"1": "Des chalands géants de 1 350 tonnes traversent enfin l'Europe."}})
    m = assemble.prepare_video(db, _settings(tmp_path), "vid", "pid")
    assert f"1{NBSP}350" in [w.text for w in m.plan.words_by_scene[1]]
    assert m.auto_subtitles["1"].startswith("Des chalands géants de 1") and "treize" not in m.auto_subtitles["1"]  # chiffres auto
    assert m.plan.words_by_scene[0][0].text == "70" and m.retouch.subtitles  # scène non retouchée : le montage automatique
    plain = assemble.prepare_video(MontageDb(None), _settings(tmp_path), "vid", "pid")
    assert not plain.retouch and " ".join(w.text for w in plain.plan.words_by_scene[1]) == plain.auto_subtitles["1"]


def test_choose_music_forced_by_the_retouch_even_where_the_model_has_none(tmp_path: Path):
    (tmp_path / "music_7.mp3").write_bytes(b"x")
    row = {"id": "music_7", "file": "music_7.mp3", "title": "Intrigante", "moods": ["mystere"], "formats": ["story"],
           "weight": 2.0, "enabled": True, "gain_db": 0, "start_s": 3.0, "lufs": -10.0, "missing": False}
    db = MontageDb(None, [row])
    template = MontageTemplate.model_validate({"audio": {"formats": ["timelapse"]}})  # pas de musique sur les récits
    script = ScriptV1.model_validate(_script())
    assert assemble.choose_music(db, _settings(tmp_path), template, "story", script, "pid", None)[0] is None
    track, why = assemble.choose_music(db, _settings(tmp_path), template, "story", script, "pid", None,
                                       forced=MusicChoice(track="music_7", start_s=20.0))
    assert track is not None and track.id == "music_7" and track.start_s == 20.0 and "retouche" in why["reason"]
    assert assemble.choose_music(db, _settings(tmp_path), MontageTemplate(), "story", script, "pid", "music_7",
                                 forced=MusicChoice(track=None))[0] is None  # « Sans musique »


def test_level_fix_only_outside_the_tolerance():
    assert assemble.level_fix_db(-16.08) == pytest.approx(2.08) and assemble.level_fix_db(-12.9) == pytest.approx(-1.1)
    assert assemble.level_fix_db(-14.4) == 0.0 and assemble.level_fix_db(None) == 0.0  # dans la tolérance, ou muette


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")
def test_fix_level_brings_a_quiet_final_back_to_target(tmp_path: Path):
    final = tmp_path / "final.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=64x112:r=16:d=6", "-f", "lavfi", "-i",
                    "sine=f=440:d=6,volume=0.05", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(final)], check=True)
    assert measure_loudness(final).lufs < -20  # type: ignore[operator]
    assert assemble.fix_level(final) > 5
    assert measure_loudness(final).lufs == pytest.approx(-14.0, abs=1.0)  # type: ignore[arg-type]
    assert assemble.fix_level(final) == 0.0 and not (tmp_path / "final.niveau.mp4").exists()


def test_tts_step_redoes_the_voice_chosen_by_the_retouch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from worker.steps import tts as tts_step

    (tmp_path / "narration.wav").write_bytes(b"old")
    asked: list[dict] = []
    monkeypatch.setattr(tts_step, "resolve_voice", lambda settings, voices, lang: (asked.append(voices) or (SimpleNamespace(name="qwen3"), "serena")))
    monkeypatch.setattr(tts_step, "load_generation_config", lambda settings, db: SimpleNamespace(voices={"fr": "kokoro:ff_siwis"}))
    saved: list[tuple] = []

    class Db:
        def fetch_one(self, sql: str, params: Any = None) -> dict:
            if "recipe" in sql:  # recipes.recipe_for_production : un drame retouché dit ses répliques seules
                return {"recipe": "story"}
            return {"lang": "fr", "timeline": {"scenes": []}, "production_id": "p", "script": _script(), "voice_speed": 1.0}

        def add_asset(self, **cols: Any) -> str:
            return "a"

        def execute(self, sql: str, params: Any = None) -> int:
            saved.append(params)
            return 1

    def ctx(payload: dict) -> Any:
        return SimpleNamespace(job=SimpleNamespace(video_id="v", payload=payload), db=Db(), settings=SimpleNamespace(dry_run=True, kokoro_speed=1.0),
                               video_dir=lambda vid: tmp_path, progress=lambda *a: None, log=lambda *a, **k: None)

    assert tts_step.TTSStep().run(ctx({}))["skipped"] is True  # narration déjà là : rien à refaire
    result = tts_step.TTSStep().run(ctx({"voice": "qwen3:serena", "retouch": True}))
    assert asked == [{"fr": "qwen3:serena"}] and result["voice"] == "qwen3:serena" and result["retouch"] is True
    assert saved and saved[-1][:2] == ("qwen3", "serena")  # videos.tts_provider, tts_voice
