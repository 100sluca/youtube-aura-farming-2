"""Vidéos longues narrées par Luca (docs/63) : calculs purs du script, de la voix, des plans et du montage."""

from __future__ import annotations

import shutil
import wave
from pathlib import Path

import numpy as np
import pytest

from worker.longform import render, vocoder, voice, voice_mod
from worker.longform.models import ChapterBatch, LongIdea, LongReview, Outline, ShotSpec
from worker.longform.motion import FPS, card_alpha, clip_frames, window
from worker.longform.prompts import WORDS_PER_MIN
from worker.longform.write import (
    director_groups,
    keyed,
    lint_long,
    numbered_text,
    para_key,
    sanitize_shots,
    script_words,
    word_budget,
)


def outline(n: int = 3, minutes: float = 1.0) -> Outline:
    return Outline.model_validate(
        {
            "central_idea": "x",
            "ending": "Fin.",
            "chapters": [{"title": f"C{i}", "goal": "g", "minutes": minutes} for i in range(n)],
        }
    )


def chapter(index: int, *texts: str) -> dict:
    return {"index": index, "title": f"C{index}", "paragraphs": [{"text": t, "show": ""} for t in texts]}


# ---- Script ----------------------------------------------------------------------------------------------------------


def test_word_budget_follows_reading_speed() -> None:
    assert word_budget(22) == 22 * WORDS_PER_MIN
    assert para_key(2, 3) == "c2p3"


def test_lint_long_flags_length_long_sentences_and_openers() -> None:
    long_sentence = " ".join(["mot"] * 30) + "."
    chapters = [chapter(0, "Bonjour à tous, aujourd'hui on parle du Sphinx. " + long_sentence)]
    problems = [p.problem for p in lint_long(chapters, outline(3), 1.0)]
    assert any("formule d'introduction" in p for p in problems)
    assert any("phrase de 30 mots" in p for p in problems)
    assert any("mots pour 150 visés" in p for p in problems)


def test_lint_long_accepts_a_well_sized_script() -> None:
    sentence = "Le vent souffle sur le plateau de Gizeh avant l'aube."  # 10 mots
    para = " ".join([sentence] * 7)  # 70 mots
    chapters = [chapter(i, para, para) for i in range(3)]  # 140 mots par chapitre
    problems = lint_long(chapters, outline(3, minutes=140 / WORDS_PER_MIN), 3 * 140 / WORDS_PER_MIN)
    assert problems == []


def test_keyed_numbers_paragraphs() -> None:
    k = keyed([chapter(0, "un deux trois", "quatre cinq"), chapter(1, "six")])
    assert [p["key"] for c in k for p in c["paragraphs"]] == ["c0p0", "c0p1", "c1p0"]
    assert k[0]["paragraphs"][0]["words"] == 3
    assert script_words([chapter(0, "un deux trois")]) == 3


def test_models_accept_loose_llm_output() -> None:
    batch = ChapterBatch.model_validate({"index": 2, "paragraphs": [{"text": "a"}]})  # un chapitre à plat
    assert batch.chapters[0].index == 2
    review = LongReview.model_validate({"ok": False, "problems": ["trop court"]})
    assert review.problems[0].problem == "trop court"
    idea = LongIdea.model_validate(
        {"subject": "s", "title": "t", "hook": "h", "promise": "p", "thumbnail": {"prompt": "x"}, "wikipedia": "Sphinx de Gizeh"}
    )
    assert idea.wikipedia == ["Sphinx de Gizeh"]


# ---- Plans du réalisateur --------------------------------------------------------------------------------------------


def test_numbered_text_marks_every_fifth_word() -> None:
    text, n = numbered_text("a b c d e f g")
    assert n == 7
    assert text == "[0] a b c d e [5] f g"


def test_sanitize_shots_forces_word_zero_and_fills_gaps() -> None:
    paras = [
        {"key": "c0p0", "text": " ".join(["m"] * 40), "show": "un lieu"},
        {"key": "c0p1", "text": "court texte ici", "show": "objet"},
    ]
    shots = [
        ShotSpec(para="c0p0", at_word=4, kind="clip", visual_prompt="a"),
        ShotSpec(para="c0p0", at_word=20, visual_prompt="b"),
        ShotSpec(para="c0p0", at_word=20, visual_prompt="doublon"),
        ShotSpec(para="c0p0", at_word=99, visual_prompt="trop loin"),
    ]
    out = sanitize_shots(shots, paras)
    assert [(s.para, s.at_word) for s in out] == [("c0p0", 0), ("c0p0", 20), ("c0p0", 37), ("c0p1", 0)]
    assert out[-1].visual_prompt == "objet"  # paragraphe oublié : un plan tiré de ce qu'on voit


