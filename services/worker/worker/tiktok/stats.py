"""Statistiques TikTok lues chez Zernio (docs/39-tiktok-partout.md) : lecture des réponses, sans réseau ni base.

`GET /analytics?platform=tiktok` renvoie une entrée par vidéo sortie sur le compte : celles publiées par l'appli (id
Zernio de la publication = videos.tiktok->>'post_id') et celles publiées à la main dans TikTok (`isExternal`). Vues,
j'aime, commentaires et partages arrivent vite ; les chiffres de TikTok for Business (temps regardé, part vue jusqu'au
bout, abonnés gagnés, provenance des vues, enregistrements, portée) 24 à 48 h après la sortie, et seulement pour les
vidéos actives dans les 7 derniers jours. Avant, Zernio renvoie des zéros : on les garde comme « pas encore connu ».

Constaté le 29/09 : une publication de l'appli a pour `postId` l'id Zernio et pas de `latePostId` ; sa copie
synchronisée depuis TikTok (s'il y en a une) porte cet id dans `latePostId`. D'où la clé `latePostId` ou `postId`,
stable d'un relevé à l'autre. L'id TikTok de la vidéo (`platformPostId`) peut changer tant que TikTok traite la vidéo
(« v_pub_url~… », « v_inbox_url~… » pour un brouillon) : il n'est gardé qu'à titre d'information.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any

PUBLISHED = {"published", "partial"}
VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v")
CAPTION_KEEP = 2200


def _int(x: Any) -> int | None:
    try:
        return None if x is None or x == "" else int(round(float(x)))
    except (TypeError, ValueError):
        return None


def _num(x: Any) -> float | None:
    try:
        return None if x is None or x == "" else float(x)
    except (TypeError, ValueError):
        return None


def _when(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _shares(raw: Any) -> dict[str, float] | None:
    """Parts (0 à 1) par provenance, type de spectateur ou pays ; None si TikTok n'a encore rien dit."""
    if not isinstance(raw, dict):
        return None
    out = {str(k): round(float(v), 4) for k, v in raw.items() if _num(v) is not None}
    return out or None


def real_tiktok_id(value: str | None) -> bool:
    """Vrai id de vidéo TikTok (chiffres), pas un id d'envoi provisoire (« v_pub_url~… ») ou de brouillon."""
    return bool(value) and not str(value).startswith("v_")


@dataclass
class TikTokPost:
    """Une vidéo sortie sur un compte TikTok et ses chiffres (colonnes de tiktok_posts)."""

    key: str
    tiktok_id: str | None = None
    zernio_post_id: str | None = None
    is_external: bool = False
    url: str | None = None
    caption: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int | None = None
    reach: int | None = None
    follows: int | None = None
    profile_views: int | None = None
    avg_watch_s: float | None = None
    total_watch_s: float | None = None
    completion_pct: float | None = None
    impression_sources: dict[str, float] | None = None
    audience_types: dict[str, float] | None = None
    audience_countries: dict[str, float] | None = None
    sync_status: str | None = None
    metrics_at: datetime | None = None


