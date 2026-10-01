"""Commandes `yt2 instagram` : publication des Shorts en Reels Instagram par Zernio (docs/48-publication-instagram.md).
La clé Zernio est celle de TikTok (`yt2 tiktok key`).

yt2 instagram accounts                 comptes Instagram connectés à Zernio
yt2 instagram link <chaîne> <compte> [--off]
                                       relie une chaîne YouTube (slug) à un compte Instagram (@nom ou id Zernio) ;
                                       chaque Short programmé ensuite part aussi en Reel (--off : relié, sans
                                       publication automatique)
yt2 instagram status                   réglages, chaînes reliées, derniers Reels
yt2 instagram post <vidéo> [--now] [--here]
                                       publie une vidéo : au créneau YouTube s'il est à venir, sinon tout de suite
                                       (--now : tout de suite ; --here : dans ce terminal au lieu du worker)
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from typing import Any

from .cli_tiktok import _client, _ctx


def _instagram_accounts(zc: Any) -> list[dict[str, Any]]:
    return [a for a in zc.accounts() if a.get("platform") == "instagram"]


def instagram_accounts(_: argparse.Namespace) -> None:
    settings, db = _ctx()
    with _client(settings, db) as zc:
        accounts = _instagram_accounts(zc)
    if not accounts:
        print("Aucun compte Instagram connecté à Zernio : zernio.com → Accounts → Connect → Instagram")
    for a in accounts:
        kind = ((a.get("metadata") or {}).get("profileData") or {}).get("extraData", {}).get("accountType", "?")
        print(
            f"@{a.get('username') or '?'}  {a.get('displayName') or ''}  id={a.get('_id')}  type={kind}  actif={a.get('isActive', True)}"
        )


def instagram_link(args: argparse.Namespace) -> None:
    from .instagram.config import save_instagram_config

    settings, db = _ctx()
    ch = db.fetch_one("select id, name from channels where slug = %s", (args.channel,))
    if not ch:
        sys.exit(f"Chaîne inconnue : {args.channel}")
    wanted = args.account.lstrip("@").lower()
    with _client(settings, db) as zc:
        accounts = _instagram_accounts(zc)
    match = next((a for a in accounts if wanted in (str(a.get("_id")).lower(), str(a.get("username") or "").lower())), None)
    if not match:
        sys.exit(f"Compte Instagram introuvable sur Zernio : {args.account} (yt2 instagram accounts)")
    row = db.fetch_one("select value from app_settings where key = 'instagram'")
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
    save_instagram_config(db, value)
    print(f"{ch['name']} → @{match.get('username')} ({'publication automatique' if enabled else 'sans publication automatique'})")


def instagram_status(_: argparse.Namespace) -> None:
    from .instagram.config import load_instagram_config

    settings, db = _ctx()
    cfg = load_instagram_config(db)
    hint = db.fetch_one("select hint from app_secrets where name = 'zernio_api_key'")
    print(f"Clé Zernio : {'…' + hint['hint'] if hint else ('.env' if settings.zernio_api_key else 'absente')}")
    print(f"Reels aussi dans la grille : {cfg.share_to_feed} · étiquette IA : {cfg.ai_label}")
    names = {str(r["id"]): r["name"] for r in db.fetch_all("select id, name from channels")}
    for cid, ch in cfg.channels.items():
        print(f"  {names.get(cid, cid)} → @{ch.username or ch.account_id} · auto={ch.enabled} depuis {ch.enabled_at}")
    for v in db.fetch_all(
        """select v.id, v.title, v.instagram from videos v where v.instagram is not null
           order by coalesce(v.scheduled_at, v.updated_at) desc limit 12"""
    ):
        t = v["instagram"] or {}
        print(
            f"  {str(v['id'])[:8]} {t.get('status', '?'):<10} {t.get('url') or t.get('scheduled_for') or ''} "
            f"{(v['title'] or '')[:50]} {('· ' + t['error']) if t.get('error') else ''}"
        )


def instagram_post(args: argparse.Namespace) -> None:
    from psycopg.types.json import Jsonb

    from .main import run_job
    from .models import Job

    settings, db = _ctx()
    v = db.fetch_one("select id, channel_id, title from videos where id::text like %s || '%%'", (args.video,))
    if not v:
        sys.exit(f"Vidéo introuvable : {args.video}")
    payload = {"source": "cli", "now": args.now}
    row = db.fetch_one(
        """insert into jobs (type, video_id, channel_id, priority, max_attempts, payload, run_after)
           values ('instagram_publish', %s, %s, 30, 3, %s, now() + case when %s then interval '1 day' else interval '0' end)
           returning id""",
        (v["id"], v["channel_id"], Jsonb(payload), args.here),
    )
    if not args.here:
        print(f"Reel en file (job {row['id']}) : le worker s'en charge — {v['title']}")
        return
    job = db.fetch_one(
        """update jobs set status = 'running', locked_by = 'cli', locked_at = now(), run_after = now(),
             attempts = attempts + 1
           where id = %s and status = 'queued' returning *""",
        (row["id"],),
    )
    run_job(Job.model_validate(job), db, settings)
    after = db.fetch_one("select status::text as status, error, progress_label from jobs where id = %s", (row["id"],))
    t = (db.fetch_one("select instagram from videos where id = %s", (v["id"],)) or {}).get("instagram") or {}
    print(f"Job : {after['status']} {after['progress_label'] or ''} {after['error'] or ''}")
    print(f"Instagram : {t.get('status')} {t.get('url') or t.get('scheduled_for') or ''} {t.get('error') or ''}")


def register(sub: Any) -> None:
    ig = sub.add_parser("instagram", help="Reels Instagram par Zernio (docs/48)").add_subparsers(dest="cmd", required=True)
    ig.add_parser("accounts", help="comptes Instagram connectés à Zernio").set_defaults(fn=instagram_accounts)
    ln = ig.add_parser("link", help="relie une chaîne YouTube à un compte Instagram")
    ln.add_argument("channel", help="slug de la chaîne, ex. fr")
    ln.add_argument("account", help="@nom Instagram ou id Zernio du compte")
    ln.add_argument("--off", action="store_true", help="relier sans publication automatique")
    ln.set_defaults(fn=instagram_link)
    ig.add_parser("status", help="réglages et derniers Reels").set_defaults(fn=instagram_status)
    po = ig.add_parser("post", help="publie une vidéo en Reel")
    po.add_argument("video", help="id de la vidéo (début suffit)")
    po.add_argument("--now", action="store_true", help="tout de suite, sans attendre le créneau YouTube")
    po.add_argument("--here", action="store_true", help="dans ce terminal, sans passer par le worker")
    po.set_defaults(fn=instagram_post)
