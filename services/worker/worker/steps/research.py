"""Page Recherche (job « research », docs/60-recherche-niches.md) : la veille des niches, faite par nous, gratuitement.

Une seule tâche, plusieurs actions (payload.action) :
- scan (chaque jour à 10 h, bouton « Relever maintenant ») : pour chaque niche suivie, ses recherches YouTube des Shorts
  les plus vus des 7 derniers jours (et des 30 et 365 derniers jours une fois par semaine), dans la limite des
  recherches du jour (Réglages de la page, 90 sur les 100 de Google) ; fiches et chiffres des vidéos, abonnés et date de
  création des chaînes, médiane des Shorts des chaînes qui surperforment ; relevé de chaque niche (worker/research.py) ;
  classement des nouvelles vidéos (agent classeur) ; phase et note de chaque niche ; vidéos de plus de 30 jours effacées
  si elles ne sont plus rafraîchies (règle développeur YouTube) ; Gemini regarde les meilleures vidéos à reproduire
  (auto_watch) ; le lundi, recommandations du stratège ;
- explore : un sujet tapé dans la page (« mini maisons en conteneur ») devient une niche proposée, relevée tout de suite
  sur 7, 30 et 365 jours ;
- watch : Gemini regarde une vidéo (providers/gemini_video.py) : accroche, structure, pourquoi ça marche, notre idée ;
- adapt : Gemini écrit la version fidèle en français (même sujet, même déroulé, nos mots, docs/64 §3) ;
- reproduce : la version fidèle (mode « fidele », par défaut) ou notre idée (« mecanique ») devient une production
  (scénario pour une histoire jouée, idée d'un de nos thèmes sinon), qui part tout de suite ; le storyboard reste à
  valider dans Création ;
- brief : le stratège écrit ses recommandations (research_reports), dont LA vidéo à faire, et propose des niches ;
- ask : le stratège répond à une question de Luca (réponse dans le résultat de la tâche, docs/64 §4) ;
- discover / discover_shorts : la Découverte, au-delà de nos niches (vidéos longues docs/63 §9, Shorts docs/64 §2).
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import structlog
from googleapiclient.errors import HttpError
from psycopg.types.json import Jsonb

from .. import research as rs
from ..analysis_frames import center_crop_916
from ..lessons import lessons_text
from ..prompts import prompt_text
from ..providers.gemini_video import get_video_llm
from ..providers.llm import get_llm, sees_images
from ..research_agents import (
    ADAPT_PROMPT,
    ASK_PROMPT,
    BRIEF_PROMPT,
    CLASSIFY_PROMPT,
    FORMATS,
    RECIPES,
    WATCH_PROMPT,
    Adaptation,
    AskAnswer,
    LabelBatch,
    ResearchBrief,
    VideoAnalysis,
    VideoLabel,
    adapt_message,
    ask_message,
    brief_message,
    classify_message,
    clean_label,
    watch_message,
)
from ..series import create_production
from ..youtube import public as yp
from ..youtube.client import YouTubeClient
from .base import Context, Step

log = structlog.get_logger(__name__)
PARIS = ZoneInfo("Europe/Paris")

DEFAULTS: dict[str, Any] = {"daily_searches": 90, "auto_watch": 4, "brief_weekday": 1, "min_views": 50_000}
SEARCH_CAP = 100  # compteur Google de search.list (par jour)
KEEP_DAYS = 30  # règle développeur YouTube : une donnée non rafraîchie depuis 30 jours est effacée
REFRESH_DAYS = 45  # vidéos dont on relève les chiffres chaque jour (vitesse, durée de vie)
REFRESH_MAX = 2_500  # 50 unités
MEDIAN_CHANNELS = 30  # chaînes dont on calcule la médiane à chaque relevé (2 unités chacune)
MEDIAN_TTL = timedelta(days=7)
CLASSIFY_BATCH = 16
CLASSIFY_MAX = 192  # 12 appels de la chaîne « default » (Flash-Lite) par relevé
WEEKS_KEPT = 8
EXPLORE_MONTHS = 6  # un sujet exploré : sa courbe sur 6 mois tout de suite (7 recherches)


def research_settings(db: Any) -> dict[str, Any]:
    row = db.fetch_one("select value from app_settings where key = 'research'")
    return DEFAULTS | (row["value"] if row and isinstance(row.get("value"), dict) else {})


def public_client(ctx: Context) -> YouTubeClient:
    """Le jeton d'une de nos chaînes connectées : il lit aussi les vidéos publiques des autres."""
    row = ctx.db.fetch_one(
        """select c.id from channels c where c.is_active and c.youtube_channel_id is not null
           and exists (select 1 from channel_credentials cc where cc.channel_id = c.id) order by c.created_at limit 1"""
    )
    assert row, "Recherche : aucune chaîne YouTube connectée (Réglages → Connecter YouTube)"
    return YouTubeClient.for_channel(ctx.settings, ctx.db, row["id"])


def slugify(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:40] or "niche"


def machine_hours(db: Any) -> dict[str, float]:
    """Temps de fabrication médian d'une vidéo prête, par recette (somme des tâches de job_runs, docs/45)."""
    try:
        rows = db.fetch_all(
            """select s.recipe, percentile_cont(0.5) within group (order by t.total) / 3600.0 as h
               from (select production_id, sum(seconds) as total from job_runs where production_id is not null
                     group by production_id) t
               join productions p on p.id = t.production_id
               join concepts c on c.id = p.concept_id
               join series s on s.id = c.series_id
               where p.status = 'ready' group by s.recipe"""
        )
    except Exception as exc:  # noqa: BLE001 — job_runs absente (migration 0032) : pas de mesure
        log.warning("research.machine_hours", error=str(exc)[:200])
        return {}
    return {r["recipe"]: round(float(r["h"]), 2) for r in rows if r["h"] is not None}


def our_series(db: Any) -> list[dict[str, Any]]:
    return db.fetch_all("select slug, name, recipe from series where is_active order by recipe, slug")


# ---- Fiches YouTube → lignes -------------------------------------------------------------------------------------------


