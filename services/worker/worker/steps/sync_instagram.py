"""Relevé des statistiques Instagram (docs/62-reseaux-et-comptes.md) : job `sync_instagram`, chaque heure
(scheduler.instagram_counters) et bouton « Actualiser » de l'onglet Instagram du Dashboard.

Deux comptes Zernio : celui de TikTok + Instagram @arzakparker (mêmes vidéos que YouTube, clé `zernio_api_key`) et celui
de « Paf, j'achète » (clé `zernio_paf_api_key`, docs/50). Pour chaque compte Instagram qu'ils voient : ses compteurs
(abonnés, publications, vues et portée du compte sur 28 jours) dans instagram_accounts et instagram_account_snapshots ;
chaque Reel dans instagram_posts (rattaché à la vidéo de l'appli ou au vendredi de « Paf, j'achète » qui l'a publié) et
instagram_post_snapshots ; les vues 24 h et 7 jours après la sortie. Un même compte Instagram vu par les deux comptes
Zernio n'est relevé qu'une fois (le premier), les deux ids Zernio sont notés dans `zernio_ids`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from psycopg.types.json import Jsonb

from ..db import Db
from ..instagram.stats import (
    InstagramPost,
    account_info,
    match_by_title,
    merge_posts,
    missing_live,
    parse_insights,
    parse_live_post,
    parse_post,
    refresh_live_counters,
    shortcode_of,
)
from ..paf import paf_key
from ..postpone import Postpone
from ..tiktok.config import zernio_key
from ..tiktok.zernio import ZernioClient, ZernioError
from .base import Context, Step
from .sync_tiktok import prune_snapshots, record_launch_marks, title_index

LOOKUPS_MAX = 12  # lectures unitaires par compte et par relevé (Reels absents de la liste de Zernio)


class SyncInstagramStep(Step):
    type = "sync_instagram"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        if ctx.settings.dry_run:
            return {"skipped": "dry_run"}
        keys = [
            (name, key)
            for name, key in (("main", zernio_key(ctx.settings, ctx.db)), ("paf", paf_key(ctx.settings, ctx.db)))
            if key
        ]
        if not keys:
            return {"skipped": "pas de clé Zernio (Réglages → TikTok, onglet Paf, j'achète)"}
        wanted = str((ctx.job.payload or {}).get("account_id") or "")
        out: dict[str, Any] = {}
        done: set[str] = set()
        errors: list[str] = []
        for i, (profile, key) in enumerate(keys):
            ctx.progress(3 + 90 * i // len(keys), f"Comptes Instagram ({'Paf, j’achète' if profile == 'paf' else 'principal'})")
            try:
                with ZernioClient(key) as zc:
                    for acc in zc.accounts():
                        if acc.get("platform") != "instagram":
                            continue
                        info = account_info(acc)
                        if wanted and wanted not in (info["id"], info["zernio_id"]):
                            continue
                        if info["id"] in done:  # déjà relevé par l'autre compte Zernio : on note seulement son id
                            note_zernio_id(ctx.db, info["id"], profile, info["zernio_id"])
                            continue
                        ctx.progress(5 + 90 * i // len(keys), f"Statistiques de @{info['username'] or '?'}")
                        out[f"@{info['username'] or info['id']}"] = sync_account(ctx.db, zc, acc, profile)
                        done.add(info["id"])
            except ZernioError as exc:
                if exc.status == 429:
                    raise Postpone(
                        f"Zernio demande d'attendre : {exc}",
                        exc.retry_after or 60,
                        label="Instagram : limite de Zernio, nouvel essai bientôt",
                    ) from exc
                if exc.status == 402:
                    errors.append(f"{profile} : option Analytics absente de l'abonnement Zernio")
                else:  # clé refusée (401) ou Zernio en panne : l'autre compte est quand même relevé
                    errors.append(f"{profile} : {exc}")
        if errors and not done:
            raise RuntimeError(" ; ".join(errors))
        return {"accounts": out, **({"errors": errors} if errors else {})}


def note_zernio_id(db: Db, ig_id: str, profile: str, zernio_id: str) -> None:
    db.execute(
        "update instagram_accounts set zernio_ids = zernio_ids || %s where id = %s",
        (Jsonb({profile: zernio_id}), ig_id),
    )


def sync_account(db: Db, zc: ZernioClient, acc: dict[str, Any], profile: str) -> dict[str, Any]:
    """Compteurs du compte, puis chaque Reel : relevés, rattachement aux vidéos de l'appli et à « Paf, j'achète »,
    repères 24 h / 7 j."""
    taken = datetime.now(UTC)
    info = account_info(acc)
    aid, zid = info["id"], info["zernio_id"]
    try:
        insights = parse_insights(zc.instagram_insights(zid))
    except ZernioError as exc:
        if exc.status == 429:
            raise
        insights = {"views_28d": None, "reach_28d": None, "interactions_28d": None, "engaged_28d": None}
    db.execute(
        """insert into instagram_accounts (id, username, display_name, avatar_url, profile_url, account_type, followers,
                                           following, media_count, views_28d, reach_28d, interactions_28d, engaged_28d,
                                           zernio_ids, fetched_at)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           on conflict (id) do update set username = excluded.username, display_name = excluded.display_name,
             avatar_url = excluded.avatar_url, profile_url = excluded.profile_url,
             account_type = coalesce(excluded.account_type, instagram_accounts.account_type),
             followers = coalesce(excluded.followers, instagram_accounts.followers),
             following = coalesce(excluded.following, instagram_accounts.following),
             media_count = coalesce(excluded.media_count, instagram_accounts.media_count),
             views_28d = coalesce(excluded.views_28d, instagram_accounts.views_28d),
             reach_28d = coalesce(excluded.reach_28d, instagram_accounts.reach_28d),
             interactions_28d = coalesce(excluded.interactions_28d, instagram_accounts.interactions_28d),
             engaged_28d = coalesce(excluded.engaged_28d, instagram_accounts.engaged_28d),
             -- les ids Zernio de ce relevé remplacent les anciens ; ceux de l'autre compte Zernio s'ajoutent ensuite
             zernio_ids = excluded.zernio_ids, fetched_at = excluded.fetched_at""",
        (
            aid,
            info["username"],
            info["display_name"],
            info["avatar_url"],
            info["profile_url"],
            info["account_type"],
            info["followers"],
            info["following"],
            info["media_count"],
            insights["views_28d"],
            insights["reach_28d"],
            insights["interactions_28d"],
            insights["engaged_28d"],
            Jsonb({profile: zid}),
            taken,
        ),
    )
    if info["followers"] is not None or insights["views_28d"] is not None:
        db.execute(
            """insert into instagram_account_snapshots (account_id, taken_at, followers, following, media_count, views_28d,
                                                        reach_28d)
               values (%s, %s, %s, %s, %s, %s, %s) on conflict do nothing""",
            (aid, taken, info["followers"], info["following"], info["media_count"], insights["views_28d"], insights["reach_28d"]),
        )

    try:  # Reels publiés à la main ou sortis depuis le dernier passage de Zernio : relus maintenant
        zc.sync_external(zid)
    except ZernioError as exc:
        if exc.status == 429:
            raise
    raw, overview = zc.post_analytics(zid, platform="instagram")
    posts = [p for p in (parse_post(item, zid) for item in raw) if p]
    try:
        live = [p for p in (parse_live_post(item) for item in zc.account_posts(zid)) if p]
    except ZernioError as exc:
        if exc.status == 429:
            raise
        live = []
    refresh_live_counters(posts, live)
    links, paf = video_links(db), paf_links(db)
    # Reels vus en direct, ou publiés par l'appli sur ce compte, que la liste de Zernio n'a pas encore : lus un par un
    # (Zernio crée leur fiche à cette lecture), sinon gardés sans vues
    lookups = [(lp.key, lp) for lp in missing_live(posts, live)]
    known = {p.zernio_post_id for p in posts} | {p.key for p in posts}
    lookups += [(pid, None) for pid in published_by_app(db, zid) if pid not in known]
    for pid, fallback in lookups[:LOOKUPS_MAX]:
        found = lookup(zc, pid, zid)
        if found:
            posts.append(found)
        elif fallback:
            posts.append(fallback)
    posts = merge_posts(posts)

    titles = title_index(db) if any(p.is_external for p in posts) else {}
    linked = 0
    for p in posts:
        code = shortcode_of(p.url) or ""
        video_id = links.get(p.zernio_post_id or "") or links.get(code)
        friday = paf.get(p.zernio_post_id or "") or paf.get(code)
        if video_id is None and friday is None and (by_title := match_by_title(p, titles)):
            video_id = by_title["id"]
        linked += video_id is not None or friday is not None
        store_post(db, aid, p, video_id, friday, taken)
    if overview.get("lastSync"):
        db.execute("update instagram_accounts set zernio_synced_at = %s where id = %s", (overview["lastSync"], aid))
    record_launch_marks(db, aid, "instagram")
    prune_snapshots(db, aid, "instagram")
    return {"followers": info["followers"], "views_28d": insights["views_28d"], "reels": len(posts), "linked": linked}


def lookup(zc: ZernioClient, post_id: str, zernio_account_id: str) -> InstagramPost | None:
    """Lecture unitaire d'un Reel (id Instagram ou id Zernio) ; None s'il n'est pas encore lisible (202) ou inconnu."""
    try:
        status, body = zc.post_analytics_one(post_id)
    except ZernioError as exc:
        if exc.status == 429:
            raise
        return None
    return parse_post(body, zernio_account_id) if status == 200 else None