def test_director_groups_split_by_words() -> None:
    paras = [{"key": f"c0p{i}", "words": 400} for i in range(5)]
    assert [len(g) for g in director_groups(paras, 900)] == [2, 2, 1]


# ---- Voix ------------------------------------------------------------------------------------------------------------


def test_compare_reads_numbers_both_ways() -> None:
    ok = voice.compare("En 1347, la peste arrive.", "en mille trois cent quarante-sept la peste arrive")
    assert ok["ratio"] == 1.0 and not ok["missing"]
    assert voice.take_verdict(ok) == "ok"


def test_compare_reports_skipped_passage() -> None:
    res = voice.compare("La peste arrive à Marseille. Personne ne sait d'où elle vient.", "la peste arrive à marseille")
    assert res["missing"] and "personne" in res["missing"][0]
    assert voice.take_verdict(res) == "problem"


def test_compare_tolerates_a_reworded_word() -> None:
    res = voice.compare("Le navire coule en quelques minutes.", "le bateau coule en quelques minutes")
    assert res["ratio"] > 0.8 and not res["missing"]


def test_denoise_only_in_a_noisy_room() -> None:
    assert voice.denoise_filter(None) is None
    assert voice.denoise_filter(-72.0) is None  # pièce calme (les prises de Khéops) : la voix n'est pas touchée
    assert voice.denoise_filter(-45.2) == "afftdn=nr=8:nf=-45"  # repli sans DeepFilterNet, réglé sur le bruit mesuré
    assert not any("afftdn" in a for a in voice.finish_command(Path("a.wav"), Path("b.wav"), 5.0))


def take_signal(sr: int, rng: np.random.Generator, mouth: float = 0.006) -> np.ndarray:
    """6 s : bruit de pièce à -68 dB, « toc » du micro à 0,03 s, bruit de bouche isolé à 0,6 s (-44 dB par défaut),
    voix de 2,0 à 3,2 s et de 3,6 à 5,0 s (pause de 0,4 s), clic du bouton d'arrêt à 5,95 s."""
    t = np.arange(sr * 6) / sr
    x = rng.normal(0, 10 ** (-68 / 20), t.size)
    voiced = ((t >= 2.0) & (t < 3.2)) | ((t >= 3.6) & (t < 5.0))
    x += 0.2 * np.sin(2 * np.pi * 150 * t) * voiced
    for at, dur, amp in ((0.03, 0.015, 0.1), (0.6, 0.12, mouth), (5.95, 0.01, 0.1)):
        k = (t >= at) & (t < at + dur)
        x[k] += amp * rng.normal(0, 1, k.sum())
    return x


def test_cut_follows_the_voice_not_the_clicks() -> None:
    sr = voice.SR
    x = take_signal(sr, np.random.default_rng(1))
    floor = voice.floor_of(x)
    assert floor is not None and abs(floor + 68) < 3
    start, end = voice.take_bounds(
        x, floor, {"words": [{"w": "En", "start": 0.0, "end": 2.3}, {"w": "fin", "start": 4.6, "end": 6.0}]}
    )
    assert 1.85 < start < 2.0  # ni le « toc » du micro ni le bruit de bouche ; Whisper disait 0,00 s
    assert 5.0 < end < 5.5  # l'extinction de la voix, pas le clic d'arrêt
    loud = take_signal(sr, np.random.default_rng(1), mouth=0.03)  # un son plus fort, 1,4 s avant la phrase
    assert voice.speech_bounds(loud, floor)[0] < 1.0  # sans Whisper, il passe pour la voix
    guided = voice.speech_bounds(loud, floor, first_word=2.05, last_word=4.95)
    assert guided is not None and 1.85 < guided[0] < 2.0  # Whisper situe la phrase : il reste dehors


