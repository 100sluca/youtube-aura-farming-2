"""yt2 arc : mini-séries des drames (docs/52) — lister, faire d'un drame la partie 1, lancer la suite, régler le pilote."""

from __future__ import annotations

import argparse
import sys
from typing import Any


def arc_list(_: argparse.Namespace) -> None:
    from .cli import _db

    _, db = _db()
    for a in db.fetch_all(
        """select a.id, a.title, a.status, a.parts_total, a.decisions,
                  (select string_agg(p.arc_part || ':' || p.status, ' ' order by p.arc_part) from productions p
                   where p.arc_id = a.id) as parts
           from story_arcs a order by a.created_at desc limit 30"""
    ):
        verdicts = " ".join(
            f"p{d.get('part')}={d.get('verdict')}({d.get('views')}/{d.get('median')})" for d in a["decisions"] or []
        )
        print(f"{str(a['id'])[:8]}  {a['status']:<8} {a['parts_total']} parties  [{a['parts'] or '—'}]  {a['title']}  {verdicts}")


def arc_show(args: argparse.Namespace) -> None:
    from .cli import _db, _full_id

    _, db = _db()
    a = db.fetch_one("select * from story_arcs where id = %s", (_full_id(db, "story_arcs", args.arc),))
    o = a["outline"]
    print(f"{a['title']} · {a['status']} · {a['parts_total']} parties\nPrémisse : {o.get('premise')}")
    print(
        f"1re réplique : {o.get('first_line')}\nInterdit : {o.get('planted')}\nRetournement : {o.get('twist')}\nMorale : {o.get('moral')}"
    )
    for p in o.get("parts", []):
        print(f"\nPartie {p['n']} : {p['synopsis']}\n  s'ouvre sur : {p.get('opens_with') or '—'}\n  coupe sur : {p['ends_on']}")
    for d in a["decisions"] or []:
        print(f"\néval. partie {d.get('part')} : {d}")


def arc_adopt(args: argparse.Namespace) -> None:
    from .arcs import adopt
    from .cli import _db, _full_id

    settings, db = _db()
    arc_id = adopt(db, settings, _full_id(db, "productions", args.production))
    print(f"mini-série {arc_id} : la production est la partie 1 (yt2 arc show {str(arc_id)[:8]})")


def arc_launch(args: argparse.Namespace) -> None:
    from .arcs import launch_part
    from .cli import _db, _full_id

    _, db = _db()
    try:
        pid = launch_part(db, _full_id(db, "story_arcs", args.arc), autopilot=args.autopilot)
    except (LookupError, ValueError) as exc:
        sys.exit(str(exc))
    print(f"production {pid} : script en file")


def arc_tick(_: argparse.Namespace) -> None:
    from .arcs import tick
    from .cli import _db

    settings, db = _db()
    for line in tick(db, settings) or ["rien à faire"]:
        print(line)


def arc_settings(args: argparse.Namespace) -> None:
    from .arcs import load, save
    from .cli import _db

    _, db = _db()
    change: dict[str, Any] = {}
    if args.autopilot is not None:
        change["autopilot"] = args.autopilot == "on"
    if args.threshold is not None:
        change["threshold"] = args.threshold
    if args.hours is not None:
        change["eval_hours"] = args.hours
    if args.parts is not None:
        change["parts"] = args.parts
    if change:
        save(db, change)
    print(load(db))


def register(sub: Any) -> None:
    ar = sub.add_parser("arc", help="mini-séries des drames (docs/52)").add_subparsers(dest="cmd", required=True)
    ar.add_parser("list").set_defaults(fn=arc_list)
    sh = ar.add_parser("show")
    sh.add_argument("arc")
    sh.set_defaults(fn=arc_show)
    ad = ar.add_parser("adopt", help="faire d'un drame déjà écrit la partie 1 d'une mini-série")
    ad.add_argument("production")
    ad.set_defaults(fn=arc_adopt)
    la = ar.add_parser("launch", help="lancer la partie suivante")
    la.add_argument("arc")
    la.add_argument("--autopilot", action="store_true", help="sans revue du storyboard, programmée seule")
    la.set_defaults(fn=arc_launch)
    ar.add_parser("tick", help="évaluer les parties sorties maintenant").set_defaults(fn=arc_tick)
    se = ar.add_parser("settings", help="pilote des mini-séries et seuil")
    se.add_argument("--autopilot", choices=["on", "off"])
    se.add_argument("--threshold", type=float, help="× la médiane des vidéos de la chaîne (1 = la médiane)")
    se.add_argument("--hours", type=int, help="âge de la partie au moment du verdict (48 par défaut)")
    se.add_argument("--parts", type=int, choices=[1, 2, 3], help="parties d'une nouvelle mini-série (1 = coupé)")
    se.set_defaults(fn=arc_settings)
