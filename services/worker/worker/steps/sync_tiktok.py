"""Relevé des statistiques TikTok (docs/39-tiktok-partout.md) : job `sync_tiktok`, chaque heure (scheduler.tiktok_counters)
et bouton « Actualiser » de l'onglet TikTok du Dashboard.

Pour chaque compte TikTok connecté à Zernio : ses compteurs (abonnés, j'aime reçus, vidéos) dans tiktok_accounts et
tiktok_account_snapshots ; chaque vidéo sortie sur le compte dans tiktok_posts (rattachée à la vidéo de l'appli qui l'a
publiée, ou reconnue à sa légende si elle a été publiée à la main dans TikTok) et tiktok_post_snapshots ; les vues 24 h et
7 jours après la sortie, d'après ces relevés ; le lien TikTok d'une vidéo de l'appli s'il manquait encore. Relevés
horaires gardés 10 jours, puis le dernier de chaque jour, comme pour YouTube (steps/sync.py).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from psycopg.types.json import Jsonb

from ..db import Db
from ..metrics import views_at
from ..postpone import Postpone
from ..tiktok.config import zernio_key
from ..tiktok.stats import (
    TikTokPost,
    account_info,
    add_live_posts,
    match_by_title,
    merge_posts,
    norm_title,
    parse_insights,
    parse_live_post,
    parse_post,
    real_tiktok_id,
    tiktok_id_of,
)
from ..tiktok.zernio import ZernioClient, ZernioError
from .base import Context, Step
from .sync import HOURLY_KEEP_DAYS, MARKS, MARKS_WINDOW_DAYS


class SyncTikTokStep(Step):
    type = "sync_tiktok"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        if ctx.settings.dry_run:
            return {"skipped": "dry_run"}
        key = zernio_key(ctx.settings, ctx.db)
        if not key:
            return {"skipped": "pas de clé Zernio (Réglages → TikTok)"}
        wanted = str((ctx.job.payload or {}).get("account_id") or "")
        out: dict[str, Any] = {}
        with ZernioClient(key) as zc:
            try:
                ctx.progress(3, "Comptes TikTok")
                accounts = [a for a in zc.tiktok_accounts() if not wanted or str(a.get("_id")) == wanted]
                for i, acc in enumerate(accounts):
                    ctx.progress(5 + 90 * i // max(1, len(accounts)), f"Statistiques de @{acc.get('username') or '?'}")
                    out[f"@{acc.get('username') or acc.get('_id')}"] = sync_account(ctx.db, zc, acc)
            except ZernioError as exc:
                if exc.status == 429:
                    raise Postpone(f"Zernio demande d'attendre : {exc}", exc.retry_after or 60,
                                   label="TikTok : limite de Zernio, nouvel essai bientôt") from exc
                if exc.status == 402:
                    raise RuntimeError("Zernio refuse les statistiques : option Analytics absente de l'abonnement") from exc
                raise
        return {"accounts": out}


def sync_account(db: Db, zc: ZernioClient, acc: dict[str, Any]) -> dict[str, Any]:
    """Compteurs du compte, puis chaque vidéo sortie : relevés, rattachement aux vidéos de l'appli, repères 24 h / 7 j."""
    taken = datetime.now(UTC)
    info = account_info(acc)
    aid = info["id"]
    try:
        counters = parse_insights(zc.account_insights(aid))
    except ZernioError as exc:
        if exc.status == 429:
            raise
        counters = info["fallback"]  # droit user.info.stats absent (412) ou TikTok muet : compteurs de la connexion
    db.execute(
        """insert into tiktok_accounts (id, username, display_name, avatar_url, profile_url, business, followers, following,
                                        likes, videos, fetched_at)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           on conflict (id) do update set username = excluded.username, display_name = excluded.display_name,
             avatar_url = excluded.avatar_url, profile_url = excluded.profile_url,
             business = coalesce(excluded.business, tiktok_accounts.business),
             followers = coalesce(excluded.followers, tiktok_accounts.followers),
             following = coalesce(excluded.following, tiktok_accounts.following),
             likes = coalesce(excluded.likes, tiktok_accounts.likes),
             videos = coalesce(excluded.videos, tiktok_accounts.videos), fetched_at = excluded.fetched_at""",
        (aid, info["username"], info["display_name"], info["avatar_url"], info["profile_url"], info["business"],
         counters["followers"], counters["following"], counters["likes"], counters["videos"], taken),
    )
    if any(v is not None for v in counters.values()):
        db.execute(
            """insert into tiktok_account_snapshots (account_id, taken_at, followers, following, likes, videos)
               values (%s, %s, %s, %s, %s, %s) on conflict do nothing""",
            (aid, taken, counters["followers"], counters["following"], counters["likes"], counters["videos"]),
        )

    try:  # vidéos publiées à la main dans TikTok : relues maintenant plutôt qu'au prochain passage de Zernio
        zc.sync_external(aid)
    except ZernioError as exc:
        if exc.status == 429:
            raise
    raw, overview = zc.post_analytics(aid)
    posts = merge_posts([p for p in (parse_post(item, aid) for item in raw) if p])
    try:  # sortie depuis le dernier passage de Zernio : visible tout de suite, vues au passage suivant
        posts = add_live_posts(posts, [p for p in (parse_live_post(item) for item in zc.account_posts(aid)) if p])
    except ZernioError as exc:
        if exc.status == 429:
            raise
    links = video_links(db)
    titles = title_index(db) if any(p.is_external for p in posts) else {}
    linked = 0
    for p in posts:
        video_id = links.get(p.zernio_post_id or "") or links.get(p.key) or links.get(tiktok_id_of(p.url) or "")
        if video_id is None and (by_title := match_by_title(p, titles)):
            video_id = by_title["id"]
            mark_manual(db, by_title, p, info)
        linked += video_id is not None
        store_post(db, aid, p, video_id, taken)
    if overview.get("lastSync"):
        db.execute("update tiktok_accounts set zernio_synced_at = %s where id = %s", (overview["lastSync"], aid))
    record_launch_marks(db, aid)
    prune_snapshots(db, aid)
    return {"followers": counters["followers"], "videos": len(posts), "from_app": linked}


