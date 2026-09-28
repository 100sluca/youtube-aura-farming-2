"""Tâches récurrentes (APScheduler). Voir docs/03-pipeline.md §3."""

from __future__ import annotations

from datetime import timedelta

import structlog
from apscheduler.schedulers.background import BackgroundScheduler

from .config import Settings
from .db import Db
from .notify import flush_pending_alerts
from .series import active_series, create_production, next_concepts
from .tiktok.config import load_tiktok_config, zernio_key

log = structlog.get_logger(__name__)

MIN_SCHEDULED_BUFFER = 6  # vidéos programmées par chaîne (≈ 2 jours)


def plan_uploads(db: Db, settings: Settings) -> None:
    """Attribue un créneau à chaque vidéo `ready` et crée le job upload (si créneau < 72 h)."""
    db.requeue_stale_jobs()
    videos = db.fetch_all(
        """select v.id, v.channel_id from videos v
           where v.status = 'ready' and v.scheduled_at is null
             and not exists (select 1 from jobs j where j.video_id = v.id and j.type = 'upload'
                             and j.status in ('queued', 'running'))
             -- titre, description et tags définitifs avant tout envoi (agent SEO)
             and not exists (select 1 from jobs j where j.video_id = v.id and j.type = 'seo'
                             and j.status in ('queued', 'running'))
           order by v.created_at limit 20"""
    )
    for v in videos:
        slot = db.fetch_one("select next_free_slot(%s) as at", (v["channel_id"],))
        if not slot or not slot["at"]:
            continue
        db.execute("update videos set scheduled_at = %s where id = %s", (slot["at"], v["id"]))
        db.enqueue(
            "upload",
            video_id=v["id"],
            channel_id=v["channel_id"],
            priority=50,
            run_after=slot["at"] - timedelta(hours=72),
            max_attempts=2,
        )
        log.info("planned", video=str(v["id"]), at=slot["at"].isoformat())


def plan_tiktok(db: Db, settings: Settings) -> None:
    """Chaque Short programmé sur YouTube d'une chaîne reliée à TikTok part aussi sur TikTok, au même créneau
    (docs/36). Seulement les créneaux qui suivent l'activation, et 24 h en arrière au plus (PC resté éteint)."""
    cfg = load_tiktok_config(db)
    channels = [(cid, ch) for cid, ch in cfg.channels.items() if ch.enabled and ch.account_id]
    if not channels or not zernio_key(settings, db):
        return
    for channel_id, ch in channels:
        rows = db.fetch_all(
            """select v.id from videos v
               where v.channel_id = %s and v.origin = 'app' and v.tiktok is null
                 and v.status in ('scheduled', 'published') and v.youtube_video_id is not null
                 and v.scheduled_at > now() - interval '24 hours'
                 and (%s::timestamptz is null or v.scheduled_at >= %s::timestamptz)
                 and not exists (select 1 from jobs j where j.video_id = v.id and j.type = 'tiktok_publish'
                                 and (j.status in ('queued', 'running')
                                      or (j.status = 'failed' and j.finished_at > now() - interval '6 hours')))
               order by v.scheduled_at limit 10""",
            (channel_id, ch.enabled_at, ch.enabled_at),
        )
        for r in rows:
            db.enqueue("tiktok_publish", video_id=r["id"], channel_id=channel_id, priority=55, max_attempts=3)
            log.info("tiktok.planned", video=str(r["id"]), account=ch.username or ch.account_id)


def top_up_ideas(db: Db, settings: Settings) -> None:
    """Chaque série active garde au moins `ideas_per_series` concepts en attente (proposés ou approuvés)."""
    for s in active_series(db):
        row = db.fetch_one(
            "select count(*) as n from concepts where series_id = %s and status in ('proposed', 'approved')", (s.id,)
        )
        pending = db.fetch_one(
            "select 1 from jobs where type = 'ideate' and status in ('queued', 'running') and payload->>'series' = %s", (s.slug,)
        )
        if row and row["n"] < settings.ideas_per_series and not pending:
            db.enqueue("ideate", payload={"series": s.slug, "count": settings.ideas_per_series}, priority=120)
            log.info("ideate.enqueued", series=s.slug, pending=row["n"])


def start_productions(db: Db, settings: Settings) -> None:
    """Le lien concept approuvé → production : au plus `productions_per_day` par jour et
    `max_productions_in_flight` en cours, réparties entre séries selon leurs poids."""
    if not settings.auto_produce:
        return
    today = db.fetch_one("select count(*) as n from productions where created_at::date = current_date")
    in_flight = db.fetch_one("select count(*) as n from productions where status not in ('ready', 'failed', 'archived')")
    room = min(settings.productions_per_day - int(today["n"] if today else 0),
               settings.max_productions_in_flight - int(in_flight["n"] if in_flight else 0))
    if room <= 0:
        return
    for c in next_concepts(db, room):
        pid, created = create_production(db, c["id"])
        if created:
            log.info("production.created", concept=c["title"], production=str(pid))


