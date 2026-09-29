"""Voix des personnages calées sur la bouche des clips (worker/lipsync.py, docs/38) : drame en voix constantes. Mesures
réelles de « Mamie Pomme » (29/09) : la bouche du clip parlait de 0,51 à 2,69 s puis de 3,27 à 4,96 s, la voix de
synthèse partait à 0,15 s. Tests sans audio pour la pose ; FFmpeg pour l'étirement et le montage."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from worker import lipsync
from worker.lipsync import Heard, Piece, assign, cut_between, mouth_span, pauses, phrases, plan_scene
from worker.steps.assemble import RenderPlan, build_command

LINE = "Mon fils se marie demain… et il me veut en servante."


def _words(spec: list[tuple[str, float, float]]) -> tuple[dict, ...]:
    return tuple({"w": w, "start": s, "end": e} for w, s, e in spec)


# Ce que Whisper et le détecteur de voix ont donné sur le clip de la scène 1 (le premier mot part de 0 s)
CLIP = Heard(_words([("mon", 0.0, 0.66), ("fils", 0.66, 1.04), ("se", 1.04, 1.3), ("marie", 1.3, 1.64), ("demain", 1.64, 2.6),
                     ("et", 3.3, 3.46), ("il", 3.46, 3.6), ("me", 3.6, 3.74), ("veut", 3.74, 3.98), ("en", 3.98, 4.1),
                     ("servante.", 4.1, 4.82)]),
             ((0.51, 2.69), (3.27, 4.96)), 0.95)
# La voix de synthèse : plus rapide, une pause plus courte après « demain… »
TTS = Heard(_words([("Mon", 0.0, 0.22), ("fils", 0.22, 0.5), ("se", 0.5, 0.62), ("marie", 0.62, 0.95), ("demain…", 0.95, 1.45),
                    ("et", 1.75, 1.86), ("il", 1.86, 1.98), ("me", 1.98, 2.1), ("veut", 2.1, 2.35), ("en", 2.35, 2.47),
                    ("servante.", 2.47, 3.3)]),
            ((0.02, 1.48), (1.72, 3.3)), 1.0)


def test_the_mouth_starts_where_the_voice_detector_hears_it():
    units = [(w["start"], w["end"]) for w in CLIP.words]
    assert mouth_span(units, CLIP.speech) == (0.51, 4.96)  # pas 0 s : Whisper fait partir le premier mot du début
    assert mouth_span([(1.26, 1.8), (4.5, 4.8)], [(0.55, 0.96), (1.73, 2.94), (3.27, 4.89)]) == (1.73, 4.89)
    # le détecteur rate le premier mot (il ne commence qu'après sa fin) : on garde celui de Whisper
    assert mouth_span([(1.28, 1.96), (4.9, 5.16)], [(2.91, 3.17), (3.52, 5.18)]) == (1.28, 5.18)
    assert phrases([(0.51, 2.69), (2.75, 3.0), (3.27, 4.96), (5.0, 5.05)], 0.51, 4.96) == [(0.51, 3.0), (3.27, 4.96)]
    gaps = pauses(TTS.speech)
    assert gaps == [(1.48, 1.72)] and cut_between((0.95, 1.45), (1.75, 1.86), gaps) == 1.6  # au milieu du blanc
    assert cut_between((1.98, 2.1), (2.1, 2.35), gaps) is None  # pas de blanc entre « me » et « veut » : pas de coupe


def test_each_phrase_of_the_line_is_laid_on_the_mouth_that_says_it():
    plan = plan_scene(LINE, "fr", CLIP, TTS, 5.17, 3.32)
    assert plan.mode == "phrases" and len(plan.pieces) == 2
    first, second = plan.pieces
    assert plan.head == pytest.approx(0.16)  # le plan commence 0,35 s avant que la bouche s'ouvre
    assert first.at == pytest.approx(0.35) and first.src == (0.02, 1.48)  # « Mon fils se marie demain… »
    assert first.factor == pytest.approx(1.4)  # la bouche prend 2,18 s pour 1,46 s : étirée au plus de 40 %
    assert second.src == (1.72, 3.3) and second.at == pytest.approx(3.27 - 0.16)  # « et il me veut en servante. »
    assert second.factor == pytest.approx(1.07, abs=0.01)
    assert plan.duration == pytest.approx(second.end + lipsync.TAIL_S, abs=0.002)
    words = dict((w, (a, b)) for w, a, b in plan.words)
    assert words["Mon"][0] == pytest.approx(0.35) and words["et"][0] == pytest.approx(second.at, abs=0.05)  # sous-titres sur la voix calée


def test_a_clip_that_does_not_say_the_line_uses_whoever_speaks_or_the_old_pose():
    garbled = Heard(_words([("générique", 0.0, 0.5)]), ((1.0, 3.5),), 0.1)
    plan = plan_scene(LINE, "fr", garbled, TTS, 5.17, 3.32)
    assert plan.mode == "span" and len(plan.pieces) == 1 and plan.pieces[0].at == pytest.approx(0.35)
    assert plan.pieces[0].factor == lipsync.F_MIN  # 2,5 s de parole pour 3,28 s de voix : resserrée de 20 % au plus
    assert plan_scene(LINE, "fr", Heard(), TTS, 5.17, 3.32).mode == "none"  # clip muet : l'ancienne pose
    assert plan_scene(LINE, "fr", Heard((), ((4.8, 5.0),), 0.0), TTS, 5.17, 3.32).mode == "none"  # un bruit, pas une phrase


def test_a_long_silence_before_the_mouth_opens_is_cut_from_the_clip():
    late = Heard(_words([(w["w"], w["start"] + 2.5, w["end"] + 2.5) for w in CLIP.words[:5]]), ((3.0, 5.1),), 0.9)
    plan = plan_scene("Mon fils se marie demain…", "fr", late, Heard(TTS.words[:5], ((0.02, 1.48),), 1.0), 5.17, 1.5)
    assert plan.head == lipsync.HEAD_MAX and plan.pieces[0].at == pytest.approx(3.0 - lipsync.HEAD_MAX)
    cmd = build_command(RenderPlan(clips=[Path("c0.mp4")], clip_durations=[5.17], scene_durations=[plan.duration],
                                   clip_offsets=[plan.head]), Path("o.mp4"), [], None)
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.startswith("[0:v]trim=start=2.000,setpts=PTS-STARTPTS,scale=1080:1920")


def test_piece_maps_synthetic_time_to_the_scene():
    p = Piece((1.0, 2.0), 0.5, 1.2)
    assert (p.out_s, p.end, p.map(1.5), p.map(9.0)) == pytest.approx((1.2, 1.7, 1.1, 1.7))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")
def test_stretch_keeps_the_exact_length(tmp_path):
    np = pytest.importorskip("numpy")
    rate = 24000
    x = np.sin(np.linspace(0, 2 * np.pi * 220, rate)).astype(np.float32)  # 1 s à 220 Hz
    y = lipsync.stretch(x, rate, 1.3, tmp_path)
    assert len(y) == round(rate * 1.3) and float(np.abs(y[: rate // 2]).max()) > 0.5
    voice = lipsync.scene_voice(x, rate, lipsync.ScenePlan(0.0, 2.0, (Piece((0.0, 1.0), 0.4, 1.0),)), tmp_path)
    assert len(voice) == 2 * rate + 1 and float(np.abs(voice[: int(0.39 * rate)]).max()) == 0.0  # silence avant la bouche


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")
def test_real_render_starts_the_clip_later(tmp_path):
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=64x112:r=24:d=5", str(clip)], check=True)
    out = tmp_path / "o.mp4"
    plan = RenderPlan(clips=[clip], clip_durations=[5.0], scene_durations=[2.0], clip_offsets=[1.5])
    subprocess.run(build_command(plan, out, ["-c:v", "libx264", "-preset", "ultrafast"], None), check=True, cwd=tmp_path)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                           capture_output=True, text=True, check=True)
    assert float(probe.stdout) == pytest.approx(2.0, abs=0.1)


def test_the_last_sync_is_reused_without_recomputing(tmp_path):
    """Essai du son de l'onglet Montage, ou calage impossible une fois : la piste et les débuts coupés du dernier montage ;
    calage coupé (DRAMA_LIPSYNC=false) : la timeline de l'étape voix, gardée au premier calage."""
    import json
    from types import SimpleNamespace

    from worker.models import NarrationTimeline, SceneTiming

    settings = SimpleNamespace(data_dir=tmp_path)
    vdir = tmp_path / "videos" / "v1"
    (vdir / "lines").mkdir(parents=True)
    synced = NarrationTimeline(lang="fr", aligner=lipsync.ALIGNER, scenes=[SceneTiming(index=0, start=0, duration=3.2)])
    assert lipsync.last_sync(settings, "v1", synced) is None  # rien sur le disque
    (vdir / "lipsync.wav").write_bytes(b"RIFF")
    (vdir / "lines" / "lipsync.json").write_text(json.dumps({"heads": [1.2], "report": {"calees": [0]}}), encoding="utf-8")
    last = lipsync.last_sync(settings, "v1", synced)
    assert last and last.heads == [1.2] and last.track == vdir / "lipsync.wav" and last.report == {"calees": [0]}
    assert lipsync.last_sync(settings, "v1", synced.model_copy(update={"aligner": "proportional"})) is None
    (vdir / "narration.wav").write_bytes(b"RIFFvoix")
    tts = NarrationTimeline(lang="fr", scenes=[SceneTiming(index=0, start=0, duration=3.0, speech_start=0.15, speech_end=2.0)])
    stamp = lipsync._stamp(vdir / "narration.wav")
    (vdir / "lines" / "lines.json").write_text(json.dumps({"narration": stamp, "tts_timeline": tts.model_dump()}), encoding="utf-8")
    assert lipsync.tts_timeline(settings, "v1") == tts
    (vdir / "narration.wav").write_bytes(b"RIFFautre voix")  # voix refaite : la timeline gardée ne vaut plus
    assert lipsync.tts_timeline(settings, "v1") is None


