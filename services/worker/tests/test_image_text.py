"""Texte écrit dans l'image par le générateur (worker/image_text.py, docs/57 §5) : permis seulement s'il porte l'enjeu,
sur un plan sans réplique, 2 par vidéo ; dit au modèle d'image, relu lettre à lettre (le lecteur ne connaît pas le texte
attendu), refait trois fois puis abandonné ; gardé immobile au clip, sinon plan fixe sur l'image vérifiée."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from test_drama import FakeDb, _scene, _script, _storyboard

from worker import drama, storycraft
from worker.image_text import (
    TEXT_TRIES,
    ImageReading,
    WrittenText,
    clean_script,
    image_clause,
    judge,
    motion_clause,
    norm,
    only_text,
    still_clip,
    with_image_text,
)
from worker.keyframe_qc import NO_WORDS, PHOTO, PHOTO_WITH_TEXT, continuity_requirements, requirements
from worker.models import ImageText, SceneDraft
from worker.providers.video import NEGATIVE, NO_TEXT, WAN_NEGATIVE, full_prompt, negative_allowing_text
from worker.reinvent import apply_rewrite
from worker.steps import storyboard as sb

PRICE = {"text": "PRIX : 1 €", "on": "a weathered wooden sign hanging on the iron gate"}


def test_only_short_texts_on_shots_without_lines_two_per_video():
    s = drama.normalize(
        _script(
            [
                _scene(0, image_text=PRICE),
                _scene(1, "kiwi", "Un euro ?", image_text=PRICE),  # une réplique : le plan de secours la perdrait
                _scene(2, image_text={"text": "À VENDRE TOUT DE SUITE PAS CHER", "on": "a sign"}),  # 6 mots
                _scene(3, image_text={"text": "Cent milliards", "on": "a golden badge above Fraise's head"}),
                _scene(4, image_text={"text": "VENDU", "on": "a red sticker"}),  # le troisième : de trop
                _scene(5, image_text={"text": "SOLD", "on": ""}),  # sans support
            ]
        )
    )
    texts = [sc.image_text.text if sc.image_text else None for sc in s.scenes[:6]]
    assert texts == ["PRIX : 1 €", None, None, "100 milliards", None, None]


def test_the_reading_is_strict_on_letters_and_lenient_on_case_and_spacing():
    it = ImageText(**PRICE)
    read = lambda *t, y=30.0, clean=True: ImageReading(  # noqa: E731
        texts=[WrittenText(text=x, box_2d=[y * 10 - 40, 100, y * 10 + 40, 900], clean=clean) for x in t]
    )
    assert judge(read("Prix: 1€"), it) == [] and norm("100 000 €") == norm("100000€")
    assert judge(read("PRIX : 1 €", "12"), it) == []  # un chiffre de cadran n'est pas un texte en trop
    assert "n'est pas écrit à l'identique" in judge(read("PRIS : 1 €"), it)[0]
    assert "n'est pas écrit à l'identique" in judge(read("PRIX : 7 €"), it)[0]
    assert any("autre texte" in p for p in judge(read("PRIX : 1 €", "SOLD"), it))
    assert any("2 fois" in p for p in judge(read("PRIX : 1 €", "PRIX : 1 €"), it))
    assert any("déformées" in p for p in judge(read("PRIX : 1 €", clean=False), it))
    assert any("haut de l'image" in p for p in judge(read("PRIX : 1 €", y=72), it))  # sous les sous-titres
    assert judge(read("PRIX : 1 €", y=72), it, where=False) == []  # au clip, la caméra le déplace un peu
    assert "aucun texte" in judge(ImageReading(), it)[0]
    assert (
        judge(ImageReading(texts=[WrittenText(text="PRIX : 1 €", box_2d=[1600, 0, 2400, 1000])]), it) == []
    )  # cadre absurde : place non jugée
    assert judge(read("À VENDRE\nPRIX : 1€"), ImageText(text="À VENDRE PRIX : 1 €", on="a sign")) == []  # deux lignes
    assert norm("ÉCOLE") != norm("ECOLE")  # les accents comptent


def test_the_prompts_say_the_exact_words_and_only_them():
    it = ImageText(**PRICE)
    assert '"PRIX : 1 €"' in image_clause(it) and "upper part" in image_clause(it)
    assert with_image_text("A banana walks past a manor gate.", it).startswith("A banana walks past a manor gate. On a weathered")
    assert with_image_text("A banana.", None) == "A banana."
    assert "stays perfectly still" in motion_clause(it)
    said = full_prompt("A manor gate", "pixar_fruit", True, it.text)
    assert said.endswith(only_text(it.text)) and NO_TEXT not in said
    assert full_prompt("A manor gate", "pixar_fruit", True).endswith(NO_TEXT)  # sans texte voulu : rien ne change
    assert NO_TEXT not in full_prompt("A manor gate", "pixar_fruit", False, it.text)  # encodeurs T5 : rien d'ajouté
    neg = negative_allowing_text(NEGATIVE)
    assert "text" not in [t.strip() for t in neg.split(",")] and "watermark" in neg and "subtitles" in neg
    assert not negative_allowing_text(WAN_NEGATIVE).endswith("text") and "subtitles" in negative_allowing_text(WAN_NEGATIVE)


def test_the_image_checks_allow_the_intended_text_only():
    s = _script([_scene(0, image_text=PRICE), _scene(1), _scene(2), _scene(3)])
    reqs = continuity_requirements(s, 0, None)
    assert NO_WORDS not in reqs and any("« PRIX : 1 € »" in r for r in reqs)
    assert NO_WORDS in continuity_requirements(s, 1, None)
    tour = s.model_copy(deep=True)
    tour.scenes[0].interior = True
    assert requirements(tour, 0, "tour")[0] == PHOTO_WITH_TEXT and requirements(tour, 1, "tour")[0] == PHOTO


def test_a_reinvented_scene_keeps_its_text_only_without_a_line():
    s = drama.normalize(_script([_scene(0, "kiwi", "Oui."), _scene(1), _scene(2, "prune", "Non.")]))
    draft = SceneDraft(visual_prompt="A manor gate with a sign", image_text=ImageText(**PRICE))
    assert apply_rewrite(s, 1, draft, "drama").scenes[1].image_text == ImageText(**PRICE)
    talking = SceneDraft(
        visual_prompt="Kiwi at the gate", lines=[{"who": "kiwi", "text": "Un euro ?"}], image_text=ImageText(**PRICE)
    )
    assert apply_rewrite(s, 0, talking, "drama").scenes[0].image_text is None


def test_the_writers_know_when_a_text_may_be_written():
    assert "AUCUN TEXTE ÉCRIT dans l'image" in drama.SCRIPT_PROMPT and "image_text" in drama.SCRIPT_PROMPT
    assert "SANS réplique" in drama.SCRIPT_PROMPT and "image_text" in drama.REWRITE_HINT
    assert "image_text" in storycraft.SHOTS_PROMPT
    assert clean_script(_script([_scene(0, image_text=PRICE)])).scenes[0].image_text is not None


# ---------------------------------------------------------------------------
# Storyboard : l'image relue, refaite, puis faite sans texte
# ---------------------------------------------------------------------------


class TextImage:
    calls: list[dict[str, Any]] = []

    def __init__(self, settings: Any, workflow: str | None = None) -> None:
        self.name, self.width, self.height, self.references = "fake_qwen", 768, 1344, True

    def generate(
        self, *, prompt: str, out_path: Path, refs: list[Path] | None = None, allowed_text: str | None = None, **_: Any
    ) -> Path:
        TextImage.calls.append({"name": out_path.name.rsplit("_", 1)[0], "prompt": prompt, "allowed_text": allowed_text})
        out_path.write_bytes(b"png")
        return out_path


class Reader:
    """Modèle de vision : relit ce qu'on lui fait lire, essai après essai."""

    def __init__(self, readings: list[list[str]]) -> None:
        self.readings = readings
        self.n = 0

    def complete_json(self, system: str, user: str, schema: Any, images: Any = None) -> Any:
        texts = self.readings[min(self.n, len(self.readings) - 1)]
        self.n += 1
        return schema(texts=[{"text": t, "box_2d": [260, 100, 340, 900]} for t in texts])


