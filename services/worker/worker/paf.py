"""« Paf, j'achète » (docs/50-paf-j-achete.md) : la même vidéo publiée chaque vendredi à 7 h, heure de Paris, en Reel sur
un compte Instagram à part, par un second compte Zernio (sa propre clé, sans lien avec celui de TikTok + @arzakparker).

Le planificateur (`plan_paf`, toutes les 5 min) crée la ligne paf_posts du prochain vendredi et le job `paf_publish`
dès 48 h avant : le Reel est programmé chez Zernio à l'avance, il sort donc même si le PC est éteint le vendredi matin.
Seuls les vendredis qui suivent l'activation (`enabled_at`) partent ; un vendredi raté (PC éteint deux jours) part
encore le jour même jusqu'à 19 h, sinon on passe au suivant.

app_settings « paf_j_achete » :
    {"enabled": true, "enabled_at": "2026-10-01T12:00:00+02:00", "account_id": "…", "username": "…",
     "captions": ["Bonjour, c'est vendredi.", "…"], "share_to_feed": true}

Légendes : une est tirée au sort juste avant chaque envoi (`pick_caption`), jamais celle du vendredi d'avant quand il y
en a plusieurs ; celle tirée est gardée dans paf_posts.caption. L'ancien champ `caption` (une seule légende) est encore lu.

Clé API : app_secrets « zernio_paf_api_key », chiffrée avec CREDENTIALS_KEY (écrite par l'onglet du dashboard).
La vidéo : le .mp4 le plus récent de <DATA_DIR>/paf-j-achete, relu à chaque envoi (la changer = remplacer le fichier).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from .config import Settings
from .youtube.auth import decrypt

log = structlog.get_logger(__name__)

SECRET_NAME = "zernio_paf_api_key"
SETTINGS_KEY = "paf_j_achete"
FOLDER = "paf-j-achete"
PARIS = ZoneInfo("Europe/Paris")
WEEKDAY = 4  # vendredi
HOUR = time(7, 0)
LEAD = timedelta(hours=48)  # programmé chez Zernio deux jours avant
LATE = timedelta(hours=12)  # vendredi raté : encore publié jusqu'à 19 h
VIDEO_EXT = {".mp4"}


@dataclass(frozen=True)
class PafConfig:
    enabled: bool = False
    enabled_at: datetime | None = None
    account_id: str = ""
    username: str = ""
    captions: tuple[str, ...] = ()
    share_to_feed: bool = True


def _when(raw: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


def _captions(v: dict[str, Any]) -> list[str]:
    raw = v.get("captions")
    if isinstance(raw, list):
        return [str(c) for c in raw if isinstance(c, str)]
    return [str(v["caption"])] if isinstance(v.get("caption"), str) else []


def pick_caption(captions: tuple[str, ...], previous: str | None = None, rng: random.Random | None = None) -> str:
    """Une légende au hasard ; pas celle du vendredi d'avant s'il y a le choix. "" s'il n'y en a aucune."""
    pool = [c for c in captions if c != previous] or list(captions)
    return (rng or random).choice(pool) if pool else ""


def parse_config(value: dict[str, Any] | None) -> PafConfig:
    v = value or {}
    return PafConfig(
        enabled=bool(v.get("enabled")),
        enabled_at=_when(v.get("enabled_at")),
        account_id=str(v.get("account_id") or ""),
        username=str(v.get("username") or ""),
        captions=tuple(c.strip() for c in _captions(v) if c.strip()),
        share_to_feed=v["share_to_feed"] if isinstance(v.get("share_to_feed"), bool) else True,
    )


def load_config(db: Any | None) -> PafConfig:
    if db is None:
        return PafConfig()
    row = db.fetch_one("select value from app_settings where key = %s", (SETTINGS_KEY,))
    return parse_config(row["value"] if row else None)


def paf_key(settings: Settings, db: Any | None) -> str | None:
    """Clé du second compte Zernio (jamais celle de TikTok / Instagram @arzakparker)."""
    if db is None or not settings.credentials_key:
        return None
    row = db.fetch_one("select value_encrypted from app_secrets where name = %s", (SECRET_NAME,))
    if not row:
        return None
    try:
        return decrypt(settings, row["value_encrypted"])
    except Exception:  # noqa: BLE001 — clé de chiffrement changée : à réenregistrer dans l'onglet
        return None


def folder(settings: Settings) -> Path:
    return settings.data_dir / FOLDER


def pick_video(path: Path) -> Path | None:
    """Le .mp4 le plus récent du dossier (None s'il n'y en a pas)."""
    if not path.is_dir():
        return None
    files = [f for f in path.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXT and not f.name.startswith(".")]
    return max(files, key=lambda f: f.stat().st_mtime, default=None)


def slot_of(friday: date) -> datetime:
    return datetime.combine(friday, HOUR, tzinfo=PARIS)


def upcoming_slot(now: datetime) -> datetime:
    """Le vendredi 7 h visé : celui de cette semaine tant qu'il n'a pas plus de 12 h de retard, sinon le suivant."""
    local = now.astimezone(PARIS)
    slot = slot_of(local.date() + timedelta(days=(WEEKDAY - local.weekday()) % 7))
    if slot + LATE < now:
        slot = slot_of(slot.date() + timedelta(days=7))
    return slot


def publish_time(slot: datetime, now: datetime) -> datetime | None:
    """Heure à donner à Zernio : le créneau s'il est à venir, None (tout de suite) s'il est passé ou tout proche."""
    return slot if slot - now > timedelta(minutes=2) else None


def due(cfg: PafConfig, now: datetime) -> datetime | None:
    """Le vendredi à préparer maintenant, ou None (coupé, pas de compte, trop tôt, vendredi d'avant l'activation)."""
    if not cfg.enabled or not cfg.account_id:
        return None
    slot = upcoming_slot(now)
    if slot - now > LEAD:
        return None
    if cfg.enabled_at and slot < cfg.enabled_at:
        return None
    return slot


def post_body(*, cfg: PafConfig, caption: str, media_url: str, when: datetime | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "content": caption.strip(),
        "mediaItems": [{"type": "video", "url": media_url}],
        "platforms": [
            {"platform": "instagram", "accountId": cfg.account_id, "platformSpecificData": {"shareToFeed": cfg.share_to_feed}}
        ],
    }
    if when is None:
        body["publishNow"] = True
    else:
        body["scheduledFor"] = when.isoformat()
    return body


def plan_paf(db: Any, settings: Settings) -> None:
    """Toutes les 5 min : prépare le prochain vendredi (ligne paf_posts + job paf_publish), une seule fois."""
    folder(settings).mkdir(parents=True, exist_ok=True)
    cfg = load_config(db)
    slot = due(cfg, datetime.now(UTC))
    if slot is None or not paf_key(settings, db):
        return
    friday = slot.date()
    row = db.fetch_one("select status from paf_posts where friday = %s", (friday,))
    if row and row["status"] != "cancelled":
        return
    if db.fetch_one("select 1 from jobs where type = 'paf_publish' and status in ('queued', 'running')"):
        return
    db.execute(
        """insert into paf_posts (friday, status) values (%s, 'queued')
           on conflict (friday) do update set status = 'queued', error = null, updated_at = now()""",
        (friday,),
    )
    db.enqueue("paf_publish", payload={"friday": friday.isoformat(), "source": "auto"}, priority=40, max_attempts=4)
    log.info("paf.planned", friday=friday.isoformat(), account=cfg.username or cfg.account_id)
