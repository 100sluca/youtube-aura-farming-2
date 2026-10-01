"""Musiques de fond (docs/26-musique.md) : ambiances, choix d'une piste, égalisation, baisse sous la voix, bibliothèque."""

import json
import re
import shutil
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from worker import music
from worker.media import Loudness, parse_ebur128
from worker.models import WordTiming
from worker.montage import DEFAULTS_FILE, AudioLayer
from worker.music import (
    MOODS,
    VOICE_REF_LUFS,
    Track,
    choose_track,
    duck_amount,
    duck_expression,
    library_files,
    mix_levels,
    mood_brief,
    mood_ids,
    music_start,
    speech_segments,
    sync_library,
)
from worker.sfx import SfxCue
from worker.steps.assemble import RenderPlan, apply_audio, build_command, sound_command


def _t(tid: str, moods: str, formats: str, weight: float = 1.0, **kw) -> Track:
    return Track(
        id=tid,
        file=f"{tid}.mp3",
        moods=tuple(moods.split()),
        formats=tuple(formats.split()),
        weight=weight,
        path=Path(f"{tid}.mp3"),
        **kw,
    )


# Les pistes du 28/09 telles que décrites par Luca (migration 0018)
LIBRARY = [
    _t("music_0", "sentimental tragique majestueux", "story tour"),
    _t("music_1", "pose decouverte", "story tour"),
    _t("music_2", "pose decouverte", "story tour", 0.5),
    _t("music_3", "epique majestueux", "story timelapse tour"),
    _t("music_4", "joyeux", "timelapse"),
    _t("music_5", "triste sentimental", "story"),
    _t("music_6", "pose", "story"),
    _t("music_7", "mystere pose decouverte", "story timelapse tour", 2.0),
    _t("music_8", "voyage sentimental decouverte", "story timelapse tour"),
    _t("music_9", "tragique sentimental decouverte", "story tour"),
]


def test_defaults_file_has_the_mixing_constants_of_the_code():
    """L'écoute de l'onglet Montage (lib/audio-mix.ts) lit ces constantes dans defaults.json : elles suivent le code."""
    audio = json.loads(DEFAULTS_FILE.read_text(encoding="utf-8"))["audio"]
    assert audio["voice_ref_lufs"] == music.VOICE_REF_LUFS and audio["solo_ref_lufs"] == music.SOLO_REF_LUFS
    assert audio["unknown_lufs"] == music.UNKNOWN_LUFS and audio["max_leveling_db"] == music.MAX_LEVELING_DB
    assert audio["duck_merge_gap_s"] == music.DUCK_MERGE_GAP_S
    assert (audio["duck_attack_s"], audio["duck_release_s"]) == (music.DUCK_ATTACK_S, music.DUCK_RELEASE_S)
    assert (audio["fade_in_s"], audio["fade_out_s"], audio["output_lufs"]) == (
        music.FADE_IN_S,
        music.FADE_OUT_S,
        music.OUTPUT_LUFS,
    )
    assert audio["moods"] == {k: list(v) for k, v in MOODS.items()}
    # le dashboard refait le choix automatique d'une piste pour la vidéo d'essai (lib/music-library.ts : chooseTrack)
    assert audio["related"] == {k: list(v) for k, v in music.RELATED.items()}
    assert audio["aliases"] == {k: list(v) for k, v in music.ALIASES.items()}


def test_mood_ids_reads_ids_labels_and_the_old_english_moods():
    assert mood_ids("mystere") == ["mystere"] and mood_ids("Mystère") == ["mystere"] and mood_ids("Posé") == ["pose"]
    assert mood_ids("mysterious") == ["mystere"] and mood_ids("suspense") == ["mystere"]
    assert mood_ids("luxury") == ["decouverte"] and mood_ids("inspiring") == ["epique", "joyeux"]
    assert mood_ids("epic, emotional") == ["epique", "sentimental"]
    assert mood_ids("découverte") == ["decouverte"] and mood_ids("xyz") == [] and mood_ids(None) == []


