"""Réglages Instagram (Réglages → Instagram du dashboard, docs/48). La clé Zernio est celle de TikTok (tiktok/config.py) :
un seul compte Zernio publie sur les deux réseaux (plan gratuit = 2 comptes).

app_settings « instagram » :
    {"channels": {"<id de la chaîne YouTube>": {"account_id": "…", "username": "…", "enabled": true,
                                                 "enabled_at": "2026-10-01T10:00:00+02:00"}},
     "share_to_feed": true, "ai_label": false}

Une chaîne YouTube publie sur un compte Instagram professionnel (Créateur ou Entreprise) connecté à Zernio. `enabled` :
chaque Short programmé sur YouTube part aussi en Reel, à la même heure ; seuls les créneaux qui suivent `enabled_at`
partent tout seuls. `share_to_feed` : le Reel paraît aussi dans la grille du profil, pas seulement dans l'onglet Reels.
`ai_label` : étiquette « IA » de Meta, coupée par défaut comme sur TikTok.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb


@dataclass(frozen=True)
class ChannelInstagram:
    account_id: str
    username: str = ""
    enabled: bool = False
    enabled_at: datetime | None = None


@dataclass
class InstagramConfig:
    channels: dict[str, ChannelInstagram] = field(default_factory=dict)
    share_to_feed: bool = True
    ai_label: bool = False

    def for_channel(self, channel_id: object) -> ChannelInstagram | None:
        ch = self.channels.get(str(channel_id))
        return ch if ch and ch.account_id else None


def _when(raw: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


def parse_config(value: dict[str, Any] | None) -> InstagramConfig:
    v = value or {}
    channels = {
        str(cid): ChannelInstagram(
            account_id=str(c.get("account_id") or ""),
            username=str(c.get("username") or ""),
            enabled=bool(c.get("enabled")),
            enabled_at=_when(c.get("enabled_at")),
        )
        for cid, c in (v.get("channels") or {}).items()
        if isinstance(c, dict)
    }
    flag = lambda k, d: bool(v[k]) if isinstance(v.get(k), bool) else d  # noqa: E731
    return InstagramConfig(channels=channels, share_to_feed=flag("share_to_feed", True), ai_label=flag("ai_label", False))


def load_instagram_config(db: Any | None) -> InstagramConfig:
    if db is None:
        return InstagramConfig()
    row = db.fetch_one("select value from app_settings where key = 'instagram'")
    return parse_config(row["value"] if row else None)


def save_instagram_config(db: Any, value: dict[str, Any]) -> None:
    db.execute(
        """insert into app_settings (key, value) values ('instagram', %s)
           on conflict (key) do update set value = excluded.value, updated_at = now()""",
        (Jsonb(value),),
    )
