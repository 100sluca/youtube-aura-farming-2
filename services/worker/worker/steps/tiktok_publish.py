"""Publication d'un Short sur TikTok par Zernio (docs/36-publication-tiktok.md).

Le job naît de trois façons : le planificateur (scheduler.plan_tiktok) le crée pour chaque Short programmé sur YouTube
d'une chaîne reliée à TikTok, le rattrapage (scheduler.plan_tiktok_backlog, docs/39) pour une vidéo déjà sortie sur
YouTube, au créneau resté vide donné dans `payload.at`, ou Luca clique « Publier sur TikTok » dans la Bibliothèque.
Déroulé :

1. le montage final part au stockage de Zernio (presign + PUT) ;
2. la publication est créée à l'heure du créneau YouTube (`scheduledFor`), ou tout de suite si le créneau est passé
   ou si Luca l'a demandé : Zernio publie à l'heure même si le PC est éteint, comme YouTube avec publishAt ;
3. le job se remet en file (Postpone) jusqu'à l'heure prévue, vérifie que la vidéo est sortie et récupère son lien,
   que TikTok ne donne que quelques minutes après.

videos.tiktok garde l'état : status (sending, scheduled, publishing…, published, failed, cancelled), post_id, url,
scheduled_for, account_id, username, error, round. Un job relancé après une panne reprend le même envoi (même clé
d'idempotence : jamais deux publications) ; une nouvelle demande après un échec en commence un autre (round suivant).

Une vidéo programmée puis retouchée (docs/44, SQL release_upload) : son ancienne publication encore seulement programmée
est supprimée chez Zernio par un job `{"delete_post": id}` ; la vidéo refaite repart comme une nouvelle publication.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from ..postpone import Postpone
from ..tiktok.config import load_tiktok_config, zernio_key
from ..tiktok.post import (
    WAITING,
    Outcome,
    build_caption,
    idempotency_key,
    post_body,
    publish_time,
    read_create,
    read_post,
)
from ..tiktok.zernio import ZernioClient, ZernioError
from .base import Context, Step

FOLLOW_AFTER = timedelta(minutes=3)  # après l'heure prévue, le temps que TikTok traite la vidéo
URL_CHECK_S = 300  # vidéo publiée sans lien : on revient voir toutes les 5 min…
URL_CHECKS = 12  # … pendant une heure au plus


def _parse(raw: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


class TikTokPublishStep(Step):
    type = "tiktok_publish"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        if (ctx.job.payload or {}).get("delete_post"):
            return self._delete(ctx, str(ctx.job.payload["delete_post"]))
        v = ctx.db.fetch_one(
            """select v.id, v.channel_id, v.title, v.description, v.scheduled_at, v.tiktok, a.local_path,
                      jsonb_array_length(coalesce(v.previous_uploads, '[]'::jsonb)) as generation,
                      coalesce(c.timezone, 'Europe/Paris') as timezone
               from videos v left join assets a on a.id = v.final_asset_id left join channels c on c.id = v.channel_id
               where v.id = %s""",
            (ctx.job.video_id,),
        )
        assert v, "vidéo introuvable"
        state: dict[str, Any] = dict(v["tiktok"] or {})
        key = zernio_key(ctx.settings, ctx.db)
        if not key:
            raise RuntimeError("Clé Zernio absente : Réglages → TikTok")
        with ZernioClient(key) as client:
            if state.get("post_id") and state.get("status") not in ("failed", "cancelled"):
                if state.get("status") == "published" and (state.get("url") or state.get("draft")):
                    return {"skipped": True, "url": state.get("url")}
                return self._follow(ctx, client, v, state)
            return self._publish(ctx, client, v, state)

    # ---- Nouvelle publication ----------------------------------------------------------------------------------------
    def _publish(self, ctx: Context, client: ZernioClient, v: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        payload = ctx.job.payload or {}
        cfg = load_tiktok_config(ctx.db)
        ch = cfg.for_channel(v["channel_id"])
        account_id = str(payload.get("account_id") or (ch.account_id if ch else ""))
        if not account_id:
            raise RuntimeError("Aucun compte TikTok relié à cette chaîne : Réglages → TikTok")
        path = v["local_path"]
        if not path or not Path(path).is_file():
            raise RuntimeError(f"Montage final introuvable sur le disque : {path}")

        round_ = int(state.get("round") or 0)
        if state.get("status") != "sending" or not round_:  # « sending » : envoi interrompu, on le reprend tel quel
            round_ += 1
        now = datetime.now(UTC)
        draft = bool(payload.get("draft"))
        # rattrapage (docs/39) : l'heure du créneau resté vide, pas celle du créneau YouTube, passé depuis longtemps
        slot = _parse(payload.get("at")) or v["scheduled_at"]
        when = publish_time(slot, now, force_now=bool(payload.get("now")) or draft)
        state = {
            "status": "sending",
            "round": round_,
            "account_id": account_id,
            "username": ch.username if ch and ch.account_id == account_id else str(payload.get("username") or ""),
            "scheduled_for": when.isoformat() if when else None,
            "draft": draft,
            "requested_at": now.isoformat(),
            # auto (créneau YouTube), rattrapage, bibliothèque ou cli : le Calendrier l'affiche
            "source": str(payload.get("source") or "auto"),
        }
        self._save(ctx, v["id"], state)

        ctx.progress(2, "Envoi du fichier à Zernio")
        media_url = client.upload_video(
            path, on_progress=lambda f: ctx.progress(2 + int(f * 88), f"Envoi à Zernio {int(f * 100)} %")
        )
        ctx.progress(92, "Création de la publication TikTok")
        body = post_body(
            caption=build_caption(v["title"], v["description"]),
            media_url=media_url,
            account_id=account_id,
            cfg=cfg,
            when=when,
            draft=draft,
        )
        try:
            code, resp = client.create_post(body, idempotency_key(v["id"], round_, int(v.get("generation") or 0)))
        except ZernioError as exc:
            if exc.status == 429 or exc.code == "idempotency_conflict":
                raise Postpone(
                    f"Zernio demande d'attendre : {exc}",
                    exc.retry_after or 120,
                    label="TikTok : limite de Zernio, nouvel essai bientôt",
                ) from exc
            state.update(status="failed", error=str(exc)[:500])
            self._save(ctx, v["id"], state)
            raise
        ctx.log(
            "Publication TikTok créée" if code != 409 else "Publication TikTok déjà créée",
            code=code,
            scheduled_for=state["scheduled_for"],
        )
        return self._record(ctx, v, state, read_create(code, resp))

    # ---- Ancienne publication d'une vidéo retouchée après son envoi (docs/44) ---------------------------------------
    def _delete(self, ctx: Context, post_id: str) -> dict[str, Any]:
        key = zernio_key(ctx.settings, ctx.db)
        if not key:
            raise RuntimeError("Clé Zernio absente : Réglages → TikTok")
        ctx.progress(30, "Annulation de l'ancienne publication TikTok")
        with ZernioClient(key) as client:
            try:
                deleted = client.delete_post(post_id)
            except ZernioError as exc:
                if exc.status == 429:
                    raise Postpone(
                        f"Zernio demande d'attendre : {exc}", exc.retry_after or 120, label="TikTok : limite de Zernio"
                    ) from exc
                if exc.status in (400, 409):  # déjà sortie : Zernio ne la retire pas de TikTok
                    ctx.log("Ancienne publication TikTok déjà sortie : à retirer à la main dans TikTok", post_id=post_id)
                    return {"deleted": False, "post_id": post_id, "reason": str(exc)[:300]}
                raise
        ctx.log("Ancienne publication TikTok annulée" if deleted else "Ancienne publication TikTok déjà absente", post_id=post_id)
        return {"deleted": deleted, "post_id": post_id}

    # ---- Suivi d'une publication existante ---------------------------------------------------------------------------
    def _follow(self, ctx: Context, client: ZernioClient, v: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        ctx.progress(50, "Vérification sur Zernio")
        return self._record(ctx, v, state, read_post(client.get_post(str(state["post_id"]))))

    def _record(self, ctx: Context, v: dict[str, Any], state: dict[str, Any], out: Outcome) -> dict[str, Any]:
        now = datetime.now(UTC)
        state.update(
            status=out.status,
            post_id=out.post_id or state.get("post_id"),
            error=out.error,
            url=out.url or state.get("url"),
            checked_at=now.isoformat(),
        )
        if out.draft:
            state["draft"] = True
        if out.status == "published":
            state.setdefault("published_at", now.isoformat())
            if not state.get("url") and not state.get("draft"):
                state["url_checks"] = int(state.get("url_checks") or 0) + 1
        self._save(ctx, v["id"], state)
        result = {k: state.get(k) for k in ("status", "post_id", "url", "scheduled_for")}

        if out.status == "failed":
            raise RuntimeError(f"TikTok a refusé la publication : {out.error}")
        if out.status == "cancelled":
            return result
        if out.status == "published":
            if state.get("url") or state.get("draft") or state["url_checks"] > URL_CHECKS:
                return result
            raise Postpone(
                "Publiée sur TikTok, lien pas encore donné par TikTok", URL_CHECK_S, label="TikTok : publiée, lien en attente"
            )
        if out.status not in WAITING:
            raise RuntimeError(f"État TikTok inattendu : {out.status}")
        when = _parse(state.get("scheduled_for"))
        if when and when > now:
            local = when.astimezone(ZoneInfo(v["timezone"]))
            raise Postpone(
                f"Programmée sur TikTok pour le {local:%d/%m à %H:%M}",
                (when + FOLLOW_AFTER - now).total_seconds(),
                label=f"TikTok : programmée le {local:%d/%m à %H:%M}",
            )
        raise Postpone("Publication TikTok en cours de traitement", 120, label="TikTok : publication en cours")

    @staticmethod
    def _save(ctx: Context, video_id: Any, state: dict[str, Any]) -> None:
        ctx.db.execute("update videos set tiktok = %s, updated_at = now() where id = %s", (Jsonb(state), video_id))