def parse_video(it: dict[str, Any]) -> dict[str, Any] | None:
    """Une vidéo de `videos.list` → ligne de research_videos ; None si ce n'est pas un Short."""
    sn, st, cd, pl = (it.get(k) or {} for k in ("snippet", "statistics", "contentDetails", "player"))
    dur = rs.parse_iso_duration(cd.get("duration"))
    w, h = int(pl.get("embedWidth") or 0) or None, int(pl.get("embedHeight") or 0) or None
    if not rs.is_short(dur, w, h):
        return None
    thumbs = sn.get("thumbnails") or {}
    thumb = next((thumbs[k]["url"] for k in ("high", "medium", "default") if k in thumbs), None)
    return {
        "external_id": it["id"],
        "url": f"https://www.youtube.com/shorts/{it['id']}",
        "title": (sn.get("title") or "")[:300],
        "description": (sn.get("description") or "")[:2000],
        "channel_ext_id": sn.get("channelId"),
        "channel_title": sn.get("channelTitle"),
        "published_at": rs.as_utc(sn.get("publishedAt")),
        "duration_s": dur,
        "lang": sn.get("defaultAudioLanguage") or sn.get("defaultLanguage"),
        "thumbnail_url": thumb,
        "views": int(st.get("viewCount") or 0),
        "likes": int(st.get("likeCount") or 0),
        "comments": int(st.get("commentCount") or 0),
    }


def to_short(v: dict[str, Any]) -> rs.ShortVideo:
    return rs.ShortVideo(
        external_id=v["external_id"],
        title=v.get("title") or "",
        channel_id=v.get("channel_ext_id") or "?",
        published_at=v["published_at"],
        views=int(v.get("views") or 0),
        likes=int(v.get("likes") or 0),
        comments=int(v.get("comments") or 0),
        duration_s=float(v["duration_s"]) if v.get("duration_s") is not None else None,
        channel_subs=v.get("channel_subs"),
        channel_created_at=v.get("channel_created_at"),
        channel_median=float(v["channel_median"]) if v.get("channel_median") else None,
    )


UPSERT = """
insert into research_videos (platform, external_id, url, title, description, channel_ext_id, channel_title, channel_subs,
                             channel_created_at, published_at, duration_s, lang, thumbnail_url, views, likes, comments,
                             stats_at, niche_id)
values ('youtube', %(external_id)s, %(url)s, %(title)s, %(description)s, %(channel_ext_id)s, %(channel_title)s,
        %(channel_subs)s, %(channel_created_at)s, %(published_at)s, %(duration_s)s, %(lang)s, %(thumbnail_url)s,
        %(views)s, %(likes)s, %(comments)s, now(), %(niche_id)s)
on conflict (platform, external_id) do update set
  title = excluded.title, description = excluded.description, channel_title = excluded.channel_title,
  channel_subs = coalesce(excluded.channel_subs, research_videos.channel_subs),
  channel_created_at = coalesce(excluded.channel_created_at, research_videos.channel_created_at),
  thumbnail_url = coalesce(excluded.thumbnail_url, research_videos.thumbnail_url),
  views = excluded.views, likes = excluded.likes, comments = excluded.comments, stats_at = now(),
  niche_id = coalesce(research_videos.niche_id, excluded.niche_id)
returning id, channel_median
"""


def store_videos(
    db: Any, videos: list[dict[str, Any]], channels: dict[str, dict[str, Any]], niche_of: dict[str, str]
) -> dict[str, UUID]:
    """Enregistre les vidéos (et un relevé de leurs chiffres) ; {identifiant YouTube : id en base}."""
    ids: dict[str, UUID] = {}
    for v in videos:
        ch = channels.get(v.get("channel_ext_id") or "") or {}
        v["channel_subs"] = ch.get("subs")
        v["channel_created_at"] = rs.as_utc(ch.get("created_at"))
        row = db.fetch_one(UPSERT, v | {"niche_id": niche_of.get(v["external_id"])})
        assert row
        ids[v["external_id"]] = row["id"]
        v["channel_median"] = row["channel_median"]
        db.execute(
            "insert into research_video_snapshots (video_id, views, likes, comments) values (%s, %s, %s, %s) on conflict do nothing",
            (row["id"], v["views"], v["likes"], v["comments"]),
        )
    return ids


# ---- Relevé -------------------------------------------------------------------------------------------------------------


def first_query(niche: dict[str, Any]) -> dict[str, Any] | None:
    """La recherche principale d'une niche (la première) : celle de sa courbe mois par mois."""
    return next((q for q in (niche["queries"] or []) if (q.get("q") or "").strip()), None)


def months_needed(db: Any, niches: list[dict[str, Any]], now: datetime, n_months: int) -> list[tuple[dict[str, Any], str]]:
    """(niche, mois) de la courbe pas encore mesurés : mois jugeables seulement, le plus récent d'abord, à tour de rôle
    entre les niches (toutes ont vite leurs derniers mois, l'historique vient ensuite)."""
    if not niches or n_months <= 0:
        return []
    # un mois mesuré sur trop peu de Shorts (pas « mature ») se remesure, mais une fois par semaine au plus
    have = {
        (str(r["niche_id"]), r["month"])
        for r in db.fetch_all(
            """select niche_id, month from research_niche_months
               where (mature or taken_at > now() - interval '7 days') and niche_id = any(%s)""",
            ([n["id"] for n in niches],),
        )
    }
    months = [m for m in rs.last_months(now, n_months + 1) if rs.is_mature(m, now)][:n_months]
    return [(n, m) for m in months for n in niches if (str(n["id"]), m) not in have and first_query(n)]


def update_channel_medians(ctx: Context, yt: YouTubeClient, videos: list[dict[str, Any]], min_views: int) -> int:
    """Médiane des Shorts des chaînes dont une vidéo dépasse `min_views` et semble surperformer (vues ÷ abonnés),
    recalculée au plus une fois par semaine ; MEDIAN_CHANNELS chaînes par relevé."""
    now = datetime.now(UTC)
    fresh = {
        r["channel_ext_id"]
        for r in ctx.db.fetch_all(
            "select distinct channel_ext_id from research_videos where channel_median_at > %s", (now - MEDIAN_TTL,)
        )
    }
    ranked = sorted(
        (v for v in videos if v["views"] >= min_views and v.get("channel_ext_id") and v["channel_ext_id"] not in fresh),
        key=lambda v: -(v["views"] / max(v.get("channel_subs") or 0, rs.SUBS_FLOOR)),
    )
    done = 0
    for ch in dict.fromkeys(v["channel_ext_id"] for v in ranked):
        if done >= MEDIAN_CHANNELS:
            break
        shorts = [(rs.as_utc(t), n) for t, n in yp.channel_shorts(yt, ctx.db, ch)]
        med = rs.channel_median([(t, n) for t, n in shorts if t], now)
        ctx.db.execute(
            "update research_videos set channel_median = %s, channel_median_at = now() where channel_ext_id = %s", (med, ch)
        )
        for v in videos:
            if v.get("channel_ext_id") == ch:
                v["channel_median"] = med
        done += 1
    return done