class ScriptDb(FakeDb):
    def __init__(self, script: Any) -> None:
        super().__init__(script)
        self.saved: Any = None

    def execute(self, sql: str, params: Any = None) -> int:
        if sql.startswith("update productions set script"):
            self.saved = params[0].obj
        return super().execute(sql, params)


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reader: Reader) -> ScriptDb:
    s = drama.normalize(_script([_scene(0, image_text=PRICE), _scene(1, "kiwi", "Un euro ?"), _scene(2), _scene(3)]))
    db = ScriptDb(s)
    TextImage.calls = []
    monkeypatch.setattr(sb, "get_vision_llm", lambda settings, d: reader)
    monkeypatch.setattr("test_drama.FakeImage", TextImage)
    monkeypatch.setattr(sb, "ComfyImage", TextImage)
    _storyboard(tmp_path, monkeypatch, s, db=db)
    return db


def test_a_text_read_right_is_kept_after_a_retry(tmp_path, monkeypatch):
    db = _run(tmp_path, monkeypatch, Reader([["PRIS : 1 €"], ["PRIX : 1 €"]]))
    shots = [c for c in TextImage.calls if c["name"] == "scene_00"]
    assert [c["allowed_text"] for c in shots] == ["PRIX : 1 €", "PRIX : 1 €"]
    assert '"PRIX : 1 €"' in shots[0]["prompt"]
    kept = [a for a in db.assets if a["kind"] == "storyboard" and a["scene_index"] == 0]
    assert kept[-1]["meta"]["image_text"]["ok"] and not kept[0]["meta"]["image_text"]["ok"]
    assert db.saved is None  # le script ne change pas
    assert all(c["allowed_text"] is None for c in TextImage.calls if c["name"] != "scene_00")


def test_a_text_missed_three_times_is_dropped_and_the_shot_made_without(tmp_path, monkeypatch):
    db = _run(tmp_path, monkeypatch, Reader([["PRIS : 1 €"]]))
    shots = [c for c in TextImage.calls if c["name"] == "scene_00"]
    assert len(shots) == TEXT_TRIES + 1 and shots[-1]["allowed_text"] is None and "PRIX" not in shots[-1]["prompt"]
    assert db.saved is not None and db.saved["scenes"][0]["image_text"] is None


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")
def test_the_fallback_is_a_still_shot_of_the_checked_image(tmp_path):
    from PIL import Image

    img = tmp_path / "scene.png"
    Image.new("RGB", (96, 170), (200, 150, 40)).save(img)
    dur, w, h = still_clip(img, tmp_path / "clip.mp4", 2.0, fps=12)
    assert (tmp_path / "clip.mp4").stat().st_size > 0 and (w, h) == (96, 170) and dur == pytest.approx(2.5, abs=0.1)
