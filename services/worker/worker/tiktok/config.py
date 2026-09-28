"""Réglages TikTok (Réglages → TikTok du dashboard) et clé Zernio.

app_settings « tiktok » :
    {"channels": {"<id de la chaîne YouTube>": {"account_id": "…", "username": "…", "enabled": true,
                                                 "enabled_at": "2026-09-29T01:40:00+02:00"}},
     "allow_comment": true, "allow_duet": true, "allow_stitch": true, "ai_label": false}

Une chaîne YouTube publie sur un compte TikTok connecté à Zernio. `enabled` : chaque Short programmé sur YouTube part
aussi sur TikTok, à la même heure ; seuls les Shorts dont le créneau suit `enabled_at` partent tout seuls (rien n'est
republié en rafale à l'activation), les autres se publient à la main depuis la Bibliothèque. `ai_label` : étiquette
« contenu généré par IA » de TikTok, coupée par défaut (choix de Luca le 29/09). La visibilité n'est pas réglable : un
compte connecté par l'appli TikTok for Business ne publie une vidéo qu'en public.

Clé API : app_secrets « zernio_api_key », chiffrée avec CREDENTIALS_KEY comme les clés des LLM (settings_store.py),
écrite par le dashboard ou `yt2 tiktok key` ; ZERNIO_API_KEY du .env sert de repli. Jamais dans le dépôt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from ..config import Settings
from ..youtube.auth import decrypt, encrypt

SECRET_NAME = "zernio_api_key"


@dataclass(frozen=True)
class ChannelTikTok:
    account_id: str
    username: str = ""
    enabled: bool = False
    enabled_at: datetime | None = None


@dataclass
class TikTokConfig:
    channels: dict[str, ChannelTikTok] = field(default_factory=dict)
    allow_comment: bool = True
    allow_duet: bool = True
    allow_stitch: bool = True
    ai_label: bool = False

    def for_channel(self, channel_id: object) -> ChannelTikTok | None:
        ch = self.channels.get(str(channel_id))
        return ch if ch and ch.account_id else None


def _when(raw: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


def parse_config(value: dict[str, Any] | None) -> TikTokConfig:
    v = value or {}
    channels = {
        str(cid): ChannelTikTok(
            account_id=str(c.get("account_id") or ""),
            username=str(c.get("username") or ""),
            enabled=bool(c.get("enabled")),
            enabled_at=_when(c.get("enabled_at")),
        )
        for cid, c in (v.get("channels") or {}).items()
        if isinstance(c, dict)
    }
    flag = lambda k, d: bool(v[k]) if isinstance(v.get(k), bool) else d  # noqa: E731
    return TikTokConfig(channels=channels, allow_comment=flag("allow_comment", True), allow_duet=flag("allow_duet", True),
                        allow_stitch=flag("allow_stitch", True), ai_label=flag("ai_label", False))


def load_tiktok_config(db: Any | None) -> TikTokConfig:
    if db is None:
        return TikTokConfig()
    row = db.fetch_one("select value from app_settings where key = 'tiktok'")
    return parse_config(row["value"] if row else None)


def save_tiktok_config(db: Any, value: dict[str, Any]) -> None:
    db.execute(
        """insert into app_settings (key, value) values ('tiktok', %s)
           on conflict (key) do update set value = excluded.value, updated_at = now()""",
        (Jsonb(value),),
    )


def zernio_key(settings: Settings, db: Any | None) -> str | None:
    """La clé Zernio : celle des Réglages (base, chiffrée), sinon ZERNIO_API_KEY du .env."""
    if db is not None and settings.credentials_key:
        row = db.fetch_one("select value_encrypted from app_secrets where name = %s", (SECRET_NAME,))
        if row:
            try:
                return decrypt(settings, row["value_encrypted"])
            except Exception:  # noqa: BLE001 — clé de chiffrement changée : on retombe sur le .env
                pass
    return settings.zernio_api_key or None


def save_zernio_key(settings: Settings, db: Any, value: str) -> str:
    """Enregistre la clé (chiffrée) et renvoie ses 4 derniers caractères, seuls affichés ensuite."""
    secret = value.strip()
    if len(secret) < 16:
        raise ValueError("clé Zernio trop courte")
    db.execute(
        """insert into app_secrets (name, value_encrypted, hint) values (%s, %s, %s)
           on conflict (name) do update set value_encrypted = excluded.value_encrypted, hint = excluded.hint,
                                            updated_at = now()""",
        (SECRET_NAME, encrypt(settings, secret), secret[-4:]),
    )
    return secret[-4:]