def scan(
    ctx: Context,
    *,
    niche_ids: list[str] | None = None,
    months: int = rs.CURVE_MONTHS,
    budget: int | None = None,
    weekly: bool = True,
    classify_top: int = 0,
) -> dict[str, Any]:
    """Recherches du jour (7 derniers jours, toutes les recherches de chaque niche, une fois par jour), puis, avec ce
    qui reste du budget, les mois de la courbe qui manquent ; puis fiches, chaînes, relevés, classement, notes.
    `weekly=False` : les mois seulement (la Découverte des Shorts) ; `classify_top` : les N Shorts les plus vus de
    chaque niche relevée sont classés en priorité (sa faisabilité en dépend)."""
    db, now = ctx.db, datetime.now(UTC)
    cfg = research_settings(db)
    used = yp.searches_today(db)
    left = min(int(cfg["daily_searches"]) - used if budget is None else budget, SEARCH_CAP - used)
    if niche_ids:
        niches = db.fetch_all("select * from research_niches where id::text = any(%s)", (niche_ids,))
    else:
        niches = db.fetch_all(
            "select * from research_niches where status = 'active' order by last_scan_at asc nulls first, created_at"
        )
    if left <= 0:
        ctx.log("Plus de recherche YouTube disponible aujourd'hui", level="warning", used=used)
        return {"searches": 0, "skipped": "quota du jour"}

    # (niche, clé, recherche, après, avant) : clé 7 = « 7 derniers jours », sinon le mois de la courbe
    tasks: list[tuple[dict[str, Any], int | str, dict[str, Any], datetime, datetime | None]] = []
    for n in niches if weekly else []:
        if not niche_ids and n["last_scan_at"] and now - n["last_scan_at"] < timedelta(hours=20):
            continue  # déjà relevée aujourd'hui (bouton pressé deux fois)
        tasks.extend((n, 7, q, now - timedelta(days=7), None) for q in n["queries"] or [] if (q.get("q") or "").strip())
    tasks = tasks[:left]
    for n, m in months_needed(db, niches, now, months)[: max(0, left - len(tasks))]:
        start, end = rs.month_bounds(m)
        q = first_query(n)
        assert q
        tasks.append((n, m, q, start, end))

    yt = public_client(ctx)
    labels = {str(n["id"]): n["label"] for n in niches}
    found: dict[str, dict[int | str, list[tuple[str, int]]]] = {}  # niche → clé → [(id YouTube, rang)]
    searches = 0
    quota_hit = False
    for i, (n, key, q, after, before) in enumerate(tasks):
        what = "7 derniers jours" if key == 7 else f"mois {key}"
        ctx.progress(5 + int(35 * i / max(len(tasks), 1)), f"Recherche YouTube : {n['label']} ({what})")
        try:
            hits = yp.search_shorts(yt, db, q["q"], after=after, before=before, lang=q.get("lang"), region=q.get("region"))
        except HttpError as exc:
            if exc.resp is not None and exc.resp.status in (403, 429):
                quota_hit = True
                ctx.log("Quota de recherche YouTube atteint", level="warning", error=str(exc)[:200])
                break
            raise
        searches += 1
        found.setdefault(str(n["id"]), {}).setdefault(key, []).extend((vid, r) for r, vid in enumerate(hits, start=1))

    all_ids = list(dict.fromkeys(vid for by_k in found.values() for hits in by_k.values() for vid, _ in hits))
    ctx.progress(45, f"Chiffres de {len(all_ids)} vidéos")
    videos = [p for it in yp.video_details(yt, db, all_ids) if (p := parse_video(it))]
    by_id = {v["external_id"]: v for v in videos}
    channels = yp.channel_details(yt, db, [v["channel_ext_id"] for v in videos])
    niche_of: dict[str, str] = {}
    for nid, by_k in found.items():
        for hits in by_k.values():
            for vid, _ in hits:
                niche_of.setdefault(vid, nid)
    ctx.progress(55, "Enregistrement")
    db_ids = store_videos(db, videos, channels, niche_of)
    min_views = int(cfg["min_views"])
    ctx.progress(60, "Médiane des chaînes qui surperforment")
    medians = update_channel_medians(ctx, yt, videos, min_views)

    # Relevé de chaque niche : les 7 derniers jours, et chaque mois mesuré de sa courbe
    months_done = 0
    for nid, by_k in found.items():
        for key, hits in by_k.items():
            best: dict[str, int] = {}
            for vid, rank in hits:
                best[vid] = min(rank, best.get(vid, rank))
            shorts = [to_short(by_id[vid]) for vid in best if vid in by_id]
            stats = rs.window_stats(shorts, 7 if key == 7 else 30, now)
            if key == 7:
                db.execute(
                    """insert into research_niche_snapshots (niche_id, taken_on, stats) values (%s, current_date, %s)
                       on conflict (niche_id, taken_on, window_days) do update set stats = excluded.stats""",
                    (nid, Jsonb(stats.to_json())),
                )
            else:
                db.execute(
                    """insert into research_niche_months (niche_id, month, stats, mature) values (%s, %s, %s, %s)
                       on conflict (niche_id, month) do update set stats = excluded.stats, mature = excluded.mature,
                         taken_at = now()""",
                    (nid, key, Jsonb(stats.to_json()), rs.month_ok(stats)),
                )
                months_done += 1
            for vid, rank in best.items():
                if vid in db_ids:
                    db.execute(
                        """insert into research_video_niches (video_id, niche_id, best_rank) values (%s, %s, %s)
                           on conflict (video_id, niche_id) do update set last_seen_at = now(),
                             best_rank = least(research_video_niches.best_rank, excluded.best_rank)""",
                        (db_ids[vid], nid, rank),
                    )
        if 7 in by_k:
            db.execute("update research_niches set last_scan_at = now() where id = %s", (nid,))

    ctx.progress(65, "Chiffres des vidéos suivies")
    refreshed = refresh_tracked(ctx, yt)
    if classify_top:
        ctx.progress(70, "Classement des Shorts les plus vus de chaque niche")
        labelled = classify_new(ctx, min_views, ids=top_of_niches(db, list(found), classify_top, min_views))
    else:
        ctx.progress(70, "Classement des nouvelles vidéos")
        labelled = classify_new(ctx, min_views)
    ctx.progress(90, "Phase et note des niches")
    market = market_of(db)
    for nid in found:
        summarize_niche(db, nid, min_views, now, market)
    pruned = prune(db)
    prune_thumbs(ctx)
    watched = plan_watches(ctx, int(cfg["auto_watch"]), min_views) if not niche_ids else 0
    briefed = plan_brief(ctx, int(cfg["brief_weekday"])) if not niche_ids else False
    log.info("research.scan", searches=searches, niches=[labels[k] for k in found][:10], months=months_done)
    return {
        "searches": searches,
        "videos": len(videos),
        "niches": len(found),
        "months": months_done,
        "months_left": len(months_needed(db, niches, now, months)),
        "channel_medians": medians,
        "refreshed": refreshed,
        "classified": labelled,
        "pruned": pruned,
        "watch_queued": watched,
        "brief_queued": briefed,
        "quota_hit": quota_hit,
    }


