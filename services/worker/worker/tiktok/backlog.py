"""Rattrapage TikTok (docs/39-tiktok-partout.md) : les vidéos de l'appli sorties sur YouTube avant la publication
automatique (ou manquées par elle, PC éteint plus de 24 h) partent sur TikTok une par une, dans les créneaux restés vides.

Règle, activée par chaîne dans Réglages → TikTok : un créneau de la chaîne sans vidéo YouTube et sans publication TikTok
prévue reçoit, entre 29 et 5 min avant son heure, la plus ancienne vidéo de v_tiktok_backlog (migration 0026). 29 min :
next_free_slot (0001) garde 30 min de marge, donc une nouvelle vidéo YouTube ne peut plus prendre ce créneau. Une vidéo
par créneau, jamais en rafale (Zernio : 15 vidéos par 24 h et par compte). Fonctions pures ; le planificateur
(scheduler.plan_tiktok_backlog) lit la base et met le job en file.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

LEAD_MIN = timedelta(minutes=5)  # assez tôt pour envoyer le fichier à Zernio avant l'heure
LEAD_MAX = timedelta(minutes=29)  # plus aucune vidéo YouTube ne peut prendre le créneau (marge de 30 min)
SAME_SLOT = timedelta(minutes=10)  # une publication à ±10 min occupe le créneau


def slot_times(publish_slots: Iterable[time | str], tz_name: str | None, now: datetime, days: int = 2) -> list[datetime]:
    """Créneaux de la chaîne (heure locale) de la veille à `days` jours, en UTC, dans l'ordre."""
    tz = ZoneInfo(tz_name or "Europe/Paris")
    slots = [s if isinstance(s, time) else time.fromisoformat(str(s)) for s in publish_slots]
    today = now.astimezone(tz).date()
    out = [datetime.combine(today + timedelta(days=d), s, tzinfo=tz).astimezone(UTC) for d in range(-1, days) for s in slots]
    return sorted(out)


def backlog_slot(slots: Iterable[datetime], now: datetime, busy: Iterable[datetime]) -> datetime | None:
    """Créneau à pourvoir maintenant : entre 29 et 5 min d'ici, sans vidéo YouTube ni publication TikTok à cette heure."""
    taken = list(busy)
    for s in sorted(slots):
        if now + LEAD_MIN < s <= now + LEAD_MAX and not any(abs(s - b) < SAME_SLOT for b in taken):
            return s
    return None
