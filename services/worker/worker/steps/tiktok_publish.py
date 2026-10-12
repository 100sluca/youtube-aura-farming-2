"""Publication d'un Short sur TikTok par Zernio (docs/36-publication-tiktok.md).

Le job naît de trois façons : le planificateur (scheduler.plan_tiktok) le crée pour chaque Short programmé sur YouTube
d'une chaîne reliée à TikTok, le rattrapage (scheduler.plan_tiktok_backlog, docs/39) pour une vidéo déjà sortie sur
YouTube, au créneau resté vide donné dans `payload.at`, ou Luca clique « Publier sur TikTok » dans la Bibliothèque.
Déroulé :

1. le montage final part au stockage de Zernio (presign + PUT) ;
2. la publication est créée au premier créneau libre sur TikTok (docs/55, slots.free_post_slot : l'heure de la vidéo
   sur YouTube quand rien ne s'est libéré avant), ou tout de suite si le créneau est passé ou si Luca l'a demandé :
   Zernio publie à l'heure même si le PC est éteint, comme YouTube avec publishAt ;
3. le job se remet en file (Postpone) jusqu'à l'heure prévue, en repassant toutes les 3 h : une publication supprimée
   chez Zernio entre-temps libère son créneau (docs/55). À l'heure, il vérifie que la vidéo est sortie et récupère son
   lien, que TikTok ne donne que quelques minutes après.

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

from .. import platform_music
from ..postpone import Postpone
from ..slots import free_post_slot
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
RECHECK = timedelta(hours=3)  # publication programmée : toujours là chez Zernio ? (docs/55)
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
        # rattrapage (docs/39) : l'heure du créneau resté vide, pas celle du créneau YouTube, passé depuis longtemps ;
        # publication automatique : le premier créneau libre sur TikTok (docs/55)
        slot = _parse(payload.get("at"))
        if slot is None and not payload.get("source") and not payload.get("now") and not draft:
            slot = free_post_slot(ctx.db, v["id"], "tiktok", ch.enabled_at if ch else None, now)
        slot = slot or v["scheduled_at"]
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
        # Musique de TikTok à la place de la nôtre (citations sans voix : worker/platform_music.py, docs/58 §4)
        music = None if draft else self._platform_music(ctx, client, v, account_id)
        if music:
            state["music"] = music["summary"]
            self._save(ctx, v["id"], state)

        def body_with(sound: dict[str, Any] | None) -> dict[str, Any]:
            return post_body(
                caption=build_caption(v["title"], v["description"]),
                media_url=media_url,
                account_id=account_id,
                cfg=cfg,
                when=when,
                draft=draft,
                music=sound,
            )

        key = idempotency_key(v["id"], round_, int(v.get("generation") or 0))
        try:
            try:
                code, resp = client.create_post(body_with(music["settings"] if music else None), key)
            except ZernioError as exc:
                if not music or exc.status != 400:
                    raise
                # musique refusée (compte non éligible, morceau retiré) : la vidéo part avec sa propre musique
                ctx.log("tiktok.musique_refusee", level="warn", musique=music["summary"].get("name"), erreur=str(exc)[:300])
                state.pop("music", None)
                state["music_refused"] = str(exc)[:300]
                self._save(ctx, v["id"], state)
                # autre clé : Zernio pourrait rejouer la réponse 400 gardée sous la première
                plain = idempotency_key(f"{v['id']}:sans-musique", round_, int(v.get("generation") or 0))
                code, resp = client.create_post(body_with(None), plain)
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

    @staticmethod
    def _platform_music(ctx: Context, client: ZernioClient, v: dict[str, Any], account_id: str) -> dict[str, Any] | None:
        """Musique de la bibliothèque commerciale de TikTok pour une vidéo sans voix d'une recette choisie (défaut : les
        citations) ; None sinon, ou si la liste des musiques ne se lit pas (la vidéo garde alors la sienne)."""
        try:
            cfg = platform_music.load_config(ctx.db)
            recipe, voiced, mood, duration = platform_music.video_facts(ctx.db, v["id"])
        except Exception as exc:  # noqa: BLE001 — la musique de la plateforme est un plus, jamais une raison d'échouer
            ctx.log("tiktok.musique_ignoree", level="warn", erreur=str(exc)[:200])
            return None
        if not cfg.applies(recipe, voiced):
            return None
        try:
            tracks = platform_music.cached_tracks(client, account_id, cfg.country, ctx.settings.data_dir / "tiktok")
        except (ZernioError, OSError, ValueError) as exc:
            ctx.log("tiktok.musiques_illisibles", level="warn", erreur=str(exc)[:300])
            return None
        track = platform_music.pick_tiktok_track(tracks, mood, str(v["id"]))
        if not track:
            return None
        ctx.log("tiktok.musique", musique=track.get("name"), artiste=track.get("artist"), ambiance=mood)
        return {
            "settings": platform_music.tiktok_settings(track, duration, cfg.volume),
            "summary": platform_music.summary(track),
        }

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
        try:
            post = client.get_post(str(state["post_id"]))
        except ZernioError as exc:
            if exc.status != 404:
                raise
            # supprimée chez Zernio (par Luca) : elle ne sortira pas, son créneau TikTok est libre (docs/55)
            gone = Outcome(status="cancelled", post_id=str(state["post_id"]), error="publication supprimée chez Zernio")
            return self._record(ctx, v, state, gone)
        return self._record(ctx, v, state, read_post(post))

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
                min(when + FOLLOW_AFTER - now, RECHECK).total_seconds(),
                label=f"TikTok : programmée le {local:%d/%m à %H:%M}",
            )
        raise Postpone("Publication TikTok en cours de traitement", 120, label="TikTok : publication en cours")

    @staticmethod
    def _save(ctx: Context, video_id: Any, state: dict[str, Any]) -> None:
        ctx.db.execute("update videos set tiktok = %s, updated_at = now() where id = %s", (Jsonb(state), video_id))