def test_choose_track_follows_format_and_mood_and_is_stable():
    track, mood = choose_track(LIBRARY, "story", "mysterious", "prod-1")
    assert track and track.id == "music_7" and mood == "mystere"
    assert choose_track(LIBRARY, "story", "mysterious", "prod-1")[0] == track  # même production, même tirage
    track, mood = choose_track(LIBRARY, "timelapse", "joyeux", "p")
    assert track and track.id == "music_4" and mood == "joyeux"
    # music_4 n'est que pour les chantiers : une visite joyeuse passe aux ambiances voisines (découverte)
    track, mood = choose_track(LIBRARY, "tour", "upbeat", "p")
    assert mood == "decouverte" and track and "tour" in track.formats


def test_choose_track_draws_by_preference():
    """music_7 (préférence 2) sort environ deux fois plus que music_1 (1) et quatre fois plus que music_2 (0,5)."""
    picks = Counter(choose_track(LIBRARY, "story", "pose", f"prod-{i}")[0].id for i in range(4000))  # type: ignore[union-attr]
    assert set(picks) == {"music_1", "music_2", "music_6", "music_7"}
    assert 1.6 < picks["music_7"] / picks["music_1"] < 2.5 and 1.6 < picks["music_1"] / picks["music_2"] < 2.5


def test_choose_track_skips_disabled_missing_and_undescribed_tracks():
    lib = [
        _t("off", "mystere", "story", enabled=False),
        Track(id="gone", file="gone.mp3", moods=("mystere",), formats=("story",), path=None),
        _t("new", "", ""),  # nouvelle piste, aucun format coché
        _t("ok", "pose", "story"),
    ]
    track, mood = choose_track(lib, "story", "mystere", "p")
    assert track and track.id == "ok" and mood == "pose"  # mystère → voisine « posé »
    assert choose_track(lib, "timelapse", "mystere", "p") == (None, None)
    # aucune ambiance reconnue : ambiances de la série, puis n'importe quelle piste du format
    assert choose_track(LIBRARY, "story", "???", "p", series_moods=["sad"])[1] == "triste"
    assert choose_track(LIBRARY, "story", None, "p")[1] is None


def test_mood_brief_lists_only_the_moods_that_have_a_track():
    brief = mood_brief(LIBRARY, "timelapse", ["inspiring", "epic", "upbeat"])
    assert "- epique (épique) : exploit" in brief and "- joyeux : léger" in brief and "- mystere (mystère)" in brief
    assert "tragique" not in brief and "triste" not in brief
    assert brief.endswith("Conseillées pour cette série : epique, joyeux.")
    assert mood_brief(LIBRARY, "story") and mood_brief([], "story") == ""


def test_mix_levels_bring_every_track_to_the_same_loudness():
    audio = AudioLayer()
    loud = mix_levels(audio, with_voice=True, track_lufs=-6.7, narration_lufs=-18.8)
    soft = mix_levels(audio, with_voice=True, track_lufs=-18.1, narration_lufs=-18.8)
    assert loud.voice_gain_db == pytest.approx(0.8) and loud.duck_db == 4.0
    assert -6.7 + loud.music_gain_db == pytest.approx(VOICE_REF_LUFS - 10) == -18.1 + soft.music_gain_db
    mine = mix_levels(AudioLayer(voice_db=2, music_db=-14), with_voice=True, track_lufs=-10, track_gain_db=-3, narration_lufs=-18)
    assert (mine.voice_gain_db, mine.music_gain_db) == (2.0, pytest.approx(-18 - 14 + 10 - 3))
    solo = mix_levels(AudioLayer(solo_db=2, sfx_db=-3), with_voice=False, track_lufs=-10)
    assert solo.music_gain_db == pytest.approx(-20 + 2 + 10) and solo.duck_db == 0 and solo.sfx_gain_db == -3
    assert mix_levels(audio, with_voice=False).music_gain_db == pytest.approx(-20 + 14)  # piste pas encore mesurée
    # garde-fou : il borne l'égalisation d'une piste presque muette (+30 dB au plus), le réglage s'y ajoute
    assert mix_levels(audio, with_voice=True, track_lufs=-90).music_gain_db == 30 - 10