def refresh_tracked(ctx: Context, yt: YouTubeClient) -> int:
    """Chiffres du jour des vidéos récentes ou gardées que la recherche n'a pas revues : leur vitesse se mesure d'un jour
    à l'autre, et une donnée rafraîchie reste dans la règle des 30 jours."""
    rows = ctx.db.fetch_all(
        """select id, external_id from research_videos
           where platform = 'youtube' and stats_at < now() - interval '20 hours'
             and (published_at > now() - make_interval(days => %s) or status in ('shortlisted', 'reproduced')
                  or analysis is not null)
           order by stats_at limit %s""",
        (REFRESH_DAYS, REFRESH_MAX),
    )
    if not rows:
        return 0
    ids = {r["external_id"]: r["id"] for r in rows}
    n = 0
    for it in yp.video_details(yt, ctx.db, list(ids)):
        st = it.get("statistics") or {}
        views, likes, comments = int(st.get("viewCount") or 0), int(st.get("likeCount") or 0), int(st.get("commentCount") or 0)
        vid = ids[it["id"]]
        ctx.db.execute(
            "update research_videos set views = %s, likes = %s, comments = %s, stats_at = now() where id = %s",
            (views, likes, comments, vid),
        )
        ctx.db.execute(
            "insert into research_video_snapshots (video_id, views, likes, comments) values (%s, %s, %s, %s) on conflict do nothing",
            (vid, views, likes, comments),
        )
        n += 1
    return n


def prune(db: Any) -> int:
    """Règle développeur YouTube : les données non rafraîchies depuis 30 jours sont effacées ; relevés de plus de 90 j."""
    n = db.execute(
        "delete from research_videos where stats_at < now() - make_interval(days => %s) and status not in ('shortlisted', 'reproduced')",
        (KEEP_DAYS,),
    )
    db.execute("delete from research_video_snapshots where taken_at < now() - interval '90 days'")
    return n


def prune_thumbs(ctx: Context) -> None:
    """Miniatures gardées pour le classement : 30 jours, comme les fiches."""
    limit = datetime.now().timestamp() - KEEP_DAYS * 86_400
    for f in (ctx.settings.data_dir / "research" / "thumbs").glob("*.jpg"):
        if f.stat().st_mtime < limit:
            f.unlink(missing_ok=True)


# ---- Classement ---------------------------------------------------------------------------------------------------------


def thumb_path(ctx: Context, external_id: str) -> Path | None:
    """Miniature YouTube recadrée en 9:16 (la vidéo verticale est au centre de l'image 4:3), gardée 30 jours."""
    from PIL import Image

    target = ctx.settings.data_dir / "research" / "thumbs" / f"{external_id}.jpg"
    if target.exists():
        return target
    try:
        r = httpx.get(f"https://i.ytimg.com/vi/{external_id}/hqdefault.jpg", timeout=20)
    except httpx.HTTPError:
        return None
    if r.status_code != 200 or len(r.content) < 2000:
        return None
    import io

    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(io.BytesIO(r.content)) as im:
        center_crop_916(im.convert("RGB")).resize((270, 480)).save(target, "JPEG", quality=85)
    return target


def top_of_niches(db: Any, niche_ids: list[str], n: int, min_views: int) -> list[str]:
    """Les `n` Shorts les plus vus de chaque niche, pas encore classés (la faisabilité d'une niche se lit sur eux)."""
    rows = db.fetch_all(
        """select id from (
             select v.id, v.classification, row_number() over (partition by vn.niche_id order by v.views desc) as rk
             from research_video_niches vn join research_videos v on v.id = vn.video_id
             where vn.niche_id::text = any(%s) and v.views >= %s) t
           where rk <= %s and classification is null""",
        (niche_ids, min_views, n),
    )
    return list(dict.fromkeys(str(r["id"]) for r in rows))


def classify_new(ctx: Context, min_views: int, ids: list[str] | None = None) -> int:
    """Classe les vidéos pas encore classées : les plus vues d'abord, ou celles de `ids`."""
    if ids is not None and not ids:
        return 0
    rows = ctx.db.fetch_all(
        """select id, external_id, title, description, channel_title, channel_subs, channel_median, views, published_at,
                  duration_s
           from research_videos where classification is null and views >= %s and (%s::text[] is null or id::text = any(%s))
           order by views desc limit %s""",
        (min_views, ids, ids, CLASSIFY_MAX if ids is None else len(ids)),
    )
    if not rows:
        return 0
    series = our_series(ctx.db)
    llm = get_llm(ctx.settings, ctx.db)
    system = prompt_text(ctx.db, "research_classify", CLASSIFY_PROMPT)
    now = datetime.now(UTC)
    done = 0
    for start in range(0, len(rows), CLASSIFY_BATCH):
        batch = rows[start : start + CLASSIFY_BATCH]
        items = []
        for i, r in enumerate(batch, start=1):
            ratio, _ = rs.outlier(
                rs.ShortVideo(
                    r["external_id"],
                    r["title"],
                    "?",
                    r["published_at"] or now,
                    int(r["views"] or 0),
                    channel_subs=r["channel_subs"],
                    channel_median=float(r["channel_median"]) if r["channel_median"] else None,
                )
            )
            items.append(
                {
                    "ref": f"V{i}",
                    "title": r["title"],
                    "channel": r["channel_title"],
                    "views": int(r["views"] or 0),
                    "age_d": rs.age_days(r["published_at"] or now, now),
                    "duration_s": round(float(r["duration_s"])) if r["duration_s"] else None,
                    "outlier": ratio,
                    "description": (r["description"] or "").replace("\n", " ")[:160],
                }
            )
        images = [p for r in batch if (p := thumb_path(ctx, r["external_id"]))]
        with_images = len(images) == len(batch) and any(sees_images(p) for p in getattr(llm, "chain", []))
        try:
            out = llm.complete_json(
                system, classify_message(items, series, with_images), LabelBatch, images=images if with_images else ()
            )
        except Exception as exc:  # noqa: BLE001 — un lot raté ne bloque pas le relevé ; il sera repris au prochain
            ctx.log("Classement d'un lot raté", level="warning", error=str(exc)[:300])
            continue
        labels: dict[str, VideoLabel] = {lab.ref.strip().upper(): lab for lab in out.videos}
        for i, r in enumerate(batch, start=1):
            lab = labels.get(f"V{i}")
            if lab is None:
                continue
            ctx.db.execute("update research_videos set classification = %s where id = %s", (Jsonb(clean_label(lab)), r["id"]))
            done += 1
        ctx.progress(70 + int(18 * (start + len(batch)) / len(rows)), f"Classement : {done} vidéos")
    return done


