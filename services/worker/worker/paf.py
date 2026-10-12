"""« Paf, j'achète » (docs/50-paf-j-achete.md) : la même vidéo publiée chaque vendredi à l'heure choisie dans l'onglet
(7 h par défaut, heure de Paris), en Reel sur un compte Instagram à part, par un second compte Zernio (sa propre clé,
sans lien avec celui de TikTok + @arzakparker).

Le planificateur (`plan_paf`, toutes les 5 min) crée la ligne paf_posts du prochain vendredi et le job `paf_publish`
dès 48 h avant : le Reel est programmé chez Zernio à l'avance, il sort donc même si le PC est éteint le vendredi matin.
Seuls les vendredis qui suivent l'activation (`enabled_at`) partent ; un vendredi raté (PC éteint deux jours) part
encore jusqu'à 12 h après l'heure prévue, jamais après minuit, sinon on passe au suivant. L'heure changée alors que le
Reel est déjà programmé chez Zernio : `paf_publish` le retire et le reprogramme à la nouvelle heure (`moved`).

app_settings « paf_j_achete » :
    {"enabled": true, "enabled_at": "2026-10-01T12:00:00+02:00", "account_id": "…", "username": "…", "hour": "09:00",
     "captions": ["Bonjour, c'est vendredi.", "…"], "date_caption": "start", "share_to_feed": true}

Légendes : une est tirée au sort juste avant chaque envoi (`pick_caption`), jamais celle du vendredi d'avant quand il y
en a plusieurs ; celle envoyée est gardée dans paf_posts.caption. L'ancien champ `caption` (une seule légende) est encore
lu. La date du vendredi (« vendredi 16 octobre ») s'écrit toute seule (`render_caption`) : `{date}` dans une légende,
et/ou `date_caption` = "start" (première ligne), "end" (dernière ligne, avant les hashtags) ou "only" (la date seule).

Clé API : app_secrets « zernio_paf_api_key », chiffrée avec CREDENTIALS_KEY (écrite par l'onglet du dashboard).
La vidéo : le .mp4 le plus récent de <DATA_DIR>/paf-j-achete, relu à chaque envoi (la changer = remplacer le fichier).
"""

from __future__ import annotations

import random
import re
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
HOUR = time(7, 0)  # heure par défaut, réglable dans l'onglet (« hour »)
LEAD = timedelta(hours=48)  # programmé chez Zernio deux jours avant
LATE = timedelta(hours=12)  # vendredi raté : encore publié 12 h après l'heure prévue, jamais après minuit
VIDEO_EXT = {".mp4"}
DATE_TAG = "{date}"
DATE_MODES = ("off", "start", "end", "only")
MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
_HOUR = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


@dataclass(frozen=True)
class PafConfig:
    enabled: bool = False
    enabled_at: datetime | None = None
    account_id: str = ""
    username: str = ""
    captions: tuple[str, ...] = ()
    share_to_feed: bool = True
    hour: time = HOUR
    date_caption: str = "off"


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


def _hour(raw: Any) -> time:
    m = _HOUR.match(str(raw or "").strip())
    return time(int(m.group(1)), int(m.group(2))) if m else HOUR


def hour_label(t: time) -> str:
    """« 7 h », « 9 h 30 »."""
    return f"{t.hour} h {t.minute:02d}" if t.minute else f"{t.hour} h"


def date_label(friday: date) -> str:
    """« vendredi 16 octobre », « vendredi 1er janvier »."""
    day = "1er" if friday.day == 1 else str(friday.day)
    return f"vendredi {day} {MONTHS[friday.month - 1]}"


def _hashtags_only(line: str) -> bool:
    words = line.split()
    return bool(words) and all(w.startswith("#") for w in words)


def render_caption(caption: str, friday: date, mode: str = "off") -> str:
    """Légende envoyée : `{date}` remplacé par la date du vendredi, puis la date ajoutée selon `mode` (sauf si la
    légende a déjà `{date}`) : première ligne, dernière ligne avant le bloc de hashtags, ou la date seule."""
    label = date_label(friday)
    title = label[0].upper() + label[1:]
    if mode == "only":
        return title
    text = caption.replace(DATE_TAG, label).strip()
    if mode not in ("start", "end") or DATE_TAG in caption:
        return text
    if not text:
        return title
    if mode == "start":
        return f"{title}\n{text}"
    lines = text.split("\n")
    if len(lines) > 1 and _hashtags_only(lines[-1]):
        return "\n".join([*lines[:-1], title, lines[-1]])
    return f"{text}\n{title}"