def test_music_can_be_turned_down_far_below_the_slider():
    """Luca (30/09) : musique trop forte même tout en bas ; une valeur tapée descend jusqu'à −120 dB, sans garde-fou."""
    quiet = mix_levels(AudioLayer(music_db=-100), with_voice=True, track_lufs=-6, narration_lufs=-18)
    assert quiet.music_gain_db == pytest.approx(VOICE_REF_LUFS + 6 - 100)
    assert mix_levels(AudioLayer(solo_db=-120), with_voice=False, track_lufs=-20).music_gain_db == pytest.approx(-120)
    with pytest.raises(ValueError):
        AudioLayer(music_db=-121)


def test_speech_segments_and_the_ducking_curve():
    words = [
        WordTiming(text=w, start=s, end=e)
        for w, s, e in [("Il", 0.4, 0.6), ("était", 0.65, 1.0), ("une", 1.5, 1.7), ("fois", 3.0, 3.4), ("rien", 3.4, 3.4)]
    ]
    segments = speech_segments(words)
    assert segments == [(0.4, 1.7), (3.0, 3.4)]  # 0,5 s de silence : même passage ; 1,3 s : la musique remonte
    assert duck_amount(0.0, segments) == 0 and duck_amount(0.34, segments) == pytest.approx(0.5)
    assert duck_amount(1.0, segments) == 1 and duck_amount(1.7 + 0.225, segments) == pytest.approx(0.5)
    assert duck_amount(2.5, segments) == 0
    expr = duck_expression(segments, 6.0)
    assert expr and duck_expression(segments, 0) is None and duck_expression([], 6) is None

    def clip(x: float, lo: float, hi: float) -> float:
        return min(hi, max(lo, x))

    depth = 1 - 10 ** (-6 / 20)
    for t in (0.0, 0.3, 0.34, 1.0, 1.9, 2.2, 2.9, 3.2, 3.7, 5.0):
        assert eval(expr, {"clip": clip, "min": min, "max": max, "t": t}) == pytest.approx(
            1 - depth * duck_amount(t, segments), abs=1e-3
        )


def test_duck_expression_stays_shallow_for_ffmpeg():
    """L'analyseur d'expressions de FFmpeg refuse plus de 100 niveaux d'imbrication : max() en arbre équilibré."""
    expr = duck_expression([(i * 2.0, i * 2.0 + 1) for i in range(64)], 4.0)
    depth = best = 0
    for ch in expr or "":
        depth += (ch == "(") - (ch == ")")
        best = max(best, depth)
    assert best < 20


def test_music_start_keeps_the_video_inside_the_file():
    track = _t("m", "pose", "story", start_s=40.0, duration_s=78.0)
    assert music_start(track, 30.0) == 40.0
    assert music_start(track, 45.0) == 33.0  # sinon la piste finirait et repartirait de zéro en pleine vidéo
    assert music_start(_t("m", "pose", "story", start_s=10.0, duration_s=20.0), 30.0) == 0.0  # plus courte : elle boucle


