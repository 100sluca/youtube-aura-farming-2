"""Publication d'un Short en Reel Instagram par Zernio (docs/48-publication-instagram.md).

Même déroulé que TikTok (steps/tiktok_publish.py) : le planificateur (scheduler.plan_instagram) crée le job pour chaque
Short programmé sur YouTube d'une chaîne reliée à Instagram, ou Luca clique « Publier sur Instagram » dans la
Bibliothèque. Le montage final part au stockage de Zernio, la publication est créée au premier créneau libre sur
Instagram (docs/55 : l'heure de la vidéo sur YouTube quand rien ne s'est libéré avant ; tout de suite si le créneau est
passé), puis le job se remet en file jusqu'à l'heure prévue pour relever le lien, en repassant toutes les 3 h : un Reel
supprimé chez Zernio entre-temps libère son créneau.

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

from .. import platform_music
from ..instagram.config import load_instagram_config
from ..instagram.post import REEL_MAX_S, build_caption, post_body
from ..postpone import Postpone
from ..slots import free_post_slot
from ..tiktok.config import zernio_key
from ..tiktok.post import WAITING, Outcome, idempotency_key, publish_time, read_create, read_post
from ..tiktok.zernio import ZernioClient, ZernioError
from .base import Context, Step

PLATFORM = "instagram"
FOLLOW_AFTER = timedelta(minutes=3)
RECHECK = timedelta(hours=3)  # Reel programmé : toujours là chez Zernio ? (docs/55)
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
        slot = None
        if not payload.get("source") and not payload.get("now"):  # publication automatique : 1er créneau libre (docs/55)
            slot = free_post_slot(ctx.db, v["id"], PLATFORM, ch.enabled_at if ch else None, now)
        when = publish_time(slot or v["scheduled_at"], now, force_now=bool(payload.get("now")))
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
        # Musique d'Instagram à la place de la nôtre (citations sans voix : worker/platform_music.py, docs/58 §4)
        audio = self._platform_music(ctx, client, v, account_id)
        if audio:
            state["music"] = audio
            self._save(ctx, v["id"], state)
        body = post_body(
            caption=build_caption(v["title"], v["description"]),
            media_url=media_url,
            account_id=account_id,
            cfg=cfg,
            when=when,
            audio_id=audio["audioId"] if audio else None,
        )
        # clé distincte de celle de TikTok pour la même vidéo et la même tentative
        key = idempotency_key(f"ig:{v['id']}", round_, int(v.get("generation") or 0))
        try:
            try:
                code, resp = client.create_post(body, key)
            except ZernioError as exc:
                if not audio or exc.status != 400:
                    raise
                ctx.log("instagram.musique_refusee", level="warn", musique=audio.get("title"), erreur=str(exc)[:300])
                state.pop("music", None)
                self._save(ctx, v["id"], state)
                body = post_body(
                    caption=build_caption(v["title"], v["description"]),
                    media_url=media_url,
                    account_id=account_id,
                    cfg=cfg,
                    when=when,
                )
                code, resp = client.create_post(
                    body, idempotency_key(f"ig:{v['id']}:sans-musique", round_, int(v.get("generation") or 0))
                )
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

    @staticmethod
    def _platform_music(ctx: Context, client: ZernioClient, v: dict[str, Any], account_id: str) -> dict[str, Any] | None:
        """Musique du catalogue d'Instagram pour une vidéo sans voix d'une recette choisie (mêmes réglages que TikTok :
        app_settings.tiktok.platform_music) ; None sinon, ou si le compte n'y a pas accès (Instagram Login au lieu de
        Facebook Login) : le Reel garde alors sa musique."""
        try:
            cfg = platform_music.load_config(ctx.db)
            recipe, voiced, mood, _duration = platform_music.video_facts(ctx.db, v["id"])
        except Exception as exc:  # noqa: BLE001 — la musique de la plateforme est un plus, jamais une raison d'échouer
            ctx.log("instagram.musique_ignoree", level="warn", erreur=str(exc)[:200])
            return None
        if not cfg.applies(recipe, voiced):
            return None
        try:
            audio = platform_music.instagram_audio(client, account_id, mood, str(v["id"]))
        except ZernioError as exc:
            ctx.log("instagram.musiques_indisponibles", level="warn", code=exc.code, erreur=str(exc)[:200])
            return None
        if audio:
            ctx.log("instagram.musique", musique=audio.get("title"), artiste=audio.get("displayArtist"))
            return {k: audio.get(k) for k in ("audioId", "title", "displayArtist")}
        return None

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
        try:
            post = client.get_post(str(state["post_id"]))
        except ZernioError as exc:
            if exc.status != 404:
                raise
            # supprimé chez Zernio (par Luca) : il ne sortira pas, son créneau Instagram est libre (docs/55)
            gone = Outcome(status="cancelled", post_id=str(state["post_id"]), error="Reel supprimé chez Zernio")
            return self._record(ctx, v, state, gone)
        return self._record(ctx, v, state, read_post(post, PLATFORM))

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
                min(when + FOLLOW_AFTER - now, RECHECK).total_seconds(),
                label=f"Instagram : programmé le {local:%d/%m à %H:%M}",
            )
        raise Postpone("Reel Instagram en cours de traitement", 120, label="Instagram : publication en cours")

    @staticmethod
    def _save(ctx: Context, video_id: Any, state: dict[str, Any]) -> None:
        ctx.db.execute("update videos set instagram = %s, updated_at = now() where id = %s", (Jsonb(state), video_id))