# ---- Une niche : phase, note, formats -----------------------------------------------------------------------------------


def market_of(db: Any) -> float | None:
    """L'élan de tout le marché : les courbes des niches suivies (worker/research.market_ratio)."""
    curves: dict[str, dict[str, rs.WindowStats]] = {}
    for r in db.fetch_all(
        """select m.niche_id, m.month, m.stats from research_niche_months m join research_niches n on n.id = m.niche_id
           where m.mature and n.status = 'active' order by m.month desc"""
    ):
        c = curves.setdefault(str(r["niche_id"]), {})
        if len(c) < rs.CURVE_MONTHS:
            c[r["month"]] = rs.WindowStats.from_json(r["stats"])
    return rs.market_ratio(list(curves.values()))


def summarize_niche(db: Any, niche_id: str, min_views: int, now: datetime, market: float | None = None) -> dict[str, Any]:
    """Phase, note, courbe, formats et effort d'une niche, rangés dans research_niches.summary pour la page."""
    weekly: dict[tuple[int, int], rs.WindowStats] = {}
    for s in db.fetch_all(
        "select taken_on, stats from research_niche_snapshots where niche_id = %s order by taken_on", (niche_id,)
    ):
        weekly[tuple(s["taken_on"].isocalendar()[:2])] = rs.WindowStats.from_json(s["stats"])  # dernier relevé de la semaine
    weeks = [weekly[k] for k in sorted(weekly)][-WEEKS_KEPT:]
    week = weeks[-1] if weeks else None
    months = {
        r["month"]: rs.WindowStats.from_json(r["stats"])
        for r in db.fetch_all(
            "select month, stats from research_niche_months where niche_id = %s and mature order by month desc limit %s",
            (niche_id, rs.CURVE_MONTHS),
        )
    }
    phase, reason = rs.niche_phase(months, weeks, now, market)
    vids = db.fetch_all(
        """select v.classification from research_video_niches vn join research_videos v on v.id = vn.video_id
           where vn.niche_id = %s and v.views >= %s and v.classification is not null order by v.views desc limit 30""",
        (niche_id, min_views),
    )
    efforts = [int(c["classification"]["effort"]) for c in vids if c["classification"].get("effort")]
    effort = round(statistics.mean(efforts), 1) if efforts else None
    formats = [
        f for f, _ in Counter(c["classification"].get("format") for c in vids if c["classification"].get("format")).most_common(3)
    ]
    last = months[max(months)] if months else None
    peak = max(months, key=lambda k: months[k].median_views or 0) if months else None
    summary = {
        "phase": phase,
        "phase_reason": reason,
        "score_parts": rs.niche_score(last or week, phase, effort),
        "effort": effort,
        "formats": formats,
        "age_months": rs.niche_age_months(months, now),
        "peak_month": peak,
        "last_month": max(months) if months else None,
        "median_views_month": last.median_views if last else None,
        "sample_month": last.n if last else None,  # Shorts du mois mesuré (50 au plus : une recherche YouTube)
        "market": market,
        "hits_month": last.hits if last else None,
        "open_share_month": last.open_share if last else None,
        "concentration_month": last.concentration if last else None,
        "median_vpd_7": week.median_vpd if week else None,
        "median_views_7": week.median_views if week else None,
        "hits_7": week.hits if week else None,
        "open_share_7": week.open_share if week else None,
        "curve": [
            {"month": k, "median_views": w.median_views, "hits": w.hits, "open_share": w.open_share, "channels": w.channels}
            for k, w in sorted(months.items())
        ],
        "weekly": [{"median_vpd": w.median_vpd, "hits": w.hits} for w in weeks],
        "classified": len(vids),
        "updated_at": now.isoformat(),
    }
    db.execute("update research_niches set summary = %s where id = %s", (Jsonb(summary), niche_id))
    return summary


# ---- Gemini regarde -----------------------------------------------------------------------------------------------------


def remake_candidates(db: Any, min_views: int, limit: int) -> list[dict[str, Any]]:
    """Les vidéos à reproduire, de la meilleure à la moins bonne (worker/research.remake_score) ; celles dont le titre
    n'est pas en alphabet latin (hindi, bengali…) passent après : elles se refont mal en français."""
    rows = db.fetch_all(
        """select id, external_id, title, channel_ext_id, channel_subs, channel_median, published_at, views, likes,
                  comments, classification, analysis, lang, niche_id
           from research_videos
           where status in ('new', 'shortlisted') and views >= %s and published_at > now() - interval '60 days'
             and coalesce((classification->>'effort')::int, 3) <= 3""",
        (min_views,),
    )
    now = datetime.now(UTC)
    scored = []
    for r in rows:
        v = to_short(r | {"external_id": r["external_id"]})
        effort = (r["classification"] or {}).get("effort")
        score = rs.remake_score(v, now, int(effort) if effort else None)
        scored.append((score if rs.mostly_latin(r["title"] or "") else score * 0.7, r))
    scored.sort(key=lambda x: -x[0])
    return [r | {"score": s} for s, r in scored[:limit]]


