"""Prompts des agents modifiables depuis le dashboard (onglet Agents, docs/22) : texte du code, version active en base."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from worker import keyframe_qc as kq
from worker.keyframe_qc import CLIP_SYSTEM, QC_SYSTEM, KeyframeVerdict
from worker.models import ScriptV1
from worker.prompts import active_prompt, code_prompts, prompt_text, sync_code_prompts
from worker.recipes import HOOK_RULES, IDEA_GUIDES, SCRIPT_PROMPTS, script_context
from worker.steps.ideate import DEFAULT_PROMPT as IDEA
from worker.steps.script import CONTINUITY_HINT
from worker.storycraft import REVIEW_PROMPT, SHOTS_PROMPT, STORY_PROMPT
from worker.storytelling import IMAGE_RULES, RULES

# Clés affichées par le dashboard (apps/dashboard/src/lib/agent-catalog.ts) : les renommer casse l'onglet Agents
DASHBOARD_KEYS = {
    "idea",
    "script",
    "script_review",
    "script_shots",
    "script_timelapse",
    "script_tour",
    "script_quote",
    "script_quote_auteur",
    "scene_rewrite",
    "script_rewrite",
    "hook_rewrite",
    "sfx_pick",
    "seo",
    "strategy",
    "improve",
    "analyst",
    "research_classify",
    "research_watch",
    "research_brief",
    "research_adapt",
    "research_ask",
    "research_discover",
    "keyframe_qc",
    "clip_qc",
    "rules_storytelling",
    "rules_images",
    "guide_timelapse",
    "guide_tour",
    "guide_quote",
    "guide_quote_auteur",
    "rules_hook_title",
    "hint_continuity",
    # vidéos longues (docs/63)
    "long_idea",
    "long_outline",
    "long_writer",
    "long_review",
    "long_director",
    "long_packaging",
    "long_image_check",
    "long_thumb_check",
    "rules_long",
    "rules_long_images",
    "rules_thumbnail",
    "guide_long_mystere",
    "guide_long_epoque",
    "long_factcheck",
    "long_thumbs",
    "long_thumb_style",
    "guide_thumb_niche",
}


class FakeDb:
    def __init__(self, active: dict[str, str] | None = None) -> None:
        self.active = active or {}
        self.ids = {k: uuid.uuid4() for k in self.active}
        self.synced: list[tuple[str, str]] = []

    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        if "sync_code_prompt" in sql:
            self.synced.append(params)
            return {"result": "unchanged"}
        if "from prompt_templates" in sql and params and params[0] in self.active:
            return {"id": self.ids[params[0]], "content": self.active[params[0]]}
        return None


def test_every_prompt_of_the_code_has_a_key_the_dashboard_knows():
    prompts = code_prompts()
    assert DASHBOARD_KEYS <= set(prompts)
    assert all(re.fullmatch(r"[a-z][a-z0-9_]{1,39}", k) for k in prompts)  # contrainte de la migration 0012
    assert all(text.strip() for text in prompts.values())
    assert prompts["idea"] == IDEA and prompts["rules_storytelling"] == RULES and prompts["hint_continuity"] == CONTINUITY_HINT
    assert prompts["script_tour"] == SCRIPT_PROMPTS["tour"] and prompts["guide_timelapse"] == IDEA_GUIDES["timelapse"]
    assert prompts["keyframe_qc"] == QC_SYSTEM and prompts["clip_qc"] == CLIP_SYSTEM and prompts["rules_hook_title"] == HOOK_RULES
    # récits (docs/37) : le conteur, son relecteur, le réalisateur et les règles de l'image
    assert prompts["script"] == STORY_PROMPT and prompts["script_review"] == REVIEW_PROMPT
    assert prompts["script_shots"] == SHOTS_PROMPT and prompts["rules_images"] == IMAGE_RULES


def test_the_active_version_wins_over_the_code():
    db = FakeDb({"seo": "Prompt SEO écrit dans le dashboard"})
    text, tid = active_prompt(db, "seo", "texte du code")
    assert text == "Prompt SEO écrit dans le dashboard" and tid == db.ids["seo"]
    assert active_prompt(db, "idea", "texte du code") == ("texte du code", None)  # rien en base : le code
    assert prompt_text(FakeDb({"idea": "   "}), "idea", "texte du code") == "texte du code"  # version vide ignorée


def test_sync_sends_the_code_text_of_every_key():
    db = FakeDb()
    out = sync_code_prompts(db)
    assert set(out) == set(code_prompts()) and set(out.values()) == {"unchanged"}
    assert dict(db.synced) == code_prompts()


def test_the_vision_checks_use_the_prompt_they_are_given(tmp_path: Path):
    seen: list[str] = []

    class Vision:
        def complete_json(self, system: str, user: str, schema: Any, images: Any = ()) -> KeyframeVerdict:
            seen.append(system)
            return KeyframeVerdict(ok=True)

    scenes = [{"index": i, "duration_s": 5, "visual_prompt": f"room {i}"} for i in range(4)]
    script = ScriptV1.model_validate({"scenes": scenes, "metadata": {"fr": {"title": "t", "description": "d"}}})
    image = tmp_path / "scene_00.png"
    image.write_bytes(b"png")
    kq.check_keyframe(Vision(), image, script, 0, "tour", system="Contrôleur réécrit dans le dashboard")
    kq.check_keyframe(Vision(), image, script, 0, "tour")
    assert seen == ["Contrôleur réécrit dans le dashboard", QC_SYSTEM]


def test_hook_title_rules_can_be_replaced():
    assert script_context("tour").startswith(HOOK_RULES)
    assert script_context("tour", "TITRE : 4 mots.").startswith("TITRE : 4 mots.\n\nBRUITAGES DISPONIBLES")
