"""yt2 variant : variante d'accroche d'une vidéo montée (docs/49-variante-accroche.md)."""

from __future__ import annotations

import argparse
import sys
from typing import Any


def variant_make(args: argparse.Namespace) -> None:
    from .cli import _db, _full_id
    from .hookvariant import make_variant

    settings, db = _db()
    vid = _full_id(db, "videos", args.video)
    try:
        out = make_variant(
            db,
            settings.data_dir,
            vid,
            hook=args.hook,
            promise=args.promise,
            hook_title=args.hook_title,
            title=args.title,
            on_screen=args.on_screen,
            description=args.description,
        )
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"variante : vidéo {out.video_id} · production {out.production_id} · {out.linked} fichiers liés")
    for issue in out.issues:
        print(f"  ! {issue}")
    print("voix → montage → contrôle en file ; elle arrive à valider dans la Bibliothèque")


def register(sub: Any) -> None:
    va = sub.add_parser("variant", help="variante d'accroche d'une vidéo (docs/49)").add_subparsers(dest="cmd", required=True)
    mk = va.add_parser("make", help="même vidéo, autre accroche et autre promesse")
    mk.add_argument("video", help="id de la vidéo d'origine (début suffit)")
    mk.add_argument("--hook", required=True, help="1re phrase dite")
    mk.add_argument("--promise", required=True, help="2e phrase dite")
    mk.add_argument("--hook-title", required=True, help="titre d'accroche gravé à l'écran")
    mk.add_argument("--title", required=True, help="titre YouTube")
    mk.add_argument("--on-screen", help="texte à l'écran sur l'accroche ('' : aucun ; absent : celui d'origine)")
    mk.add_argument("--description", help="description YouTube (absent : celle d'origine)")
    mk.set_defaults(fn=variant_make)