def plan_watches(ctx: Context, n: int, min_views: int) -> int:
    if n <= 0:
        return 0
    queued = {
        str(r["vid"])
        for r in ctx.db.fetch_all(
            "select payload->>'video_id' as vid from jobs where type = 'research' and status in ('queued', 'running') and payload->>'action' = 'watch'"
        )
    }
    picked = [r for r in remake_candidates(ctx.db, min_views, 40) if r["analysis"] is None and str(r["id"]) not in queued][:n]
    for r in picked:
        ctx.enqueue("research", payload={"action": "watch", "video_id": str(r["id"]), "source": "relevé"}, priority=130)
    return len(picked)


def clean_analysis(a: VideoAnalysis, series: list[dict[str, Any]]) -> dict[str, Any]:
    d = a.model_dump()
    fmt = next((f for f in FORMATS if f.lower() == a.format.strip().lower()), "autre")
    recipe = a.recipe.strip().lower()
    slugs = {s["slug"] for s in series}
    d.update(
        format=fmt,
        recipe=recipe if recipe in RECIPES else "none",
        series=a.series if a.series in slugs else "",
        effort=max(1, min(5, int(a.effort or 3))),
    )
    return d


def watch(ctx: Context, video_id: str) -> dict[str, Any]:
    row = ctx.db.fetch_one("select * from research_videos where id = %s", (video_id,))
    assert row, f"vidéo de recherche introuvable : {video_id}"
    url = f"https://www.youtube.com/watch?v={row['external_id']}"
    llm = get_video_llm(ctx.settings, ctx.db, url)
    assert llm, "Recherche : aucune clé Gemini (Réglages → IA)"
    ctx.progress(20, f"Gemini regarde « {row['title'][:60]} »")
    series = our_series(ctx.db)
    out = llm.complete_json(
        prompt_text(ctx.db, "research_watch", WATCH_PROMPT), watch_message(row, series, machine_hours(ctx.db)), VideoAnalysis
    )
    analysis = clean_analysis(out, series) | {"model": llm.used[-1] if llm.used else None}
    ctx.db.execute("update research_videos set analysis = %s, analysis_at = now() where id = %s", (Jsonb(analysis), video_id))
    if row["classification"] is None:  # vidéo ajoutée à la main ou pas encore classée : l'analyse classe aussi
        ctx.db.execute(
            "update research_videos set classification = %s where id = %s",
            (
                Jsonb(
                    {k: analysis[k] for k in ("format", "recipe", "series", "effort")} | {"angle": analysis["hook_visual"][:240]}
                ),
                video_id,
            ),
        )
    return {"video_id": video_id, "model": analysis["model"], "recipe": analysis["recipe"], "effort": analysis["effort"]}


# ---- Reproduire ---------------------------------------------------------------------------------------------------------

STYLE_KEYS = ("cinematic_real", "pixar_human", "dreamworks_animal", "pixar_fruit")
SPEECH_KEYS = ("muet", "repliques", "dialogues")


def adapt(ctx: Context, video_id: str) -> dict[str, Any]:
    """La version fidèle en français (agent research_adapt, Gemini regarde la vidéo) : rangée dans
    research_videos.adaptation, montrée dans « Pourquoi ça marche », utilisée par « Refaire fidèlement »."""
    row = ctx.db.fetch_one("select * from research_videos where id = %s", (video_id,))
    assert row, f"vidéo de recherche introuvable : {video_id}"
    url = f"https://www.youtube.com/watch?v={row['external_id']}"
    llm = get_video_llm(ctx.settings, ctx.db, url)
    assert llm, "Recherche : aucune clé Gemini (Réglages → IA)"
    ctx.progress(30, f"Version fidèle de « {row['title'][:60]} »")
    series = our_series(ctx.db)
    out = llm.complete_json(
        prompt_text(ctx.db, "research_adapt", ADAPT_PROMPT), adapt_message(row, series, row["analysis"]), Adaptation
    )
    ad = out.model_dump()
    recipe = ad["recipe"].strip().lower()
    slugs = {s["slug"] for s in series}
    ad.update(
        recipe=recipe if recipe in RECIPES else "none",
        series=ad["series"] if ad["series"] in slugs else "",
        duration_s=max(15, min(90, int(ad["duration_s"] or 45))),
        model=llm.used[-1] if llm.used else None,
    )
    ctx.db.execute("update research_videos set adaptation = %s, adaptation_at = now() where id = %s", (Jsonb(ad), video_id))
    return {"video_id": video_id, "model": ad["model"], "recipe": ad["recipe"]}


def faithful_text(row: dict[str, Any], ad: dict[str, Any]) -> str:
    """La version fidèle mise en prémisse (thèmes) ou en scénario (« Mon scénario ») : le conteur et le scénariste
    gardent le sujet et le déroulé, et réécrivent à notre façon."""
    views = f"{int(row.get('views') or 0):,}".replace(",", " ")
    beats = "\n".join(
        f"- {b.get('t', '')} : {b.get('image', '')}" + (f" — « {b['words']} »" if b.get("words") else "")
        for b in ad.get("beats") or []
    )
    parts = [
        f"VERSION FIDÈLE d'un Short qui a marché (« {row['title']} », {row.get('channel_title') or '?'}, {views} vues) : "
        "même sujet, même déroulé, même accroche, même fin, avec nos mots en français et nos images. Ne pas changer "
        "l'histoire ; reformuler chaque phrase.",
        f"Sujet : {ad.get('subject') or ''}",
        f"Ouverture : {ad.get('hook') or ''}",
        f"Déroulé :\n{beats}" if beats else "",
        f"Texte de la voix off (déjà réécrit avec nos mots) :\n{ad['narration']}" if ad.get("narration") else "",
        f"Fin : {ad['ending']}" if ad.get("ending") else "",
        "Faits à vérifier avant de les dire : " + " ; ".join(ad["facts_to_check"]) if ad.get("facts_to_check") else "",
    ]
    return "\n".join(p for p in parts if p)


def remake_premise(row: dict[str, Any], a: dict[str, Any]) -> str:
    r = a.get("remake") or {}
    parts = [r.get("premise") or ""]
    if r.get("hook"):
        parts.append(f"Ouverture : {r['hook']}")
    if r.get("keep"):
        parts.append("Mécanique reprise d'un Short qui a marché : " + " ; ".join(r["keep"]))
    if r.get("change"):
        parts.append("Différences voulues : " + " ; ".join(r["change"]))
    views = f"{int(row.get('views') or 0):,}".replace(",", " ")  # 36 348 937
    parts.append(
        f"Modèle : « {row['title']} » ({row.get('channel_title') or '?'}, {views} vues). "
        "Ne rien en recopier : même mécanique, histoire et personnages nouveaux."
    )
    return "\n".join(p for p in parts if p)


