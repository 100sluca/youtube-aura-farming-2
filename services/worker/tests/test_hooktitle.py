import pytest

from worker.hooktitle import HookStyle, build_png, clean_hook, lint_hook_title, overlay_filter, render_image


def test_clean_hook_keeps_the_meaning_and_drops_the_noise():
    assert clean_hook("« Ils ont sauvé cette maison. » 😱 #renovation") == "Ils ont sauvé cette maison"
    assert clean_hook("Tu paierais combien pour cette villa ?") == "Tu paierais combien pour cette villa ?"
    assert clean_hook("Personne ne voulait de ce terrain…") == "Personne ne voulait de ce terrain…"
    assert clean_hook("construire au bord du vide") == "Construire au bord du vide"  # sortie réelle de Gemini
    assert clean_hook("   ") == ""


def test_lint_hook_title_word_count_and_shouting():
    assert lint_hook_title("Regarde ce qu'ils ont fait de ce stade") == []
    assert "mots" in lint_hook_title("Waouh")[0]
    assert any("majuscules" in i for i in lint_hook_title("REGARDE CE QU'ILS ONT FAIT"))
    assert "manquant" in lint_hook_title("", "en")[0]


def test_render_image_draws_one_rounded_plate_per_line():
    pytest.importorskip("PIL")
    one = render_image("Tu paierais combien ?")
    two = render_image("Ils ont transformé ce terrain abandonné en villa de rêve avec piscine")
    assert one.size[0] == 1080 and two.size[0] == 1080
    assert two.size[1] > one.size[1] * 1.5  # le texte long passe sur plusieurs lignes, une plaque chacune
    assert one.getpixel((2, 2))[3] == 0  # fond transparent autour des plaques
    r, g, b, a = one.getpixel((540, one.size[1] // 2 + 20))  # dans la plaque, sous le texte ou entre deux lettres
    assert a == 255


def test_build_png_and_overlay(tmp_path):
    pytest.importorskip("PIL")
    assert build_png("", tmp_path / "vide.png") is None
    png = build_png("Tu paierais combien pour cette villa ?", tmp_path / "hook.png")
    assert png and png.exists() and png.stat().st_size > 0
    assert overlay_filter(HookStyle()) == "overlay=(W-w)/2:150"
    assert overlay_filter(HookStyle(duration_s=4), total_s=30) == "overlay=(W-w)/2:150:enable='between(t,0,4.000)'"
    assert overlay_filter(HookStyle(duration_s=40), total_s=30) == "overlay=(W-w)/2:150"  # plus long que la vidéo
