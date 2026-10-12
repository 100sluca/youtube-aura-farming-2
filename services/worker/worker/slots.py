"""Les créneaux libres d'abord (docs/55-creneaux-libres.md).

Règle de Luca (01/10) : 3 vidéos par jour sur YouTube, TikTok et Instagram, aux créneaux de la chaîne (9 h, 13 h, 18 h,
channels.publish_slots). Sur chaque plateforme, une vidéo prend le premier créneau libre entre maintenant et la fin du
planning ; le jour d'après seulement si tout est pris.

- YouTube : `next_free_slot` (SQL) donne le premier créneau sans vidéo. Quand un créneau se libère, la vidéo prête la plus
  proche, pas encore envoyée, y avance (`fill_free_slots`, appelée par scheduler.plan_uploads) ; une date choisie à la
  main (videos.slot_pinned) ne bouge jamais.
- YouTube Studio : la synchro horaire (steps/sync.py) lit l'état de chaque vidéo programmée (`follow_youtube`). Non
  répertoriée, privée sans date ou supprimée : la vidéo quitte le planning (SQL withdraw_from_schedule, qui annule aussi
  ses publications TikTok / Instagram pas encore sorties) ; déplacée : l'appli suit la nouvelle date.
- TikTok et Instagram : chaque publication automatique va au premier créneau libre de sa plateforme (`free_post_slot`) ;
  quand rien ne s'est libéré, c'est l'heure de la vidéo sur YouTube, comme avant.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from .tiktok.backlog import SAME_SLOT, slot_times

log = structlog.get_logger(__name__)

UPLOAD_LEAD = timedelta(hours=72)  # l'envoi YouTube part 72 h avant le créneau (scheduler.plan_uploads)
MOVE_AFTER = timedelta(minutes=90)  # une vidéo n'avance que dans un créneau à 2 h au moins (90 min + 30 de next_free_slot)
POST_MARGIN = timedelta(minutes=15)  # le temps d'envoyer le fichier à Zernio avant l'heure
POST_DAYS = 60  # créneaux TikTok / Instagram cherchés sur 60 jours
POST_MAX_AHEAD = timedelta(days=6)  # Zernio garde le fichier 7 jours avant la sortie : au-delà, l'heure YouTube
SAME_TIME = timedelta(minutes=1)  # écart toléré entre la date connue et celle de YouTube Studio
PLATFORMS = ("tiktok", "instagram")


# ---- Règles pures ----------------------------------------------------------------------------------------------------
def first_free(candidates: Iterable[datetime], busy: Iterable[datetime], after: datetime) -> datetime | None:
    """Premier créneau après `after` sans publication à ±10 min."""
    taken = list(busy)
    for s in sorted(candidates):
        if s > after and not any(abs(s - b) < SAME_SLOT for b in taken):
            return s
    return None


@dataclass(frozen=True)
class YoutubeChange:
    """Ce qui a changé dans YouTube Studio pour une vidéo programmée par l'appli."""

    kind: str  # moved (nouvelle date) | withdrawn (retirée du planning) | back (reprogrammée) | public | late
    at: datetime | None = None
    reason: str = ""