def pick_caption(
    captions: tuple[str, ...],
    previous: str | None = None,
    rng: random.Random | None = None,
    previous_friday: date | None = None,
) -> str:
    """Une légende au hasard ; pas celle du vendredi d'avant s'il y a le choix. "" s'il n'y en a aucune.

    `previous` est la légende envoyée le vendredi d'avant : avec `previous_friday`, on la reconnaît même écrite avec
    sa date."""

    def same(c: str) -> bool:
        if c == previous:
            return True
        return previous_friday is not None and previous in {render_caption(c, previous_friday, m) for m in DATE_MODES}

    pool = [c for c in captions if not same(c)] or list(captions)
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
        hour=_hour(v.get("hour")),
        date_caption=str(v["date_caption"]) if v.get("date_caption") in DATE_MODES else "off",
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


def slot_of(friday: date, hour: time = HOUR) -> datetime:
    return datetime.combine(friday, hour, tzinfo=PARIS)


def late_limit(slot: datetime) -> datetime:
    """Vendredi raté : encore publié jusqu'à 12 h après l'heure prévue, jamais après minuit (heure de Paris)."""
    midnight = datetime.combine(slot.astimezone(PARIS).date() + timedelta(days=1), time(0), tzinfo=PARIS)
    return min(slot + LATE, midnight)


def upcoming_slot(now: datetime, hour: time = HOUR) -> datetime:
    """Le vendredi visé, à l'heure choisie : celui de cette semaine tant qu'il n'est pas trop en retard, sinon le suivant."""
    local = now.astimezone(PARIS)
    slot = slot_of(local.date() + timedelta(days=(WEEKDAY - local.weekday()) % 7), hour)
    if late_limit(slot) < now:
        slot = slot_of(slot.date() + timedelta(days=7), hour)
    return slot


def publish_time(slot: datetime, now: datetime) -> datetime | None:
    """Heure à donner à Zernio : le créneau s'il est à venir, None (tout de suite) s'il est passé ou tout proche."""
    return slot if slot - now > timedelta(minutes=2) else None


def due(cfg: PafConfig, now: datetime) -> datetime | None:
    """Le vendredi à préparer maintenant, ou None (coupé, pas de compte, trop tôt, vendredi d'avant l'activation)."""
    if not cfg.enabled or not cfg.account_id:
        return None
    slot = upcoming_slot(now, cfg.hour)
    if slot - now > LEAD:
        return None
    if cfg.enabled_at and slot < cfg.enabled_at:
        return None
    return slot


def moved(cfg: PafConfig, friday: date, scheduled_for: datetime | None, now: datetime) -> datetime | None:
    """Heure changée dans l'onglet alors que le Reel est déjà programmé chez Zernio : la nouvelle heure, sinon None.

    Seulement pour un Reel encore à venir (plus de 5 min) et une nouvelle heure pas trop en retard ; un Reel publié
    tout de suite (`publishNow`) a une heure déjà passée et n'est jamais touché."""
    if not cfg.enabled or scheduled_for is None or scheduled_for - now <= timedelta(minutes=5):
        return None
    new = slot_of(friday, cfg.hour)
    if new == scheduled_for or late_limit(new) < now:
        return None
    return new


def main_clash(account: dict[str, Any], main_accounts: list[dict[str, Any]]) -> str | None:
    """Le compte Instagram choisi est-il aussi sur le compte Zernio principal (@arzakparker) ? Son nom si oui.

    Instagram branche le compte ouvert dans le navigateur : connecté sur @arzakparker, le second compte Zernio reçoit
    @arzakparker une seconde fois (même `platformUserId`), et le Reel du vendredi partirait sur le mauvais compte.
    """
    pid = str(account.get("platformUserId") or "")
    name = str(account.get("username") or "").lower()
    for other in main_accounts:
        if other.get("platform") != "instagram":
            continue
        if (pid and str(other.get("platformUserId") or "") == pid) or (name and str(other.get("username") or "").lower() == name):
            return str(other.get("username") or name)
    return None


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
