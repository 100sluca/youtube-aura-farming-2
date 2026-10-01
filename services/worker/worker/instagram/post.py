"""Légende et corps d'un Reel Instagram (docs/48). Rien ici ne touche au réseau ; la lecture des réponses de Zernio est
celle de TikTok (tiktok/post.py, `platform="instagram"`).

Corps envoyé à `POST /posts` (https://docs.zernio.com/platforms/instagram) : une seule vidéo verticale = un Reel ;
les réglages propres à Instagram vont dans `platforms[].platformSpecificData`. Limites : 90 s, 300 Mo, légende de
2 200 caractères, 100 publications par 24 h et par compte. Pas de brouillon possible par l'API.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from ..tiktok.post import build_caption as _tiktok_caption
from .config import InstagramConfig

REEL_MAX_S = 90.0
HASHTAGS_MAX = 5  # Instagram n'en accepte plus que 5 par publication (fin 2025) : les suivants sont retirés
_HASHTAG = re.compile(r"(?<![\w&])#\w+")


def build_caption(title: str | None, description: str | None) -> str:
    """Même légende que sur TikTok (titre, description YouTube sans #shorts), avec 5 hashtags au plus."""
    caption = _tiktok_caption(title, description)
    seen = 0

    def keep(m: re.Match[str]) -> str:
        nonlocal seen
        seen += 1
        return m.group(0) if seen <= HASHTAGS_MAX else ""

    caption = _HASHTAG.sub(keep, caption)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"[ \t]+\n", "\n", caption)).strip()


def post_body(*, caption: str, media_url: str, account_id: str, cfg: InstagramConfig, when: datetime | None) -> dict[str, Any]:
    specific: dict[str, Any] = {"shareToFeed": cfg.share_to_feed}
    if cfg.ai_label:
        specific["isAiGenerated"] = True
    body: dict[str, Any] = {
        "content": caption,
        "mediaItems": [{"type": "video", "url": media_url}],
        "platforms": [{"platform": "instagram", "accountId": account_id, "platformSpecificData": specific}],
    }
    if when is None:
        body["publishNow"] = True
    else:
        body["scheduledFor"] = when.isoformat()  # avec son décalage horaire, comme pour TikTok
    return body
