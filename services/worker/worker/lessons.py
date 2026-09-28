"""Leçons de l'agent analyste (docs/25-dashboard-statistiques.md) : celles que Luca a validées dans le Dashboard sont
glissées dans le message de l'agent qu'elles visent (idées, scénaristes, SEO), à chaque appel. Les leçons de cible
« production » (modèle vidéo, durée, musique, montage) ne vont à aucun agent : ce sont des réglages à faire soi-même.
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger(__name__)

MAX_LESSONS = 12  # par message d'agent, les plus récemment validées d'abord


def active_lessons(db: Any, channel_id: Any = None) -> list[dict[str, Any]]:
    """Leçons en service (toutes cibles), pour l'agent analyste : ne pas les reproposer, les confronter aux chiffres."""
    try:
        return db.fetch_all(
            """select id, target, recipe, rule from performance_lessons
               where status = 'active' and (%s::uuid is null or channel_id is null or channel_id = %s)
               order by decided_at desc nulls last, created_at desc""",
            (channel_id, channel_id),
        )
    except Exception as exc:  # noqa: BLE001 — migration 0016 absente : pas de leçon
        log.warning("lessons.lecture_impossible", error=str(exc)[:200])
        return []


def lessons_text(db: Any, target: str, *, channel_id: Any = None, recipe: str | None = None) -> str:
    """Bloc à ajouter au message d'un agent ; vide s'il n'y a aucune leçon validée pour lui."""
    try:
        rows = db.fetch_all(
            """select rule from performance_lessons
               where status = 'active' and target = %s
                 and (%s::uuid is null or channel_id is null or channel_id = %s)
                 and (recipe is null or %s::text is null or recipe = %s)
               order by decided_at desc nulls last, created_at desc
               limit %s""",
            (target, channel_id, channel_id, recipe, recipe, MAX_LESSONS),
        )
    except Exception as exc:  # noqa: BLE001 — une leçon manquante ne doit jamais bloquer un agent
        log.warning("lessons.lecture_impossible", error=str(exc)[:200])
        return ""
    if not rows:
        return ""
    return "LEÇONS TIRÉES DES VIDÉOS PUBLIÉES DE LA CHAÎNE (validées par l'humain, à appliquer en priorité) :\n" + "\n".join(
        f"- {r['rule']}" for r in rows
    )
