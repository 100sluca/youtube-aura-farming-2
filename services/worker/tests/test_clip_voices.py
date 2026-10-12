"""Voix des clips d'un drame (docs/70 §6) : réplique dite en français, plans muets sans paroles, voix fixe par
personnage."""

from __future__ import annotations

from pathlib import Path

from tests.test_drama import _script
from worker import drama
from worker.clip_voices import Line, ambience_file, consistency, converted_file, reference_key, reference_sets


def test_a_line_said_in_english_is_not_said():
    good = {"ratio": 1.0, "lang": "fr", "lang_p": 0.97}
    assert drama.line_said(good, "fr")
    # forcé en français, Whisper « traduisait » la réplique anglaise : elle ressemblait, mais ce n'était pas du français
    assert not drama.line_said({**good, "lang": "en", "lang_p": 0.81}, "fr")
    assert drama.line_said({**good, "lang": "en", "lang_p": 0.3}, "fr")  # doute de Whisper : on garde
    assert not drama.line_said({"ratio": 0.2, "lang": "fr", "lang_p": 0.9}, "fr")
    assert drama.line_said(None, "fr")  # sans transcription, on ne peut pas savoir


def test_a_silent_plan_may_laugh_but_not_talk():
    def heard(*ws: str) -> list[dict[str, str]]:
        return [{"w": w} for w in ws]

    assert drama.invented_words(heard("Ha", "ha", "ha", "ha!")) == []
    assert drama.invented_words(heard("Hmm.", "Oh", "Huh.", "Hahaha")) == []
    assert drama.invented_words(heard("Hey", "you", "little", "muscle")) == ["you", "little", "muscle"]
    assert drama.invented_words(heard("Yeah,", "starry", "man")) == ["yeah", "starry", "man"]
    assert "every mouth stays closed" in drama.clip_prompt(
        drama.normalize(
            _script([{"index": 0, "duration_s": 2, "visual_prompt": "v", "motion_prompt": "m", "characters": [], "lines": []}])
        ),
        0,
        "fr",
        "pixar_fruit",
    )


def test_each_character_gets_a_reference_made_of_its_best_lines():
    lines = [Line(0, "awa", True), Line(3, "awa", True), Line(5, "awa", False), Line(7, "awa", True), Line(2, "papa", True)]
    emb = {
        0: [1.0, 0.0, 0.0],
        3: [0.8, 0.6, 0.0],  # la plus proche des autres : la plus typique
        5: [0.6, 0.8, 0.0],
        7: [0.6, 0.0, 0.8],
        2: [0.0, 0.0, 1.0],
    }
    # répliques bien dites seulement (5 n'est pas dite en français), des plus typiques aux moins typiques ; un
    # personnage d'une seule réplique n'a rien à harmoniser
    assert reference_sets(lines, emb) == {"awa": [3, 0, 7]}
    assert consistency(lines, emb)["awa"] == 0.63  # ressemblance moyenne de ses 4 répliques entre elles


def test_a_character_who_never_says_his_lines_well_still_gets_one_voice():
    lines = [Line(0, "kofi", False), Line(1, "kofi", False)]
    assert sorted(reference_sets(lines, {0: [1.0, 0.0], 1: [0.0, 1.0]})["kofi"]) == [0, 1]


def test_fixed_voices_live_next_to_their_clip():
    clip = Path("C:/x/scene_05.mp4")
    assert ambience_file(clip).name == "scene_05.ambiance.wav" and drama.voice_file(clip).name == "scene_05.voix.wav"
    key = reference_key([Path("C:/x/scene_02.mp4"), clip])
    assert len(key) == 8 and converted_file(clip, key).name == f"scene_05.timbre_{key}.wav"
