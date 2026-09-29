"""Synchronisation YouTube → Postgres (docs/25-dashboard-statistiques.md).

Un seul job, `sync_metrics`, à deux niveaux :
- les compteurs publics (Data API, 1 unité pour 50 vidéos) : abonnés et vues de la chaîne, vues, j'aime et commentaires
  de chaque vidéo, passage en « publiée ». Toutes les heures (payload {"scope": "counters"}), gardés dans
  channel_snapshots et video_snapshots. YouTube Analytics ne publie ses chiffres qu'avec 2 à 3 jours de retard : ces
  relevés donnent le nombre d'abonnés, les vues des derniers jours et le démarrage de chaque vidéo (vues à 24 h, à 7 j) ;
- YouTube Analytics (toutes les 6 h, et bouton « Actualiser » du Dashboard) : la chaîne jour par jour, chaque vidéo jour
  par jour sur `days` jours, les totaux de toute la vie de chaque vidéo (rétention, durée moyenne, partages, abonnés,
  vues engagées) et la courbe de rétention des vidéos de moins de 45 jours (une par jour au plus).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from ..db import Db
from ..metrics import retention_summary, views_at
from ..youtube.client import AnalyticsBadRequest, YouTubeClient
from .base import Context, Step

HOURLY_KEEP_DAYS = 10  # relevés horaires gardés 10 jours, puis le dernier de chaque jour
MARKS_WINDOW_DAYS = 14  # vues à 24 h / 7 j : calculées tant que la vidéo a moins de 14 jours, puis abandon
# (colonne, instant après la mise en ligne, écart maximal entre les deux relevés qui l'encadrent)
MARKS = (("views_24h", timedelta(hours=24), timedelta(hours=6)), ("views_7d", timedelta(days=7), timedelta(hours=30)))
RETENTION_MAX_AGE_DAYS = 45
RETENTION_REFRESH_H = 20
RETENTION_MAX_PER_RUN = 30
LIFETIME_METRICS = {  # colonne de video_stats ← métrique YouTube Analytics (totaux de toute la vie de la vidéo)
    "analytics_views": "views",
    "engaged_views": "engagedViews",
    "shares": "shares",
    "subscribers_gained": "subscribersGained",
    "subscribers_lost": "subscribersLost",
    "estimated_minutes_watched": "estimatedMinutesWatched",
    "average_view_duration_s": "averageViewDuration",
    "average_view_pct": "averageViewPercentage",
}


class SyncMetricsStep(Step):
    type = "sync_metrics"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        cid = ctx.job.channel_id
        assert cid
        if ctx.settings.dry_run:
            return {"skipped": "dry_run"}
        counters_only = ctx.job.payload.get("scope") == "counters"
        yt = YouTubeClient.for_channel(ctx.settings, ctx.db, cid)
        videos = ctx.db.fetch_all(
            "select id, youtube_video_id, published_at from videos where channel_id = %s and youtube_video_id is not null "
            "and status in ('scheduled', 'published')",
            (cid,),
        )
        by_yt = {v["youtube_video_id"]: v["id"] for v in videos}

        ctx.progress(5, "Compteurs YouTube")
        out: dict[str, Any] = {"videos": len(by_yt), **collect_counters(ctx, yt, cid, by_yt, alert_private=not counters_only)}
        if not counters_only:
            end = date.today()
            start = end - timedelta(days=int(ctx.job.payload.get("days", 7)))
            first = min((v["published_at"].date() for v in videos if v["published_at"]), default=start)
            out |= collect_analytics(ctx, yt, cid, by_yt, start, end, first)
            ctx.progress(85, "Courbes de rétention")
            out["retention_curves"] = collect_retention(ctx.db, yt, cid, force=bool(ctx.job.payload.get("retention_all")))
        record_launch_marks(ctx.db, cid)
        return out


def collect_counters(
    ctx: Context, yt: YouTubeClient, cid: UUID, by_yt: dict[str, UUID], *, alert_private: bool
) -> dict[str, Any]:
    """Compteurs publics de la chaîne et de ses vidéos, relevés dans channel_snapshots / video_snapshots."""
    taken = datetime.now(UTC)
    stats = yt.channel_statistics()
    ctx.db.record_quota(cid, "channels.list", 1)
    if stats:
        ctx.db.execute(
            """insert into channel_snapshots (channel_id, taken_at, subscribers, views, videos) values (%s, %s, %s, %s, %s)
               on conflict do nothing""",
            (cid, taken, stats["subscribers"], stats["views"], stats["videos"]),
        )
    public = 0
    for chunk in _chunks(list(by_yt), 50):
        for item in yt.videos_list(chunk):
            vid = by_yt.get(item["id"])
            if vid is None:
                continue
            st = item.get("statistics", {})
            views, likes, comments = (int(st.get(k, 0)) for k in ("viewCount", "likeCount", "commentCount"))
            ctx.db.execute(
                """insert into video_stats (video_id, views, likes, comments, fetched_at) values (%s, %s, %s, %s, %s)
                   on conflict (video_id) do update set views = excluded.views, likes = excluded.likes,
                   comments = excluded.comments, fetched_at = excluded.fetched_at""",
                (vid, views, likes, comments, taken),
            )
            privacy = item["status"]["privacyStatus"]
            if privacy == "public":
                public += 1
                ctx.db.execute(
                    "update videos set status = 'published', published_at = coalesce(published_at, %s) where id = %s",
                    (item["snippet"]["publishedAt"], vid),
                )
                ctx.db.execute(
                    "insert into video_snapshots (video_id, taken_at, views, likes, comments) values (%s, %s, %s, %s, %s) "
                    "on conflict do nothing",
                    (vid, taken, views, likes, comments),
                )
            elif privacy == "private" and item["status"].get("publishAt") is None and alert_private:
                ctx.db.alert(
                    "error",
                    "Vidéo restée privée après le créneau",
                    "Projet API non audité ? Voir docs/05-youtube-api.md §2",
                    video_id=vid,
                )
        ctx.db.record_quota(cid, "videos.list", 1)
    prune_snapshots(ctx.db, cid)
    return {"subscribers": stats["subscribers"] if stats else None, "public": public}


def prune_snapshots(db: Db, cid: UUID) -> None:
    """Au-delà de HOURLY_KEEP_DAYS jours, on ne garde que le dernier relevé de chaque jour (heure de Paris)."""
    same_day = "(t.taken_at at time zone 'Europe/Paris')::date = (s.taken_at at time zone 'Europe/Paris')::date"
    db.execute(
        f"""delete from video_snapshots s using videos v
            where v.id = s.video_id and v.channel_id = %s and s.taken_at < now() - make_interval(days => %s)
              and exists (select 1 from video_snapshots t where t.video_id = s.video_id and t.taken_at > s.taken_at
                          and {same_day})""",  # noqa: S608 — texte fixe
        (cid, HOURLY_KEEP_DAYS),
    )
    db.execute(
        f"""delete from channel_snapshots s
            where s.channel_id = %s and s.taken_at < now() - make_interval(days => %s)
              and exists (select 1 from channel_snapshots t where t.channel_id = s.channel_id and t.taken_at > s.taken_at
                          and {same_day})""",  # noqa: S608 — texte fixe
        (cid, HOURLY_KEEP_DAYS),
    )


def collect_analytics(
    ctx: Context, yt: YouTubeClient, cid: UUID, by_yt: dict[str, UUID], start: date, end: date, first: date
) -> dict[str, Any]:
    """YouTube Analytics : la chaîne jour par jour, chaque vidéo jour par jour, puis les totaux de chaque vidéo depuis sa
    mise en ligne. Les jours d'Analytics suivent l'heure du Pacifique ; il ne renvoie rien au-delà du dernier jour publié."""
    ctx.progress(20, "Analytics · chaîne")
    channel_rows = yt.analytics(
        start,
        end,
        dimensions="day",
        metrics="views,engagedViews,estimatedMinutesWatched,subscribersGained,subscribersLost,likes,comments,shares",
    )
    for r in channel_rows:
        # le nombre d'abonnés du jour n'existe pas dans Analytics : il vient des relevés (channel_snapshots)
        ctx.db.execute(
            """insert into channel_metrics_daily (channel_id, day, views, engaged_views, estimated_minutes_watched,
                 subscribers_gained, subscribers_lost, likes, comments, shares)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (channel_id, day) do update set views = excluded.views,
                 engaged_views = excluded.engaged_views, estimated_minutes_watched = excluded.estimated_minutes_watched,
                 subscribers_gained = excluded.subscribers_gained, subscribers_lost = excluded.subscribers_lost,
                 likes = excluded.likes, comments = excluded.comments, shares = excluded.shares""",
            (
                cid,
                r["day"],
                r["views"],
                r["engagedViews"],
                r["estimatedMinutesWatched"],
                r["subscribersGained"],
                r["subscribersLost"],
                r["likes"],
                r["comments"],
                r["shares"],
            ),
        )
    through = max((str(r["day"]) for r in channel_rows), default=None)

    # chaque vidéo, jour par jour : rapport « Top videos » (dimension video, ≤ 200 id), une requête par jour et par lot
    ctx.progress(40, "Analytics · vidéos jour par jour")
    ids = list(by_yt)
    day = start
    while day <= end:
        for chunk in _chunks(ids, 200):
            for r in yt.analytics_video_metrics(day, chunk):
                ctx.db.execute(
                    """insert into video_metrics_daily (video_id, day, views, engaged_views, likes, dislikes, comments, shares,
                         subscribers_gained, subscribers_lost, estimated_minutes_watched, average_view_duration_s, average_view_pct)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       on conflict (video_id, day) do update set views = excluded.views, engaged_views = excluded.engaged_views,
                         likes = excluded.likes, dislikes = excluded.dislikes, comments = excluded.comments, shares = excluded.shares,
                         subscribers_gained = excluded.subscribers_gained, subscribers_lost = excluded.subscribers_lost,
                         estimated_minutes_watched = excluded.estimated_minutes_watched,
                         average_view_duration_s = excluded.average_view_duration_s,
                         average_view_pct = excluded.average_view_pct, fetched_at = now()""",
                    (
                        by_yt[r["video"]],
                        day,
                        *[
                            r.get(k)
                            for k in (
                                "views",
                                "engagedViews",
                                "likes",
                                "dislikes",
                                "comments",
                                "shares",
                                "subscribersGained",
                                "subscribersLost",
                                "estimatedMinutesWatched",
                                "averageViewDuration",
                                "averageViewPercentage",
                            )
                        ],
                    ),
                )
        day += timedelta(days=1)

    # totaux de toute la vie de chaque vidéo (rétention et durée moyennes exactes, pas une moyenne de moyennes)
    ctx.progress(70, "Analytics · totaux par vidéo")
    lifetime = 0
    for chunk in _chunks(ids, 200):
        for r in yt.analytics_video_metrics(first - timedelta(days=1), chunk, end=end):
            sets = ", ".join(f"{col} = %s" for col in LIFETIME_METRICS)
            ctx.db.execute(
                f"""update video_stats set {sets}, analytics_through = %s, analytics_fetched_at = now()
                    where video_id = %s""",  # noqa: S608 — colonnes fixes
                (*[r.get(metric) for metric in LIFETIME_METRICS.values()], through, by_yt[r["video"]]),
            )
            lifetime += 1
    return {"from": start.isoformat(), "to": end.isoformat(), "analytics_through": through, "analytics_videos": lifetime}


def collect_retention(db: Db, yt: YouTubeClient, cid: UUID, *, force: bool = False) -> int:
    """Courbe de rétention des vidéos publiées depuis moins de RETENTION_MAX_AGE_DAYS jours, une par jour au plus."""
    rows = db.fetch_all(
        """select v.id, v.youtube_video_id, v.published_at, v.duration_s,
                  (select max(r.fetched_at) from video_retention r where r.video_id = v.id) as last_curve
           from videos v
           where v.channel_id = %s and v.status = 'published' and v.youtube_video_id is not null
             and v.published_at is not null and v.published_at > now() - make_interval(days => %s)
           order by v.published_at desc""",
        (cid, RETENTION_MAX_AGE_DAYS),
    )
    fresh = datetime.now(UTC) - timedelta(hours=RETENTION_REFRESH_H)
    stored = 0
    for v in rows:
        if stored >= RETENTION_MAX_PER_RUN:
            break
        if not force and v["last_curve"] and v["last_curve"] > fresh:
            continue
        if store_retention(db, yt, v):
            stored += 1
    return stored


def store_retention(db: Db, yt: YouTubeClient, v: dict[str, Any]) -> bool:
    """Enregistre la courbe de rétention d'une vidéo (la plus récente seulement) et ce qu'on en tire : audience à 3 s
    et à la fin. False si Analytics n'a encore rien pour elle."""
    try:
        rows = yt.analytics_retention(v["youtube_video_id"], v["published_at"].date() - timedelta(days=1), date.today())
    except AnalyticsBadRequest:
        return False
    curve = [
        {"t": r["elapsedVideoTimeRatio"], "w": r["audienceWatchRatio"], "rel": r["relativeRetentionPerformance"]} for r in rows
    ]
    if not curve:
        return False
    db.execute("insert into video_retention (video_id, curve) values (%s, %s)", (v["id"], Jsonb(curve)))
    db.execute(
        """delete from video_retention where video_id = %s
           and fetched_at < (select max(fetched_at) from video_retention where video_id = %s)""",
        (v["id"], v["id"]),
    )
    hook, end = retention_summary(curve, float(v["duration_s"]) if v.get("duration_s") else None)
    db.execute("update video_stats set hook_retention_pct = %s, end_retention_pct = %s where video_id = %s", (hook, end, v["id"]))
    return True