def test_apply_audio_sets_the_plan_and_reports_the_mix():
    words = [WordTiming(text="Bonjour", start=0.5, end=1.2)]
    track = _t("music_7", "mystere", "story", lufs=-10.0, gain_db=-2.0, start_s=5.0, duration_s=227.0)
    plan = RenderPlan(clips=[Path("c.mp4")], clip_durations=[5.0], scene_durations=[5.0], narration=Path("n.wav"))
    mix = apply_audio(plan, AudioLayer(), track, narration_lufs=-20.0, words=words)
    assert plan.music == Path("music_7.mp3") and plan.music_start_s == 5.0 and plan.speech == [(0.5, 1.2)]
    assert (plan.voice_gain_db, plan.music_gain_db, plan.duck_db) == (2.0, pytest.approx(-18 - 10 + 10 - 2), 4.0)
    assert mix["track"] == "music_7" and mix["narration_lufs"] == -20.0 and mix["duck_db"] == 4.0
    graph = build_command(plan, Path("o.mp4"), [], None)
    assert "atrim=start=5.000,asetpts=PTS-STARTPTS,volume=-20.00dB" in graph[graph.index("-filter_complex") + 1]
    silent = RenderPlan(clips=[Path("c.mp4")], clip_durations=[5.0], scene_durations=[5.0])
    assert apply_audio(silent, AudioLayer(), None)["track"] is None and silent.music is None


def test_sound_command_keeps_the_picture_and_remixes_the_sound():
    """Essai du son (onglet Montage → Son) : l'image de la vidéo montée est copiée, le son refait par le même graphe."""
    cue = SfxCue(Path("pas.wav"), 1.0, 2.0, 0.5, False)
    plan = RenderPlan(
        clips=[Path("c.mp4")],
        clip_durations=[5.0],
        scene_durations=[5.0],
        narration=Path("n.wav"),
        music=Path("m.mp3"),
        music_gain_db=-17.5,
        duck_db=4.0,
        speech=[(0.5, 2.0)],
        sfx=[cue],
    )
    cmd = sound_command(plan, Path("final.mp4"), Path("essai.mp4"))
    assert cmd[cmd.index("-i") + 1] == "final.mp4" and "c.mp4" not in cmd  # pas de remontage des clips
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "[1:a]" in graph and "[2:a]" in graph and "[3:a]" in graph  # voix, musique, bruitage
    assert "volume=-17.50dB" in graph and "eval=frame" in graph and graph.endswith("[aout]")
    assert cmd[cmd.index("-c:v") + 1] == "copy" and ["-map", "0:v"] == cmd[cmd.index("-map") : cmd.index("-map") + 2]
    assert cmd[-1] == "essai.mp4" and cmd[cmd.index("-t") + 1] == "5.000"


def test_parse_ebur128_summary():
    stderr = (
        "Input #0, mp3, from 'm.mp3':\n  Duration: 00:04:09.50, start: 0.025057, bitrate: 192 kb/s\n"
        "[Parsed_ebur128_0 @ 0000] Summary:\n\n  Integrated loudness:\n    I:         -15.8 LUFS\n"
        "    Threshold: -26.0 LUFS\n\n  Loudness range:\n    LRA:         1.9 LU\n\n  True peak:\n    Peak:       -2.6 dBFS"
    )
    assert parse_ebur128(stderr) == Loudness(-15.8, -2.6, 249.5)
    assert parse_ebur128("Duration: 00:00:02.00\nSummary:\n    I:         -70.0 LUFS\n    Peak:       -inf dBFS").lufs is None


class FakeDb:
    """Juste ce que sync_library demande à la base."""

    def __init__(self, rows: list[dict]) -> None:
        self.rows = {r["id"]: r for r in rows}

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        return [dict(r) for r in self.rows.values()]

    def execute(self, sql: str, params=None) -> int:
        if sql.startswith("insert into music_tracks"):
            tid, file, title = params
            self.rows.setdefault(
                tid,
                {
                    "id": tid,
                    "file": file,
                    "title": title,
                    "moods": [],
                    "formats": [],
                    "weight": 1.0,
                    "enabled": True,
                    "gain_db": 0,
                    "start_s": 0,
                    "lufs": None,
                    "missing": False,
                    "file_size": None,
                    "file_mtime": None,
                },
            )
        elif "lufs = %s" in sql:
            file, lufs, peak, dur, size, mtime, tid = params
            self.rows[tid].update(
                file=file, lufs=lufs, peak_db=peak, duration_s=dur, file_size=size, file_mtime=mtime, missing=False
            )
        elif "missing = true" in sql:
            self.rows[params[0]]["missing"] = True
        elif "missing = false" in sql:
            self.rows[params[1]].update(missing=False, file=params[0])
        return 1