def video_links(db: Db) -> dict[str, Any]:
    """Publication Zernio (et id TikTok tiré du lien) → vidéo de l'appli, d'après videos.tiktok écrit par
    steps/tiktok_publish.py."""
    out: dict[str, Any] = {}
    for r in db.fetch_all(
        "select id, tiktok->>'post_id' as post_id, tiktok->>'url' as url from videos where tiktok is not null"
    ):
        for k in (r["post_id"], tiktok_id_of(r["url"])):
            if k:
                out[k] = r["id"]
    return out


def title_index(db: Db) -> dict[str, dict[str, Any]]:
    """Titre normalisé → vidéo de l'appli montée ; à titre égal, celle déjà partie sur TikTok ou publiée l'emporte."""
    rows = db.fetch_all(
        """select id, title, created_at, tiktok from videos
           where origin = 'app' and title is not null and final_asset_id is not null
           order by (tiktok is not null), (status in ('published', 'scheduled')), created_at"""
    )
    return {norm_title(r["title"]): r for r in rows}


def mark_manual(db: Db, v: dict[str, Any], p: TikTokPost, account: dict[str, Any]) -> None:
    """Vidéo de l'appli publiée à la main dans TikTok : videos.tiktok la dit sortie (source « manuel ») pour la
    Bibliothèque et le Calendrier, et pour que ni la publication automatique ni le rattrapage ne la republient. Un brouillon
    envoyé par l'appli puis publié dans l'appli TikTok devient public."""
    state = v.get("tiktok")
    published_at = p.published_at.isoformat() if p.published_at else None
    if not state:
        if db.fetch_one(
            "select 1 from jobs where video_id = %s and type = 'tiktok_publish' and status in ('queued', 'running')", (v["id"],)
        ):
            return  # une publication est en cours : son step écrit l'état
        db.execute(
            "update videos set tiktok = %s, updated_at = now() where id = %s and tiktok is null",
            (Jsonb({"status": "published", "source": "manuel", "url": p.url, "published_at": published_at,
                    "account_id": account["id"], "username": account["username"], "external_post_id": p.key}), v["id"]),
        )
    elif state.get("draft") and state.get("status") == "published":
        db.execute(
            "update videos set tiktok = tiktok || %s, updated_at = now() where id = %s",
            (Jsonb({"draft": False, "url": p.url, "published_at": published_at, "external_post_id": p.key}), v["id"]),
        )