def record_launch_marks(db: Db, cid: UUID) -> None:
    """Vues 24 h et 7 jours après la mise en ligne, calculées une fois quand la vidéo passe le cap : d'après les relevés
    horaires, sinon (7 jours) la somme de ses jours dans YouTube Analytics quand ceux-ci sont tous publiés."""
    rows = db.fetch_all(
        """select v.id, v.published_at, s.views_24h, s.views_7d, s.analytics_through
           from videos v join video_stats s on s.video_id = v.id
           where v.channel_id = %s and v.status = 'published' and v.published_at is not null
             and v.published_at > now() - make_interval(days => %s)
             and (s.views_24h is null or s.views_7d is null)""",
        (cid, MARKS_WINDOW_DAYS),
    )
    now = datetime.now(UTC)
    for r in rows:
        for col, mark, gap in MARKS:
            at = r["published_at"] + mark
            if r[col] is not None or at > now:
                continue
            snaps = db.fetch_all(
                "select taken_at, views from video_snapshots where video_id = %s and taken_at between %s and %s order by taken_at",
                (r["id"], at - gap, at + gap),
            )
            value = views_at([(s["taken_at"], s["views"]) for s in snaps], r["published_at"], at, gap)
            if value is None and col == "views_7d":
                value = _first_week_from_analytics(db, r)
            if value is not None:
                db.execute(f"update video_stats set {col} = %s where video_id = %s", (value, r["id"]))  # noqa: S608