def reproduce(ctx: Context, video_id: str, channel_id: str | None = None, mode: str = "fidele") -> dict[str, Any]:
    """Notre version part en fabrication. `mode` : « fidele » (même sujet, même déroulé, nos mots en français : le choix
    de Luca, docs/64 §3) ou « mecanique » (même mécanique, histoire et personnages nouveaux, docs/60)."""
    db = ctx.db
    row = db.fetch_one("select * from research_videos where id = %s", (video_id,))
    assert row, f"vidéo de recherche introuvable : {video_id}"
    if row["concept_id"]:
        return {"concept_id": str(row["concept_id"]), "already": True}
    if not row["analysis"]:
        watch(ctx, video_id)
        row = db.fetch_one("select * from research_videos where id = %s", (video_id,))
        assert row
    if mode == "fidele" and not row["adaptation"]:
        adapt(ctx, video_id)
        row = db.fetch_one("select * from research_videos where id = %s", (video_id,))
        assert row
    a = row["analysis"] or {}
    ad = row["adaptation"] if mode == "fidele" else None
    r = a.get("remake") or {}
    src = ad or r  # titre, ouverture, style, paroles, durée
    recipe = (ad or a).get("recipe") or "none"
    wanted = (ad or a).get("series") or ""
    series = None
    if recipe not in ("drama", "none"):
        series = db.fetch_one(
            "select id, slug from series where is_active and (slug = %s or recipe = %s) order by (slug = %s) desc, weight desc limit 1",
            (wanted, recipe, wanted),
        )
    ctx.progress(60, "Notre version part en fabrication")
    if series is None:  # histoire jouée, ou rien d'approchant : l'équipe « Mon scénario » (docs/59)
        if ad:
            text = ((ad.get("scenario") or "").strip() + "\n\n" + faithful_text(row, ad)).strip()
        else:
            text = (r.get("scenario") or "").strip() or remake_premise(row, a)
            text += (
                f"\n\n(Inspiré de la mécanique d'un Short qui a marché : « {row['title']} ». Histoire et personnages nouveaux.)"
            )
        style = src.get("style") if src.get("style") in STYLE_KEYS else "auto"
        speech = src.get("speech") if src.get("speech") in SPEECH_KEYS else "auto"
        duration = max(20, min(90, int(src.get("duration_s") or 45)))
        prod = db.fetch_one(
            "select submit_scenario(%s, %s, %s, %s, %s, %s) as id", (channel_id, text, src.get("title"), style, speech, duration)
        )
        assert prod
        pid = prod["id"]
        concept = db.fetch_one("select concept_id from productions where id = %s", (pid,))
        cid = concept["concept_id"] if concept else None
    else:
        c = db.fetch_one(
            """insert into concepts (title, hook, premise, source, series_id, channel_id, status, research_video_id)
               values (%s, %s, %s, 'clone', %s, coalesce(%s::uuid, (select id from channels where is_active order by created_at limit 1)),
                       'proposed', %s) returning id""",
            (
                (src.get("title") or row["title"])[:200],
                src.get("hook") or None,
                faithful_text(row, ad) if ad else remake_premise(row, a),
                series["id"],
                channel_id,
                video_id,
            ),
        )
        assert c
        cid = c["id"]
        pid, _ = create_production(db, cid, priority=50, channel_id=channel_id)
    if cid:
        db.execute("update concepts set research_video_id = %s where id = %s", (video_id, cid))
    db.execute("update research_videos set status = 'reproduced', concept_id = %s where id = %s", (cid, video_id))
    return {
        "production_id": str(pid),
        "concept_id": str(cid) if cid else None,
        "series": series["slug"] if series else "mes_scenarios",
        "mode": "fidele" if ad else "mecanique",
    }


# ---- Explorer un sujet --------------------------------------------------------------------------------------------------


def explore(ctx: Context, q: str, lang: str | None) -> dict[str, Any]:
    q = q.strip()
    assert len(q) >= 3, "sujet trop court"
    lang = lang if lang in ("fr", "en") else "en"
    region = "FR" if lang == "fr" else "US"
    slug = "explore_" + slugify(q)
    row = ctx.db.fetch_one(
        """insert into research_niches (slug, label, queries, status, origin)
           values (%s, %s, %s, 'proposed', 'explore')
           on conflict (slug) do update set queries = excluded.queries returning id""",
        (slug, q[:80], Jsonb([{"q": q, "lang": lang, "region": region}])),
    )
    assert row
    out = scan(ctx, niche_ids=[str(row["id"])], months=EXPLORE_MONTHS, budget=1 + EXPLORE_MONTHS)
    return out | {"niche_id": str(row["id"])}


# ---- Le stratège --------------------------------------------------------------------------------------------------------


def plan_brief(ctx: Context, weekday: int) -> bool:
    """Le jour choisi (1 = lundi), après le relevé : recommandations, si la dernière date de plus de 6 jours."""
    if datetime.now(PARIS).isoweekday() != weekday:
        return False
    if ctx.db.fetch_one("select 1 from research_reports where created_at > now() - interval '6 days'"):
        return False
    if ctx.db.fetch_one(
        "select 1 from jobs where type = 'research' and status in ('queued', 'running') and payload->>'action' = 'brief'"
    ):
        return False
    ctx.enqueue(
        "research",
        payload={"action": "brief", "source": "hebdomadaire"},
        priority=135,
        run_after=datetime.now(UTC) + timedelta(minutes=30),  # après les vidéos que Gemini regarde
    )
    return True


