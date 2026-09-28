from pathlib import Path

import pytest

from worker.models import ScriptV1
from worker.steps.assemble import RenderPlan, build_command, plan_from
from worker.subtitles import BUILTIN_PROFILES
from worker.timeline import LEAD_IN, TAIL, SceneSpeech, estimate_speech_s, plan_timeline


def test_plan_timeline_stretches_long_scenes_and_places_words():
    tl = plan_timeline(
        [SceneSpeech(0, 5.0, "Une phrase courte.", 2.0), SceneSpeech(1, 5.0, "Une très longue phrase qui déborde.", 6.0),
         SceneSpeech(2, 5.0, "", None)],
        "fr",
    )
    assert [s.duration for s in tl.scenes] == [5.0, pytest.approx(LEAD_IN + 6.0 + TAIL), 5.0]
    assert tl.scenes[1].start == 5.0 and tl.scenes[2].start == pytest.approx(5.0 + LEAD_IN + 6.0 + TAIL)
    assert tl.scenes[1].words[0].start == pytest.approx(5.0 + LEAD_IN)
    assert tl.scenes[1].words[-1].end == pytest.approx(5.0 + LEAD_IN + 6.0, abs=1e-3)
    assert tl.scenes[2].words == []
    assert tl.duration_s == pytest.approx(sum(s.duration for s in tl.scenes))


def test_estimate_speech():
    assert estimate_speech_s("") is None
    # 3 mots par seconde (voix mesurée à 3,2 le 28/09, docs/24)
    assert estimate_speech_s("un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze") == pytest.approx(5.0)


def _script() -> ScriptV1:
    return ScriptV1.model_validate({
        "scenes": [{"index": i, "duration_s": 5, "visual_prompt": "x", "on_screen_text": {"fr": "Titre"} if i == 1 else {}}
                   for i in range(4)],
        "metadata": {"fr": {"title": "t", "description": "d"}},
    })


def test_plan_from_uses_timeline_and_places_titles():
    script = _script()
    tl = plan_timeline([SceneSpeech(i, 5.0, "mot", 1.0) for i in range(4)], "fr")
    durations, words, titles = plan_from(script, "fr", tl)
    assert durations == [5.0] * 4 and all(len(w) == 1 for w in words)
    assert titles == [(5.0, 10.0, "Titre")]
    assert plan_from(script, "fr", None)[1] == [[], [], [], []]


def _plan(**kw) -> RenderPlan:
    base = dict(clips=[Path(f"c{i}.mp4") for i in range(3)], clip_durations=[5.0, 3.0, 2.0], scene_durations=[5.0, 3.9, 5.0])
    return RenderPlan(**{**base, **kw})


def test_build_command_stretches_short_clips_and_holds_last_frame():
    cmd = build_command(_plan(), Path("out.mp4"), ["-c:v", "libx264"], None)
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:v]scale=1080:1920" in graph and "setpts=1.3000*PTS" in graph  # 3 s → 3,9 s : ralenti ×1,3
    assert "tpad=stop_mode=clone" in graph  # 2 s → 5 s : ×1,35 puis image tenue
    assert "concat=n=3:v=1:a=0[vcat]" in graph and "[vcat]null[vout]" in graph
    assert cmd[cmd.index("-t") + 1] == "13.900" and "-an" in cmd


def test_build_command_ducks_music_under_narration_and_burns_subtitles():
    plan = _plan(narration=Path("narration.wav"), music=Path("m.mp3"), music_gain_db=-12.5, voice_gain_db=0.8, duck_db=4.0,
                 speech=[(0.4, 3.2), (4.1, 9.0)], profile=BUILTIN_PROFILES["impact"])
    cmd = build_command(plan, Path("out.mp4"), ["-c:v", "h264_nvenc"], "subtitles=subtitles.ass:fontsdir=fonts")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert cmd[cmd.index("-stream_loop") + 3] == "m.mp3"  # musique en boucle
    assert "volume=0.80dB[nar]" in graph and "volume=-12.50dB" in graph  # voix et musique égalisées puis réglées
    assert "volume='1-0.3690*max(clip(" in graph and ":eval=frame" in graph  # 4 dB de moins pendant la voix
    assert "amix=inputs=2" in graph and "loudnorm=I=-14" in graph
    assert "[vcat]subtitles=subtitles.ass:fontsdir=fonts[vout]" in graph
    assert "-map" in cmd and "[aout]" in cmd and "h264_nvenc" in cmd