def test_pauses_are_lowered_and_the_voice_is_untouched() -> None:
    sr = voice.SR
    x = take_signal(sr, np.random.default_rng(2))
    g = voice.pause_gain(x, voice.floor_of(x))
    assert g[int(2.5 * sr)] == pytest.approx(1.0, abs=1e-3) and g[int(4.0 * sr)] == pytest.approx(1.0, abs=1e-3)
    assert 20 * np.log10(g[int(0.3 * sr)]) == pytest.approx(-voice.GATE_RANGE_DB, abs=0.5)  # avant tout son
    assert 20 * np.log10(g[int(1.8 * sr)]) < -20  # refermé après le bruit de bouche
    assert g[int(1.99 * sr)] > 0.95  # ouvert avant la voix : l'attaque passe entière
    assert g[int(3.35 * sr)] > 0.9  # reste ouvert 150 ms après (fin de mot douce)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")
def test_noise_floor_is_the_room_not_the_voice(tmp_path) -> None:
    sr = voice.SR
    rng = np.random.default_rng(0)
    t = np.arange(sr * 6) / sr
    speech = 0.3 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 0.7 * t) > -0.6)  # parole presque continue
    for noise_db, expected in [(-72, -72), (-45, -45)]:
        x = speech + rng.normal(0, 10 ** (noise_db / 20), t.size)
        path = tmp_path / f"prise_{-noise_db}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
        floor = voice.noise_floor(path, 0, 6)
        assert floor is not None and abs(floor - expected) < 4  # coupe-haut à 16 kHz : un bruit blanc perd 2 dB


def test_voice_mod_settings_are_bounded_and_neutral_by_default() -> None:
    p = voice_mod.normalize({"pitch_st": 9, "formant_pct": "x", "range_pct": 40, "engine": "autre"})
    assert p["pitch_st"] == 4 and p["formant_pct"] == 0 and p["range_pct"] == 50 and p["engine"] == "naturel"
    assert voice_mod.normalize({"engine": "rubberband"})["engine"] == "naturel"  # retiré le 05/10 : le son « électrique »
    assert voice_mod.normalize({"engine": "praat"})["engine"] == "praat"
    neutral = voice_mod.normalize({})
    assert voice_mod.shape_is_neutral(neutral) and voice_mod.eq_filters(neutral) == []


