"""`yt2 quotes …` : citations (docs/58-citations.md).

yt2 quotes music [--country FR]                      musiques commerciales de TikTok en tendance (lecture seule),
                                                      et celle que prendrait une citation de chaque ambiance
yt2 quotes carousel [--channel fr] [--count 5] [--draft] [--at 2026-10-03T18:00:00+02:00] [--dry]
                                                      carrousel photo TikTok des dernières citations (musique de
                                                      TikTok) ; --dry : montre la publication sans rien envoyer
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
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
        sys.exit("Pas de clé Zernio : Réglages → TikTok")
    return ZernioClient(key)


def music(args: argparse.Namespace) -> None:
    from . import platform_music as pm
    from .tiktok.config import load_tiktok_config

    settings, db = _ctx()
    cfg = load_tiktok_config(db)
    account = next((c.account_id for c in cfg.channels.values() if c.account_id), None)
    if not account:
        sys.exit("Aucun compte TikTok relié : Réglages → TikTok")
    with _client(settings, db) as client:
        tracks = pm.cached_tracks(client, account, args.country.upper(), settings.data_dir / "tiktok")
    print(f"{len(tracks)} musiques commerciales en tendance ({args.country.upper()}) :")
    for t in tracks[: args.limit]:
        print(
            f"  {t.get('rank', '?'):>3}. {t.get('name')} — {t.get('artist')} {t.get('genres') or ''} ({t.get('durationSec')} s)"
        )
    print("\nChoix pour une citation (exemple, une vidéo donnée) :")
    for mood in pm.MOOD_WORDS:
        t = pm.pick_tiktok_track(tracks, mood, "exemple")
        print(f"  {mood:<7} → {t.get('name') if t else '—'}")


def carousel(args: argparse.Namespace) -> None:
    from . import quotes
    from .models import ScriptV1
    from .tiktok.carousel import carousel_body, carousel_caption, carousel_title
    from .tiktok.config import load_tiktok_config
    from .tiktok.post import idempotency_key, read_create

    settings, db = _ctx()
    ch = db.fetch_one("select id, slug, lang from channels where slug = %s", (args.channel,))
    if not ch:
        sys.exit(f"chaîne inconnue : {args.channel}")
    rows = db.fetch_all(
        """select v.id, v.lang, v.tags, p.script, co.category from videos v
           join productions p on p.id = v.production_id join series s on s.id = p.series_id
           left join concepts co on co.id = p.concept_id
           where v.channel_id = %s and s.recipe = 'quote' and v.archived_at is null
             and v.status in ('review', 'ready', 'scheduled', 'published')
           order by v.created_at desc limit %s""",
        (ch["id"], max(1, min(args.count, 35))),
    )
    cards, texts, tags = [], [], ["citation", "pensée"]
    for r in rows:
        card = Path(settings.data_dir) / "videos" / str(r["id"]) / "card.jpg"
        if not card.is_file():
            print(f"  (sans affiche, ignorée : vidéo {str(r['id'])[:8]})")
            continue
        cards.append(card)
        texts.append(quotes.quote_text(ScriptV1.model_validate(r["script"]), r["lang"]))
        if r.get("category"):
            tags.append(str(r["category"]).replace("_", ""))
    if not cards:
        sys.exit("Aucune citation montée avec son affiche sur cette chaîne.")
    cfg = load_tiktok_config(db)
    link = cfg.for_channel(ch["id"])
    if not link or not link.account_id:
        sys.exit("Aucun compte TikTok relié à cette chaîne : Réglages → TikTok")
    when = datetime.fromisoformat(args.at) if args.at else None
    title, caption = carousel_title(texts), carousel_caption(texts, tags[:5])
    print(
        f"Carrousel de {len(cards)} citations pour @{link.username or link.account_id}" + (" (brouillon)" if args.draft else "")
    )
    for i, t in enumerate(texts, 1):
        print(f"  {i}. {t.splitlines()[0][:90]}")
    if args.dry:
        body = carousel_body(
            title=title,
            caption=caption,
            image_urls=[f"<{c.name}>" for c in cards],
            account_id=link.account_id,
            cfg=cfg,
            when=when,
            draft=args.draft,
        )
        print(json.dumps(body, ensure_ascii=False, indent=1))
        return
    with _client(settings, db) as client:
        urls = [client.upload_image(c) for c in cards]
        body = carousel_body(
            title=title, caption=caption, image_urls=urls, account_id=link.account_id, cfg=cfg, when=when, draft=args.draft
        )
        key = idempotency_key("carousel:" + ",".join(str(r["id"]) for r in rows), 1)
        code, resp = client.create_post(body, key)
    out = read_create(code, resp)
    print(
        f"Zernio : {code} → {out.status}"
        + (f" · {out.error}" if out.error else "")
        + (f" · post {out.post_id}" if out.post_id else "")
    )
    log = Path(settings.data_dir) / "tiktok" / "carrousels.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": datetime.now().isoformat(), "videos": [str(r["id"]) for r in rows], "post_id": out.post_id,
                            "status": out.status, "draft": args.draft}, ensure_ascii=False) + "\n")  # fmt: skip


def register(sub: Any) -> None:
    """Ajoute le groupe `quotes` à l'analyseur de `yt2` (worker/cli.py)."""
    q = sub.add_parser("quotes", help="citations (docs/58)").add_subparsers(dest="cmd", required=True)
    m = q.add_parser("music", help="musiques commerciales de TikTok en tendance (lecture seule)")
    m.add_argument("--country", default="FR")
    m.add_argument("--limit", type=int, default=30)
    m.set_defaults(fn=music)
    c = q.add_parser("carousel", help="carrousel photo TikTok des dernières citations, musique de TikTok")
    c.add_argument("--channel", default="fr")
    c.add_argument("--count", type=int, default=5)
    c.add_argument("--draft", action="store_true", help="dans la boîte de réception TikTok (le son se choisit dans l'appli)")
    c.add_argument("--at", help="heure de publication ISO avec décalage (défaut : tout de suite)")
    c.add_argument("--dry", action="store_true", help="montrer la publication sans rien envoyer")
    c.set_defaults(fn=carousel)
