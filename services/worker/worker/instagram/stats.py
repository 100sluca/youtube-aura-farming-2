"""Statistiques Instagram lues chez Zernio (docs/62-reseaux-et-comptes.md) : lecture des réponses, sans réseau ni base.

`GET /analytics?platform=instagram` renvoie une entrée par Reel du compte, avec ses chiffres lus chez Instagram : vues,
portée, j'aime, commentaires, partages, enregistrements, durée moyenne regardée (`igReelsAvgWatchTime`, en ms), temps
total regardé et part des spectateurs partis dans les 3 premières secondes (`reelsSkipRate`, 0 à 100, estimation de
Meta). Pas d'abonnés gagnés pour un Reel (`follows` nul), pas de part vue jusqu'au bout ni de provenance des vues.

Constaté le 04/10 : la liste peut rester vide alors que le compte a des Reels publiés par l'appli ; une lecture unitaire
(`GET /analytics?postId=<id Instagram>`) fait apparaître le Reel, avec ses chiffres, et la liste le donne ensuite. Le
step relit donc un par un les Reels que `GET /accounts/{id}/posts` (lecture en direct) montre et que la liste n'a pas.

Clé d'un Reel : son id Instagram (`platformPostId`), stable, le même quel que soit le compte Zernio qui le lit (les deux
comptes Zernio de l'appli peuvent voir le même compte Instagram).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..tiktok.stats import CAPTION_KEEP, _int, _num, _thumbnail, _when, caption_head, clean_url, norm_title

PUBLISHED = {"published", "partial"}
VIDEO_TYPES = {"video", "reel", "reels", "clips"}


@dataclass
class InstagramPost:
    """Un Reel sorti sur un compte Instagram et ses chiffres (colonnes de instagram_posts)."""

    key: str
    zernio_post_id: str | None = None
    is_external: bool = False
    url: str | None = None
    caption: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None
    duration_s: float | None = None
    views: int = 0
    reach: int | None = None
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int | None = None
    follows: int | None = None
    avg_watch_s: float | None = None
    total_watch_s: float | None = None
    skip_rate_pct: float | None = None
    sync_status: str | None = None
    metrics_at: datetime | None = None


def instagram_entry(item: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
    """Entrée Instagram de `platformAnalytics` (celle du compte Zernio voulu s'il est donné), sinon {}."""
    for p in item.get("platformAnalytics") or item.get("platforms") or []:
        if (
            isinstance(p, dict)
            and p.get("platform") == "instagram"
            and (not account_id or not p.get("accountId") or str(p.get("accountId")) == account_id)
        ):
            return p
    return {}


def shortcode_of(url: str | None) -> str | None:
    """Code d'un Reel d'après son lien (…/reel/Dd_3njFDkTk/ ou …/p/…) : le même pour toutes les formes du lien."""
    m = re.search(r"instagram\.com/(?:[\w.]+/)?(?:reels?|p|tv)/([\w-]+)", url or "")
    return m.group(1) if m else None


def parse_post(item: dict[str, Any], account_id: str | None = None) -> InstagramPost | None:
    """Une entrée de `GET /analytics` (liste ou lecture unitaire) → InstagramPost ; None pour une publication pas encore
    sortie, un échec, ou une entrée d'une autre plateforme."""
    entry = instagram_entry(item, account_id)
    if not entry and item.get("platform") not in (None, "instagram"):
        return None
    status = str(entry.get("status") or item.get("status") or "")
    if status not in PUBLISHED:
        return None
    ig_id = str(entry["platformPostId"]) if entry.get("platformPostId") else None
    key = ig_id or item.get("latePostId") or item.get("postId")
    if not key:
        return None
    a: dict[str, Any] = entry.get("analytics") or item.get("analytics") or {}
    watch_ms = _num(a.get("igReelsAvgWatchTime")) or 0
    total_ms = _num(a.get("igReelsVideoViewTotalTime")) or 0
    skip = _num(a.get("reelsSkipRate"))
    zernio_id = item.get("latePostId") or (None if item.get("isExternal") else item.get("postId"))
    url = entry.get("platformPostUrl") or item.get("platformPostUrl") or a.get("platformPostUrl") or None
    return InstagramPost(
        key=str(key),
        zernio_post_id=str(zernio_id) if zernio_id else None,
        # publiée à la main dans Instagram (pas de publication Zernio d'origine)
        is_external=bool(item.get("isExternal")) and not item.get("latePostId"),
        url=clean_url(url),
        caption=(str(item.get("content") or "")[:CAPTION_KEEP] or None),
        thumbnail_url=_thumbnail(item),
        published_at=_when(item.get("publishedAt") or entry.get("publishedAt")),
        duration_s=_num(a.get("videoDurationSeconds")) or None,
        views=_int(a.get("views")) or 0,
        reach=_int(a.get("reach")),
        likes=_int(a.get("likes")) or 0,
        comments=_int(a.get("comments")) or 0,
        shares=_int(a.get("shares")) or 0,
        saves=_int(a.get("saves")),
        follows=_int(a.get("follows")),  # nul pour un Reel : Meta ne le donne pas
        # 0 : pas encore connu (Instagram remplit ces chiffres après les premières vues)
        avg_watch_s=round(watch_ms / 1000, 2) if watch_ms > 0 else None,
        total_watch_s=round(total_ms / 1000, 2) if total_ms > 0 else None,
        skip_rate_pct=round(skip, 2) if skip is not None and (skip > 0 or watch_ms > 0) else None,
        sync_status=str(entry.get("syncStatus") or item.get("syncStatus") or "") or None,
        metrics_at=_when(a.get("lastUpdated")),
    )


def parse_live_post(item: dict[str, Any]) -> InstagramPost | None:
    """Entrée de `GET /accounts/{id}/posts` (lue en direct chez Instagram) → InstagramPost sans vues (`sync_status`
    « live ») ; None pour une photo ou un carrousel (on ne suit que les vidéos)."""
    pid = str(item.get("id") or "")
    if not pid or str(item.get("mediaType") or "video").lower() not in VIDEO_TYPES:
        return None
    picture = item.get("picture")
    return InstagramPost(
        key=pid,
        is_external=True,  # jusqu'à preuve du contraire (lien ou légende d'une vidéo de l'appli)
        url=clean_url(item.get("permalink")),
        caption=(str(item.get("message") or "")[:CAPTION_KEEP] or None),
        thumbnail_url=picture if isinstance(picture, str) and picture.startswith("http") else None,
        published_at=_when(item.get("createdTime")),
        likes=_int(item.get("likeCount")) or 0,
        comments=_int(item.get("commentCount")) or 0,
        sync_status="live",
    )


def merge_posts(posts: list[InstagramPost]) -> list[InstagramPost]:
    """Une ligne par Reel (même clé) : la plus avancée en vues, complétée par les autres."""
    out: dict[str, InstagramPost] = {}
    for p in posts:
        best = out.get(p.key)
        if best is None:
            out[p.key] = p
            continue
        keep, other = (
            (p, best) if (p.zernio_post_id is not None, p.views) > (best.zernio_post_id is not None, best.views) else (best, p)
        )
        for f in InstagramPost.__dataclass_fields__:
            if getattr(keep, f) in (None, "") and getattr(other, f) not in (None, ""):
                setattr(keep, f, getattr(other, f))
        out[p.key] = keep
    return list(out.values())


def missing_live(posts: list[InstagramPost], live: list[InstagramPost]) -> list[InstagramPost]:
    """Reels que Instagram montre déjà mais que la liste de Zernio n'a pas (même id ou même lien)."""
    known = {p.key for p in posts} | {c for p in posts if (c := shortcode_of(p.url))}
    return [lp for lp in live if lp.key not in known and shortcode_of(lp.url) not in known]


def refresh_live_counters(posts: list[InstagramPost], live: list[InstagramPost]) -> None:
    """J'aime et commentaires lus en direct, s'ils sont plus récents que ceux de Zernio ; lien et image s'ils manquent."""
    by_key = {lp.key: lp for lp in live} | {c: lp for lp in live if (c := shortcode_of(lp.url))}
    for p in posts:
        lp = by_key.get(p.key) or by_key.get(shortcode_of(p.url) or "")
        if lp:
            p.likes, p.comments = max(p.likes, lp.likes), max(p.comments, lp.comments)
            p.url = p.url or lp.url
            p.thumbnail_url = p.thumbnail_url or lp.thumbnail_url


def match_by_title(post: InstagramPost, videos: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Vidéo de l'appli publiée à la main dans Instagram : reconnue à la première ligne de sa légende, égale à son titre,
    et sortie après sa fabrication (même règle que TikTok). `videos` : titre normalisé → ligne."""
    if not post.is_external:
        return None
    v = videos.get(norm_title(caption_head(post.caption)))
    if not v or (post.published_at and v.get("created_at") and post.published_at < v["created_at"]):
        return None
    return v


def parse_insights(resp: dict[str, Any]) -> dict[str, int | None]:
    """Réponse de `GET /analytics/instagram/account-insights` → vues, portée, interactions, comptes engagés."""
    metrics = resp.get("metrics") or {}

    def total(name: str) -> int | None:
        m = metrics.get(name)
        return _int(m.get("total")) if isinstance(m, dict) else None

    return {
        "views_28d": total("views"),
        "reach_28d": total("reach"),
        "interactions_28d": total("total_interactions"),
        "engaged_28d": total("accounts_engaged"),
    }


def account_info(acc: dict[str, Any]) -> dict[str, Any]:
    """Entrée de `GET /accounts` → colonnes de instagram_accounts. `id` : l'id Instagram du compte (le même pour les deux
    comptes Zernio), `zernio_id` : celui du compte Zernio qui le lit."""
    meta = acc.get("metadata") or {}
    profile = meta.get("profileData") or {}
    extra = profile.get("extraData") or {}
    username = str(acc.get("username") or profile.get("username") or "")
    return {
        "id": str(acc.get("platformUserId") or profile.get("id") or acc.get("_id")),
        "zernio_id": str(acc.get("_id")),
        "username": username,
        "display_name": acc.get("displayName") or profile.get("displayName") or None,
        "avatar_url": acc.get("profilePicture") or profile.get("profilePicture") or None,
        "profile_url": acc.get("profileUrl")
        or profile.get("profileUrl")
        or (f"https://www.instagram.com/{username}" if username else None),
        "account_type": extra.get("accountType") or None,
        "followers": _int(acc.get("followersCount") if acc.get("followersCount") is not None else profile.get("followersCount")),
        "following": _int(extra.get("followsCount")),
        "media_count": _int(extra.get("mediaCount")),
        "active": acc.get("isActive") is not False and acc.get("needsReconnection") is not True,
    }
