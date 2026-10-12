"""Données publiques des Shorts des autres chaînes (page Recherche, docs/60-recherche-niches.md).

Avec le jeton OAuth d'une de nos chaînes (aucune clé à ajouter) :
- `search_shorts` : `search.list`, compteur à part de 100 appels par jour (1 unité), 50 vidéos au plus par appel ;
- `video_details` : `videos.list` par 50 (1 unité), avec `player` pour la taille du lecteur (un Short est vertical) ;
- `channel_details` : `channels.list` par 50 (1 unité) : abonnés, date de création ;
- `channel_shorts` : la playlist « UUSH » d'une chaîne, qui ne contient que ses Shorts (astuce connue, non documentée),
  puis leurs vues : la médiane de la chaîne, pour savoir de combien une vidéo la dépasse.
Chaque appel est inscrit dans api_quota_usage (chaîne vide : ce n'est pas une de nos chaînes qui le consomme).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from googleapiclient.errors import HttpError

from ..db import Db
from .client import YouTubeClient

SEARCH_ENDPOINT = "search.list"


def searches_today(db: Db) -> int:
    """Recherches déjà faites aujourd'hui (jour UTC, comme la jauge des Réglages)."""
    row = db.fetch_one(
        "select coalesce(sum(units), 0) as n from api_quota_usage where endpoint = %s and day = current_date", (SEARCH_ENDPOINT,)
    )
    return int(row["n"]) if row else 0


def search_shorts(
    yt: YouTubeClient,
    db: Db,
    q: str,
    *,
    after: datetime,
    before: datetime | None = None,
    lang: str | None,
    region: str | None,
    n: int = 50,
) -> list[str]:
    """Identifiants des vidéos de moins de 4 min publiées entre `after` et `before`, les plus vues d'abord."""
    params: dict[str, Any] = {
        "part": "id",
        "q": q,
        "type": "video",
        "videoDuration": "short",
        "order": "viewCount",
        "publishedAfter": after.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "maxResults": max(1, min(n, 50)),
    }
    if before:
        params["publishedBefore"] = before.strftime("%Y-%m-%dT%H:%M:%SZ")
    if lang:
        params["relevanceLanguage"] = lang
    if region:
        params["regionCode"] = region
    res = yt.api.search().list(**params).execute()
    db.record_quota(None, SEARCH_ENDPOINT, 1)
    return [it["id"]["videoId"] for it in res.get("items", []) if it.get("id", {}).get("videoId")]


def video_details(yt: YouTubeClient, db: Db, ids: list[str]) -> list[dict[str, Any]]:
    """Fiche, chiffres, durée et taille du lecteur, par lots de 50."""
    out: list[dict[str, Any]] = []
    for i in range(0, len(ids), 50):
        chunk = ids[i : i + 50]
        res = yt.api.videos().list(part="snippet,statistics,contentDetails,player", id=",".join(chunk), maxHeight=1280).execute()
        db.record_quota(None, "videos.list", 1)
        out.extend(res.get("items", []))
    return out


def channel_details(yt: YouTubeClient, db: Db, ids: list[str]) -> dict[str, dict[str, Any]]:
    """{identifiant de chaîne : {"title", "subs", "created_at", "videos"}} par lots de 50."""
    out: dict[str, dict[str, Any]] = {}
    uniq = list(dict.fromkeys(i for i in ids if i))
    for i in range(0, len(uniq), 50):
        res = yt.api.channels().list(part="snippet,statistics", id=",".join(uniq[i : i + 50])).execute()
        db.record_quota(None, "channels.list", 1)
        for it in res.get("items", []):
            st = it.get("statistics", {})
            out[it["id"]] = {
                "title": it.get("snippet", {}).get("title"),
                "created_at": it.get("snippet", {}).get("publishedAt"),
                "subs": None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0)),
                "videos": int(st.get("videoCount", 0)),
            }
    return out


def channel_shorts(yt: YouTubeClient, db: Db, channel_id: str, n: int = 30) -> list[tuple[str, int]]:
    """(mise en ligne ISO, vues) des `n` derniers Shorts de la chaîne ; vide si la playlist n'existe pas (2 unités)."""
    if not channel_id.startswith("UC"):
        return []
    try:
        page = (
            yt.api.playlistItems()
            .list(part="contentDetails", playlistId="UUSH" + channel_id[2:], maxResults=min(n, 50))
            .execute()
        )
    except HttpError:  # chaîne sans Shorts, playlist introuvable
        db.record_quota(None, "playlistItems.list", 1)
        return []
    db.record_quota(None, "playlistItems.list", 1)
    ids = [it["contentDetails"]["videoId"] for it in page.get("items", [])]
    if not ids:
        return []
    res = yt.api.videos().list(part="statistics,snippet", id=",".join(ids)).execute()
    db.record_quota(None, "videos.list", 1)
    return [
        (it["snippet"]["publishedAt"], int(it.get("statistics", {}).get("viewCount", 0)))
        for it in res.get("items", [])
        if it.get("statistics", {}).get("viewCount") is not None
    ]
