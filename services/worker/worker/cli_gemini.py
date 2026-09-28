"""Commandes `yt2 gemini` : Gemini en ligne pour les clips vidéo (docs/17-gemini-en-ligne.md).

    yt2 gemini open                      ouvre gemini.google.com dans le Chrome dédié (s'y connecter une fois)
    yt2 gemini status                    réglages, Chrome dédié, dernier résultat, quota
    yt2 gemini check [--image scene.png] parcours complet jusqu'au bouton « Envoyer », sans rien envoyer (capture dans
                                         DATA_DIR/gemini-debug) : sert à vérifier les repères de l'interface
    yt2 gemini clip --image scene.png --prompt "slow push-in…" [--seconds 4] [--out clip.mp4]
                                         une vraie vidéo (consomme le quota Google AI), attendue jusqu'au bout
    yt2 gemini send <production>         valide le storyboard et fait fabriquer les clips par Gemini (comme le bouton
                                         Gemini de Création)
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def _db() -> tuple[Any, Any]:
    from .config import Settings
    from .db import Db

    settings = Settings()
    try:
        return settings, Db(settings.database_url)
    except Exception:  # noqa: BLE001 — base éteinte : les réglages du .env suffisent pour ouvrir ou vérifier
        return settings, None


def gemini_open(_args: argparse.Namespace) -> None:
    from .providers.gemini_web import Runtime, open_tab

    settings, db = _db()
    rt = Runtime.load(settings, db)
    open_tab(rt, rt.home)
    print(f"Gemini ouvert dans le Chrome dédié (profil {rt.profile}, port {rt.port}) : s'y connecter au compte Google AI si besoin.")


def gemini_status(_args: argparse.Namespace) -> None:
    from .providers.gemini_web import Runtime, devtools_up
    from .settings_store import load_gemini_config, load_gemini_status

    settings, db = _db()
    rt = Runtime.load(settings, db)
    cfg = load_gemini_config(settings, db, use_cache=False)
    print(json.dumps({
        "chrome": str(rt.chrome) if rt.chrome else None, "profil": str(rt.profile), "profil_créé": rt.profile.exists(),
        "port": rt.port, "chrome_dédié_ouvert": devtools_up(rt.port), "adresse": rt.home,
        "réglages": {"compte": cfg.authuser, "modèle": cfg.model or "(celui de l'appli)", "durée": cfg.duration, "source": cfg.source},
        "dernier_résultat": load_gemini_status(db),
    }, ensure_ascii=False, indent=2))


def gemini_check(args: argparse.Namespace) -> None:
    from .providers.gemini_web import check

    settings, db = _db()
    report = check(settings, db, [Path(p) for p in args.image or []])
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def gemini_clip(args: argparse.Namespace) -> None:
    from .postpone import Postpone
    from .providers.gemini_web import GeminiWebVideo

    settings, db = _db()
    provider = GeminiWebVideo(settings, db)
    out = Path(args.out) if args.out else Path(tempfile.gettempdir()) / "yt2_gemini" / f"clip_{time.strftime('%Y%m%d-%H%M%S')}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    image = Path(args.image) if args.image else None
    while True:
        try:
            info = provider.generate(prompt=args.prompt, style_preset=args.style, duration_s=args.seconds, out_path=out,
                                     on_progress=lambda p: print(f"  {p} %", flush=True), image_path=image)
        except Postpone as later:
            print(f"{time.strftime('%H:%M:%S')} {later.reason}", flush=True)
            if later.error:  # quota : inutile d'attendre des heures dans un terminal
                sys.exit(f"{later.label} ; relancer la même commande avec --out {out} pour reprendre")
            time.sleep(min(later.delay_s, 60))
            continue
        print(f"Clip prêt : {out} ({info.width}×{info.height}, {info.duration_s:.1f} s)")
        return


def gemini_send(args: argparse.Namespace) -> None:
    from .cli import _full_id

    settings, db = _db()
    if db is None:
        sys.exit("base injoignable")
    pid = _full_id(db, "productions", args.production)
    script = db.fetch_one("select script from productions where id = %s", (pid,))
    scenes = ((script or {}).get("script") or {}).get("scenes") or []
    if any(s.get("clip_mode") == "flf" for s in scenes):
        print("Essai : clips « première + dernière image » (chantier, passages) ; Gemini reçoit les deux images, sans garantie")
    missing = db.fetch_all(
        """select distinct a.scene_index from assets a where a.production_id = %s and a.kind = 'storyboard'
           and not exists (select 1 from assets b where b.production_id = a.production_id and b.kind = 'storyboard'
                           and b.scene_index = a.scene_index and b.selected)""",
        (pid,),
    )
    if missing:
        sys.exit(f"scènes sans image retenue : {[m['scene_index'] for m in missing]} (yt2 storyboard pick …)")
    db.execute("update productions set video_provider = 'gemini_web' where id = %s", (pid,))
    if not db.fetch_one("select 1 from jobs where production_id = %s and type = 'render' and status in ('queued', 'running')", (pid,)):
        db.enqueue("render", production_id=pid, priority=90)
    db.execute("update productions set status = 'generating' where id = %s and status = 'storyboard_review'", (pid,))
    print(f"Production {str(pid)[:8]} : clips confiés à Gemini (render en file)")


def register(sub: Any) -> None:
    g = sub.add_parser("gemini", help="clips vidéo par l'appli Gemini (docs/17)").add_subparsers(dest="cmd", required=True)
    g.add_parser("open", help="ouvrir Gemini dans le Chrome dédié").set_defaults(fn=gemini_open)
    g.add_parser("status", help="réglages, Chrome dédié, dernier résultat").set_defaults(fn=gemini_status)
    c = g.add_parser("check", help="parcours jusqu'au bouton Envoyer, sans rien envoyer")
    c.add_argument("--image", action="append", help="image à joindre (répéter pour deux images, départ puis arrivée) ; rien n'est envoyé")
    c.set_defaults(fn=gemini_check)
    cl = g.add_parser("clip", help="une vraie vidéo (consomme le quota Google AI)")
    cl.add_argument("--image")
    cl.add_argument("--prompt", required=True, help="mouvement et caméra, en anglais")
    cl.add_argument("--seconds", type=float, default=4.0, help="durée de la scène (la vidéo demandée la couvre)")
    cl.add_argument("--style", help="style_preset (providers/video.py STYLE_PRESETS)")
    cl.add_argument("--out")
    cl.set_defaults(fn=gemini_clip)
    s = g.add_parser("send", help="valider le storyboard d'une production et confier ses clips à Gemini")
    s.add_argument("production")
    s.set_defaults(fn=gemini_send)
