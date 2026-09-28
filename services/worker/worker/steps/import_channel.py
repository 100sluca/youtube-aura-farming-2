"""Import de l'historique d'une chaîne YouTube connectée (docs/16 §3).

Mis en file par le dashboard à la connexion d'une chaîne (et par « Importer l'historique » dans Réglages). Les
vidéos déjà en ligne entrent dans la bibliothèque avec origin = 'imported' : sans production, sans fichier local,
avec titre, durée, vignette YouTube et totaux (vues, j'aime, commentaires). Elles sont distinguées des vidéos
produites par l'appli partout dans le dashboard, et exclues des statistiques qui nourrissent les agents
(v_video_performance ne garde que les vidéos avec production). Une vidéo déjà connue (envoyée par l'appli, ou
importée plus tôt) n'est pas dupliquée : relancer l'import ne fait qu'ajouter les nouvelles.

Quota Data API : 1 unité pour la chaîne, 1 par page de 50 vidéos, 1 par lot de 50 détails. Les métriques jour par
jour et la courbe de rétention arrivent ensuite par sync_metrics (mis en file à la fin, sur 28 jours).
"""

from __future__ import annotations

import re
from typing import Any

from ..youtube.client import YouTubeClient
from .base import Context, Step

ISO_DURATION = re.compile(r"^P(?:(?P<d>\d+)D)?(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+(?:\.\d+)?)S)?)?$")


def parse_iso_duration(value: str | None) -> float | None:
    """« PT1M5S » → 65.0 ; None si la durée est absente ou illisible (direct, première en attente)."""
    if not value:
        return None
    m = ISO_DURATION.match(value)
    if not m or not any(m.groupdict().values()):
        return None
    d, h, mi, s = (float(m.group(k) or 0) for k in ("d", "h", "m", "s"))
    return d * 86400 + h * 3600 + mi * 60 + s


def best_thumbnail(snippet: dict[str, Any]) -> str | None:
    thumbs = snippet.get("thumbnails") or {}
    for key in ("maxres", "standard", "high", "medium", "default"):
        url = (thumbs.get(key) or {}).get("url")
        if url:
            return url
    return None


def imported_video(item: dict[str, Any]) -> dict[str, Any]:
    """Réponse videos.list → colonnes de `videos` (et totaux de `video_stats`)."""
    snippet = item.get("snippet") or {}
    status = item.get("status") or {}
    stats = item.get("statistics") or {}
    privacy = status.get("privacyStatus")
    if privacy in ("public", "unlisted"):
        state = "published"
    elif privacy == "private" and status.get("publishAt"):
        state = "scheduled"
    else:
        state = "unpublished"
    return {
        "youtube_video_id": item["id"],
        "status": state,
        "title": (snippet.get("title") or "")[:300] or None,
        "description": snippet.get("description") or None,
        "tags": list(snippet.get("tags") or [])[:50],
        "duration_s": parse_iso_duration((item.get("contentDetails") or {}).get("duration")),
        "published_at": snippet.get("publishedAt") if state == "published" else None,
        "youtube_publish_at": status.get("publishAt"),
        "thumbnail_url": best_thumbnail(snippet),
        "views": int(stats.get("viewCount", 0) or 0),
        "likes": int(stats.get("likeCount", 0) or 0),
        "comments": int(stats.get("commentCount", 0) or 0),
    }


class ImportChannelStep(Step):
    type = "import_channel"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        cid = ctx.job.channel_id
        assert cid, "import_channel : channel_id requis"
        if ctx.settings.dry_run:
            return {"skipped": "dry_run"}
        channel = ctx.db.fetch_one("select id, lang from channels where id = %s", (cid,))
        assert channel, "chaîne introuvable"
        yt = YouTubeClient.for_channel(ctx.settings, ctx.db, cid)

        ctx.progress(5, "Liste des vidéos de la chaîne")
        snippet, ids, calls = yt.channel_uploads(int(ctx.job.payload.get("max", 500)))
        ctx.db.record_quota(cid, "playlistItems.list", calls)
        if snippet:
            ctx.db.execute(
                "update channels set youtube_title = %s, youtube_thumbnail_url = coalesce(%s, youtube_thumbnail_url) where id = %s",
                (snippet.get("title"), best_thumbnail(snippet), cid),
            )
        known = {
            r["youtube_video_id"]
            for r in ctx.db.fetch_all("select youtube_video_id from videos where youtube_video_id = any(%s)", (ids,))
        }
        todo = [i for i in ids if i not in known]
        imported = 0
        for start in range(0, len(todo), 50):
            ctx.progress(10 + int(80 * start / max(1, len(todo))), f"Import {imported}/{len(todo)}")
            items = yt.videos_details(todo[start : start + 50])
            ctx.db.record_quota(cid, "videos.list", 1)
            for item in items:
                v = imported_video(item)
                row = ctx.db.fetch_one(
                    """insert into videos (channel_id, lang, origin, status, title, description, tags, duration_s,
                                           youtube_video_id, published_at, youtube_publish_at, thumbnail_url)
                       values (%s, %s, 'imported', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       on conflict (youtube_video_id) do nothing returning id""",
                    (cid, channel["lang"], v["status"], v["title"], v["description"], v["tags"], v["duration_s"],
                     v["youtube_video_id"], v["published_at"], v["youtube_publish_at"], v["thumbnail_url"]),
                )
                if not row:
                    continue
                ctx.db.execute(
                    """insert into video_stats (video_id, views, likes, comments, fetched_at) values (%s, %s, %s, %s, now())
                       on conflict (video_id) do update set views = excluded.views, likes = excluded.likes,
                       comments = excluded.comments, fetched_at = now()""",
                    (row["id"], v["views"], v["likes"], v["comments"]),
                )
                imported += 1
        ctx.db.execute("update channels set history_imported_at = now() where id = %s", (cid,))
        if imported:  # métriques jour par jour des vidéos importées (et de la chaîne) sur 4 semaines
            ctx.enqueue("sync_metrics", channel_id=cid, priority=80, payload={"days": 28})
        return {"found": len(ids), "already_known": len(known), "imported": imported}