def _when(raw: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")) if raw else None
    except ValueError:
        return None


def youtube_change(status: str, known_at: datetime | None, item: dict[str, Any] | None, now: datetime) -> YoutubeChange | None:
    """Compare l'état d'une vidéo dans l'appli (`status` : scheduled, ou unpublished après un retrait) et sur YouTube
    (`item` de videos.list, None si YouTube ne la connaît plus). None : rien à faire."""
    if item is None:
        return YoutubeChange("withdrawn", reason="supprimée de YouTube") if status == "scheduled" else None
    st = item.get("status") or {}
    privacy = st.get("privacyStatus")
    publish_at = _when(st.get("publishAt"))
    if privacy == "public":
        return YoutubeChange("public")
    if status == "unpublished":  # retirée plus tôt : elle revient si Luca lui redonne une date
        return YoutubeChange("back", publish_at) if privacy == "private" and publish_at else None
    if privacy == "unlisted":
        return YoutubeChange("withdrawn", reason="passée en non répertoriée dans YouTube Studio")
    if privacy == "private" and publish_at:
        if known_at is None or abs(publish_at - known_at) > SAME_TIME:
            return YoutubeChange("moved", publish_at)
        return None
    if privacy == "private":
        if known_at is None or known_at > now:
            return YoutubeChange("withdrawn", reason="passée en privée, sans date, dans YouTube Studio")
        return YoutubeChange("late")  # créneau passé et toujours privée : YouTube ne l'a pas publiée
    return None


# ---- YouTube ---------------------------------------------------------------------------------------------------------
def fill_free_slots(db: Any) -> int:
    """Avance dans le premier créneau libre chaque vidéo prête, pas encore envoyée sur YouTube, dont la date n'a pas été
    choisie à la main. La plus proche d'abord : chacune libère le sien pour la suivante. Renvoie le nombre déplacé."""
    rows = db.fetch_all(
        """select v.id, v.channel_id, v.scheduled_at, v.title from videos v
           where v.status = 'ready' and v.scheduled_at is not null and v.youtube_video_id is null and not v.slot_pinned
             and not exists (select 1 from jobs j where j.video_id = v.id and j.type = 'upload' and j.status = 'running')
           order by v.scheduled_at"""
    )
    moved = 0
    for v in rows:
        row = db.fetch_one("select next_free_slot(%s, now() + %s) as at", (v["channel_id"], MOVE_AFTER))
        at = row["at"] if row else None
        if not at or at >= v["scheduled_at"]:
            continue
        done = db.execute(
            """update videos v set scheduled_at = %s
               where v.id = %s and v.status = 'ready' and v.youtube_video_id is null and not v.slot_pinned
                 and not exists (select 1 from jobs j where j.video_id = v.id and j.type = 'upload' and j.status = 'running')""",
            (at, v["id"]),
        )
        if not done:
            continue
        db.execute(
            "update jobs set run_after = least(run_after, %s) where video_id = %s and type = 'upload' and status = 'queued'",
            (at - UPLOAD_LEAD, v["id"]),
        )
        moved += 1
        log.info("slot.advanced", video=str(v["id"]), before=v["scheduled_at"].isoformat(), at=at.isoformat())
    return moved


def follow_youtube(
    db: Any, channel_id: UUID, items: dict[str, dict[str, Any]], *, alert_private: bool, now: datetime | None = None
) -> dict[str, int]:
    """Applique ce que Luca a changé dans YouTube Studio aux vidéos programmées de la chaîne (et à celles retirées
    plus tôt). `items` : réponses de videos.list par identifiant YouTube, pour toutes les vidéos demandées."""
    now = now or datetime.now(UTC)
    rows = db.fetch_all(
        """select v.id, v.title, v.status, v.youtube_video_id, coalesce(v.youtube_publish_at, v.scheduled_at) as at,
                  coalesce(c.timezone, 'Europe/Paris') as timezone
           from videos v join channels c on c.id = v.channel_id
           where v.channel_id = %s and v.youtube_video_id is not null and v.origin = 'app'
             and v.status in ('scheduled', 'unpublished')""",
        (channel_id,),
    )
    out = {"moved": 0, "withdrawn": 0, "back": 0}
    if not items:  # rien reçu du tout : mauvais compte ou API muette, on ne conclut pas à des suppressions
        return out
    for v in rows:
        change = youtube_change(v["status"], v["at"], items.get(v["youtube_video_id"]), now)
        if change is None:
            continue
        tz = ZoneInfo(v["timezone"])
        title = v["title"] or "Short"
        if change.kind == "public" and v["status"] == "unpublished":
            published = _when((items[v["youtube_video_id"]].get("snippet") or {}).get("publishedAt")) or now
            db.execute(
                "update videos set status = 'published', published_at = coalesce(published_at, %s), error = null where id = %s",
                (published, v["id"]),
            )
        elif change.kind in ("moved", "back") and change.at:
            db.execute(
                "update videos set status = 'scheduled', scheduled_at = %s, youtube_publish_at = %s, error = null where id = %s",
                (change.at, change.at, v["id"]),
            )
            out[change.kind] += 1
            when = change.at.astimezone(tz)
            db.alert(
                "info",
                f"Vidéo {'déplacée' if change.kind == 'moved' else 'reprogrammée'} dans YouTube Studio",
                f"« {title} » sortira sur YouTube le {when:%d/%m à %H:%M}."
                + (
                    " Son ancien créneau YouTube est libre pour la prochaine vidéo ; TikTok et Instagram gardent leur heure."
                    if change.kind == "moved"
                    else ""
                )
                + (" TikTok et Instagram la republient au premier créneau libre." if change.kind == "back" else ""),
                video_id=v["id"],
            )
        elif change.kind == "withdrawn":
            slot = v["at"].astimezone(tz) if v["at"] else None
            reason = f"Retirée du planning : {change.reason}"
            if not db.fetch_one("select withdraw_from_schedule(%s, %s) as ok", (v["id"], reason))["ok"]:
                continue  # envoi TikTok ou Instagram en cours : la synchro suivante réessaie
            out["withdrawn"] += 1
            db.alert(
                "info",
                f"Créneau libéré{f' : {slot:%d/%m à %H:%M}' if slot else ''}",
                f"« {title} » {change.reason}. Elle ne sort plus, ni sur TikTok ni sur Instagram ; la prochaine vidéo "
                "prête prend ce créneau.",
                video_id=v["id"],
            )
        elif change.kind == "late" and alert_private:
            db.alert(
                "error",
                "Vidéo restée privée après le créneau",
                "Projet API non audité ? Voir docs/05-youtube-api.md §2",
                video_id=v["id"],
            )
    if any(out.values()):
        log.info("slot.youtube_studio", channel=str(channel_id), **out)
    return out


# ---- TikTok et Instagram ---------------------------------------------------------------------------------------------
def free_post_slot(
    db: Any, video_id: UUID, platform: str, enabled_at: datetime | None, now: datetime | None = None
) -> datetime | None:
    """Premier créneau libre sur TikTok ou Instagram pour cette vidéo, ou None (l'heure YouTube s'applique).

    Un créneau est pris par une publication déjà programmée chez Zernio, ou réservé par une autre vidéo de la chaîne qui
    partira à son heure YouTube et n'est pas encore envoyée sur cette plateforme. Sans trou, c'est donc l'heure de la
    vidéo sur YouTube ; une publication retirée (par Luca chez Zernio, ou avec sa vidéo YouTube) laisse un trou que
    la vidéo suivante prend."""
    assert platform in PLATFORMS
    now = now or datetime.now(UTC)
    ch = db.fetch_one(
        """select v.channel_id, c.publish_slots, coalesce(c.timezone, 'Europe/Paris') as timezone
           from videos v join channels c on c.id = v.channel_id where v.id = %s""",
        (video_id,),
    )
    if not ch or not ch["publish_slots"]:
        return None
    busy = [
        r["at"]
        for r in db.fetch_all(
            f"""select (o.{platform} ->> 'scheduled_for')::timestamptz as at from videos o
                where o.channel_id = %(ch)s and o.id <> %(v)s and o.{platform} ->> 'scheduled_for' is not null
                  and coalesce(o.{platform} ->> 'status', '') not in ('failed', 'cancelled')
                  and (o.{platform} ->> 'scheduled_for')::timestamptz > now() - interval '1 hour'
                union all
                select o.scheduled_at from videos o
                where o.channel_id = %(ch)s and o.id <> %(v)s and o.origin = 'app' and o.scheduled_at > now()
                  and o.status in ('ready', 'uploading', 'scheduled')
                  and (o.{platform} is null or o.{platform} ? 'withdrawn')
                  and (%(since)s::timestamptz is null or o.scheduled_at >= %(since)s::timestamptz)""",  # noqa: S608 — colonne fixe
            {"ch": ch["channel_id"], "v": video_id, "since": enabled_at},
        )
        if r["at"] is not None
    ]
    slot = first_free(slot_times(ch["publish_slots"], ch["timezone"], now, days=POST_DAYS), busy, now + POST_MARGIN)
    if slot is None or slot - now > POST_MAX_AHEAD:
        return None
    return slot