def strategist_inputs(db: Any, n_videos: int, n_found: int = 15) -> tuple[list[dict[str, Any]], str, dict[str, str]]:
    """Ce que lit le stratège : les niches relevées (les suivies d'abord, puis les meilleures découvertes), les vidéos à
    reproduire avec leurs références V1…, nos temps de fabrication et nos leçons. (niches, message, {V1 : id})."""
    cfg = research_settings(db)
    niches = db.fetch_all(
        """select id, slug, label, recipe, summary, origin from research_niches
           where status in ('active', 'proposed') and summary is not null"""
    )
    assert niches, "Recherche : aucune niche relevée (lancer d'abord un relevé)"
    niches.sort(key=lambda n: -((n["summary"] or {}).get("score_parts") or {}).get("score", 0))
    ours = [n for n in niches if n["origin"] != "discover"][:25]
    found = [n for n in niches if n["origin"] == "discover"][:n_found]
    labels = {str(n["id"]): n["label"] for n in niches}
    cands = remake_candidates(db, int(cfg["min_views"]), n_videos)
    now = datetime.now(UTC)
    videos, refs = [], {}
    for i, r in enumerate(cands, start=1):
        cl, an = r["classification"] or {}, r["analysis"] or {}
        ratio, _ = rs.outlier(to_short(r))
        videos.append(
            {
                "ref": f"V{i}",
                "title": r["title"],
                "niche": labels.get(str(r["niche_id"])) if r["niche_id"] else None,
                "lang": r["lang"],
                "views": r["views"],
                "outlier": ratio,
                "age_d": rs.age_days(r["published_at"], now),
                "format": cl.get("format"),
                "effort": cl.get("effort"),
                "angle": cl.get("angle"),
                "why": " ; ".join(an.get("why_it_works") or [])[:400] or None,
            }
        )
        refs[f"V{i}"] = str(r["id"])
    message = brief_message(ours + found, videos, machine_hours(db), lessons_text(db, "idea"))
    return ours + found, message, refs


def brief(ctx: Context) -> dict[str, Any]:
    db = ctx.db
    niches, message, refs = strategist_inputs(db, 15)
    ctx.progress(30, "Le stratège lit la veille")
    llm = get_llm(ctx.settings, db, writer=True)
    out = llm.complete_json(prompt_text(db, "research_brief", BRIEF_PROMPT), message, ResearchBrief)
    report = out.model_dump()
    slugs = {n["slug"] for n in niches}
    report["niches"] = [p for p in report["niches"] if p["niche"] in slugs]
    for p in report["remakes"]:
        p["video_id"] = refs.get(p["ref"].strip().upper())
    report["remakes"] = [p for p in report["remakes"] if p.get("video_id")]
    nv = report.get("next_video")
    if nv:
        nv["video_id"] = refs.get(nv["ref"].strip().upper())
        if not nv["video_id"]:
            report["next_video"] = None
    added = 0
    for nn in report["new_niches"][:3]:
        queries = [
            {"q": q, "lang": "fr" if i else "en", "region": "FR" if i else "US"}
            for i, q in enumerate(nn["queries"][:2])
            if q.strip()
        ]
        if not queries:
            continue
        added += db.execute(
            """insert into research_niches (slug, label, description, queries, status, origin) values (%s, %s, %s, %s, 'proposed', 'agent')
               on conflict (slug) do nothing""",
            (
                "agent_" + slugify(nn["label"]),
                nn["label"][:80],
                (nn.get("description") or nn.get("why") or "")[:400],
                Jsonb(queries),
            ),
        )
    picked = [p["video_id"] for p in report["remakes"]] + ([report["next_video"]["video_id"]] if report.get("next_video") else [])
    for vid in picked:
        db.execute("update research_videos set status = 'shortlisted' where id = %s and status = 'new'", (vid,))
    row = db.fetch_one(
        "insert into research_reports (report, model) values (%s, %s) returning id",
        (Jsonb(report), llm.used[-1] if llm.used else None),
    )
    assert row
    return {"report_id": str(row["id"]), "niches": len(report["niches"]), "remakes": len(report["remakes"]), "new_niches": added}


def ask(ctx: Context, question: str) -> dict[str, Any]:
    """Une question de Luca au stratège (Recherche → Recommandations) : la réponse est rangée dans le résultat de la
    tâche, avec les vidéos et les niches citées ; les 3 derniers échanges servent de contexte."""
    db = ctx.db
    question = question.strip()[:1000]
    assert question, "question vide"
    niches, context, refs = strategist_inputs(db, 20, n_found=100)  # une question peut viser n'importe laquelle
    history = db.fetch_all(
        """select payload->>'question' as question, result->>'answer' as answer from jobs
           where type = 'research' and payload->>'action' = 'ask' and status = 'done' order by finished_at desc limit 3"""
    )
    report = db.fetch_one("select report->>'headline' as h from research_reports order by created_at desc limit 1")
    ctx.progress(30, "Le stratège réfléchit")
    llm = get_llm(ctx.settings, db, writer=True)
    out = llm.complete_json(
        prompt_text(db, "research_ask", ASK_PROMPT),
        ask_message(context, report["h"] if report else None, list(reversed(history)), question),
        AskAnswer,
    )
    slugs = {n["slug"] for n in niches}
    return {
        "question": question,
        "answer": out.answer.strip(),
        "video_ids": [v for ref in out.video_refs[:4] if (v := refs.get(ref.strip().upper()))],
        "niches": [s for s in out.niches if s in slugs][:4],
        "model": llm.used[-1] if llm.used else None,
    }


class ResearchStep(Step):
    type = "research"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        p = ctx.job.payload or {}
        action = p.get("action", "scan")
        if action == "scan":
            return scan(ctx, niche_ids=p.get("niches"))
        if action == "explore":
            return explore(ctx, str(p.get("q") or ""), p.get("lang"))
        if action == "watch":
            out = watch(ctx, str(p["video_id"]))
            if p.get("then") == "reproduce":
                out |= reproduce(ctx, str(p["video_id"]), p.get("channel_id"), str(p.get("mode") or "fidele"))
            return out
        if action == "adapt":
            return adapt(ctx, str(p["video_id"]))
        if action == "reproduce":
            return reproduce(ctx, str(p["video_id"]), p.get("channel_id"), str(p.get("mode") or "fidele"))
        if action == "brief":
            return brief(ctx)
        if action == "ask":
            return ask(ctx, str(p.get("question") or ""))
        if action == "discover_shorts":  # Découverte des niches Shorts hors des nôtres (docs/64 §2)
            from ..discovery_shorts import discover_shorts

            return discover_shorts(ctx, p.get("budget"))
        if action == "discover":  # Découverte : les niches qui rapportent, au-delà des nôtres (docs/63 §9)
            from ..discovery import discover

            budget = int(p.get("budget") or research_settings(ctx.db).get("discover_searches", 25))
            return discover(ctx, public_client(ctx), budget)
        raise ValueError(f"action de recherche inconnue : {action}")
