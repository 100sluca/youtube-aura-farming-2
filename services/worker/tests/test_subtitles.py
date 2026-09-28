import re

import pytest

from worker.config import WORKER_ROOT
from worker.models import WordTiming
from worker.subtitles import (
    BUILTIN_PROFILES,
    FontRegistry,
    SubtitleProfile,
    ass_color,
    ass_time,
    build_ass,
    distribute_words,
    group_words,
    resolve_profile,
    split_lines,
    strip_emojis,
)

FONTS = FontRegistry.scan(WORKER_ROOT / "assets" / "fonts")


def test_ass_color_and_time():
    assert ass_color("#FFD400") == "&H0000D4FF"
    assert ass_color("#000000", 0.6) == "&H66000000"
    assert ass_time(3723.456) == "1:02:03.46"
    assert ass_time(-1) == "0:00:00.00"


def test_profile_rejects_bad_color():
    with pytest.raises(ValueError):
        SubtitleProfile(text_color="blanc")


def test_resolve_profile_prefers_saved_then_builtin():
    assert resolve_profile("inconnu").name == "impact"
    assert resolve_profile("karaoke").highlight_mode == "karaoke"
    saved = {"maison": {"font_family": "Anton", "font_size": 120}}
    p = resolve_profile("maison", saved)
    assert (p.name, p.font_family, p.font_size) == ("maison", "Anton", 120)


def test_distribute_words_is_monotonic_and_pauses_after_punctuation():
    words = distribute_words("Personne ne pousse ce miroir, et pourtant il cache un secret.", 1.0, 5.0)
    assert len(words) == 11
    assert words[0].start == pytest.approx(1.0)
    assert words[-1].end == pytest.approx(5.0, abs=1e-3)
    assert all(a.end <= b.start + 1e-6 for a, b in zip(words, words[1:], strict=False))
    comma = next(i for i, w in enumerate(words) if w.text.endswith(","))
    gaps = [b.start - a.end for a, b in zip(words, words[1:], strict=False)]
    assert gaps[comma] > max(g for i, g in enumerate(gaps) if i != comma) - 1e-9


def test_group_words_limits_and_scene_boundaries():
    prof = SubtitleProfile(max_words=3, max_chars=40)
    s1 = distribute_words("un deux trois quatre cinq. six", 0.0, 3.0)
    s2 = distribute_words("sept huit", 3.5, 4.5)
    caps = group_words([s1, s2], prof)
    texts = [[w.text for w in c.words] for c in caps]
    assert texts == [["un", "deux", "trois"], ["quatre", "cinq."], ["six"], ["sept", "huit"]]
    assert all(a.end <= b.start + 1e-9 for a, b in zip(caps, caps[1:], strict=False))


def test_split_lines_balances_two_lines():
    assert split_lines(["court"], 10) == [["court"]]
    assert split_lines(["un", "dressing", "secret", "géant"], 12) == [["un", "dressing"], ["secret", "géant"]]


def test_build_ass_word_mode_highlights_each_word_with_shadow_layer():
    words = [WordTiming(text=t, start=i * 0.5, end=i * 0.5 + 0.4) for i, t in enumerate(["le", "miroir", "secret"])]
    ass = build_ass([words], BUILTIN_PROFILES["impact"], [(0.0, 2.0, "Titre 🔥")], fonts=FONTS)
    main = [line for line in ass.splitlines() if line.startswith("Dialogue: 2,")]
    shadow = [line for line in ass.splitlines() if line.startswith("Dialogue: 1,")]
    assert len(main) == 3 and len(shadow) == 3
    assert "\\c&H00D4FF&}MIROIR" in main[1]  # mot actif en jaune (BGR)
    assert "\\fscx80" in main[0] and "\\fscx80" not in main[1]  # « pop » seulement à l'apparition
    assert "Style: Main,Montserrat," in ass  # nom de famille lu dans le fichier de police
    title = [line for line in ass.splitlines() if line.startswith("Dialogue: 3,")]
    assert title and title[0].endswith("TITRE")  # émoji retiré, capitales


def test_build_ass_karaoke_durations_cover_caption():
    words = [WordTiming(text=t, start=0.2 + i * 0.5, end=0.2 + i * 0.5 + 0.45) for i, t in enumerate(["a", "b", "c"])]
    ass = build_ass([words], BUILTIN_PROFILES["karaoke"], fonts=FONTS)
    line = next(line for line in ass.splitlines() if line.startswith("Dialogue: 2,"))
    ks = [int(k) for k in re.findall(r"\\kf?(\d+)", line)]
    start, end = (float(t.split(":")[-1]) + 60 * int(t.split(":")[-2]) for t in line.split(",")[1:3])
    assert "\\kf" in line
    assert sum(ks) == round((end - start) * 100)


def test_box_profile_uses_single_box_and_no_shadow():
    words = [WordTiming(text="bonjour", start=0, end=0.5)]
    ass = build_ass([words], BUILTIN_PROFILES["sobre"], fonts=FONTS)
    main_style = next(line for line in ass.splitlines() if line.startswith("Style: Main,"))
    assert main_style.split(",")[15] == "4"  # BorderStyle 4 : une boîte pour toute la légende
    assert not [line for line in ass.splitlines() if line.startswith("Dialogue: 1,")]


def test_text_is_escaped_and_emojis_stripped():
    assert strip_emojis("Waouh 🤯✨") == "Waouh "
    words = [WordTiming(text="{\\pos(1,1)}piège", start=0, end=1)]
    ass = build_ass([words], BUILTIN_PROFILES["impact"], fonts=FONTS)
    dialogue = next(line for line in ass.splitlines() if line.startswith("Dialogue: 2,"))
    assert "(⧵POS(1,1))PIÈGE" in dialogue


def test_font_registry_finds_bundled_fonts():
    assert {"Montserrat", "Poppins", "Bebas Neue", "Luckiest Guy", "Anton"} <= set(FONTS.families())
    choice = FONTS.pick("Poppins", bold=True)
    assert choice.fontname == "Poppins SemiBold" and choice.path and not choice.synthetic_bold
    assert FONTS.pick("Arial Black", bold=True).path is None  # police système : demandée telle quelle
