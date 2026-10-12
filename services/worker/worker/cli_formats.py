"""Commandes `yt2` des formats visuels (docs/15) : titre d'accroche, bibliothèques de bruitages et de musique.

    yt2 hook preview "Tu paierais combien ?" [--image photo.png] [--out apercu.png]
    yt2 sfx list                                       étiquettes, fichiers présents dans DATA_DIR/sfx
    yt2 sfx generate [--tags excavator,whoosh] [--count 2] [--all]   génère les manquants (Stable Audio Open)
    yt2 music list                                     musiques de Luca (dossier « music », docs/26) et DATA_DIR/music
    yt2 music generate --mood luxury [--count 3] [--seconds 90]      pistes instrumentales (ACE-Step 1.5)

La génération passe par ComfyUI (COMFY_BASE_URL) : une fois les bibliothèques remplies, le montage y pioche et
aucune production ne relance de génération audio.
"""

from __future__ import annotations

import argparse
import random
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .media import AUDIO_EXT


def _settings() -> Any:
    from .config import Settings

    return Settings()


def hook_preview(args: argparse.Namespace) -> None:
    from .hooktitle import HookStyle, build_png, lint_hook_title

    style = HookStyle(font_path=args.font)
    out = Path(args.out) if args.out else Path(tempfile.gettempdir()) / "yt2_apercu" / "hook_title.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    png = build_png(args.text, out.with_suffix(".title.png") if args.image else out, style)
    if not png:
        sys.exit("titre vide, ou Pillow absent (uv sync)")
    for issue in lint_hook_title(args.text):
        print("attention :", issue)
    if args.image:  # le titre posé sur une image 1080×1920, comme dans le montage
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(Path(args.image).resolve()),
                "-i",
                str(png),
                "-filter_complex",
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[bg];[bg][1:v]overlay=(W-w)/2:{style.y}",
                "-frames:v",
                "1",
                str(out.resolve()),
            ],
            check=True,
        )
    print(f"Aperçu : {out}")


def _count(folder: Path) -> int:
    return sum(1 for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXT) if folder.is_dir() else 0


def _missing_model(exc: Exception) -> None:
    """ComfyUI refuse un workflow dont le modèle n'est pas installé : message clair au lieu d'une trace."""
    import re

    names = sorted(set(re.findall(r"'([^']+\.(?:safetensors|gguf))' not in", str(exc))))
    sys.exit(
        f"Modèle absent de ComfyUI : {', '.join(names) or str(exc)[:300]}\n"
        "→ powershell -ExecutionPolicy Bypass -File scripts\\download_models.ps1 -Formats -ComfyModels <dossier models> "
        "(docs/15 §5), puis redémarrer ComfyUI."
    )


def sfx_list(_: argparse.Namespace) -> None:
    from .sfx import TAGS

    root = _settings().effective_sfx_dir
    print(f"Bibliothèque : {root}")
    for tag, spec in TAGS.items():
        print(f"  {tag:<16} {spec.kind:<4} {_count(root / tag):>2} fichier(s)  {spec.label}")


def sfx_generate(args: argparse.Namespace) -> None:
    from .providers.audio import ComfyAudio
    from .sfx import TAGS

    settings = _settings()
    root = settings.effective_sfx_dir
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else list(TAGS)
    unknown = [t for t in tags if t not in TAGS]
    if unknown:
        sys.exit(f"étiquettes inconnues : {unknown} (yt2 sfx list)")
    from .providers.video import WorkflowError

    audio = ComfyAudio(settings)
    for tag in tags:
        folder = root / tag
        todo = args.count - (0 if args.all else _count(folder))
        for _ in range(max(0, todo)):
            folder.mkdir(parents=True, exist_ok=True)
            seed = random.randint(0, 2**31)
            try:
                path = audio.sfx(tag, TAGS[tag].prompt, folder, seed=seed, seconds=TAGS[tag].seconds)
            except WorkflowError as exc:
                _missing_model(exc)
            print(f"{tag} : {path}")


