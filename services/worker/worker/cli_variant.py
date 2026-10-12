"""yt2 variant : variante d'accroche d'une vidéo montée ; yt2 withdraw : retirer une vidéo programmée de YouTube et
TikTok, et la refaire au besoin avec une autre voix (docs/49-variante-accroche.md)."""

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


def variant_rewrite(args: argparse.Namespace) -> None:
    from .cli import _db, _full_id
    from .rewrite import rewrite_story

    settings, db = _db()
    vid = _full_id(db, "videos", args.video)
    try:
        out, rw, issues = rewrite_story(
            db, settings, settings.data_dir, vid, args.note or "", pages=args.page or [], dry=args.dry
        )
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"Idée : {rw.central_idea}\nEnjeu : {rw.stakes}\nTitre : {rw.title} · titre d'accroche : {rw.hook_title}\n")
    for sc in rw.scenes:
        print(f"{sc.index:>2} [{sc.part}] {sc.text}" + (f"   ⟨{sc.on_screen}⟩" if sc.on_screen else ""))
    for issue in issues:
        print(f"  ! {issue}")
    if out:
        print(f"\nréécriture : vidéo {out.video_id} · production {out.production_id} · {out.linked} fichiers liés")
        print("voix → montage → contrôle → SEO en file ; elle arrive à valider dans la Bibliothèque")


def variant_clip_voices(args: argparse.Namespace) -> None:
    from .cli import _db, _full_id
    from .hookvariant import clone, source_of
    from .models import ScriptV1

    settings, db = _db()
    vid = _full_id(db, "videos", args.video)
    try:
        v, p = source_of(db, vid, voiced=False)
    except ValueError as exc:
        sys.exit(str(exc))
    script = ScriptV1.model_validate(p["script"])
    if not script.cast:
        sys.exit("seul un drame a des voix dans ses clips")
    out = clone(db, settings.data_dir, v, p, script, v["title"], None, [], clip_voices=True)
    print(f"voix des clips : vidéo {out.video_id} · production {out.production_id} · {out.linked} fichiers liés")
    print("montage → contrôle en file ; elle arrive à valider dans la Bibliothèque, à comparer avec l'originale")


def withdraw(args: argparse.Namespace) -> None:
    """Vidéo programmée, pas encore sortie : privée et sans date sur YouTube (rien n'est supprimé), publication TikTok
    programmée supprimée, envoi gardé dans previous_uploads (release_upload, docs/44). Sans --voice, elle revient à
    valider ; avec --voice, la narration est refaite avec cette voix (retouch_video, docs/34) puis montée."""
    from psycopg.types.json import Jsonb

    from .cli import _db, _full_id
    from .youtube.client import YouTubeClient

    settings, db = _db()
    vid = _full_id(db, "videos", args.video)
    v = db.fetch_one("select title, status, channel_id, youtube_video_id, retouch from videos where id = %s", (vid,))
    if v["status"] != "scheduled" or not v["youtube_video_id"]:
        sys.exit(f"« {v['title']} » : {v['status']}, pas une vidéo programmée sur YouTube")
    status = YouTubeClient.for_channel(settings, db, v["channel_id"]).unschedule(v["youtube_video_id"])
    print(f"YouTube {v['youtube_video_id']} : {status.get('privacyStatus')}, sans date de publication")
    if args.voice:
        retouch = {**(v["retouch"] or {}), "voice": args.voice}
        db.execute("select retouch_video(%s, %s, %s)", (vid, Jsonb(retouch), args.voice))
        print(f"« {v['title']} » : voix {args.voice} puis montage en file ; elle reviendra à valider")
    else:
        db.execute("select release_upload(%s)", (vid,))
        db.execute(
            """update jobs set status = 'cancelled', finished_at = now()
               where video_id = %s and type = 'upload' and status = 'queued'""",
            (vid,),
        )
        db.execute("update videos set status = 'review', scheduled_at = null where id = %s", (vid,))
        print(f"« {v['title']} » : retirée, à valider dans la Bibliothèque")


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
    rw = va.add_parser("rewrite", help="réécrire tout le récit sur les mêmes plans (docs/49 §6)")
    rw.add_argument("video", help="id de la vidéo d'origine (début suffit)")
    rw.add_argument("--note", help="ce qui ne va pas et l'angle voulu (guide le conteur)")
    rw.add_argument("--page", action="append", help="page Wikipédia à ajouter au dossier (répétable)")
    rw.add_argument("--dry", action="store_true", help="afficher le texte sans rien créer")
    rw.set_defaults(fn=variant_rewrite)
    cv = va.add_parser("clip-voices", help="même drame, avec le son de ses clips (voix du modèle vidéo, ambiance)")
    cv.add_argument("video", help="id de la vidéo d'origine (début suffit)")
    cv.set_defaults(fn=variant_clip_voices)
    wd = sub.add_parser("withdraw", help="retirer une vidéo programmée de YouTube et TikTok (docs/49)")
    wd.add_argument("video", help="id de la vidéo (début suffit)")
    wd.add_argument("--voice", help="refaire la narration avec cette voix (« moteur:voix », ex. qwen3:mystere)")
    wd.set_defaults(fn=withdraw)