def store_post(db: Db, account_id: str, p: TikTokPost, video_id: Any, taken: datetime) -> None:
    if p.sync_status == "live":
        # Lue en direct seulement : si Zernio l'a déjà relevée sous une autre clé (absente de sa liste ce coup-ci), on ne
        # touche qu'aux compteurs lus en direct ; son historique reste intact
        other = db.fetch_one("select id from tiktok_posts where tiktok_id = %s and id <> %s limit 1", (p.tiktok_id, p.key))
        if other:
            db.execute(
                """update tiktok_posts set likes = greatest(likes, %s), comments = greatest(comments, %s),
                     shares = greatest(shares, %s), video_id = coalesce(video_id, %s), fetched_at = %s where id = %s""",
                (p.likes, p.comments, p.shares, video_id, taken, other["id"]),
            )
            return
    db.execute(
        """insert into tiktok_posts (id, account_id, video_id, tiktok_id, zernio_post_id, is_external, url, caption,
             thumbnail_url, published_at, views, likes, comments, shares, saves, reach, follows, profile_views,
             avg_watch_s, total_watch_s, completion_pct, impression_sources, audience_types, audience_countries,
             sync_status, metrics_at, fetched_at)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                   %s, %s, %s)
           on conflict (id) do update set account_id = excluded.account_id,
             video_id = coalesce(excluded.video_id, tiktok_posts.video_id),
             tiktok_id = coalesce(excluded.tiktok_id, tiktok_posts.tiktok_id),
             zernio_post_id = coalesce(excluded.zernio_post_id, tiktok_posts.zernio_post_id),
             is_external = excluded.is_external, url = coalesce(excluded.url, tiktok_posts.url),
             caption = coalesce(excluded.caption, tiktok_posts.caption),
             thumbnail_url = coalesce(excluded.thumbnail_url, tiktok_posts.thumbnail_url),
             published_at = coalesce(excluded.published_at, tiktok_posts.published_at),
             -- les compteurs publics redescendent parfois (vues retirées) : on prend la dernière valeur
             views = excluded.views, likes = excluded.likes, comments = excluded.comments, shares = excluded.shares,
             saves = coalesce(excluded.saves, tiktok_posts.saves), reach = coalesce(excluded.reach, tiktok_posts.reach),
             follows = coalesce(excluded.follows, tiktok_posts.follows),
             profile_views = coalesce(excluded.profile_views, tiktok_posts.profile_views),
             avg_watch_s = coalesce(excluded.avg_watch_s, tiktok_posts.avg_watch_s),
             total_watch_s = coalesce(excluded.total_watch_s, tiktok_posts.total_watch_s),
             completion_pct = coalesce(excluded.completion_pct, tiktok_posts.completion_pct),
             impression_sources = coalesce(excluded.impression_sources, tiktok_posts.impression_sources),
             audience_types = coalesce(excluded.audience_types, tiktok_posts.audience_types),
             audience_countries = coalesce(excluded.audience_countries, tiktok_posts.audience_countries),
             sync_status = excluded.sync_status, metrics_at = coalesce(excluded.metrics_at, tiktok_posts.metrics_at),
             fetched_at = excluded.fetched_at""",
        (p.key, account_id, video_id, p.tiktok_id, p.zernio_post_id, p.is_external, p.url, p.caption, p.thumbnail_url,
         p.published_at, p.views, p.likes, p.comments, p.shares, p.saves, p.reach, p.follows, p.profile_views,
         p.avg_watch_s, p.total_watch_s, p.completion_pct, _json(p.impression_sources), _json(p.audience_types),
         _json(p.audience_countries), p.sync_status, p.metrics_at, taken),
    )
    same = [i for i in {p.tiktok_id if real_tiktok_id(p.tiktok_id) else None, tiktok_id_of(p.url)} if i]
    if p.sync_status != "live" and same:
        # même vidéo relevée plus tôt sous une autre clé (lue en direct, copie synchronisée) : une seule ligne
        db.execute("delete from tiktok_posts where id <> %s and (tiktok_id = any(%s) or id = any(%s))", (p.key, same, same))
    if p.sync_status != "live":  # vues pas encore connues : pas de relevé, sinon un faux départ à 0
        db.execute(
            """insert into tiktok_post_snapshots (post_id, taken_at, views, likes, comments, shares, saves)
               values (%s, %s, %s, %s, %s, %s, %s) on conflict do nothing""",
            (p.key, taken, p.views, p.likes, p.comments, p.shares, p.saves),
        )
    if video_id and p.url:  # lien arrivé après la fin du suivi de la publication (steps/tiktok_publish.py)
        db.execute(
            """update videos set tiktok = jsonb_set(tiktok, '{url}', to_jsonb(%s::text)), updated_at = now()
               where id = %s and coalesce(tiktok->>'url', '') = '' and coalesce(tiktok->>'draft', 'false') <> 'true'""",
            (p.url, video_id),
        )