def published_by_app(db: Db, zernio_account_id: str) -> list[str]:
    """Publications Zernio de l'appli déjà sorties sur ce compte (vidéos et vendredis de « Paf, j'achète »)."""
    rows = db.fetch_all(
        """select instagram->>'post_id' as post_id from videos
           where instagram->>'account_id' = %s and instagram->>'status' = 'published' and instagram->>'post_id' is not null
           union
           select post_id from paf_posts where account_id = %s and status = 'published' and post_id is not null""",
        (zernio_account_id, zernio_account_id),
    )
    return [r["post_id"] for r in rows]


def video_links(db: Db) -> dict[str, Any]:
    """Publication Zernio (et code du lien du Reel) → vidéo de l'appli, d'après videos.instagram (steps/instagram_publish.py)."""
    out: dict[str, Any] = {}
    for r in db.fetch_all(
        "select id, instagram->>'post_id' as post_id, instagram->>'url' as url from videos where instagram is not null"
    ):
        for k in (r["post_id"], shortcode_of(r["url"])):
            if k:
                out[k] = r["id"]
    return out


def paf_links(db: Db) -> dict[str, Any]:
    """Publication Zernio (et code du lien du Reel) → vendredi de « Paf, j'achète » (paf_posts, steps/paf_publish.py)."""
    out: dict[str, Any] = {}
    for r in db.fetch_all("select friday, post_id, url from paf_posts where post_id is not null or url is not null"):
        for k in (r["post_id"], shortcode_of(r["url"])):
            if k:
                out[k] = r["friday"]
    return out


