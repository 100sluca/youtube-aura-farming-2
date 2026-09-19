"""Synchronisation YouTube → Postgres : métriques journalières, totaux, rétention, commentaires."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from ..youtube.client import YouTubeClient
from .base import Context, Step


class SyncMetricsStep(Step):
    type = "sync_metrics"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        cid = ctx.job.channel_id
        assert cid
        if ctx.settings.dry_run:
            return {"skipped": "dry_run"}
        yt = YouTubeClient.for_channel(ctx.settings, ctx.db, cid)
        videos = ctx.db.fetch_all(
            "select id, youtube_video_id from videos where channel_id = %s and youtube_video_id is not null "
            "and status in ('scheduled', 'published')",
            (cid,),
        )
        by_yt = {v["youtube_video_id"]: v["id"] for v in videos}
        end, start = date.today(), date.today() - timedelta(days=int(ctx.job.payload.get("days", 3)))

        # 1) totaux + statut de publication (Data API, 1 unité / 50 vidéos)
        ctx.progress(10, "videos.list")
        for chunk in _chunks(list(by_yt), 50):
            for item in yt.videos_list(chunk):
                vid = by_yt[item["id"]]
                st = item["statistics"]
                ctx.db.execute(
                    """insert into video_stats (video_id, views, likes, comments, fetched_at) values (%s, %s, %s, %s, now())
                       on conflict (video_id) do update set views = excluded.views, likes = excluded.likes,
                       comments = excluded.comments, fetched_at = now()""",
                    (vid, int(st.get("viewCount", 0)), int(st.get("likeCount", 0)), int(st.get("commentCount", 0))),
                )
                privacy = item["status"]["privacyStatus"]
                if privacy == "public":
                    ctx.db.execute(
                        "update videos set status = 'published', published_at = coalesce(published_at, %s) where id = %s",
                        (item["snippet"]["publishedAt"], vid),
                    )
                elif privacy == "private" and item["status"].get("publishAt") is None:
                    ctx.db.alert(
                        "error",
                        "Vidéo restée privée après le créneau",
                        "Projet API non audité ? Voir docs/05-youtube-api.md §2",
                        video_id=vid,
                    )
            ctx.db.record_quota(cid, "videos.list", 1)

        # 2) métriques par jour et par vidéo : rapport « Top videos » (dimension video, ≤ 200 lignes,
        #    filtre video== liste d'id), une requête par jour et par lot de 200 vidéos.
        ctx.progress(50, "Analytics par vidéo")
        day = start
        while day <= end:
            for chunk in _chunks(list(by_yt), 200):
                rows = yt.analytics_video_metrics(day, chunk)
                for r in rows:
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

        # 3) chaîne par jour + total d'abonnés
        ctx.progress(85, "Analytics chaîne")
        subs = yt.channel_subscribers()
        ctx.db.record_quota(cid, "channels.list", 1)
        for r in yt.analytics(
            start,
            end,
            dimensions="day",
            metrics="views,engagedViews,estimatedMinutesWatched,subscribersGained,subscribersLost,likes,comments,shares",
        ):
            ctx.db.execute(
                """insert into channel_metrics_daily (channel_id, day, subscribers, views, engaged_views, estimated_minutes_watched,
                     subscribers_gained, subscribers_lost, likes, comments, shares)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   on conflict (channel_id, day) do update set subscribers = excluded.subscribers, views = excluded.views,
                     engaged_views = excluded.engaged_views, estimated_minutes_watched = excluded.estimated_minutes_watched,
                     subscribers_gained = excluded.subscribers_gained, subscribers_lost = excluded.subscribers_lost,
                     likes = excluded.likes, comments = excluded.comments, shares = excluded.shares""",
                (
                    cid,
                    r["day"],
                    subs if r["day"] == end.isoformat() else None,
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
        return {"videos": len(by_yt), "from": start.isoformat(), "to": end.isoformat()}


class SyncRetentionStep(Step):
    type = "sync_retention"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        vid = ctx.job.video_id
        v = ctx.db.fetch_one("select channel_id, youtube_video_id, published_at from videos where id = %s", (vid,))
        assert v and v["youtube_video_id"]
        if ctx.settings.dry_run:
            return {"skipped": "dry_run"}
        yt = YouTubeClient.for_channel(ctx.settings, ctx.db, v["channel_id"])
        rows = yt.analytics(
            v["published_at"].date(),
            date.today(),
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={v['youtube_video_id']}",
            metrics="audienceWatchRatio,relativeRetentionPerformance",
        )
        curve = [
            {"t": r["elapsedVideoTimeRatio"], "w": r["audienceWatchRatio"], "rel": r["relativeRetentionPerformance"]}
            for r in rows
        ]
        ctx.db.execute("insert into video_retention (video_id, curve) values (%s, %s)", (vid, Jsonb(curve)))
        return {"points": len(curve)}


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