def test_vocoder_mel_matches_its_training_format() -> None:
    mel = vocoder.mel_basis()
    assert mel.shape == (vocoder.NMELS, vocoder.NFFT // 2 + 1) and (mel >= 0).all() and (mel.sum(axis=1) > 0).all()
    freqs = np.linspace(0, vocoder.SR / 2, vocoder.NFFT // 2 + 1)
    assert freqs[mel[0] > 0].min() >= vocoder.FMIN - 25 and freqs[mel[-1] > 0].max() <= vocoder.FMAX + 25
    x = 0.3 * np.sin(2 * np.pi * 440 * np.arange(vocoder.SR) / vocoder.SR)
    mag = vocoder.magnitude(x)
    assert mag.shape == (vocoder.NFFT // 2 + 1, vocoder.SR // vocoder.HOP)  # une trame par pas, comme DiffSinger
    peak = int(np.argmax(mag[:, 40]))
    assert abs(peak * vocoder.SR / vocoder.NFFT - 440) < 25


def test_vocoder_moves_formants_and_tempo() -> None:
    mag = np.full((1025, 10), 1e-3)
    mag[200] = 1.0  # un formant à la case 200
    assert int(np.argmax(vocoder.warp_frequencies(mag, 0.9)[:, 0])) == 180  # timbre −10 % : formants 10 % plus bas
    assert vocoder.stretch_frames(np.zeros((100, 128)), 0.9).shape == (111, 128)  # débit 90 % : 11 % plus long
    assert vocoder.stretch_frames(np.zeros((100, 128)), 1.0).shape == (100, 128)


def test_voice_mod_profile_is_read_from_app_settings() -> None:
    class Db:
        def fetch_one(self, sql, params=None):
            return {
                "value": {
                    "profiles": [{"id": "ab12cd34", "name": "Grave léger", "params": {"pitch_st": -1.2, "engine": "rubberband"}}]
                }
            }

    p = voice_mod.profile_params(Db(), "reglage:ab12cd34")
    assert p is not None and p["pitch_st"] == -1.2 and p["engine"] == "naturel" and p["room"] == 0
    assert voice_mod.profile_params(Db(), "reglage:inconnu") is None
    assert voice_mod.profile_params(Db(), "qwen3:narrateur") is None


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")
def test_voice_mod_apply_keeps_length_and_follows_speed(tmp_path) -> None:
    pytest.importorskip("parselmouth")
    sr = voice_mod.SR
    t = np.arange(sr * 3) / sr
    x = 0.3 * np.sin(2 * np.pi * 140 * t) * (1 + 0.5 * np.sin(2 * np.pi * 3 * t))  # voyelle tenue, voix grave
    src = tmp_path / "voix.wav"
    voice_mod.write_wav(src, x)
    assert voice_mod.apply(src, tmp_path / "eq.wav", {"warmth_db": 3, "density": 50, "room": 40}) == pytest.approx(1.0, abs=0.01)
    ratio = voice_mod.apply(src, tmp_path / "lent.wav", {"pitch_st": -1, "formant_pct": -4, "speed_pct": 90})
    assert ratio == pytest.approx(1 / 0.9, abs=0.03)


# ---- Montage ---------------------------------------------------------------------------------------------------------


def para(key: str, chapter_: int, duration: float, words: int) -> render.Para:
    return render.Para(
        key=key,
        chapter=chapter_,
        path=Path("x.wav"),
        duration=duration,
        words=[{"w": "m", "start": i * duration / words, "end": (i + 1) * duration / words} for i in range(words)],
        script_words=words,
    )


def test_place_paragraphs_adds_breaths_and_chapter_pauses() -> None:
    paras = [para("c0p0", 0, 10, 20), para("c0p1", 0, 10, 20), para("c1p0", 1, 10, 20)]
    spans, total = render.place_paragraphs(paras)
    assert spans["c0p0"] == (render.START_PAD_S, render.START_PAD_S + 10)
    assert spans["c0p1"][0] == round(spans["c0p0"][1] + render.PARA_GAP_S, 3)
    assert spans["c1p0"][0] == round(spans["c0p1"][1] + render.CHAPTER_GAP_S, 3)
    assert total == round(spans["c1p0"][1] + render.END_PAD_S, 3)


def test_plan_shots_follow_words_without_drift() -> None:
    paras = [para("c0p0", 0, 10, 20), para("c1p0", 1, 10, 20)]
    spans, total = render.place_paragraphs(paras)
    shots = [
        {"idx": 0, "para": "c0p0", "at_word": 0, "kind": "image", "image_path": "a.png", "motion": "in"},
        {"idx": 1, "para": "c0p0", "at_word": 10, "kind": "image", "image_path": "b.png", "motion": "left"},
        {"idx": 2, "para": "c0p0", "at_word": 11, "kind": "image", "image_path": "c.png"},  # trop près : retiré
        {"idx": 3, "para": "c1p0", "at_word": 0, "kind": "clip", "image_path": "d.png", "clip_path": "d.mp4"},
    ]
    timed = render.plan_shots(paras, shots, spans, total)
    assert [t.idx for t in timed] == [0, 1, 3]
    assert timed[0].start == 0.0
    assert abs(timed[1].start - (spans["c0p0"][0] + 5.0)) < 1e-6  # le 10e mot sur 20, à mi-paragraphe
    assert timed[2].first_of_chapter and timed[2].kind == "clip"
    assert timed[2].start == round(spans["c0p0"][1] + render.CUT_AFTER_S, 3)  # dans le silence avant le chapitre
    assert sum(t.frames for t in timed) == round(total * FPS)  # aucune image perdue ni ajoutée


def test_chapter_marks_start_at_zero_and_skip_close_ones() -> None:
    paras = [para("c0p0", 0, 30, 20), para("c1p0", 1, 30, 20), para("c2p0", 2, 5, 5)]
    spans, total = render.place_paragraphs(paras)
    shots = [{"idx": i, "para": p.key, "at_word": 0, "kind": "image", "image_path": "x.png"} for i, p in enumerate(paras)]
    marks = render.chapter_marks(render.plan_shots(paras, shots, spans, total), {0: "Ouverture", 1: "Un", 2: "Deux"})
    assert marks[0] == (0.0, "Ouverture")
    assert [t for _, t in marks] == ["Ouverture", "Un", "Deux"]
    assert render.fmt_ts(3725) == "1:02:05" and render.fmt_ts(65) == "01:05"


def test_motion_window_and_card_fade() -> None:
    base = (2150, 1210)
    x0, y0, x1, y1 = window(0.0, "in", base)
    assert (x0, y0) == (0.0, 0.0) and (x1, y1) == base  # zoom avant : de l'image entière…
    x0, _, x1, _ = window(1.0, "in", base)
    assert x1 - x0 < base[0]  # …au centre agrandi
    assert card_alpha(0) == 0 and card_alpha(1.0) == 1.0 and card_alpha(10) == 0
    assert clip_frames(5.0, 300) == int(5.0 * 1.25 * FPS) and clip_frames(5.0, 60) == 60


# ---- Sous-titres (docs/63 §12) ---------------------------------------------------------------------------------------


def heard(*items: tuple[str, float, float]) -> list[dict]:
    return [{"w": w, "start": s, "end": e} for w, s, e in items]


def test_captions_show_the_script_timed_by_the_voice() -> None:
    from worker.longform.captions import align

    # Whisper écrit « 4500 » et « Merrer » : on affiche le script (« 4 500 », « Merer »), au moment où c'est dit
    words = align(
        "Merer note : 4 500 ans.",
        heard(("Merrer", 0.1, 0.5), ("note", 0.6, 0.9), ("quatre", 1.0, 1.2), ("mille", 1.2, 1.4), ("cinq", 1.4, 1.6),
              ("cents", 1.6, 1.8), ("ans", 1.9, 2.2)),
        3.0,
    )  # fmt: skip
    assert [w.text for w in words] == ["Merer", "note\u00a0:", "4 500", "ans."]
    assert (words[2].start, words[2].end) == (1.0, 1.8)  # le nombre dure le temps des mots qui le disent
    assert words[0].start == 0.1 and words[0].end <= words[1].start  # mal entendu : placé entre ses voisins
    assert words[3].start == 1.9


def test_captions_place_reworded_words_between_their_neighbours() -> None:
    from worker.longform.captions import align

    words = align(
        "il partit très vite vers la mer", heard(("il", 0.0, 0.2), ("file", 0.3, 0.8), ("la", 1.0, 1.1), ("mer", 1.1, 1.5)), 2.0
    )
    times = [(w.text, w.start) for w in words]
    assert times[0] == ("il", 0.0) and times[-2:] == [("la", 1.0), ("mer", 1.1)]
    assert all(0.2 <= w.start <= 1.0 for w in words[1:5])  # « partit très vite vers » dans le trou laissé
    assert all(a.start <= b.start for a, b in zip(words, words[1:], strict=False))


def test_captions_without_heard_words_spread_over_the_voice() -> None:
    from worker.longform.captions import align

    words = align("« Un » deux trois.", [], 3.0)
    assert [w.text for w in words] == ["«\u00a0Un\u00a0»", "deux", "trois."]  # la ponctuation seule suit son mot
    assert words[0].start == 0.0 and abs(words[-1].end - 3.0) < 1e-6


def test_caption_chunks_break_at_clauses_and_never_end_on_a_small_word() -> None:
    from worker.longform.captions import align, chunks

    text = "En 2013, au fond d'une galerie creusée dans le désert égyptien, un archéologue découvre des papyrus de Ouadi el-Jarf qui font l'objet d'un débat."
    groups = [" ".join(w.text for w in g) for g in chunks(align(text, [], 12.0))]
    assert groups[0] == "En 2013, au fond d'une galerie"  # la virgule après 2 mots ne coupe pas
    assert all(len(g.split()) <= 7 for g in groups)
    assert not any(g.split()[-1] in ("de", "d'un", "des", "l'objet") for g in groups[:-1] if g.split()[-1][-1] not in ",.")


def test_captions_ass_is_16_9_at_the_bottom() -> None:
    from worker.longform.captions import PROFILE, align, chunks
    from worker.subtitles import build_ass

    ass = build_ass(chunks(align("Une phrase lue par Luca.", [], 2.0)), PROFILE, width=1920, height=1080)
    assert "PlayResX: 1920" in ass and "PlayResY: 1080" in ass
    assert r"\pos(960,950)" in ass and r"{\c&H00D4FF&}" in ass  # centrée en bas, mot prononcé en jaune