def _json(value: dict[str, float] | None) -> Jsonb | None:
    return Jsonb(value) if value else None


def record_launch_marks(db: Db, account_id: str) -> None:
    """Vues 24 h et 7 jours après la sortie, calculées une fois le cap passé, d'après les relevés horaires (mêmes règles
    que YouTube, steps/sync.py) ; restent vides si le worker ne tournait pas à ce moment-là."""
    rows = db.fetch_all(
        """select id, published_at, views_24h, views_7d from tiktok_posts
           where account_id = %s and published_at is not null and published_at > now() - make_interval(days => %s)
             and (views_24h is null or views_7d is null)""",
        (account_id, MARKS_WINDOW_DAYS),
    )
    now = datetime.now(UTC)
    for r in rows:
        for col, mark, gap in MARKS:
            at = r["published_at"] + mark
            if r[col] is not None or at > now:
                continue
            snaps = db.fetch_all(
                """select taken_at, views from tiktok_post_snapshots where post_id = %s and taken_at between %s and %s
                   order by taken_at""",
                (r["id"], at - gap, at + gap),
            )
            value = views_at([(s["taken_at"], s["views"]) for s in snaps], r["published_at"], at, gap)
            if value is not None:
                db.execute(f"update tiktok_posts set {col} = %s where id = %s", (value, r["id"]))  # noqa: S608


def prune_snapshots(db: Db, account_id: str) -> None:
    """Au-delà de HOURLY_KEEP_DAYS jours, on ne garde que le dernier relevé de chaque jour (heure de Paris)."""
    same_day = "(t.taken_at at time zone 'Europe/Paris')::date = (s.taken_at at time zone 'Europe/Paris')::date"
    db.execute(
        f"""delete from tiktok_post_snapshots s using tiktok_posts p
            where p.id = s.post_id and p.account_id = %s and s.taken_at < now() - make_interval(days => %s)
              and exists (select 1 from tiktok_post_snapshots t where t.post_id = s.post_id and t.taken_at > s.taken_at
                          and {same_day})""",  # noqa: S608 — texte fixe
        (account_id, HOURLY_KEEP_DAYS),
    )
    db.execute(
        f"""delete from tiktok_account_snapshots s
            where s.account_id = %s and s.taken_at < now() - make_interval(days => %s)
              and exists (select 1 from tiktok_account_snapshots t where t.account_id = s.account_id
                          and t.taken_at > s.taken_at and {same_day})""",  # noqa: S608 — texte fixe
        (account_id, HOURLY_KEEP_DAYS),
    )
