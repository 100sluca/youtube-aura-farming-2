"""Appels YouTube. Une instance par chaîne (jetons distincts, quota distinct si projets GCP séparés)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date, datetime
from typing import Any
from uuid import UUID

from google.auth.transport.requests import AuthorizedSession, Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from ..config import Settings
from ..db import Db
from .auth import credentials_for

ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
CATEGORY_HOWTO = "26"


class AnalyticsBadRequest(RuntimeError):
    """Réponse 400 de l'Analytics API (combinaison métriques/dimensions refusée)."""


class YouTubeClient:
    def __init__(self, creds) -> None:  # noqa: ANN001
        creds.refresh(Request())
        self.creds = creds
        self.api = build("youtube", "v3", credentials=creds, cache_discovery=False)
        self.session = AuthorizedSession(creds)

    @classmethod
    def for_channel(cls, settings: Settings, db: Db, channel_id: UUID) -> YouTubeClient:
        return cls(credentials_for(settings, db, channel_id))

    # ---- Data API -------------------------------------------------------------
    def upload(
        self,
        *,
        path: str,
        title: str,
        description: str,
        tags: list[str],
        publish_at: datetime,
        lang: str,
        on_progress: Callable[[float], None],
        synthetic: bool = True,
    ) -> str:
        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags[:30],
                "categoryId": CATEGORY_HOWTO,
                "defaultLanguage": lang,
                "defaultAudioLanguage": lang,
            },
            "status": {
                "privacyStatus": "private",
                "publishAt": publish_at.astimezone().isoformat(),
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": synthetic,
            },
        }
        media = MediaFileUpload(path, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
        req = self.api.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = None
        while resp is None:
            status, resp = req.next_chunk()
            if status:
                on_progress(status.progress())
        return resp["id"]

    def videos_list(self, ids: list[str]) -> list[dict[str, Any]]:
        r = self.api.videos().list(part="statistics,status,snippet", id=",".join(ids)).execute()
        return r.get("items", [])

    def videos_details(self, ids: list[str]) -> list[dict[str, Any]]:
        """Titre, description, durée, statistiques et statut de ≤ 50 vidéos (1 unité)."""
        r = self.api.videos().list(part="snippet,contentDetails,statistics,status", id=",".join(ids[:50])).execute()
        return r.get("items", [])

    def channel_uploads(self, max_items: int = 500) -> tuple[dict[str, Any] | None, list[str], int]:
        """Identité de la chaîne (snippet) et identifiants de ses vidéos, les plus récentes d'abord (playlist
        « uploads »). Renvoie aussi le nombre d'appels, à compter dans le quota (1 unité chacun)."""
        r = self.api.channels().list(part="snippet,contentDetails", mine=True).execute()
        calls = 1
        items = r.get("items", [])
        if not items:
            return None, [], calls
        playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        ids: list[str] = []
        token: str | None = None
        while len(ids) < max_items:
            page = (
                self.api.playlistItems()
                .list(part="contentDetails", playlistId=playlist, maxResults=50, pageToken=token)
                .execute()
            )
            calls += 1
            ids.extend(it["contentDetails"]["videoId"] for it in page.get("items", []))
            token = page.get("nextPageToken")
            if not token:
                break
        return items[0].get("snippet", {}), ids[:max_items], calls

    def channel_statistics(self) -> dict[str, int | None] | None:
        """Compteurs publics de la chaîne (1 unité) : abonnés (None s'ils sont masqués), vues, vidéos publiques."""
        r = self.api.channels().list(part="statistics", mine=True).execute()
        items = r.get("items", [])
        if not items:
            return None
        st = items[0]["statistics"]
        return {
            "subscribers": None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0)),
            "views": int(st.get("viewCount", 0)),
            "videos": int(st.get("videoCount", 0)),
        }

    def channel_subscribers(self) -> int | None:
        stats = self.channel_statistics()
        return stats["subscribers"] if stats else None

    def comment_threads(self, video_id: str, max_results: int = 20) -> Iterator[dict[str, Any]]:
        r = (
            self.api.commentThreads()
            .list(part="snippet", videoId=video_id, maxResults=max_results, order="relevance", textFormat="plainText")
            .execute()
        )
        yield from r.get("items", [])

    # ---- Analytics API --------------------------------------------------------
    VIDEO_METRICS = (
        "views,engagedViews,likes,dislikes,comments,shares,subscribersGained,subscribersLost,"
        "estimatedMinutesWatched,averageViewDuration,averageViewPercentage"
    )

    def analytics_video_metrics(self, start: date, video_ids: list[str], end: date | None = None) -> list[dict[str, Any]]:
        """Rapport « Top videos » sur un jour (ou de `start` à `end`) : une ligne par vidéo (≤ 200 id par appel)."""
        end = end or start
        filters = f"video=={','.join(video_ids[:200])}"
        try:
            return self.analytics(
                start, end, metrics=self.VIDEO_METRICS, dimensions="video", filters=filters, sort="-views", max_results=200
            )
        except AnalyticsBadRequest as exc:  # metrics récentes (engagedViews) parfois refusées : on les retire
            metrics = self.VIDEO_METRICS.replace("engagedViews,", "")
            if "engagedViews" not in str(exc):
                raise
            return self.analytics(start, end, metrics=metrics, dimensions="video", filters=filters, sort="-views", max_results=200)

    def analytics_retention(self, video_id: str, start: date, end: date) -> list[dict[str, Any]]:
        """Courbe de rétention d'une vidéo : 100 points (avancement 0,01 → 1), part de l'audience encore là."""
        return self.analytics(
            start,
            end,
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id}",
            metrics="audienceWatchRatio,relativeRetentionPerformance",
        )

    def analytics(
        self,
        start: date,
        end: date,
        *,
        metrics: str,
        dimensions: str,
        filters: str | None = None,
        sort: str | None = None,
        max_results: int = 10000,
    ) -> list[dict[str, Any]]:
        params = {
            "ids": "channel==MINE",
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "metrics": metrics,
            "dimensions": dimensions,
            "maxResults": max_results,
        }
        if filters:
            params["filters"] = filters
        if sort:
            params["sort"] = sort
        r = self.session.get(ANALYTICS, params=params, timeout=60)
        if r.status_code == 400:
            raise AnalyticsBadRequest(r.text)
        r.raise_for_status()
        data = r.json()
        cols = [c["name"] for c in data.get("columnHeaders", [])]
        return [dict(zip(cols, row, strict=True)) for row in data.get("rows", [])]