def sfx_pick(args: argparse.Namespace) -> None:
    """Bruitages d'un drame plan par plan (le bruiteur, prompt sfx_pick), enregistrés dans le script de sa production ;
    --remount refait le montage avec eux (SQL retouch_video, sans toucher aux voix)."""
    from psycopg.types.json import Jsonb

    from .cli import _full_id
    from .db import Db
    from .models import ScriptV1
    from .prompts import prompt_text
    from .providers.llm import get_llm
    from .sfx import pick_sfx as library_file
    from .sfx_pick import PICK_PROMPT, pick_sfx, with_sfx

    settings = _settings()
    db = Db(settings.database_url, max_size=1)
    vid = _full_id(db, "videos", args.video)
    v = db.fetch_one(
        "select v.lang, v.production_id, p.script from videos v join productions p on p.id = v.production_id where v.id = %s",
        (vid,),
    )
    script = ScriptV1.model_validate(v["script"])
    picks = pick_sfx(get_llm(settings, db), script, v["lang"], prompt_text(db, "sfx_pick", PICK_PROMPT))
    db.execute(
        "update productions set script = %s where id = %s",
        (Jsonb(with_sfx(script, picks).model_dump(mode="json")), v["production_id"]),
    )
    root = settings.effective_sfx_dir
    for pos, s in enumerate(script.scenes, start=1):
        tags = picks.get(s.index, "")
        absent = [t.strip() for t in tags.split(",") if t.strip() and not library_file(root, t.strip(), "x")]
        print(f"  plan {pos:>2} : {tags or '—'}" + (f"   (absents de la bibliothèque : {', '.join(absent)})" if absent else ""))
    if args.remount:
        db.execute(
            "select retouch_video(%s, coalesce((select retouch from videos where id = %s), '{}'::jsonb), null)", (vid, vid)
        )
        print("montage → contrôle en file ; la vidéo revient à valider")


def music_list(_: argparse.Namespace) -> None:
    """Bibliothèque de Luca (mesure les pistes nouvelles ou remplacées), puis l'ancienne bibliothèque générée."""
    from .db import Db
    from .music import sync_library
    from .providers.audio import MUSIC_MOODS

    settings = _settings()
    folder = settings.effective_music_library_dir
    print(f"Musiques de Luca : {folder} (onglet Montage → Musiques)")
    for t in sync_library(Db(settings.database_url, max_size=1), folder):
        level = f"{t.lufs:6.1f} LUFS" if t.lufs is not None else "  non mesurée"
        state = "absente" if t.path is None else "coupée" if not t.enabled else "à décrire" if not t.formats else f"×{t.weight:g}"
        print(f"  {t.id:<12} {level}  {','.join(t.formats) or '—':<20} {','.join(t.moods) or '—':<32} {state:<10} {t.title}")
    root = settings.effective_music_dir
    print(f"\nAncienne bibliothèque générée, à défaut de la première : {root}")
    for mood in MUSIC_MOODS:
        print(f"  {mood:<11} {_count(root / mood):>2} piste(s)")


def music_generate(args: argparse.Namespace) -> None:
    from .providers.audio import MUSIC_MOODS, ComfyAudio

    if args.mood not in MUSIC_MOODS:
        sys.exit(f"ambiance inconnue : {args.mood} ({', '.join(MUSIC_MOODS)})")
    from .providers.video import WorkflowError

    settings = _settings()
    folder = settings.effective_music_dir / args.mood
    folder.mkdir(parents=True, exist_ok=True)
    audio = ComfyAudio(settings)
    for _ in range(args.count):
        try:
            print(f"{args.mood} : {audio.music(args.mood, folder, seed=random.randint(0, 2**31), seconds=args.seconds)}")
        except WorkflowError as exc:
            _missing_model(exc)


def register(sub: Any) -> None:
    """Ajoute les groupes hook, sfx et music à l'analyseur de `yt2` (worker/cli.py)."""
    hk = sub.add_parser("hook", help="titre d'accroche (façon MJClipIt)").add_subparsers(dest="cmd", required=True)
    hp = hk.add_parser("preview")
    hp.add_argument("text")
    hp.add_argument("--image", help="image de fond (sinon PNG transparent seul)")
    hp.add_argument("--font", help=".ttf (défaut : Arial Black)")
    hp.add_argument("--out")
    hp.set_defaults(fn=hook_preview)

    sx = sub.add_parser("sfx", help="bibliothèque de bruitages").add_subparsers(dest="cmd", required=True)
    sx.add_parser("list").set_defaults(fn=sfx_list)
    sg = sx.add_parser("generate")
    sg.add_argument("--tags", help="étiquettes séparées par des virgules (défaut : toutes)")
    sg.add_argument("--count", type=int, default=2, help="fichiers visés par étiquette")
    sg.add_argument("--all", action="store_true", help="générer --count fichiers même si la bibliothèque en a déjà")
    sg.set_defaults(fn=sfx_generate)
    sp = sx.add_parser("pick", help="le bruiteur choisit les bruitages d'un drame, plan par plan (docs/49 §10)")
    sp.add_argument("video", help="id de la vidéo (début suffit)")
    sp.add_argument("--remount", action="store_true", help="refaire le montage ensuite (la vidéo revient à valider)")
    sp.set_defaults(fn=sfx_pick)

    mu = sub.add_parser("music", help="bibliothèque de musique").add_subparsers(dest="cmd", required=True)
    mu.add_parser("list").set_defaults(fn=music_list)
    mg = mu.add_parser("generate")
    mg.add_argument("--mood", required=True)
    mg.add_argument("--count", type=int, default=3)
    mg.add_argument("--seconds", type=float, default=90.0)
    mg.set_defaults(fn=music_generate)