def tiktok_entry(item: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
    """Entrée TikTok de `platformAnalytics` (celle du compte voulu s'il est donné), sinon {}."""
    for p in item.get("platformAnalytics") or []:
        if (
            isinstance(p, dict)
            and p.get("platform") == "tiktok"
            and (not account_id or not p.get("accountId") or str(p.get("accountId")) == account_id)
        ):
            return p
    return {}


def _thumbnail(item: dict[str, Any]) -> str | None:
    """Image de couverture ; Zernio renvoie parfois l'adresse du MP4 envoyé à la place (constaté le 29/09)."""
    candidates = [item.get("thumbnailUrl"), *((m or {}).get("thumbnail") for m in item.get("mediaItems") or [])]
    for c in candidates:
        if isinstance(c, str) and c.startswith("http") and not c.split("?")[0].lower().endswith(VIDEO_EXT):
            return c
    return None


def parse_post(item: dict[str, Any], account_id: str | None = None) -> TikTokPost | None:
    """Une entrée de `GET /analytics` → TikTokPost ; None pour une publication pas encore sortie, un échec ou un
    brouillon envoyé dans la boîte de réception TikTok (rien de public à mesurer)."""
    entry = tiktok_entry(item, account_id)
    if item.get("platform") not in (None, "tiktok") and not entry:
        return None
    status = str(entry.get("status") or item.get("status") or "")
    tiktok_id = str(entry["platformPostId"]) if entry.get("platformPostId") else None
    if status not in PUBLISHED or (tiktok_id or "").startswith("v_inbox"):
        return None
    key = item.get("latePostId") or item.get("postId") or tiktok_id
    if not key:
        return None
    a: dict[str, Any] = entry.get("analytics") or item.get("analytics") or {}

    watch_ms = _num(a.get("igReelsAvgWatchTime"))
    total_ms = _num(a.get("igReelsVideoViewTotalTime"))
    completion = _num(a.get("completionRate"))
    profile_views = _int(a.get("profileViews"))
    sources = _shares(a.get("impressionSources"))
    types_ = _shares(a.get("audienceTypes"))
    countries = _shares(a.get("audienceCountries"))
    # Chiffres TikTok for Business : tous à zéro tant que TikTok ne les a pas remplis (24 à 48 h) → inconnus
    business = bool(
        sources
        or types_
        or countries
        or (watch_ms or 0) > 0
        or (total_ms or 0) > 0
        or (completion or 0) > 0
        or (profile_views or 0) > 0
    )
    saves, reach = _int(a.get("saves")), _int(a.get("reach"))
    zernio_id = item.get("latePostId") or (None if item.get("isExternal") else item.get("postId"))

    return TikTokPost(
        key=str(key),
        tiktok_id=tiktok_id,
        zernio_post_id=str(zernio_id) if zernio_id else None,
        # publiée à la main dans TikTok (sa copie synchronisée n'a pas de publication Zernio d'origine)
        is_external=bool(item.get("isExternal")) and not item.get("latePostId"),
        url=clean_url(entry.get("platformPostUrl") or item.get("platformPostUrl") or a.get("platformPostUrl") or None),
        caption=(str(item.get("content") or "")[:CAPTION_KEEP] or None),
        thumbnail_url=_thumbnail(item),
        published_at=_when(item.get("publishedAt") or entry.get("publishedAt")),
        views=_int(a.get("views")) or 0,
        likes=_int(a.get("likes")) or 0,
        comments=_int(a.get("comments")) or 0,
        shares=_int(a.get("shares")) or 0,
        saves=saves if business or (saves or 0) > 0 else None,
        reach=reach if business or (reach or 0) > 0 else None,
        follows=_int(a.get("follows")) if business else None,
        profile_views=profile_views if business else None,
        avg_watch_s=round(watch_ms / 1000, 2) if business and watch_ms is not None else None,
        total_watch_s=round(total_ms / 1000, 2) if business and total_ms is not None else None,
        completion_pct=round(completion * 100, 2) if business and completion is not None else None,
        impression_sources=sources,
        audience_types=types_,
        audience_countries=countries,
        sync_status=str(entry.get("syncStatus") or item.get("syncStatus") or "") or None,
        metrics_at=_when(a.get("lastUpdated")),
    )


def clean_url(url: str | None) -> str | None:
    """Lien d'une vidéo TikTok sans ses paramètres de suivi (?utm_campaign=…)."""
    return url.split("?")[0] if url else None


def tiktok_id_of(url: str | None) -> str | None:
    """Id TikTok d'une vidéo d'après son lien (…/video/7690741999670021398)."""
    m = re.search(r"/video/(\d+)", url or "")
    return m.group(1) if m else None


def parse_live_post(item: dict[str, Any]) -> TikTokPost | None:
    """Entrée de `GET /accounts/{id}/posts` (lue en direct chez TikTok) → TikTokPost sans vues : j'aime, commentaires et
    partages sont à jour, les vues arrivent au passage suivant de Zernio (`sync_status` « live »)."""
    tid = str(item.get("id") or "")
    if not real_tiktok_id(tid):
        return None
    picture = item.get("picture")
    return TikTokPost(
        key=tid,
        tiktok_id=tid,
        is_external=True,  # jusqu'à preuve du contraire (lien ou légende d'une vidéo de l'appli)
        url=clean_url(item.get("permalink")),
        caption=(str(item.get("message") or "")[:CAPTION_KEEP] or None),
        thumbnail_url=picture if isinstance(picture, str) and not picture.split("?")[0].lower().endswith(VIDEO_EXT) else None,
        published_at=_when(item.get("createdTime")),
        likes=_int(item.get("likeCount")) or 0,
        comments=_int(item.get("commentCount")) or 0,
        shares=_int(item.get("shareCount")) or 0,
        sync_status="live",
    )


def add_live_posts(posts: list[TikTokPost], live: list[TikTokPost]) -> list[TikTokPost]:
    """Ajoute les vidéos que TikTok montre déjà mais que les statistiques de Zernio n'ont pas encore (même vrai id TikTok
    ou même lien) ; pour les autres, les j'aime, commentaires et partages lus en direct, s'ils sont plus récents."""
    known = {p.tiktok_id: p for p in posts if real_tiktok_id(p.tiktok_id)}
    known |= {tid: p for p in posts if (tid := tiktok_id_of(p.url))}
    out = list(posts)
    for lp in live:
        p = known.get(lp.tiktok_id or "")
        if p is None:
            out.append(lp)
            continue
        p.likes, p.comments, p.shares = max(p.likes, lp.likes), max(p.comments, lp.comments), max(p.shares, lp.shares)
        p.url = p.url or lp.url
        p.thumbnail_url = p.thumbnail_url or lp.thumbnail_url
    return out


def merge_posts(posts: list[TikTokPost]) -> list[TikTokPost]:
    """Une ligne par vidéo : une publication de l'appli et sa copie synchronisée depuis TikTok (même clé, ou même vrai id
    TikTok) ne font qu'une. On garde la publication de l'appli et les chiffres les plus avancés."""
    groups: dict[str, list[TikTokPost]] = {}
    alias: dict[str, str] = {}  # vrai id TikTok → clé du groupe
    for p in posts:
        group = p.key
        if p.key not in groups and real_tiktok_id(p.tiktok_id):
            group = alias.get(str(p.tiktok_id), p.key)
        groups.setdefault(group, []).append(p)
        if real_tiktok_id(p.tiktok_id):
            alias.setdefault(str(p.tiktok_id), group)
    out: list[TikTokPost] = []
    for group in groups.values():
        best = max(group, key=lambda p: (p.zernio_post_id is not None, not p.is_external, p.views))
        for other in group:
            if other is best:
                continue
            for f in fields(TikTokPost):
                mine, theirs = getattr(best, f.name), getattr(other, f.name)
                if f.name in ("views", "likes", "comments", "shares"):
                    setattr(best, f.name, max(mine, theirs))
                elif mine in (None, "", {}) and theirs not in (None, "", {}):
                    setattr(best, f.name, theirs)
        out.append(best)
    return out


def norm_title(text: str | None) -> str:
    """Titre comparable : casse, espaces et ponctuation finale ignorés."""
    return re.sub(r"\s+", " ", text or "").strip().rstrip(".!?…").strip().casefold()


def caption_head(caption: str | None) -> str:
    """Première ligne non vide d'une légende : le titre de la vidéo dans celles que l'appli écrit (post.build_caption)."""
    return next((line for line in (caption or "").splitlines() if line.strip()), "")


def match_by_title(post: TikTokPost, videos: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Vidéo de l'appli publiée à la main dans TikTok (brouillon terminé dans l'appli, envoi fait à la main) : reconnue à la
    première ligne de sa légende, égale à son titre, et sortie après sa fabrication. `videos` : titre normalisé → ligne."""
    if not post.is_external:
        return None
    v = videos.get(norm_title(caption_head(post.caption)))
    if not v or (post.published_at and v.get("created_at") and post.published_at < v["created_at"]):
        return None
    return v


def parse_insights(resp: dict[str, Any]) -> dict[str, int | None]:
    """Réponse de `GET /analytics/tiktok/account-insights` → abonnés, abonnements, j'aime reçus, vidéos."""
    metrics = resp.get("metrics") or {}

    def total(name: str) -> int | None:
        m = metrics.get(name)
        return _int(m.get("total")) if isinstance(m, dict) else None

    return {
        "followers": total("follower_count"),
        "following": total("following_count"),
        "likes": total("likes_count"),
        "videos": total("video_count"),
    }


def account_info(acc: dict[str, Any]) -> dict[str, Any]:
    """Entrée de `GET /accounts` → colonnes de tiktok_accounts ; les compteurs relevés à la connexion servent de repli
    si les statistiques du compte ne répondent pas."""
    meta = acc.get("metadata") or {}
    extra = (meta.get("profileData") or {}).get("extraData") or {}
    return {
        "id": str(acc.get("_id")),
        "username": str(acc.get("username") or ""),
        "display_name": acc.get("displayName") or None,
        "avatar_url": acc.get("profilePicture") or None,
        "profile_url": acc.get("profileUrl") or (f"https://www.tiktok.com/@{acc['username']}" if acc.get("username") else None),
        "business": meta.get("apiFlavor") == "business" if meta.get("apiFlavor") else None,
        "fallback": {
            "followers": _int(acc.get("followersCount")),
            "following": _int(extra.get("followingCount")),
            "likes": _int(extra.get("likesCount")),
            "videos": _int(extra.get("videoCount")),
        },
    }
