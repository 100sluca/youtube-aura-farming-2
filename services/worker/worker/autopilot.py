"""Pilote automatique (docs/46) : Luca part, les vidéos se font sans lui, de l'idée au montage.

Réglage : app_settings.autopilot = {"enabled", "series" (le thème), "target" (vidéos à faire), "channel_id" (facultatif),
"started_at"}, écrit par le dashboard (Création → Pilote automatique) ou `yt2 autopilot`. Toutes les 2 min, `tick` :
1. rien si une production du pilote est encore en route (une à la fois : la carte n'en fait qu'une) ;
2. sinon, la MEILLEURE idée (score de l'agent idée) parmi celles proposées pour la série depuis le départ du pilote ;
   s'il n'y en a plus, l'agent idée en fait un lot (IDEAS_PER_BATCH) et on attend le tick suivant ;
3. la production est créée marquée `autopilot` : script, puis storyboard validé seul après le contrôle de continuité
   (4 essais par image au plus, worker/steps/storyboard.py), puis clips, voix (le jeu des Réglages, Gemini 3.8 par
   défaut), montage, QA. La vidéo finit « à valider » dans la Bibliothèque, comme les autres.
Le pilote s'arrête seul quand `target` vidéos sont prêtes, ou après trop d'échecs (MAX_FAILURES), avec une alerte.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from psycopg.types.json import Jsonb

from .series import create_production, get_series

log = structlog.get_logger(__name__)

KEY = "autopilot"
IDEAS_PER_BATCH = 6  # l'agent idée en propose autant, le pilote prend la meilleure, puis la suivante…
MAX_FAILURES = 3  # productions ratées (ou lots d'idées ratés) avant que le pilote s'arrête
TERMINAL = ("ready", "failed", "archived", "cancelled")


def load(db: Any) -> dict[str, Any]:
    row = db.fetch_one("select value from app_settings where key = %s", (KEY,))
    return dict(row["value"]) if row and row["value"] else {}


def save(db: Any, value: dict[str, Any]) -> None:
    db.execute(
        """insert into app_settings (key, value) values (%s, %s)
           on conflict (key) do update set value = excluded.value, updated_at = now()""",
        (KEY, Jsonb(value)),
    )


def start(db: Any, series: str, target: int, channel_id: str | None = None) -> dict[str, Any]:
    get_series(db, series)  # LookupError si le thème n'existe pas
    value = {
        "enabled": True,
        "series": series,
        "target": max(1, int(target)),
        "channel_id": channel_id,
        "started_at": datetime.now(UTC).isoformat(),
    }
    save(db, value)
    return value


def stop(db: Any, reason: str) -> None:
    value = load(db)
    if value.get("enabled"):
        save(db, {**value, "enabled": False, "stopped_at": datetime.now(UTC).isoformat(), "stopped_reason": reason})


def tick(db: Any, settings: Any = None) -> str:
    """Un pas du pilote ; renvoie ce qu'il a fait (journal, tests)."""
    st = load(db)
    if not st.get("enabled"):
        return "coupé"
    try:
        series = get_series(db, st["series"])
    except LookupError:
        stop(db, f"thème introuvable : {st.get('series')}")
        return "thème introuvable"
    since = st["started_at"]
    rows = db.fetch_all(
        """select p.id, p.status::text as status,
                  (p.created_at > now() - interval '15 minutes'
                   or exists (select 1 from jobs j where j.status in ('queued', 'running')
                              and (j.production_id = p.id
                                   or j.video_id in (select v.id from videos v where v.production_id = p.id)))) as busy
           from productions p where p.autopilot and p.created_at >= %s""",
        (since,),
    )
    ready = [r for r in rows if r["status"] == "ready"]
    target = int(st.get("target") or 1)
    if len(ready) >= target:
        stop(db, "terminé")
        db.alert(
            "info", f"Pilote automatique : {len(ready)} vidéo(s) prête(s)", f"Thème {series.name}. À voir dans la Bibliothèque."
        )
        return "terminé"
    if any(r["status"] not in TERMINAL and r["busy"] for r in rows):
        return "en route"
    # une production arrêtée en route (plus aucune tâche) compte comme ratée, comme une production en échec
    failures = sum(1 for r in rows if r["status"] != "ready")
    if failures >= MAX_FAILURES:
        stop(db, f"{failures} productions ratées")
        db.alert("error", "Pilote automatique arrêté", f"{failures} productions ratées (thème {series.name}) : voir Tâches.")
        return "trop d'échecs"
    concept = db.fetch_one(
        """select id, title, score from concepts where series_id = %s and status = 'proposed' and created_at >= %s
           order by score desc nulls last, created_at desc limit 1""",
        (series.id, since),
    )
    if concept:
        pid, _ = create_production(db, concept["id"], channel_id=st.get("channel_id"), priority=80)
        db.execute("update productions set autopilot = true where id = %s", (pid,))
        log.info("autopilot.production", concept=concept["title"], score=concept["score"], production=str(pid))
        return "production lancée"
    if db.fetch_one(
        "select 1 from jobs where type = 'ideate' and status in ('queued', 'running') and payload->>'autopilot' = 'true'"
    ):
        return "idées en cours"
    # un lot raté, ou fini sans aucune idée (matière épuisée), compte comme un échec : jamais de boucle d'idées
    failed = db.fetch_one(
        """select count(*) as n from jobs where type = 'ideate' and payload->>'autopilot' = 'true' and created_at >= %s
           and (status = 'failed' or (status = 'done' and coalesce((result->>'created')::int, 0) = 0))""",
        (since,),
    )
    if failed and int(failed["n"]) >= MAX_FAILURES:
        stop(db, "l'agent idée échoue")
        db.alert("error", "Pilote automatique arrêté", f"L'agent idée a échoué {failed['n']} fois (thème {series.name}).")
        return "idées ratées"
    payload: dict[str, Any] = {"series": series.slug, "count": IDEAS_PER_BATCH, "autopilot": True}
    if st.get("channel_id"):
        payload["channel_id"] = st["channel_id"]
    db.enqueue("ideate", payload=payload, priority=60)
    log.info("autopilot.ideate", series=series.slug)
    return "idées demandées"
