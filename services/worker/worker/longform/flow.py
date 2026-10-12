"""Enchaînement d'une vidéo longue (docs/63 §1) et ce qui la relie au reste de l'usine.

idea → (Écrire) → writing → script (Luca relit, corrige, valide) → making : les plans du réalisateur, puis images,
clips et miniatures sur la carte graphique, pendant que Luca enregistre sa voix dans le Studio voix → (Terminer
l'enregistrement) → voix finale → montage (il attend que les images soient faites) → review (Luca regarde, choisit
titre et miniature) → (Programmer) → envoi sur YouTube avec la miniature → done.

Une vidéo longue est une production (kind = 'long', un concept pour son titre dans le panneau Tâches) : pause, arrêt,
ordre de la file marchent comme pour les Shorts. Sa vidéo finale est une ligne de videos d'origine 'long' : ni
créneau des Shorts, ni envoi automatique sur TikTok ou Instagram.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from psycopg.types.json import Jsonb

log = structlog.get_logger(__name__)

SETTINGS_DEFAULT: dict[str, Any] = {
    "weekdays": [2, 4, 6],  # mardi, jeudi, samedi (1 = lundi)
    "hour": "17:00",
    "target_minutes": 22,
    "formats": ["mystere", "epoque"],
    "voice_modifier": False,
    "modifier_voice": "",
    "clip_hook_s": 90,
    "clips_per_chapter": 1,
    "image_size": "1664x928",
    "clip_size": "832x480",
    "subtitles": True,  # le texte lu gravé en bas de l'image (captions.py, docs/63 §12)
}


def long_settings(db: Any) -> dict[str, Any]:
    row = db.fetch_one("select value from app_settings where key = 'long'")
    return {**SETTINGS_DEFAULT, **((row or {}).get("value") or {})}


def get_long(db: Any, long_id: Any) -> dict[str, Any]:
    lv = db.fetch_one("select * from long_videos where id = %s", (long_id,))
    if not lv:
        raise RuntimeError(f"vidéo longue {long_id} introuvable")
    return lv


def update_long(db: Any, long_id: Any, **cols: Any) -> None:
    keys = list(cols)
    vals = [Jsonb(v) if isinstance(v, (dict, list)) else v for v in cols.values()]
    db.execute(
        f"update long_videos set {', '.join(f'{k} = %s' for k in keys)} where id = %s",  # noqa: S608 — colonnes du code
        (*vals, long_id),
    )


def ensure_production(db: Any, settings: Any, lv: dict[str, Any]) -> tuple[UUID, Path]:
    """La production de la vidéo longue (et son concept, qui donne son titre au panneau Tâches) et son dossier."""
    if lv.get("production_id") and lv.get("dir"):
        return lv["production_id"], Path(lv["dir"])
    idea = lv.get("idea") or {}
    title = idea.get("title") or lv["subject"]
    pid = lv.get("production_id")
    if not pid:
        concept = db.fetch_one(
            """insert into concepts (title, hook, category, premise, source, status, channel_id, angle, score)
               values (%s, %s, 'long', %s, 'agent', 'used', %s, %s, %s) returning id""",
            (title[:200], idea.get("hook"), lv["subject"], lv["channel_id"], idea.get("angle"), idea.get("score")),
        )
        row = db.fetch_one(
            """insert into productions (concept_id, format, status, target_duration_s, channel_id, kind)
               values (%s, 'A_voiceover', 'scripting', %s, %s, 'long') returning id""",
            (concept["id"], int(lv["target_minutes"]) * 60, lv["channel_id"]),
        )
        pid = row["id"]
    folder = Path(settings.data_dir) / "productions" / str(pid) / "long"
    folder.mkdir(parents=True, exist_ok=True)
    update_long(db, lv["id"], production_id=pid, dir=str(folder))
    lv["production_id"], lv["dir"] = pid, str(folder)
    return pid, folder


def set_production_status(db: Any, lv: dict[str, Any], status: str) -> None:
    if lv.get("production_id"):
        db.execute("update productions set status = %s where id = %s", (status, lv["production_id"]))


def pending(db: Any, long_id: Any, *types: str, actions: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Tâches en attente ou en cours de cette vidéo longue."""
    rows = db.fetch_all(
        """select id, type::text as type, payload, status from jobs
           where payload->>'long_id' = %s and status in ('queued', 'running') and type::text = any(%s)""",
        (str(long_id), list(types) or ["long_write", "long_make", "long_take"]),
    )
    return [r for r in rows if not actions or (r["payload"] or {}).get("action") in actions]


def enqueue_make(
    db: Any, lv: dict[str, Any], action: str, *, priority: int = 95, depends_on: list[UUID] | None = None, **payload: Any
) -> UUID:
    return db.enqueue(
        "long_make",
        production_id=lv.get("production_id"),
        channel_id=lv["channel_id"],
        payload={"long_id": str(lv["id"]), "action": action, **payload},
        priority=priority,
        depends_on=depends_on or [],
        max_attempts=3,
    )