def store_post(db: Db, account_id: str, p: InstagramPost, video_id: Any, friday: Any, taken: datetime) -> None:
    live = p.sync_status == "live"
    db.execute(
        """insert into instagram_posts (id, account_id, video_id, paf_friday, zernio_post_id, is_external, url, caption,
             thumbnail_url, published_at, duration_s, views, reach, likes, comments, shares, saves, follows, avg_watch_s,
             total_watch_s, skip_rate_pct, sync_status, metrics_at, fetched_at)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           on conflict (id) do update set account_id = excluded.account_id,
             video_id = coalesce(excluded.video_id, instagram_posts.video_id),
             paf_friday = coalesce(excluded.paf_friday, instagram_posts.paf_friday),
             zernio_post_id = coalesce(excluded.zernio_post_id, instagram_posts.zernio_post_id),
             is_external = excluded.is_external and instagram_posts.is_external,
             url = coalesce(excluded.url, instagram_posts.url), caption = coalesce(excluded.caption, instagram_posts.caption),
             -- les liens d'images d'Instagram expirent : le plus récent l'emporte
             thumbnail_url = coalesce(excluded.thumbnail_url, instagram_posts.thumbnail_url),
             published_at = coalesce(excluded.published_at, instagram_posts.published_at),
             duration_s = coalesce(excluded.duration_s, instagram_posts.duration_s),
             -- lu en direct seulement (vues inconnues) : on garde les vues déjà relevées
             views = case when excluded.sync_status = 'live' then instagram_posts.views else excluded.views end,
             reach = coalesce(excluded.reach, instagram_posts.reach),
             likes = greatest(excluded.likes, case when excluded.sync_status = 'live' then instagram_posts.likes else 0 end),
             comments = greatest(excluded.comments,
                                 case when excluded.sync_status = 'live' then instagram_posts.comments else 0 end),
             shares = case when excluded.sync_status = 'live' then instagram_posts.shares else excluded.shares end,
             saves = coalesce(excluded.saves, instagram_posts.saves),
             follows = coalesce(excluded.follows, instagram_posts.follows),
             avg_watch_s = coalesce(excluded.avg_watch_s, instagram_posts.avg_watch_s),
             total_watch_s = coalesce(excluded.total_watch_s, instagram_posts.total_watch_s),
             skip_rate_pct = coalesce(excluded.skip_rate_pct, instagram_posts.skip_rate_pct),
             sync_status = case when excluded.sync_status = 'live' and instagram_posts.sync_status <> 'live'
                                then instagram_posts.sync_status else excluded.sync_status end,
             metrics_at = coalesce(excluded.metrics_at, instagram_posts.metrics_at),
             fetched_at = excluded.fetched_at""",
        (
            p.key,
            account_id,
            video_id,
            friday,
            p.zernio_post_id,
            p.is_external and video_id is None and friday is None,
            p.url,
            p.caption,
            p.thumbnail_url,
            p.published_at,
            p.duration_s,
            p.views,
            p.reach,
            p.likes,
            p.comments,
            p.shares,
            p.saves,
            p.follows,
            p.avg_watch_s,
            p.total_watch_s,
            p.skip_rate_pct,
            p.sync_status,
            p.metrics_at,
            taken,
        ),
    )
    if not live:  # vues pas encore connues : pas de relevé, sinon un faux départ à 0
        db.execute(
            """insert into instagram_post_snapshots (post_id, taken_at, views, reach, likes, comments, shares, saves)
               values (%s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing""",
            (p.key, taken, p.views, p.reach, p.likes, p.comments, p.shares, p.saves),
        )
    if video_id and p.url:  # lien arrivé après la fin du suivi de la publication (steps/instagram_publish.py)
        db.execute(
            """update videos set instagram = jsonb_set(instagram, '{url}', to_jsonb(%s::text)), updated_at = now()
               where id = %s and coalesce(instagram->>'url', '') = ''""",
            (p.url, video_id),
        )
