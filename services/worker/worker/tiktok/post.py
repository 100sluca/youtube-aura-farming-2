"""Légende et corps d'une publication TikTok, lecture des réponses de Zernio. Rien ici ne touche au réseau."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .config import TikTokConfig

CAPTION_MAX = 2200  # légende d'une vidéo TikTok
NOW_MARGIN = timedelta(minutes=2)  # créneau passé ou tout proche : publication immédiate
# états Zernio d'une publication (et de son entrée TikTok) qui ne sont pas terminés
WAITING = {"scheduled", "pending", "publishing", "processing", "uploading"}
_SHORTS_TAG = re.compile(r"(?<!\w)#shorts?\b", re.IGNORECASE)
_KEY_NS = uuid.UUID("0f6f1d4e-7a52-4c1e-9d0a-5a1f0c7b7e21")


def build_caption(title: str | None, description: str | None) -> str:
    """Titre puis description de la vidéo YouTube (question, hashtags, sources et licence Wikipédia comprises) ;
    sans #shorts, propre à YouTube. Coupée à 2 200 caractères."""
    head = (title or "").strip()
    body = _SHORTS_TAG.sub("", description or "")
    body = re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", body)).strip()
    if head and body.startswith(head):
        head = ""
    caption = f"{head}\n\n{body}".strip() if body else head
    if len(caption) > CAPTION_MAX:
        caption = caption[: CAPTION_MAX - 1].rstrip() + "…"
    return caption


def publish_time(scheduled_at: datetime | None, now: datetime, force_now: bool = False) -> datetime | None:
    """Heure à laquelle programmer la publication : le créneau YouTube, ou None pour publier tout de suite (créneau
    absent, passé ou dans moins de 2 min, ou publication demandée à la main « maintenant »)."""
    if force_now or scheduled_at is None or scheduled_at <= now + NOW_MARGIN:
        return None
    return scheduled_at


def idempotency_key(video_id: object, round_: int, generation: int = 0) -> str:
    """Même clé pour toutes les tentatives d'un même envoi (un job relancé ne publie pas deux fois) ; une nouvelle
    demande après un échec (`round_` suivant) en prend une autre, de même une vidéo retouchée après son envoi
    (`generation` = nombre d'envois remplacés, videos.previous_uploads, docs/44)."""
    return str(uuid.uuid5(_KEY_NS, f"{video_id}:{round_}" if not generation else f"{video_id}:{generation}:{round_}"))


def post_body(
    *, caption: str, media_url: str, account_id: str, cfg: TikTokConfig, when: datetime | None, draft: bool = False
) -> dict[str, Any]:
    settings: dict[str, Any] = {
        # explicite : le 29/09, une publication programmée sans ce champ s'est retrouvée en « photo » chez Zernio
        # douze minutes après sa création, avec risque de refus à l'heure prévue (corrigée par PUT /posts/{id})
        "media_type": "video",
        # compte connecté par l'appli TikTok for Business : une vidéo publiée directement est toujours publique
        "privacy_level": "PUBLIC_TO_EVERYONE",
        "allow_comment": cfg.allow_comment,
        "allow_duet": cfg.allow_duet,
        "allow_stitch": cfg.allow_stitch,
        # exigés par TikTok : Luca a choisi ces réglages et relu la vidéo avant de l'autoriser (Création)
        "content_preview_confirmed": True,
        "express_consent_given": True,
    }
    if cfg.ai_label:
        settings["video_made_with_ai"] = True
    if draft:
        settings["draft"] = True  # boîte de réception TikTok : Luca termine la publication dans l'appli
    body: dict[str, Any] = {
        "content": caption,
        "mediaItems": [{"type": "video", "url": media_url}],
        "platforms": [{"platform": "tiktok", "accountId": account_id}],
        "tiktokSettings": settings,
    }
    if when is None:
        body["publishNow"] = True
    else:
        body["scheduledFor"] = when.isoformat()  # avec son décalage horaire : pris tel quel par Zernio
    return body


@dataclass
class Outcome:
    """Ce que dit Zernio d'une publication TikTok."""

    status: str  # scheduled | published | failed | pending, publishing… (WAITING)
    post_id: str | None = None
    url: str | None = None
    error: str | None = None
    draft: bool = False


def tiktok_entry(post: dict[str, Any], platform: str = "tiktok") -> dict[str, Any]:
    for p in post.get("platforms") or []:
        if isinstance(p, dict) and p.get("platform") == platform:
            return p
    return {}


def read_post(post: dict[str, Any], platform: str = "tiktok") -> Outcome:
    """État d'une publication d'après son entrée TikTok (celle de la publication entière à défaut) ; `platform` :
    l'entrée Instagram pour un Reel (docs/48)."""
    entry = tiktok_entry(post, platform)
    status = str(entry.get("status") or post.get("status") or "pending")
    if post.get("status") == "scheduled" and status == "pending":
        status = "scheduled"
    specific = entry.get("platformSpecificData") or {}
    return Outcome(
        status=status,
        post_id=post.get("_id") or post.get("id"),
        url=entry.get("platformPostUrl") or None,
        error=entry.get("errorMessage") or (post.get("error") if status == "failed" else None),
        # brouillon : isDraft d'après la doc, ou les réglages renvoyés tels quels (constaté le 29/09)
        draft=bool(specific.get("isDraft") or (specific.get("tiktokSettings") or {}).get("draft")),
    )


def read_create(code: int, body: dict[str, Any], platform: str = "tiktok") -> Outcome:
    """Réponse de `POST /posts` : 201/200 créée (ou déjà créée par un envoi identique), 207 échec chez TikTok, 409
    même contenu déjà publié sur ce compte dans les 24 h (on suit la publication d'origine)."""
    if code == 409:
        existing = body.get("existingPostId") or (body.get("post") or {}).get("_id")
        if existing:
            return Outcome(status="pending", post_id=str(existing))
        return Outcome(status="failed", error=str(body.get("error") or "doublon refusé par Zernio"))
    if code == 202 and body.get("postId"):
        return Outcome(status="pending", post_id=str(body["postId"]))
    out = read_post(body.get("post") or {}, platform)
    if code == 207 and out.status != "failed":
        out.status = "failed"
    if out.status == "failed" and not out.error:
        out.error = str(body.get("error") or body.get("message") or "publication refusée")
    return out
