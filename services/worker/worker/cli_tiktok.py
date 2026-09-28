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
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from typing import Any


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
        print(f"  {names.get(cid, cid)} → @{ch.username or ch.account_id} · auto={ch.enabled} depuis {ch.enabled_at}")
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
