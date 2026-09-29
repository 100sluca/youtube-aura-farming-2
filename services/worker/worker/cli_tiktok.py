"""Commandes `yt2 tiktok` : publication des Shorts sur TikTok par Zernio (docs/36-publication-tiktok.md).

    yt2 tiktok key CLE | -                 enregistre la clé API Zernio (chiffrée en base) ; « - » la lit sur l'entrée
                                           standard, pour qu'elle n'apparaisse pas dans l'historique du terminal
    yt2 tiktok accounts                    comptes TikTok connectés à Zernio
    yt2 tiktok link <chaîne> <compte> [--off]
                                           relie une chaîne YouTube (slug) à un compte TikTok (@nom ou id Zernio) ;
                                           chaque Short programmé ensuite part aussi sur TikTok (--off : relié, sans
                                           publication automatique)
    yt2 tiktok status                      réglages, chaînes reliées, dernières publications
    yt2 tiktok check <chaîne>              ce que TikTok autorise pour le compte relié (visibilités, interactions)
    yt2 tiktok post <vidéo> [--now] [--draft] [--here]
                                           publie une vidéo : au créneau YouTube s'il est à venir, sinon tout de suite
                                           (--now : tout de suite ; --draft : dans la boîte de réception TikTok, rien de
                                           public ; --here : dans ce terminal au lieu du worker)
    yt2 tiktok stats [--here]              relève les statistiques TikTok des comptes (docs/39), comme chaque heure
    yt2 tiktok backlog <chaîne> [--on|--off]
                                           rattrapage (docs/39) : vidéos déjà sorties sur YouTube qui partiront sur
                                           TikTok, une par créneau resté vide ; --on / --off l'active ou le coupe
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo


def _ctx() -> tuple[Any, Any]:
    from .config import Settings, utf8_console
    from .db import Db

    utf8_console()
    settings = Settings()
    return settings, Db(settings.database_url)


def _client(settings: Any, db: Any) -> Any:
    from .tiktok.config import zernio_key
    from .tiktok.zernio import ZernioClient

    key = zernio_key(settings, db)
    if not key:
        sys.exit("Pas de clé Zernio : yt2 tiktok key CLE (ou Réglages → TikTok)")
    return ZernioClient(key)


def tiktok_key(args: argparse.Namespace) -> None:
    from .tiktok.config import save_zernio_key

    settings, db = _ctx()
    value = sys.stdin.readline() if args.value == "-" else args.value
    hint = save_zernio_key(settings, db, value)
    print(f"Clé Zernio enregistrée (…{hint})")


def tiktok_accounts(_: argparse.Namespace) -> None:
    settings, db = _ctx()
    with _client(settings, db) as zc:
        accounts = zc.tiktok_accounts()
    if not accounts:
        print("Aucun compte TikTok connecté à Zernio : zernio.com → Accounts → Connect → TikTok")
    for a in accounts:
        print(f"@{a.get('username') or '?'}  {a.get('displayName') or ''}  id={a.get('_id')}  actif={a.get('isActive', True)}")


def tiktok_link(args: argparse.Namespace) -> None:
    from .tiktok.config import save_tiktok_config

    settings, db = _ctx()
    ch = db.fetch_one("select id, name from channels where slug = %s", (args.channel,))
    if not ch:
        sys.exit(f"Chaîne inconnue : {args.channel}")
    wanted = args.account.lstrip("@").lower()
    with _client(settings, db) as zc:
        accounts = zc.tiktok_accounts()
    match = next((a for a in accounts if wanted in (str(a.get("_id")).lower(), str(a.get("username") or "").lower())), None)
    if not match:
        sys.exit(f"Compte TikTok introuvable sur Zernio : {args.account} (yt2 tiktok accounts)")
    row = db.fetch_one("select value from app_settings where key = 'tiktok'")
    value = dict(row["value"]) if row and row["value"] else {}
    channels = dict(value.get("channels") or {})
    before = channels.get(str(ch["id"])) or {}
    enabled = not args.off
    channels[str(ch["id"])] = {
        "account_id": str(match["_id"]),
        "username": str(match.get("username") or ""),
        "enabled": enabled,
        # l'activation date le premier créneau concerné : rien d'ancien ne part en rafale
        "enabled_at": (before.get("enabled_at") if before.get("enabled") else None) or datetime.now(UTC).isoformat(),
        "backlog": bool(before.get("backlog")),  # rattrapage (docs/39) : yt2 tiktok backlog
    }
    value["channels"] = channels
    save_tiktok_config(db, value)
    print(f"{ch['name']} → @{match.get('username')} ({'publication automatique' if enabled else 'sans publication automatique'})")


def tiktok_status(_: argparse.Namespace) -> None:
    from .tiktok.config import load_tiktok_config

    settings, db = _ctx()
    cfg = load_tiktok_config(db)
    hint = db.fetch_one("select hint from app_secrets where name = 'zernio_api_key'")
    print(f"Clé Zernio : {'…' + hint['hint'] if hint else ('.env' if settings.zernio_api_key else 'absente')}")
    print(f"Interactions : commentaires={cfg.allow_comment} duo={cfg.allow_duet} collage={cfg.allow_stitch} · "
          f"étiquette IA={cfg.ai_label}")
    names = {str(r["id"]): r["name"] for r in db.fetch_all("select id, name from channels")}
    for cid, ch in cfg.channels.items():
        print(f"  {names.get(cid, cid)} → @{ch.username or ch.account_id} · auto={ch.enabled} depuis {ch.enabled_at}"
              f" · rattrapage={ch.backlog}")
    for a in db.fetch_all(
        """select a.username, a.followers, a.likes, a.fetched_at, count(p.id) as posts, coalesce(sum(p.views), 0) as views
           from tiktok_accounts a left join tiktok_posts p on p.account_id = a.id group by a.id order by a.username"""
    ):
        print(f"  Stats @{a['username']} : {a['followers']} abonnés · {a['posts']} vidéos · {a['views']} vues · "
              f"relevé {a['fetched_at'].astimezone(ZoneInfo('Europe/Paris')):%d/%m %H:%M}")
    for v in db.fetch_all(
        """select v.id, v.title, v.scheduled_at, v.tiktok from videos v where v.tiktok is not null
           order by coalesce(v.scheduled_at, v.updated_at) desc limit 12"""
    ):
        t = v["tiktok"] or {}
        print(f"  {str(v['id'])[:8]} {t.get('status', '?'):<10} {t.get('url') or t.get('scheduled_for') or ''} "
              f"{(v['title'] or '')[:50]} {('· ' + t['error']) if t.get('error') else ''}")


def tiktok_check(args: argparse.Namespace) -> None:
    from .tiktok.config import load_tiktok_config

    settings, db = _ctx()
    ch = db.fetch_one("select id from channels where slug = %s", (args.channel,))
    link = load_tiktok_config(db).for_channel(ch["id"]) if ch else None
    if not link:
        sys.exit("Chaîne non reliée à TikTok : yt2 tiktok link <chaîne> <compte>")
    with _client(settings, db) as zc:
        info = zc.creator_info(link.account_id)
    creator = info.get("creator") or {}
    print(f"@{creator.get('nickname') or link.username} · peut encore publier : {creator.get('canPostMore')}")
    print("Visibilités :", ", ".join(p.get("value", "?") for p in info.get("privacyLevels") or []))
    for name, s in ((info.get("postingLimits") or {}).get("interactionSettings") or {}).items():
        print(f"  {name}: {'possible' if (s or {}).get('enabled') else 'coupé dans l’appli TikTok'}")


def tiktok_post(args: argparse.Namespace) -> None:
    from psycopg.types.json import Jsonb

    from .main import run_job
    from .models import Job

    settings, db = _ctx()
    v = db.fetch_one("select id, channel_id, title from videos where id::text like %s || '%%'", (args.video,))
    if not v:
        sys.exit(f"Vidéo introuvable : {args.video}")
    payload = {"source": "cli", "now": args.now, "draft": args.draft}
    row = db.fetch_one(
        """insert into jobs (type, video_id, channel_id, priority, max_attempts, payload, run_after)
           values ('tiktok_publish', %s, %s, 30, 3, %s, now() + case when %s then interval '1 day' else interval '0' end)
           returning id""",
        (v["id"], v["channel_id"], Jsonb(payload), args.here),
    )
    if not args.here:
        print(f"Publication en file (job {row['id']}) : le worker s'en charge — {v['title']}")
        return
    job = db.fetch_one(
        """update jobs set status = 'running', locked_by = 'cli', locked_at = now(), run_after = now(),
             attempts = attempts + 1
           where id = %s and status = 'queued' returning *""",
        (row["id"],),
    )
    run_job(Job.model_validate(job), db, settings)
    after = db.fetch_one("select status::text as status, error, progress_label from jobs where id = %s", (row["id"],))
    t = (db.fetch_one("select tiktok from videos where id = %s", (v["id"],)) or {}).get("tiktok") or {}
    print(f"Job : {after['status']} {after['progress_label'] or ''} {after['error'] or ''}")
    print(f"TikTok : {t.get('status')} {t.get('url') or t.get('scheduled_for') or ''} {t.get('error') or ''}")


def tiktok_stats(args: argparse.Namespace) -> None:
    from .main import run_job
    from .models import Job

    settings, db = _ctx()
    row = db.fetch_one(
        """insert into jobs (type, priority, payload, run_after)
           values ('sync_tiktok', 10, '{"source": "cli"}', now() + case when %s then interval '1 day' else interval '0' end)
           returning id""",
        (args.here,),
    )
    if not args.here:
        print(f"Relevé en file (job {row['id']}) : le worker s'en charge")
        return
    job = db.fetch_one(
        """update jobs set status = 'running', locked_by = 'cli', locked_at = now(), run_after = now(), attempts = attempts + 1
           where id = %s and status = 'queued' returning *""",
        (row["id"],),
    )
    run_job(Job.model_validate(job), db, settings)
    after = db.fetch_one("select status::text as status, error, result from jobs where id = %s", (row["id"],))
    print(f"Job : {after['status']} {after['error'] or ''}")
    for p in db.fetch_all(
        """select p.views, p.likes, p.comments, p.shares, p.completion_pct, p.url, p.sync_status,
                  coalesce(v.title, left(p.caption, 50)) as title
           from tiktok_posts p left join videos v on v.id = p.video_id order by p.published_at desc nulls last limit 15"""
    ):
        done = f" · {p['completion_pct']} % jusqu'au bout" if p["completion_pct"] is not None else ""
        views = "?" if p["sync_status"] == "live" else p["views"]  # tout juste sortie : Zernio n'a pas encore ses vues
        print(f"  {views:>7} vues {p['likes']:>5} j'aime {p['comments']:>4} comm. {p['shares']:>4} part.{done}  "
              f"{(p['title'] or '')[:50]}")


def tiktok_backlog(args: argparse.Namespace) -> None:
    from .tiktok.config import save_tiktok_config

    settings, db = _ctx()
    ch = db.fetch_one("select id, name from channels where slug = %s", (args.channel,))
    if not ch:
        sys.exit(f"Chaîne inconnue : {args.channel}")
    row = db.fetch_one("select value from app_settings where key = 'tiktok'")
    value = dict(row["value"]) if row and row["value"] else {}
    channels = dict(value.get("channels") or {})
    link = dict(channels.get(str(ch["id"])) or {})
    if not link.get("account_id"):
        sys.exit("Chaîne non reliée à TikTok : yt2 tiktok link <chaîne> <compte>")
    if args.on or args.off:
        link["backlog"] = bool(args.on)
        channels[str(ch["id"])] = link
        value["channels"] = channels
        save_tiktok_config(db, value)
    todo = db.fetch_all(
        "select id, title, published_at from v_tiktok_backlog where channel_id = %s order by published_at, id", (ch["id"],)
    )
    print(f"{ch['name']} → @{link.get('username')} · rattrapage {'activé' if link.get('backlog') else 'coupé'} · "
          f"{len(todo)} vidéo(s) à rattraper, une par créneau resté vide :")
    for v in todo:
        day = v["published_at"].astimezone(ZoneInfo("Europe/Paris"))
        print(f"  {str(v['id'])[:8]} sortie sur YouTube le {day:%d/%m} · {(v['title'] or '')[:60]}")


def register(sub: Any) -> None:
    tk = sub.add_parser("tiktok", help="publication sur TikTok par Zernio (docs/36)").add_subparsers(dest="cmd", required=True)
    k = tk.add_parser("key", help="enregistre la clé API Zernio (chiffrée en base)")
    k.add_argument("value", help="la clé, ou « - » pour la lire sur l'entrée standard")
    k.set_defaults(fn=tiktok_key)
    tk.add_parser("accounts", help="comptes TikTok connectés à Zernio").set_defaults(fn=tiktok_accounts)
    ln = tk.add_parser("link", help="relie une chaîne YouTube à un compte TikTok")
    ln.add_argument("channel", help="slug de la chaîne, ex. fr")
    ln.add_argument("account", help="@nom TikTok ou id Zernio du compte")
    ln.add_argument("--off", action="store_true", help="relier sans publication automatique")
    ln.set_defaults(fn=tiktok_link)
    tk.add_parser("status", help="réglages et dernières publications").set_defaults(fn=tiktok_status)
    ck = tk.add_parser("check", help="ce que TikTok autorise pour le compte relié à la chaîne")
    ck.add_argument("channel")
    ck.set_defaults(fn=tiktok_check)
    po = tk.add_parser("post", help="publie une vidéo sur TikTok")
    po.add_argument("video", help="id de la vidéo (début suffit)")
    po.add_argument("--now", action="store_true", help="tout de suite, sans attendre le créneau YouTube")
    po.add_argument("--draft", action="store_true", help="dans la boîte de réception TikTok (rien de public)")
    po.add_argument("--here", action="store_true", help="dans ce terminal, sans passer par le worker")
    po.set_defaults(fn=tiktok_post)
    st = tk.add_parser("stats", help="relève les statistiques TikTok (docs/39)")
    st.add_argument("--here", action="store_true", help="dans ce terminal, sans passer par le worker")
    st.set_defaults(fn=tiktok_stats)
    bl = tk.add_parser("backlog", help="rattrapage des vidéos déjà sorties sur YouTube (docs/39)")
    bl.add_argument("channel", help="slug de la chaîne, ex. fr")
    onoff = bl.add_mutually_exclusive_group()
    onoff.add_argument("--on", action="store_true", help="active le rattrapage")
    onoff.add_argument("--off", action="store_true", help="le coupe")
    bl.set_defaults(fn=tiktok_backlog)