def _first_week_from_analytics(db: Db, r: dict[str, Any]) -> int | None:
    """Somme des 7 premiers jours (heure du Pacifique, celle d'Analytics), si Analytics les a tous publiés."""
    row = db.fetch_one(
        """select (%s at time zone 'America/Los_Angeles')::date as first_day,
                  coalesce(sum(d.views), 0)::bigint as views
           from video_metrics_daily d
           where d.video_id = %s
             and d.day between (%s at time zone 'America/Los_Angeles')::date
                           and (%s at time zone 'America/Los_Angeles')::date + 6""",
        (r["published_at"], r["id"], r["published_at"], r["published_at"]),
    )
    through = r.get("analytics_through")
    if not row or through is None or through < row["first_day"] + timedelta(days=6):
        return None
    return int(row["views"])


class SyncRetentionStep(Step):
    type = "sync_retention"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        vid = ctx.job.video_id
        v = ctx.db.fetch_one(
            "select id, channel_id, youtube_video_id, published_at, duration_s from videos where id = %s", (vid,)
        )
        assert v and v["youtube_video_id"]
        if ctx.settings.dry_run:
            return {"skipped": "dry_run"}
        yt = YouTubeClient.for_channel(ctx.settings, ctx.db, v["channel_id"])
        return {"stored": store_retention(ctx.db, yt, v)}


class SyncCommentsStep(Step):
    type = "sync_comments"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        vid = ctx.job.video_id
        v = ctx.db.fetch_one("select channel_id, youtube_video_id from videos where id = %s", (vid,))
        assert v and v["youtube_video_id"]
        if ctx.settings.dry_run:
            return {"skipped": "dry_run"}
        yt = YouTubeClient.for_channel(ctx.settings, ctx.db, v["channel_id"])
        n = 0
        for c in yt.comment_threads(v["youtube_video_id"], max_results=20):
            top = c["snippet"]["topLevelComment"]
            s = top["snippet"]
            ctx.db.execute(
                """insert into video_comments (id, video_id, author, text, like_count, published_at)
                   values (%s, %s, %s, %s, %s, %s)
                   on conflict (id) do update set like_count = excluded.like_count, text = excluded.text, fetched_at = now()""",
                (top["id"], vid, s["authorDisplayName"], s["textOriginal"], s["likeCount"], s["publishedAt"]),
            )
            n += 1
        ctx.db.record_quota(v["channel_id"], "commentThreads.list", 1)
        return {"comments": n}


def _chunks(items: list, n: int):  # noqa: ANN202
    for i in range(0, len(items), n):
        yield items[i : i + n]
