"""Variante d'accroche (docs/49, worker/hookvariant.py), page du sujet ajoutée au dossier et rétention posée sur les
phrases dites (worker/metrics.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_storycraft import _draft, _shots
from worker.hookvariant import check_texts, link_file, variant_script
from worker.metrics import retention_by_scene, retention_drops
from worker.sources import wikipedia
from worker.storycraft import build_script, scene_seconds, split_scenes
from worker.storytelling import said_words

HOOK = "Ce phare tient debout depuis 130 ans sans un seul gardien voyant."
PROMISE = "Pourtant, une nuit lui a tout pris."


def _script():
    d = _draft()
    return build_script(d, split_scenes(d, "fr"), _shots(len(split_scenes(d, "fr"))), "fr", ["fr"], title="Le gardien")


def test_variant_changes_only_the_opening():
    script = _script()
    out = variant_script(script, "fr", HOOK, PROMISE, "Le phare sans yeux", "Le phare sans yeux 🌊", on_screen="")
    assert out.scenes[0].narration["fr"] == HOOK
    assert out.scenes[1].narration["fr"] == PROMISE
    assert out.scenes[0].on_screen_text == {}  # "" : plus de texte gravé sur l'accroche
    assert out.scenes[0].duration_s == scene_seconds(len(said_words(HOOK, "fr")))
    assert [s.narration for s in out.scenes[2:]] == [s.narration for s in script.scenes[2:]]
    assert [s.visual_prompt for s in out.scenes] == [s.visual_prompt for s in script.scenes]
    assert out.story.beats[0].text == HOOK and out.story.beats[1].text == PROMISE
    assert out.hook_title["fr"] == "Le phare sans yeux"
    assert out.metadata["fr"].title == "Le phare sans yeux 🌊"
    assert script.scenes[0].narration["fr"] != HOOK  # le script d'origine ne bouge pas


def test_variant_keeps_the_on_screen_text_unless_asked():
    script = _script()
    kept = variant_script(script, "fr", HOOK, PROMISE, "Le phare sans yeux", "t")
    assert kept.scenes[0].on_screen_text == script.scenes[0].on_screen_text
    other = variant_script(script, "fr", HOOK, PROMISE, "Le phare sans yeux", "t", on_screen="130 ANS")
    assert other.scenes[0].on_screen_text == {"fr": "130 ANS"}


def test_variant_needs_a_story_opening():
    script = _script().model_copy(update={"story": None})
    with pytest.raises(ValueError):
        variant_script(script, "fr", HOOK, PROMISE, "Le phare sans yeux", "t")


def test_check_texts_flags_a_long_opening():
    assert check_texts(HOOK, PROMISE, "Le phare sans yeux") == []
    long = check_texts(HOOK + " Et il voit tout, même les étoiles du ciel.", PROMISE, "Le phare sans yeux")
    assert any("accroche" in i for i in long)


def test_link_file_shares_the_bytes(tmp_path: Path):
    src = tmp_path / "a" / "clip.mp4"
    src.parent.mkdir()
    src.write_bytes(b"x" * 10)
    dst = link_file(src, tmp_path / "b" / "clips" / "clip.mp4")
    assert dst.read_bytes() == src.read_bytes()
    src.unlink()  # effacer l'originale ne casse pas la variante
    assert dst.exists()


def test_retention_is_read_sentence_by_sentence():
    curve = [{"t": 0.0, "w": 1.0}, {"t": 0.1, "w": 0.7}, {"t": 0.5, "w": 0.6}, {"t": 0.6, "w": 0.4}, {"t": 1.0, "w": 0.35}]
    scenes = [
        {"start": 0, "duration": 3, "words": [{"text": "Accroche"}]},
        {"start": 3, "duration": 12, "words": [{"text": "Contexte"}]},
        {"start": 15, "duration": 3, "words": [{"text": "Berbères"}]},
        {"start": 18, "duration": 12, "words": [{"text": "Fin"}]},
    ]
    rows = retention_by_scene(curve, 30.0, scenes)
    assert [r["text"] for r in rows] == ["Accroche", "Contexte", "Berbères", "Fin"]
    assert rows[0]["before"] == 100.0 and rows[0]["after"] == 70.0
    drops = retention_drops(rows, n=2)
    assert [d["text"] for d in drops] == ["Accroche", "Berbères"]  # les pertes les plus rapides, dans l'ordre
    assert retention_by_scene([], 30.0, scenes) == [] and retention_by_scene(curve, None, scenes) == []


class _Client:
    def search(self, query: str, limit: int = 8) -> list[str]:
        assert query == "Zraoua"
        return ["Liste de villes fantômes", "Matmata", "Zraoua"]


def test_subject_page_skips_lists_and_unrelated_pages():
    title = "Zraoua : le village berbère accroché au vide depuis 2000 ans"
    assert wikipedia.subject_page(_Client(), title, ["Liste de villes fantômes"]) == "Zraoua"  # type: ignore[arg-type]