def enqueue_write(db: Any, lv: dict[str, Any], action: str, *, priority: int = 60, **payload: Any) -> UUID:
    return db.enqueue(
        "long_write",
        production_id=lv.get("production_id"),
        channel_id=lv["channel_id"],
        payload={"long_id": str(lv["id"]), "action": action, **payload},
        priority=priority,
        max_attempts=3,
    )


def enqueue_visuals(db: Any, lv: dict[str, Any]) -> list[UUID]:
    """Après les plans du réalisateur : les images chapitre par chapitre (l'ouverture d'abord), les clips de chaque
    chapitre dès que ses images sont faites, les miniatures. Même priorité que les clips des Shorts : l'ordre de la file
    (panneau Tâches, glisser pour réordonner, docs/40) décide qui passe d'abord sur la carte graphique."""
    jobs: list[UUID] = []
    chapters = [
        r["chapter"]
        for r in db.fetch_all("select distinct chapter from long_shots where long_id = %s order by chapter", (lv["id"],))
    ]
    for c in chapters:
        img = enqueue_make(db, lv, "images", chapter=c, priority=100)
        jobs.append(img)
        for s in db.fetch_all(
            "select idx from long_shots where long_id = %s and chapter = %s and kind = 'clip' order by idx", (lv["id"], c)
        ):
            jobs.append(enqueue_make(db, lv, "clip", idx=s["idx"], priority=100, depends_on=[img]))
    jobs.append(enqueue_make(db, lv, "thumbnails", priority=100))
    return jobs


# ---------------------------------------------------------------------------------------------------------------------
# Mails
# ---------------------------------------------------------------------------------------------------------------------


def mail(db: Any, settings: Any, subject: str, text: str, image: Path | None = None) -> None:
    """Un mail à Luca (Réglages → Notifications) ; jamais d'exception."""
    try:
        from ..notify import Mail, load_notify_config, send_email

        ok, why = send_email(
            load_notify_config(settings, db),
            Mail(subject=subject, text=text, image=image.read_bytes() if image and image.exists() else None),
        )
        if not ok:
            log.info("long.mail_non_envoye", raison=why)
    except Exception as exc:  # noqa: BLE001
        log.warning("long.mail_impossible", error=str(exc)[:300])


def reading_minutes(lv: dict[str, Any]) -> float:
    words = int((lv.get("script") or {}).get("words") or 0)
    return round(words / 150 * 1.6) if words else 0  # 1,6 × la durée lue : les reprises


def to_read(db: Any) -> list[dict[str, Any]]:
    """Vidéos longues validées dont la voix n'est pas encore enregistrée."""
    return db.fetch_all(
        """select id, subject, idea, script from long_videos
           where stage in ('making') and voice_done_at is null order by approved_at nulls last, created_at"""
    )


def notify_to_read(db: Any, settings: Any, just: dict[str, Any] | None = None) -> None:
    """« N vidéos à lire » : à la validation d'un script, puis chaque matin tant qu'il en reste."""
    rows = to_read(db)
    if not rows:
        return
    total = sum(reading_minutes(r) for r in rows)
    lines = "\n".join(f"- {(r['idea'] or {}).get('title') or r['subject']} (≈ {reading_minutes(r)} min de micro)" for r in rows)
    url = f"{settings.dashboard_url.rstrip('/')}/long"
    head = f"« {(just.get('idea') or {}).get('title') or just['subject']} » est prête à lire. " if just else ""
    mail(
        db,
        settings,
        f"🎙️ {len(rows)} vidéo{'s' if len(rows) > 1 else ''} longue{'s' if len(rows) > 1 else ''} à lire (≈ {total} min)",
        f"{head}Tout est prêt sauf ta voix : ouvre le Studio voix dans la page Vidéos longues.\n\n{lines}\n\n{url}",
    )


def daily_digest(db: Any, settings: Any) -> None:
    try:
        notify_to_read(db, settings)
    except Exception as exc:  # noqa: BLE001 — table absente (migration 0054) ou base injoignable
        log.warning("long.digest_impossible", error=str(exc)[:300])


# ---------------------------------------------------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------------------------------------------------


def next_slot(db: Any, channel_id: Any, after: datetime | None = None) -> datetime:
    """Prochain créneau des vidéos longues (Réglages : jours et heure, Europe/Paris) que n'occupe aucune autre vidéo
    longue."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    cfg = long_settings(db)
    tz = ZoneInfo("Europe/Paris")
    hh, mm = (int(x) for x in str(cfg.get("hour") or "17:00").split(":")[:2])
    days = {int(d) for d in cfg.get("weekdays") or [2, 4, 6]} or {2, 4, 6}
    taken = {
        r["at"].astimezone(tz).date()
        for r in db.fetch_all(
            """select v.scheduled_at as at from videos v where v.channel_id = %s and v.origin = 'long'
               and v.scheduled_at is not null and v.status in ('ready', 'uploading', 'scheduled')""",
            (channel_id,),
        )
    }
    now = (after or datetime.now(tz)).astimezone(tz) + timedelta(hours=3)
    day = now.date()
    for _ in range(120):
        at = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
        if day.isoweekday() in days and at > now and day not in taken:
            return at
        day += timedelta(days=1)
    return now + timedelta(days=1)
