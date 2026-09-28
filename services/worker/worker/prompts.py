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
    from .keyframe_qc import CLIP_SYSTEM, QC_SYSTEM
    from .recipes import HOOK_RULES, IDEA_GUIDES, SCRIPT_PROMPTS
    from .reinvent import REWRITE_PROMPT
    from .steps.analyze import ANALYST_PROMPT
    from .steps.ideate import DEFAULT_PROMPT as IDEA
    from .steps.improve import IMPROVE_PROMPT
    from .steps.script import CONTINUITY_HINT, REVIEW_PROMPT
    from .steps.script import DEFAULT_PROMPT as SCRIPT
    from .steps.seo import DEFAULT_PROMPT as SEO
    from .steps.strategy import DEFAULT_PROMPT as STRATEGY
    from .storytelling import RULES

    return {
        # prompts système des agents
        "idea": IDEA,
        "script": SCRIPT,
        "script_review": REVIEW_PROMPT,  # relecture éditoriale des récits (docs/24)
        **{f"script_{recipe}": text for recipe, text in SCRIPT_PROMPTS.items()},  # formats visuels (docs/15)
        "scene_rewrite": REWRITE_PROMPT,  # scène réinventée pendant la revue du storyboard (docs/27)
        "seo": SEO,
        "strategy": STRATEGY,
        "improve": IMPROVE_PROMPT,
        "analyst": ANALYST_PROMPT,  # analyse des vidéos publiées, leçons à valider (docs/25)
        "keyframe_qc": QC_SYSTEM,
        "clip_qc": CLIP_SYSTEM,
        # consignes communes, ajoutées au message de l'agent avec les données de la tâche
        "rules_storytelling": RULES,
        **{f"guide_{recipe}": text for recipe, text in IDEA_GUIDES.items()},
        "rules_hook_title": HOOK_RULES,
        "hint_continuity": CONTINUITY_HINT,
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
