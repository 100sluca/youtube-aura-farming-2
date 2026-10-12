"""Retoucher → Récit (docs/53) : l'accroche réécrite seule, et la vidéo faite d'un texte relu (worker/rewrite.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from tests.test_hookvariant import HOOK, PROMISE, _script
from worker import rewrite
from worker.hookvariant import Variant
from worker.rewrite import HookRewrite, SceneText, Shot, Source, StoryRewrite, hook_issues, opening_of, tidy_hook
from worker.steps.base import Context
from worker.steps.rewrite import RewriteStep


def _source() -> Source:
    script = _script()
    shots = [Shot(s.index, 6.0, "un phare", s.narration["fr"], 17) for s in script.scenes]
    video = {"id": uuid4(), "title": "Le gardien", "lang": "fr"}
    return Source(video, {"id": uuid4()}, script, shots, "fr", 40.0)


def test_opening_is_the_hook_scene_then_the_promise_scene():
    assert opening_of(_script(), "fr") == {"hook": 0, "promise": 1}
    with pytest.raises(ValueError):
        opening_of(_script().model_copy(update={"story": None}), "fr")


def test_hook_issues_measure_each_sentence_against_its_clip():
    shots = [Shot(0, 2.0, "un phare", "", 6), Shot(1, 6.0, "la mer", "", 17)]
    ok = HookRewrite(hook="Ce phare n'a plus de gardien.", promise=PROMISE, hook_title={"fr": "Le phare sans yeux"})
    assert hook_issues(ok, shots, {"hook": 0, "promise": 1}, "fr") == []
    long = ok.model_copy(update={"hook": HOOK})
    assert any("son plan en porte 6 au plus" in i for i in hook_issues(long, shots, {"hook": 0, "promise": 1}, "fr"))
    assert hook_issues(ok.model_copy(update={"promise": " "}), shots, {"hook": 0, "promise": 1}, "fr")


def test_tidy_hook_writes_numbers_in_digits():
    hr = tidy_hook(HookRewrite(hook="Ce phare  tient depuis cent trente ans.", promise=PROMISE, title=" Le  phare "), "fr")
    assert hr.hook == "Ce phare tient depuis 130 ans."
    assert hr.title == "Le phare"


def test_make_story_clones_the_rewritten_script(monkeypatch: pytest.MonkeyPatch):
    src = _source()
    monkeypatch.setattr(rewrite, "load_source", lambda db, vid: src)
    got: dict[str, Any] = {}

    def clone(db, data_dir, v, p, script, title, description, issues, *, seo=False):
        got.update(script=script, title=title, seo=seo)
        return Variant(uuid4(), uuid4(), 3, issues)

    monkeypatch.setattr(rewrite, "clone", clone)
    scenes = [
        SceneText(index=s.index, part=b, text=s.narration["fr"]) for s, b in zip(src.script.scenes, _parts(src), strict=True)
    ]
    scenes[0] = scenes[0].model_copy(update={"text": "Ce phare n'a plus de gardien depuis 1990."})
    rw = StoryRewrite(scenes=scenes, title="Le phare sans gardien")
    out, _ = rewrite.make_story(None, Path("."), src.video["id"], rw)
    assert out.linked == 3 and got["seo"] is True and got["title"] == "Le phare sans gardien"
    assert got["script"].scenes[0].narration["fr"] == "Ce phare n'a plus de gardien depuis 1990."
    assert [s.visual_prompt for s in got["script"].scenes] == [s.visual_prompt for s in src.script.scenes]

    with pytest.raises(ValueError, match="scènes sans texte"):
        rewrite.make_story(None, Path("."), src.video["id"], rw.model_copy(update={"scenes": scenes[:-1]}))


def _parts(src: Source) -> list[str]:
    """Le temps du récit de chaque scène, lu dans le récit du conteur."""
    said = [s.narration["fr"] for s in src.script.scenes]
    out = []
    for text in said:
        out.append(next(b.part for b in src.script.story.beats if text in b.text))
    return out


def test_make_hook_keeps_the_hook_title_when_none_is_given(monkeypatch: pytest.MonkeyPatch):
    src = _source()
    monkeypatch.setattr(rewrite, "load_source", lambda db, vid: src)
    got: dict[str, Any] = {}
    monkeypatch.setattr(rewrite, "make_variant", lambda db, data_dir, vid, **kw: got.update(kw) or "variante")
    assert rewrite.make_hook(None, Path("."), src.video["id"], HookRewrite(hook=HOOK, promise=PROMISE)) == "variante"
    assert got["hook"] == HOOK and got["promise"] == PROMISE and got["on_screen"] == ""
    assert got["hook_title"] == src.script.hook_title["fr"] and got["title"] == "Le gardien"


def test_the_step_refuses_an_unknown_mode():
    job = type("Job", (), {"payload": {"action": "propose", "mode": "tout"}, "video_id": uuid4()})()
    with pytest.raises(ValueError, match="mode"):
        RewriteStep().run(Context(job=job, db=None, settings=None))  # type: ignore[arg-type]