def check_buffers(db: Db, settings: Settings) -> None:
    rows = db.fetch_all(
        """select c.id, c.slug, count(v.*) filter (where v.status = 'scheduled') as scheduled
           from channels c left join videos v on v.channel_id = c.id
           where c.is_active group by c.id, c.slug"""
    )
    for r in rows:
        if r["scheduled"] < MIN_SCHEDULED_BUFFER:
            db.alert(
                "warning",
                f"Tampon faible sur {r['slug']}",
                f"{r['scheduled']} vidéo(s) programmée(s), minimum {MIN_SCHEDULED_BUFFER}.",
            )
    quota = db.fetch_all(
        """select c.slug, coalesce(sum(u.units), 0) as units from channels c
           left join api_quota_usage u on u.channel_id = c.id and u.day = current_date
             -- envois et recherches : compteurs à part (100 appels par jour), hors des 10 000 unités
             and u.endpoint not in ('videos.insert', 'search.list')
           group by c.slug"""
    )
    for q in quota:
        if q["units"] > 8000:
            db.alert("warning", f"Quota YouTube à {q['units']} / 10 000 ({q['slug']})")


def enqueue_sync(db: Db, channel_id: object, payload: dict, priority: int) -> bool:
    """Met en file une synchro YouTube de la chaîne, sauf si une autre attend déjà (ou tourne, pour les compteurs)."""
    busy = ("queued", "running") if payload.get("scope") == "counters" else ("queued",)
    if db.fetch_one(
        "select 1 from jobs where type = 'sync_metrics' and channel_id = %s and status::text = any(%s) limit 1",
        (channel_id, list(busy)),
    ):
        return False
    db.enqueue("sync_metrics", channel_id=channel_id, payload=payload, priority=priority)
    return True


def connected_channels(db: Db) -> list[dict]:
    return db.fetch_all(
        """select c.id from channels c where c.is_active and c.youtube_channel_id is not null
           and exists (select 1 from channel_credentials cc where cc.channel_id = c.id)"""
    )


def hourly_counters(db: Db, settings: Settings) -> None:
    """Toutes les heures : abonnés, vues, j'aime et commentaires (Data API, 1 unité pour 50 vidéos), docs/25."""
    for c in connected_channels(db):
        enqueue_sync(db, c["id"], {"scope": "counters"}, priority=85)


def analytics_sync(db: Db, settings: Settings) -> None:
    """Toutes les 6 h : YouTube Analytics, publié une fois par jour avec 2 à 3 jours de retard, à une heure inconnue."""
    for c in connected_channels(db):
        enqueue_sync(db, c["id"], {"days": 7}, priority=80)


def nightly_sync(db: Db, settings: Settings) -> None:
    """Chaque nuit : Analytics (courbes de rétention comprises, worker/steps/sync.py) et commentaires récents."""
    analytics_sync(db, settings)
    for v in db.fetch_all("select id from videos where status = 'published' order by published_at desc limit 10"):
        db.enqueue("sync_comments", video_id=v["id"], priority=95)


def weekly_analysis(db: Db, settings: Settings) -> None:
    """Chaque dimanche : l'agent analyste compare les vidéos qui marchent et les autres, et propose des leçons (docs/25)."""
    for c in connected_channels(db):
        if not db.fetch_one(
            "select 1 from jobs where type = 'analyze' and channel_id = %s and status in ('queued', 'running')", (c["id"],)
        ):
            db.enqueue("analyze", channel_id=c["id"], payload={"source": "hebdomadaire"}, priority=140)


def weekly_improve(db: Db, settings: Settings) -> None:
    db.enqueue("improve", payload={"window_days": 14}, priority=150)


def weekly_strategy(db: Db, settings: Settings) -> None:
    """Une proposition de stratégie par chaîne active, à valider avec `yt2 strategy accept`."""
    for c in db.fetch_all("select id from channels where is_active"):
        db.enqueue("strategy", channel_id=c["id"], payload={"window_days": settings.strategy_window_days}, priority=150)


def start_scheduler(db: Db, settings: Settings) -> BackgroundScheduler:
    s = BackgroundScheduler(timezone="Europe/Paris")
    s.add_job(plan_uploads, "interval", minutes=5, args=[db, settings], id="plan_uploads")
    s.add_job(plan_tiktok, "interval", minutes=5, args=[db, settings], id="plan_tiktok")  # docs/36
    s.add_job(top_up_ideas, "interval", hours=1, args=[db, settings], id="top_up_ideas")
    s.add_job(start_productions, "interval", minutes=15, args=[db, settings], id="start_productions")
    s.add_job(flush_pending_alerts, "interval", seconds=20, args=[db, settings], id="alerts")  # mails, docs/32
    s.add_job(check_buffers, "cron", hour=6, args=[db, settings], id="check_buffers")
    s.add_job(hourly_counters, "cron", minute=5, args=[db, settings], id="hourly_counters")
    s.add_job(nightly_sync, "cron", hour=3, minute=20, args=[db, settings], id="nightly_sync")
    s.add_job(analytics_sync, "cron", hour="9,15,21", minute=20, args=[db, settings], id="analytics_sync")
    s.add_job(weekly_improve, "cron", day_of_week="sun", hour=4, args=[db, settings], id="improve")
    s.add_job(weekly_strategy, "cron", day_of_week="sun", hour=4, minute=30, args=[db, settings], id="strategy")
    s.add_job(weekly_analysis, "cron", day_of_week="sun", hour=5, args=[db, settings], id="analysis")
    s.start()
    return s