def test_sync_library_adds_new_files_measures_once_and_flags_removed_ones(tmp_path, monkeypatch):
    for name in ("music_1.mp3", "music_2.MP3", "notes.txt", "music_1.wav"):
        (tmp_path / name).write_bytes(b"x" * 10)
    assert sorted(library_files(tmp_path)) == ["music_1", "music_2"]  # music_1.wav : même nom, le premier reste
    measured: list[str] = []
    monkeypatch.setattr(music, "measure_loudness", lambda p: measured.append(p.name) or Loudness(-12.0, -1.0, 90.0))
    db = FakeDb(
        [
            {
                "id": "music_1",
                "file": "music_1.mp3",
                "title": "Narration douce",
                "moods": ["pose"],
                "formats": ["story"],
                "weight": 1.0,
                "enabled": True,
                "gain_db": 0,
                "start_s": 0,
                "lufs": None,
                "missing": False,
                "file_size": None,
                "file_mtime": None,
            },
            {
                "id": "old",
                "file": "old.mp3",
                "title": "Retirée",
                "moods": [],
                "formats": ["story"],
                "weight": 1.0,
                "enabled": True,
                "lufs": -9.0,
                "missing": False,
            },
        ]
    )
    tracks = {t.id: t for t in sync_library(db, tmp_path)}
    assert sorted(measured) == ["music_1.mp3", "music_2.MP3"] and db.rows["old"]["missing"] is True
    assert tracks["music_1"].lufs == -12.0 and tracks["music_1"].title == "Narration douce" and tracks["music_1"].usable
    assert tracks["music_2"].title == "Music 2" and tracks["music_2"].formats == () and tracks["old"].path is None
    sync_library(db, tmp_path)
    assert len(measured) == 2  # déjà mesurées, fichiers inchangés : pas de nouvelle mesure
    (tmp_path / "music_2.MP3").write_bytes(b"y" * 20)  # fichier remplacé
    sync_library(db, tmp_path)
    assert measured[-1] == "music_2.MP3" and len(measured) == 3
    assert isinstance(db.rows["music_2"]["file_mtime"], datetime) and db.rows["music_2"]["file_mtime"].tzinfo == UTC


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")
def test_real_render_levels_and_ducks_the_music(tmp_path):
    """Le vrai FFmpeg accepte le graphe (expression de la baisse comprise) et la musique baisse bien sous la voix."""
    clip, nar, mus, out = tmp_path / "c.mp4", tmp_path / "n.wav", tmp_path / "m.wav", tmp_path / "o.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=64x112:r=16:d=4", str(clip)], check=True)
    # voix : un son de 1 à 2 s seulement ; musique : une note continue
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=f=1000:d=4",
            "-af",
            "volume='between(t,1,2)':eval=frame",
            str(nar),
        ],
        check=True,
    )
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=10", str(mus)], check=True)
    plan = RenderPlan(
        clips=[clip],
        clip_durations=[4.0],
        scene_durations=[4.0],
        narration=nar,
        music=mus,
        music_gain_db=-6.0,
        duck_db=12.0,
        speech=[(1.0, 2.0)],
    )
    subprocess.run(build_command(plan, out, ["-c:v", "libx264", "-preset", "ultrafast"], None), check=True, capture_output=True)

    def music_level(start: float) -> float:  # niveau de la note de la musique (220 Hz) sur 0,4 s
        r = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "info",
                "-ss",
                str(start),
                "-t",
                "0.4",
                "-i",
                str(out),
                "-af",
                "lowpass=f=400,lowpass=f=400,volumedetect",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
        )
        return float(re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr).group(1))  # type: ignore[union-attr]

    assert music_level(1.3) < music_level(2.9) - 6  # baissée pendant la voix, remontée après