def test_line_regions_on_the_three_hard_clips_of_mamie_pomme():
    """Mesures réelles du 29/09 : le détecteur rate une réplique criée (plan 7), Whisper place un mot dans un silence
    (plan 3) ou fait durer le premier mot depuis 0 s (plan 9, sanglots avant la réplique)."""
    from worker.lipsync import line_regions

    # plan 3 : « Maman, » placé par Whisper à 2,26-2,74 s, dans un blanc ; la bouche le dit à 1,60-2,08 s
    units3 = [(2.26, 2.74), (2.74, 3.22), (3.22, 3.44), (3.44, 3.6), (3.6, 4.0), (4.0, 4.3), (4.3, 4.5), (4.5, 4.98)]
    vad3 = [(0.066, 0.574), (0.994, 1.374), (1.602, 2.078), (2.786, 5.184)]
    assert line_regions(units3, vad3) == [(1.602, 2.078), (2.786, 5.184)]
    # plan 7 : « Attention la vieille ! » crié sur de la musique : seule l'énergie du son le montre
    units7 = [(1.28, 1.96), (1.96, 2.42), (2.42, 2.94), (3.52, 3.8), (3.8, 4.2), (4.2, 4.6), (4.6, 5.16)]
    vad7 = [(2.914, 3.166), (3.522, 5.184)]
    energy7 = [0.01] * 8 + [0.1] * 18 + [0.02, 0.01] + [0.25] * 8 + [0.03] + [0.3] * 20 + [0.01] * 8 + [0.2] * 30 + [0.01] * 10
    assert line_regions(units7, vad7, energy7) == [(1.4, 3.166), (3.522, 5.184)]  # l'ambiance du début n'en fait pas partie
    # plan 9 : premier mot de 0 à 1,74 s (sanglots avant) ; il chevauche le passage détecté : on garde le détecteur
    units9 = [(0.0, 1.74), (1.74, 2.2), (2.74, 3.3), (3.3, 3.82), (3.82, 4.88)]
    energy9 = [0.01] * 16 + [0.06] * 16 + [0.1] * 60 + [0.02] * 12
    assert line_regions(units9, [(1.602, 5.184)], energy9) == [(1.602, 5.184)]


