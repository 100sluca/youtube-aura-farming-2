"""« Paf, j'achète » : envoi du Reel du vendredi par le second compte Zernio (docs/50-paf-j-achete.md).

Même déroulé que steps/instagram_publish.py, sans vidéo de l'appli : le .mp4 du dossier <DATA_DIR>/paf-j-achete part au
stockage de Zernio, la publication est programmée au vendredi 7 h (ou publiée tout de suite si le créneau est passé),
puis le job se remet en file jusqu'à l'heure prévue pour relever le lien. L'état vit dans paf_posts (une ligne par
vendredi). L'interrupteur coupé dans l'onglet : le Reel encore seulement programmé est supprimé par un job
`{"delete_post": id, "friday": …}`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from ..paf import folder, load_config, paf_key, pick_caption, pick_video, post_body, publish_time, slot_of
from ..postpone import Postpone
from ..tiktok.post import WAITING, Outcome, idempotency_key, read_create, read_post
from ..tiktok.zernio import ZernioClient, ZernioError
from .base import Context, Step

FOLLOW_AFTER = timedelta(minutes=3)
URL_CHECK_S = 300
URL_CHECKS = 12
FIELDS = (
    "status",
    "scheduled_for",
    "post_id",
    "url",
    "error",
    "file_name",
    "account_id",
    "username",
    "round",
    "published_at",
    "caption",
)


class PafPublishStep(Step):
    type = "paf_publish"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        payload = ctx.job.payload or {}
        friday = date.fromisoformat(str(payload["friday"]))
        key = paf_key(ctx.settings, ctx.db)
        if not key:
            raise RuntimeError("Clé Zernio de « Paf, j'achète » absente : à coller dans l'onglet")
        with ZernioClient(key) as client:
            if payload.get("delete_post"):
                return self._delete(ctx, client, friday, str(payload["delete_post"]))
            row = ctx.db.fetch_one("select * from paf_posts where friday = %s", (friday,)) or {}
            state = {k: row.get(k) for k in FIELDS}
            if state.get("post_id") and state.get("status") not in ("failed", "cancelled", "queued"):
                if state.get("status") == "published" and state.get("url"):
                    return {"skipped": True, "url": state["url"]}
                return self._follow(ctx, client, friday, state)
            return self._publish(ctx, client, friday, state)

    # ---- Nouvelle publication ----------------------------------------------------------------------------------------
    def _publish(self, ctx: Context, client: ZernioClient, friday: date, state: dict[str, Any]) -> dict[str, Any]:
        cfg = load_config(ctx.db)
        if not cfg.enabled:
            self._save(ctx, friday, {**state, "status": "cancelled", "error": "coupé dans l'onglet avant l'envoi"})
            return {"cancelled": True}
        if not cfg.account_id:
            raise RuntimeError("Aucun compte Instagram choisi dans l'onglet « Paf, j'achète »")
        video = pick_video(folder(ctx.settings))
        if video is None:
            self._save(ctx, friday, {**state, "status": "failed", "error": f"aucune vidéo .mp4 dans {folder(ctx.settings)}"})
            raise RuntimeError(f"Aucune vidéo .mp4 dans {folder(ctx.settings)}")

        previous = ctx.db.fetch_one(
            """select caption from paf_posts where friday < %s and status = 'published' and caption is not null
               order by friday desc limit 1""",
            (friday,),
        )
        caption = pick_caption(cfg.captions, previous["caption"] if previous else None)  # tirée au sort à l'envoi
        now = datetime.now(UTC)
        when = publish_time(slot_of(friday), now)
        round_ = int(state.get("round") or 0) + 1
        state = {
            "status": "sending",
            "round": round_,
            "account_id": cfg.account_id,
            "username": cfg.username,
            "file_name": video.name,
            "caption": caption,
            "scheduled_for": (when or now).isoformat(),
            "post_id": None,
            "url": None,
            "error": None,
            "published_at": None,
        }
        self._save(ctx, friday, state)

        ctx.progress(2, f"Envoi de {video.name} à Zernio")
        media_url = client.upload_video(
            video, on_progress=lambda f: ctx.progress(2 + int(f * 88), f"Envoi à Zernio {int(f * 100)} %")
        )
        ctx.progress(92, "Création du Reel du vendredi")
        body = post_body(cfg=cfg, caption=caption, media_url=media_url, when=when)
        try:
            code, resp = client.create_post(body, idempotency_key(f"paf:{friday.isoformat()}", round_))
        except ZernioError as exc:
            if exc.status == 429 or exc.code == "idempotency_conflict":
                raise Postpone(
                    f"Zernio demande d'attendre : {exc}", exc.retry_after or 120, label="Paf, j'achète : limite de Zernio"
                ) from exc
            self._save(ctx, friday, {**state, "status": "failed", "error": str(exc)[:500]})
            raise
        ctx.log(
            "Reel du vendredi créé", code=code, caption=caption, friday=friday.isoformat(), scheduled_for=state["scheduled_for"]
        )
        return self._record(ctx, friday, state, read_create(code, resp, "instagram"))

    # ---- Interrupteur coupé : Reel encore programmé supprimé ---------------------------------------------------------
    def _delete(self, ctx: Context, client: ZernioClient, friday: date, post_id: str) -> dict[str, Any]:
        ctx.progress(30, "Annulation du Reel programmé")
        try:
            deleted = client.delete_post(post_id)
        except ZernioError as exc:
            if exc.status == 429:
                raise Postpone(f"Zernio demande d'attendre : {exc}", exc.retry_after or 120) from exc
            if exc.status in (400, 409):  # déjà sorti : reste sur Instagram
                ctx.log("Reel déjà sorti : il reste sur Instagram", post_id=post_id)
                return {"deleted": False, "post_id": post_id}
            raise
        ctx.db.execute(
            "update paf_posts set status = 'cancelled', updated_at = now() where friday = %s and post_id = %s",
            (friday, post_id),
        )
        ctx.log("Reel du vendredi annulé" if deleted else "Reel déjà absent chez Zernio", post_id=post_id)
        return {"deleted": deleted, "post_id": post_id}

    # ---- Suivi ---------------------------------------------------------------------------------------------------------
    def _follow(self, ctx: Context, client: ZernioClient, friday: date, state: dict[str, Any]) -> dict[str, Any]:
        ctx.progress(50, "Vérification sur Zernio")
        return self._record(ctx, friday, state, read_post(client.get_post(str(state["post_id"])), "instagram"))

    def _record(self, ctx: Context, friday: date, state: dict[str, Any], out: Outcome) -> dict[str, Any]:
        now = datetime.now(UTC)
        state.update(
            status=out.status, post_id=out.post_id or state.get("post_id"), error=out.error, url=out.url or state.get("url")
        )
        if out.status == "published" and not state.get("published_at"):
            state["published_at"] = now.isoformat()
        self._save(ctx, friday, state)
        result = {k: state.get(k) for k in ("status", "post_id", "url", "scheduled_for")}

        if out.status == "failed":
            raise RuntimeError(f"Instagram a refusé le Reel : {out.error}")
        if out.status == "cancelled":
            return result
        if out.status == "published":
            checks = int((ctx.job.payload or {}).get("url_checks") or 0)
            if state.get("url") or checks >= URL_CHECKS:
                return result
            ctx.db.execute(
                "update jobs set payload = payload || jsonb_build_object('url_checks', %s::int) where id = %s",
                (checks + 1, ctx.job.id),
            )
            raise Postpone("Publié, lien pas encore donné", URL_CHECK_S, label="Paf, j'achète : publié, lien en attente")
        if out.status not in WAITING:
            raise RuntimeError(f"État Instagram inattendu : {out.status}")
        when = datetime.fromisoformat(str(state["scheduled_for"])) if state.get("scheduled_for") else None
        if when and when > now:
            raise Postpone(
                f"Programmé sur Instagram pour le vendredi {friday:%d/%m} à 7 h",
                (when + FOLLOW_AFTER - now).total_seconds(),
                label=f"Paf, j'achète : programmé le {friday:%d/%m} à 7 h",
            )
        raise Postpone("Reel en cours de traitement", 120, label="Paf, j'achète : publication en cours")

    @staticmethod
    def _save(ctx: Context, friday: date, state: dict[str, Any]) -> None:
        values = {k: state.get(k) for k in FIELDS}
        values["round"] = int(values["round"] or 0)
        values["status"] = values["status"] or "queued"
        cols = ", ".join(FIELDS)
        ctx.db.execute(
            f"""insert into paf_posts (friday, {cols}) values (%s, {", ".join(["%s"] * len(FIELDS))})
                on conflict (friday) do update set {", ".join(f"{c} = excluded.{c}" for c in FIELDS)}, updated_at = now()""",
            (friday, *values.values()),
        )
