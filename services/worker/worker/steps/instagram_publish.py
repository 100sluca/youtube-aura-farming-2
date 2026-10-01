"""Publication d'un Short en Reel Instagram par Zernio (docs/48-publication-instagram.md).

Même déroulé que TikTok (steps/tiktok_publish.py) : le planificateur (scheduler.plan_instagram) crée le job pour chaque
Short programmé sur YouTube d'une chaîne reliée à Instagram, ou Luca clique « Publier sur Instagram » dans la
Bibliothèque. Le montage final part au stockage de Zernio, la publication est créée à l'heure du créneau YouTube (ou
tout de suite si le créneau est passé), puis le job se remet en file jusqu'à l'heure prévue pour relever le lien.

videos.instagram garde l'état (mêmes champs que videos.tiktok, sans brouillon : l'API d'Instagram n'en a pas). Une
vidéo programmée puis retouchée (release_upload, migration 0036) : l'ancien Reel encore seulement programmé est supprimé
chez Zernio par un job `{"delete_post": id}`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from ..instagram.config import load_instagram_config
from ..instagram.post import REEL_MAX_S, build_caption, post_body
from ..postpone import Postpone
from ..tiktok.config import zernio_key
from ..tiktok.post import WAITING, Outcome, idempotency_key, publish_time, read_create, read_post
from ..tiktok.zernio import ZernioClient, ZernioError
from .base import Context, Step

PLATFORM = "instagram"
FOLLOW_AFTER = timedelta(minutes=3)
URL_CHECK_S = 300
URL_CHECKS = 12


def _parse(raw: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


class InstagramPublishStep(Step):
    type = "instagram_publish"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        if (ctx.job.payload or {}).get("delete_post"):
            return self._delete(ctx, str(ctx.job.payload["delete_post"]))
        v = ctx.db.fetch_one(
            """select v.id, v.channel_id, v.title, v.description, v.scheduled_at, v.duration_s, v.instagram, a.local_path,
                      jsonb_array_length(coalesce(v.previous_uploads, '[]'::jsonb)) as generation,
                      coalesce(c.timezone, 'Europe/Paris') as timezone
               from videos v left join assets a on a.id = v.final_asset_id left join channels c on c.id = v.channel_id
               where v.id = %s""",
            (ctx.job.video_id,),
        )
        assert v, "vidéo introuvable"
        state: dict[str, Any] = dict(v["instagram"] or {})
        key = zernio_key(ctx.settings, ctx.db)
        if not key:
            raise RuntimeError("Clé Zernio absente : Réglages → TikTok")
        with ZernioClient(key) as client:
            if state.get("post_id") and state.get("status") not in ("failed", "cancelled"):
                if state.get("status") == "published" and state.get("url"):
                    return {"skipped": True, "url": state.get("url")}
                return self._follow(ctx, client, v, state)
            return self._publish(ctx, client, v, state)

    # ---- Nouvelle publication ----------------------------------------------------------------------------------------
    def _publish(self, ctx: Context, client: ZernioClient, v: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        payload = ctx.job.payload or {}
        cfg = load_instagram_config(ctx.db)
        ch = cfg.for_channel(v["channel_id"])
        account_id = str(payload.get("account_id") or (ch.account_id if ch else ""))
        if not account_id:
            raise RuntimeError("Aucun compte Instagram relié à cette chaîne : Réglages → Instagram")
        path = v["local_path"]
        if not path or not Path(path).is_file():
            raise RuntimeError(f"Montage final introuvable sur le disque : {path}")
        if v["duration_s"] and float(v["duration_s"]) > REEL_MAX_S + 0.5:
            state.update(status="failed", error=f"vidéo de {float(v['duration_s']):.0f} s : un Reel dure 90 s au plus")
            self._save(ctx, v["id"], state)
            raise RuntimeError(f"Trop longue pour un Reel ({float(v['duration_s']):.0f} s > 90 s)")

        round_ = int(state.get("round") or 0)
        if state.get("status") != "sending" or not round_:
            round_ += 1
        now = datetime.now(UTC)
        when = publish_time(v["scheduled_at"], now, force_now=bool(payload.get("now")))
        state = {
            "status": "sending",
            "round": round_,
            "account_id": account_id,
            "username": ch.username if ch and ch.account_id == account_id else str(payload.get("username") or ""),
            "scheduled_for": when.isoformat() if when else None,
            "requested_at": now.isoformat(),
            "source": str(payload.get("source") or "auto"),
        }
        self._save(ctx, v["id"], state)

        ctx.progress(2, "Envoi du fichier à Zernio")
        media_url = client.upload_video(
            path, on_progress=lambda f: ctx.progress(2 + int(f * 88), f"Envoi à Zernio {int(f * 100)} %")
        )
        ctx.progress(92, "Création du Reel Instagram")
        body = post_body(
            caption=build_caption(v["title"], v["description"]),
            media_url=media_url,
            account_id=account_id,
            cfg=cfg,
            when=when,
        )
        # clé distincte de celle de TikTok pour la même vidéo et la même tentative
        key = idempotency_key(f"ig:{v['id']}", round_, int(v.get("generation") or 0))
        try:
            code, resp = client.create_post(body, key)
        except ZernioError as exc:
            if exc.status == 429 or exc.code == "idempotency_conflict":
                raise Postpone(
                    f"Zernio demande d'attendre : {exc}",
                    exc.retry_after or 120,
                    label="Instagram : limite de Zernio, nouvel essai bientôt",
                ) from exc
            state.update(status="failed", error=str(exc)[:500])
            self._save(ctx, v["id"], state)
            raise
        ctx.log(
            "Reel Instagram créé" if code != 409 else "Reel Instagram déjà créé",
            code=code,
            scheduled_for=state["scheduled_for"],
        )
        return self._record(ctx, v, state, read_create(code, resp, PLATFORM))

    # ---- Ancien Reel d'une vidéo retouchée après son envoi -----------------------------------------------------------
    def _delete(self, ctx: Context, post_id: str) -> dict[str, Any]:
        key = zernio_key(ctx.settings, ctx.db)
        if not key:
            raise RuntimeError("Clé Zernio absente : Réglages → TikTok")
        ctx.progress(30, "Annulation de l'ancien Reel Instagram")
        with ZernioClient(key) as client:
            try:
                deleted = client.delete_post(post_id)
            except ZernioError as exc:
                if exc.status == 429:
                    raise Postpone(
                        f"Zernio demande d'attendre : {exc}", exc.retry_after or 120, label="Instagram : limite de Zernio"
                    ) from exc
                if exc.status in (400, 409):  # déjà sorti : reste sur Instagram
                    ctx.log("Ancien Reel déjà sorti : à retirer à la main dans Instagram", post_id=post_id)
                    return {"deleted": False, "post_id": post_id, "reason": str(exc)[:300]}
                raise
        ctx.log("Ancien Reel Instagram annulé" if deleted else "Ancien Reel Instagram déjà absent", post_id=post_id)
        return {"deleted": deleted, "post_id": post_id}

    # ---- Suivi d'une publication existante ---------------------------------------------------------------------------
    def _follow(self, ctx: Context, client: ZernioClient, v: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        ctx.progress(50, "Vérification sur Zernio")
        return self._record(ctx, v, state, read_post(client.get_post(str(state["post_id"])), PLATFORM))

    def _record(self, ctx: Context, v: dict[str, Any], state: dict[str, Any], out: Outcome) -> dict[str, Any]:
        now = datetime.now(UTC)
        state.update(
            status=out.status,
            post_id=out.post_id or state.get("post_id"),
            error=out.error,
            url=out.url or state.get("url"),
            checked_at=now.isoformat(),
        )
        if out.status == "published":
            state.setdefault("published_at", now.isoformat())
            if not state.get("url"):
                state["url_checks"] = int(state.get("url_checks") or 0) + 1
        self._save(ctx, v["id"], state)
        result = {k: state.get(k) for k in ("status", "post_id", "url", "scheduled_for")}

        if out.status == "failed":
            raise RuntimeError(f"Instagram a refusé le Reel : {out.error}")
        if out.status == "cancelled":
            return result
        if out.status == "published":
            if state.get("url") or state["url_checks"] > URL_CHECKS:
                return result
            raise Postpone(
                "Publié sur Instagram, lien pas encore donné", URL_CHECK_S, label="Instagram : publié, lien en attente"
            )
        if out.status not in WAITING:
            raise RuntimeError(f"État Instagram inattendu : {out.status}")
        when = _parse(state.get("scheduled_for"))
        if when and when > now:
            local = when.astimezone(ZoneInfo(v["timezone"]))
            raise Postpone(
                f"Programmé sur Instagram pour le {local:%d/%m à %H:%M}",
                (when + FOLLOW_AFTER - now).total_seconds(),
                label=f"Instagram : programmé le {local:%d/%m à %H:%M}",
            )
        raise Postpone("Reel Instagram en cours de traitement", 120, label="Instagram : publication en cours")

    @staticmethod
    def _save(ctx: Context, video_id: Any, state: dict[str, Any]) -> None:
        ctx.db.execute("update videos set instagram = %s, updated_at = now() where id = %s", (Jsonb(state), video_id))
