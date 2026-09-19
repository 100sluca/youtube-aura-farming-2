"""Tâches récurrentes (APScheduler). Voir docs/03-pipeline.md §3."""

from __future__ import annotations

from datetime import timedelta

import structlog
from apscheduler.schedulers.background import BackgroundScheduler

from .config import Settings
from .db import Db
from .notify import flush_pending_alerts

log = structlog.get_logger(__name__)

MIN_SCHEDULED_BUFFER = 6  # vidéos programmées par chaîne (≈ 2 jours)
MIN_IDEA_BACKLOG = 10


def plan_uploads(db: Db, settings: Settings) -> None:
    """Attribue un créneau à chaque vidéo `ready` et crée le job upload (si créneau < 72 h)."""
    db.requeue_stale_jobs()
    videos = db.fetch_all(
        """select v.id, v.channel_id from videos v
           where v.status = 'ready' and v.scheduled_at is null
             and not exists (select 1 from jobs j where j.video_id = v.id and j.type = 'upload'
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


def top_up_ideas(db: Db, settings: Settings) -> None:
    row = db.fetch_one("select count(*) as n from concepts where status in ('proposed', 'approved')")
    if (
        row
        and row["n"] < MIN_IDEA_BACKLOG
        and not db.fetch_one("select 1 from jobs where type = 'ideate' and status in ('queued', 'running')")
    ):
        db.enqueue("ideate", payload={"count": 10}, priority=120)


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
           group by c.slug"""
    )
    for q in quota:
        if q["units"] > 8000:
            db.alert("warning", f"Quota YouTube à {q['units']} / 10 000 ({q['slug']})")


def nightly_sync(db: Db, settings: Settings) -> None:
    for c in db.fetch_all("select id from channels where is_active and youtube_channel_id is not null"):
        db.enqueue("sync_metrics", channel_id=c["id"], priority=80)
    for v in db.fetch_all(
        """select id from videos where status = 'published'
           and (published_at::date = current_date - 3 or published_at::date = current_date - 14)"""
    ):
        db.enqueue("sync_retention", video_id=v["id"], priority=90)
    for v in db.fetch_all("select id from videos where status = 'published' order by published_at desc limit 10"):
        db.enqueue("sync_comments", video_id=v["id"], priority=95)


def weekly_improve(db: Db, settings: Settings) -> None:
    db.enqueue("improve", payload={"window_days": 14}, priority=150)


def start_scheduler(db: Db, settings: Settings) -> BackgroundScheduler:
    s = BackgroundScheduler(timezone="Europe/Paris")
    s.add_job(plan_uploads, "interval", minutes=5, args=[db, settings], id="plan_uploads")
    s.add_job(top_up_ideas, "interval", hours=1, args=[db, settings], id="top_up_ideas")
    s.add_job(flush_pending_alerts, "interval", minutes=2, args=[db, settings], id="alerts")
    s.add_job(check_buffers, "cron", hour=6, args=[db, settings], id="check_buffers")
    s.add_job(nightly_sync, "cron", hour=3, args=[db, settings], id="nightly_sync")
    s.add_job(weekly_improve, "cron", day_of_week="sun", hour=4, args=[db, settings], id="improve")
    s.start()
    return s
