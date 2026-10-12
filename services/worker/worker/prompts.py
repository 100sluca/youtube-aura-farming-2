"""Prompts des agents : texte écrit dans le code, version active en base, modifiable depuis le dashboard (onglet
Agents, docs/22-agents.md).

Chaque agent LLM a une clé pour son prompt système (« idea », « script », « seo »…), et chaque consigne commune glissée
dans ses messages en a une aussi (« rules_storytelling », « guide_tour »…). Toutes vivent dans prompt_templates,
versionnées, une seule version active par clé (migration 0012) :
- au démarrage, le worker y enregistre le texte du code de chaque clé (sync_code_prompts) : quand le code change, la
  nouvelle version sert aussitôt si l'on suivait le code ; une version modifiée dans le dashboard reste en service ;
- les steps lisent la version active à chaque appel (active_prompt, prompt_text) : une modification faite dans le
  dashboard sert dès la tâche suivante, sans relancer le worker ;
- le texte du code reste le repli quand la base n'a pas (encore) la clé.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID


def code_prompts() -> dict[str, str]:
    """Le texte du code de chaque clé. Imports tardifs : ces modules importent eux-mêmes celui-ci."""
    from .arcs import ARC_PROMPT
    from .discovery import CLASSIFY_PROMPT as DISCOVER_CLASSIFY
    from .keyframe_qc import CLIP_SYSTEM, QC_SYSTEM
    from .longform import prompts as long_prompts
    from .recipes import HOOK_RULES, IDEA_GUIDES, SCRIPT_PROMPTS
    from .reinvent import REWRITE_PROMPT
    from .research_agents import ADAPT_PROMPT as RESEARCH_ADAPT
    from .research_agents import ASK_PROMPT as RESEARCH_ASK
    from .research_agents import BRIEF_PROMPT as RESEARCH_BRIEF
    from .research_agents import CLASSIFY_PROMPT as RESEARCH_CLASSIFY
    from .research_agents import WATCH_PROMPT as RESEARCH_WATCH
    from .rewrite import HOOK_PROMPT as HOOK_REWRITE
    from .rewrite import REWRITE_PROMPT as STORY_REWRITE
    from .scenario import ADAPT_PROMPT as SCENARIO_ADAPT
    from .scenario import REVIEW_PROMPT as SCENARIO_REVIEW
    from .scenario import SCRIPT_PROMPT as SCENARIO_SCRIPT
    from .sfx_pick import PICK_PROMPT as SFX_PICK
    from .steps.analyze import ANALYST_PROMPT
    from .steps.ideate import DEFAULT_PROMPT as IDEA
    from .steps.improve import IMPROVE_PROMPT
    from .steps.script import CONTINUITY_HINT
    from .steps.seo import DEFAULT_PROMPT as SEO
    from .steps.strategy import DEFAULT_PROMPT as STRATEGY
    from .storycraft import REVIEW_PROMPT, SHOTS_PROMPT, STORY_PROMPT
    from .storytelling import IMAGE_RULES, RULES

    return {
        # prompts système des agents
        "idea": IDEA,
        "script": STORY_PROMPT,  # le conteur des récits : l'histoire en entier, avant le découpage (docs/37)
        "arc_outline": ARC_PROMPT,  # le showrunner des mini-séries : l'histoire en 3 parties (docs/52)
        "script_review": REVIEW_PROMPT,  # relecture du récit, checklist du storytelling (docs/24, docs/37)
        "script_shots": SHOTS_PROMPT,  # le réalisateur des récits : les plans de chaque scène (docs/37)
        **{f"script_{recipe}": text for recipe, text in SCRIPT_PROMPTS.items()},  # formats visuels (docs/15)
        # l'équipe des scénarios de Luca (docs/59) : metteur en scène, scénariste, relecteur de fidélité
        "scenario_adapt": SCENARIO_ADAPT,
        "script_scenario": SCENARIO_SCRIPT,
        "scenario_review": SCENARIO_REVIEW,
        "scene_rewrite": REWRITE_PROMPT,  # scène réinventée pendant la revue du storyboard (docs/27)
        "script_rewrite": STORY_REWRITE,  # récit réécrit sur les plans d'une vidéo faite (docs/49 §6)
        "sfx_pick": SFX_PICK,  # le bruiteur des drames : bruitages plan par plan (docs/49 §10)
        "hook_rewrite": HOOK_REWRITE,  # accroche et promesse réécrites seules, Retoucher → Récit (docs/53)
        "seo": SEO,
        "strategy": STRATEGY,
        "improve": IMPROVE_PROMPT,
        "analyst": ANALYST_PROMPT,  # analyse des vidéos publiées, leçons à valider (docs/25)
        # page Recherche (docs/60) : classeur des Shorts trouvés, analyste vidéo (Gemini les regarde), stratège
        "research_classify": RESEARCH_CLASSIFY,
        "research_watch": RESEARCH_WATCH,
        "research_brief": RESEARCH_BRIEF,
        "research_adapt": RESEARCH_ADAPT,  # version fidèle en français d'un Short qui a marché (docs/64 §3)
        "research_ask": RESEARCH_ASK,  # le stratège répond aux questions de Luca (docs/64 §4)
        "research_discover": DISCOVER_CLASSIFY,  # Découverte : chaînes qui percent, niche et effort (docs/63 §9)
        "keyframe_qc": QC_SYSTEM,
        "clip_qc": CLIP_SYSTEM,
        # consignes communes, ajoutées au message de l'agent avec les données de la tâche
        "rules_storytelling": RULES,
        "rules_images": IMAGE_RULES,  # règles de l'image des récits (réalisateur, scène réinventée, docs/37)
        **{f"guide_{recipe}": text for recipe, text in IDEA_GUIDES.items()},
        "rules_hook_title": HOOK_RULES,
        "hint_continuity": CONTINUITY_HINT,
        # vidéos longues narrées par Luca (docs/63) : sujets, plan, conteur, relecteur, réalisateur, publication, contrôles
        "long_idea": long_prompts.IDEA_PROMPT,
        "long_outline": long_prompts.OUTLINE_PROMPT,
        "long_writer": long_prompts.WRITER_PROMPT,
        "long_review": long_prompts.REVIEW_PROMPT,
        "long_director": long_prompts.DIRECTOR_PROMPT,
        "long_packaging": long_prompts.PACKAGING_PROMPT,
        "long_image_check": long_prompts.IMAGE_CHECK_PROMPT,
        "long_thumb_check": long_prompts.THUMB_CHECK_PROMPT,
        "long_factcheck": long_prompts.FACTCHECK_PROMPT,
        "long_thumbs": long_prompts.THUMBS_PROMPT,
        "long_thumb_style": long_prompts.THUMB_STYLE_PROMPT,
        "guide_thumb_niche": long_prompts.GUIDE_THUMB_NICHE,
        "rules_long": long_prompts.RULES_LONG,
        "rules_long_images": long_prompts.IMAGE_RULES_LONG,
        "rules_thumbnail": long_prompts.THUMB_RULES,
        **{f"guide_long_{fmt}": text for fmt, text in long_prompts.GUIDES.items()},
    }


def active_prompt(db: Any, key: str, default: str) -> tuple[str, UUID | None]:
    """(texte, id de la version) de la version active de `key` ; le texte du code si la base n'en a aucune."""
    row = db.fetch_one("select id, content from prompt_templates where agent = %s and is_active", (key,))
    if row and (row.get("content") or "").strip():
        return row["content"], row["id"]
    return default, None


def prompt_text(db: Any, key: str, default: str) -> str:
    return active_prompt(db, key, default)[0]


def sync_code_prompts(db: Any) -> dict[str, str]:
    """Enregistre le texte du code de chaque clé (démarrage du worker, `yt2 prompts sync`). Renvoie, par clé :
    unchanged, activated, added_active (le code a changé et l'on suivait le code) ou added (une version choisie à la
    main reste active)."""
    out: dict[str, str] = {}
    for key, text in code_prompts().items():
        row = db.fetch_one("select sync_code_prompt(%s, %s) as result", (key, text))
        out[key] = row["result"] if row else "?"
    return out
