"""Carrousel photo TikTok de citations (docs/58 §5) : les affiches de plusieurs citations (fond + texte, 1080 × 1920,
worker/quotes.py) publiées en une seule publication « Photo », avec une musique choisie par TikTok (auto_add_music),
comme les comptes de citations étudiés le 02/10 (5 citations, « Andante in C Minor », 296 k j'aime).

Corps envoyé à `POST /posts` (https://docs.zernio.com/platforms/tiktok, « photo carousel ») : `mediaItems` = images
(JPEG, 35 au plus, 20 Mo chacune), `tiktokSettings.media_type = "photo"`, `photo_cover_index` (la première),
`description` (légende longue, 4 000 caractères) ; `content` sert de titre (90 caractères, sans hashtag).
`auto_add_music` ne vaut que pour une publication directe : dans un brouillon, Luca choisit le son dans l'appli.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .config import TikTokConfig

IMAGES_MAX = 35
TITLE_MAX = 90
DESCRIPTION_MAX = 4000
_HASHTAG = re.compile(r"(?<![\w&])#\w+")


def carousel_title(texts: list[str]) -> str:
    """Titre de la publication : la première citation, coupée à un mot, sans hashtag."""
    first = _HASHTAG.sub("", (texts[0] if texts else "").split("\n")[0]).strip()
    if len(first) <= TITLE_MAX:
        return first
    return first[: TITLE_MAX - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def carousel_caption(texts: list[str], hashtags: list[str]) -> str:
    """Légende : une invitation à choisir sa citation préférée, puis 3 à 5 hashtags."""
    tags = " ".join(dict.fromkeys(t if t.startswith("#") else f"#{t}" for t in hashtags if t))[:300]
    head = f"Laquelle te parle le plus ? 1 à {len(texts)} 👇" if len(texts) > 1 else "Enregistre-la pour plus tard."
    return f"{head}\n\n{tags}".strip()[:DESCRIPTION_MAX]


def carousel_body(
    *,
    title: str,
    caption: str,
    image_urls: list[str],
    account_id: str,
    cfg: TikTokConfig,
    when: datetime | None,
    draft: bool = False,
) -> dict[str, Any]:
    if not image_urls:
        raise ValueError("carrousel vide")
    settings: dict[str, Any] = {
        "media_type": "photo",
        "privacy_level": "PUBLIC_TO_EVERYONE",
        "allow_comment": cfg.allow_comment,
        "photo_cover_index": 0,
        "description": caption,
        "content_preview_confirmed": True,
        "express_consent_given": True,
    }
    if draft:
        settings["draft"] = True
    else:
        settings["auto_add_music"] = True  # musique recommandée par TikTok, sous licence (docs/58 §4)
    if cfg.ai_label:
        settings["video_made_with_ai"] = True
    body: dict[str, Any] = {
        "content": title[:TITLE_MAX],
        "mediaItems": [{"type": "image", "url": u} for u in image_urls[:IMAGES_MAX]],
        "platforms": [{"platform": "tiktok", "accountId": account_id}],
        "tiktokSettings": settings,
    }
    if when is None:
        body["publishNow"] = True
    else:
        body["scheduledFor"] = when.isoformat()
    return body