def test_the_line_is_never_cut_inside_a_word():
    """« Madame Figue », plan 16 (29/09) : la bouche parle en trois morceaux (un souffle, « Prune… », « pourquoi elle
    dort… ») et Whisper place « pourquoi » 0,5 s trop tôt. Avant, la voix était coupée après « pour » (« pour » à 1,4 s,
    « quoi… » à 2,8 s). Désormais le souffle ne porte aucun mot, et la seule coupe tombe dans le blanc après « Prune ».
    """
    text = "Prune… Pourquoi elle dort dans ta chambre ?"
    clip = Heard(_words([("Prune,", 0.0, 1.92), ("pourquoi", 2.5, 3.34), ("elle", 3.34, 3.66), ("dort", 3.66, 4.08),
                         ("dans", 4.08, 4.28), ("ta", 4.28, 4.46), ("chambre?", 4.46, 5.16)]),
                 ((0.514, 0.734), (1.538, 2.078), (3.01, 5.184)), 1.0)
    tts = Heard(_words([("Prune,", 0.0, 0.32), ("pourquoi", 0.96, 1.64), ("elle", 1.64, 1.84), ("dort", 1.84, 1.94),
                        ("dans", 1.94, 2.12), ("ta", 2.12, 2.28), ("chambre", 2.28, 2.58), ("?", 2.58, 2.64)]),
                ((0.098, 0.478), (1.378, 2.67)), 1.0)
    plan = plan_scene(text, "fr", clip, tts, 5.17, 2.67)
    assert [p.src for p in plan.pieces] == [(0.098, 0.478), (1.378, 2.67)]  # « Prune… » puis « pourquoi … chambre ? »
    assert plan.pieces[1].at + plan.head == pytest.approx(3.01, abs=0.01)  # quand la bouche dit « pourquoi »
    assert assign([(0.0, 1.92), (2.5, 3.34), (3.34, 3.66)], [(0.514, 0.734), (1.538, 2.078), (3.01, 5.184)]) == [1, 2, 2]
    # « Mamie Pomme », plan 3 : « Maman, » placé par Whisper dans un blanc ; la phrase de bouche d'avant est vide : à elle
    assert assign([(2.26, 2.74), (2.74, 3.22), (3.22, 3.44)], [(1.602, 2.078), (2.786, 5.184)]) == [0, 1, 1]


def test_pauses_come_from_the_voice_energy_too():
    """Un blanc de 0,15 s que le détecteur (0,2 s au moins) ne voit pas, mais pas la fermeture d'un « k » (0,05 s)."""
    e = [0.2] * 30 + [0.001] * 15 + [0.2] * 20 + [0.001] * 5 + [0.2] * 30  # 10 ms par tranche
    assert pauses([(0.0, 1.0)], e) == [(0.3, 0.45)]
