"""Jetons OAuth : refresh token chiffré (AES-GCM) dans channel_credentials, déchiffré localement."""

from __future__ import annotations

import base64
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from google.oauth2.credentials import Credentials

from ..config import Settings
from ..db import Db

TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def decrypt(settings: Settings, payload: str) -> str:
    """payload = base64(nonce[12] + ciphertext) — même format que le dashboard (Web Crypto AES-GCM)."""
    assert settings.credentials_key, "CREDENTIALS_KEY manquante"
    raw = base64.b64decode(payload)
    key = base64.b64decode(settings.credentials_key)
    return AESGCM(key).decrypt(raw[:12], raw[12:], None).decode()


def credentials_for(settings: Settings, db: Db, channel_id: UUID) -> Credentials:
    row = db.fetch_one("select refresh_token_encrypted from channel_credentials where channel_id = %s", (channel_id,))
    assert row, "chaîne non connectée (Réglages → Connecter YouTube)"
    return Credentials(
        token=None,
        refresh_token=decrypt(settings, row["refresh_token_encrypted"]),
        token_uri=TOKEN_URI,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )
