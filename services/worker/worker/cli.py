"""Commande `yt2` : les gestes humains du pipeline, en attendant les écrans du dashboard.

    yt2 series list                                      séries de contenu et concepts en attente
    yt2 ideate SERIE [--count 6]                         mettre l'agent idée d'une série en file
    yt2 concepts list [--status proposed] [--series X]   concepts (id court, score, série, titre)
    yt2 concepts show ID                                 accroche, prémisse, faits et sources
    yt2 concepts approve ID [ID …] / reject ID [ID …]    valider ou refuser des concepts
    yt2 produce ID [--format A_voiceover] [--duration 30] [--channel fr]  créer la production d'un concept + script
    yt2 remake PRODUCTION                                refaire une production (même script, modèles actuels)
    yt2 wiki today [--series histoires_wikipedia]        matière Wikipédia du jour (sans LLM)
    yt2 script lint PRODUCTION                           vérifier un script contre les règles de storytelling
    yt2 subtitles list                                   profils de sous-titres disponibles
    yt2 subtitles preview [--profile impact] [--voice]   vidéo d'essai d'un profil (sans base de données)
    yt2 subtitles save NOM --file profil.json            enregistrer un profil personnalisé
    yt2 storyboard show PRODUCTION                       images par scène + planche PNG
    yt2 storyboard pick PRODUCTION 2:1 [4:0 …]           retenir l'image 1 pour la scène 2
    yt2 storyboard redo PRODUCTION 2 [4 …]               regénérer les images de ces scènes
    yt2 storyboard reinvent PRODUCTION 4 ["remarque"]    faire réécrire la scène (plan, narration) puis ses images
    yt2 storyboard approve PRODUCTION                    valider : lance clips, voix, montage
    yt2 strategy show fr [VERSION]                       dernière proposition (ou une version)
    yt2 strategy accept fr VERSION                       l'appliquer (agents + créneaux)
    yt2 strategy reject fr VERSION
    yt2 strategy run fr                                  calculer une proposition maintenant
    yt2 seo redo VIDEO                                   réécrire titre, description, tags
    yt2 settings show                                    réglages IA effectifs (base > .env)
    yt2 settings key gemini CLE                          enregistrer une clé API (chiffrée en base)
    yt2 settings llm --provider gemini --model gemini-3.8-flash [--fallbacks anthropic,ollama]
    yt2 settings test [gemini] [--model X]               appel minimal pour vérifier clé et modèle
    yt2 settings generation [--image zimage_turbo] [--video wan22_i2v_20step] [--candidates 2] [--voice-fr kokoro:ff_siwis]
    yt2 prompts list                                     prompts des agents : version active, origine (code, dashboard)
    yt2 prompts show idea [--version 3]                  texte d'un prompt (version active par défaut)
    yt2 prompts sync                                     enregistrer le texte du code (fait à chaque démarrage du worker)
    yt2 voice list                                       moteurs de voix (installés ?) et voix par langue (docs/18)
    yt2 voice say kokoro:ff_siwis [--text "…"] [--out f.wav]  faire dire une phrase par une voix
    yt2 hook preview "TEXTE" [--image photo.png]          titre d'accroche façon MJClipIt (formats visuels, docs/15)
    yt2 sfx list | generate [--tags excavator,whoosh]     bibliothèque de bruitages (Stable Audio Open)
    yt2 music list | generate --mood luxury               bibliothèque de musique (ACE-Step 1.5)

Les identifiants (concept, production, vidéo) acceptent un préfixe (8 premiers caractères).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .config import WORKER_ROOT, utf8_console
from .subtitles import BUILTIN_PROFILES, FontRegistry, SubtitleProfile, build_ass, resolve_profile, write_subtitles
from .timeline import SceneSpeech, estimate_speech_s, mix_speech, plan_timeline, trim_silence

SAMPLE = {
    "fr": [
        "Personne ne pousse jamais ce miroir…",
        "Et pourtant, il cache un secret.",
        "Derrière : un dressing de douze mètres carrés, éclairé en LED !",
    ],
    "en": [
        "Nobody ever pushes this mirror…",
        "And yet, it hides a secret.",
        "Behind it: a hidden walk-in closet, lit with LED strips!",
    ],
}


def _db() -> Any:
    from .config import Settings
    from .db import Db

    settings = Settings()
    return settings, Db(settings.database_url)


def _full_id(db: Any, table: str, prefix: str) -> str:
    assert table in {"concepts", "productions", "videos"}
    rows = db.fetch_all(f"select id from {table} where id::text like %s", (f"{prefix}%",))  # noqa: S608
    if len(rows) != 1:
        sys.exit(f"{table} : {len(rows)} correspondance(s) pour « {prefix} »")
    return str(rows[0]["id"])


# ---------------------------------------------------------------------------
# Séries, concepts, production
# ---------------------------------------------------------------------------


def series_list(_: argparse.Namespace) -> None:
    _, db = _db()
    rows = db.fetch_all(
        """select s.slug, s.name, s.source, s.weight, s.is_active, s.style_preset, s.recipe,
                  count(c.*) filter (where c.status = 'proposed') as proposed,
                  count(c.*) filter (where c.status = 'approved') as approved,
                  count(c.*) filter (where c.status = 'used') as used
           from series s left join concepts c on c.series_id = s.id group by s.id order by s.slug"""
    )
    print(f"{'série':<22} {'recette':<9} {'source':<10} {'poids':>5} {'actif':<6} {'proposés':>8} {'approuvés':>9} {'produits':>8}  style")
    for r in rows:
        print(f"{r['slug']:<22} {r['recipe']:<9} {r['source']:<10} {float(r['weight']):>5.1f} {'oui' if r['is_active'] else 'non':<6} "
              f"{r['proposed']:>8} {r['approved']:>9} {r['used']:>8}  {r['style_preset'] or ''}")


def ideate_series(args: argparse.Namespace) -> None:
    _, db = _db()
    from .series import get_series

    s = get_series(db, args.series)
    db.enqueue("ideate", payload={"series": s.slug, "count": args.count}, priority=60)
    print(f"Agent idée mis en file pour « {s.name} » ({args.count} idées). Suivre : yt2 concepts list --series {s.slug}")


def concepts_list(args: argparse.Namespace) -> None:
    _, db = _db()
    cond, params = ["true"], []
    if args.status:
        cond.append("c.status = %s")
        params.append(args.status)
    if args.series:
        cond.append("s.slug = %s")
        params.append(args.series)
    rows = db.fetch_all(
        f"""select c.id, c.status, c.score, c.title, c.hook, coalesce(s.slug, '-') as slug,
                   jsonb_array_length(c.facts) as facts
            from concepts c left join series s on s.id = c.series_id
            where {' and '.join(cond)} order by c.status, c.score desc nulls last, c.created_at desc limit %s""",  # noqa: S608
        (*params, args.limit),
    )
    for r in rows:
        print(f"{str(r['id'])[:8]}  {r['status']:<9} {float(r['score'] or 0):>5.0f}  {r['slug']:<20} {r['facts']:>2} faits  {r['title']}")
        print(f"          ↳ {r['hook']}")
    if not rows:
        print("aucun concept")


def concepts_show(args: argparse.Namespace) -> None:
    _, db = _db()
    cid = _full_id(db, "concepts", args.id)
    c = db.fetch_one(
        """select c.*, s.slug from concepts c left join series s on s.id = c.series_id where c.id = %s""", (cid,)
    )
    print(f"{c['title']}  [{c['status']}] · série {c['slug']} · catégorie {c['category']} · score {c['score']}")
    print(f"Accroche : {c['hook']}\nAngle : {c['angle'] or '-'}\nPrémisse : {c['premise']}")
    print("Temps visuels :", " → ".join(c["visual_beats"] or []))
    if c["facts"]:
        print("Faits :")
        for f in c["facts"]:
            print(f"  [{f['source'] + 1}] {f['claim']}")
        print("Sources :")
        for i, s in enumerate(c["sources"] or []):
            print(f"  [{i + 1}] {s['title']} — {s['url']} (révision {s.get('revision')})")


def concepts_decide(args: argparse.Namespace, status: str) -> None:
    _, db = _db()
    for prefix in args.ids:
        cid = _full_id(db, "concepts", prefix)
        db.execute("update concepts set status = %s where id = %s and status in ('proposed', 'approved', 'rejected')", (status, cid))
        print(f"{cid[:8]} → {status}")
    if status == "approved":
        print("Production automatique toutes les 15 min si AUTO_PRODUCE=1, sinon : yt2 produce <id>")


def produce(args: argparse.Namespace) -> None:
    _, db = _db()
    from .series import create_production

    cid = _full_id(db, "concepts", args.id)
    channel = db.fetch_one("select id from channels where slug = %s", (args.channel,)) if args.channel else None
    if args.channel and not channel:
        sys.exit(f"chaîne inconnue : {args.channel}")
    pid, created = create_production(db, cid, format=args.format, target_duration_s=args.duration, priority=50,
                                     channel_id=channel["id"] if channel else None)
    print(f"Production {pid} {'créée : script en file' if created else 'déjà en cours'}. Suivre : yt2 storyboard show {str(pid)[:8]}")


def wiki_today(args: argparse.Namespace) -> None:
    settings, db = _db()
    from .series import get_series
    from .sources.wikipedia import WikipediaClient, daily_material, material_text

    s = get_series(db, args.series)
    if s.source != "wikipedia":
        sys.exit(f"la série {s.slug} n'utilise pas Wikipédia")
    client = WikipediaClient(lang=s.lang, user_agent=settings.effective_wikipedia_user_agent)
    docs = daily_material(client, s.source_config, date.today(), max_docs=int(s.source_config.get("max_docs", 6)))
    for d in docs:
        print(f"- {d.title} · {d.kind} · {d.note or ''} · {d.words} mots · {d.url}")
    if args.full:
        print("\n" + material_text(docs))


def script_lint(args: argparse.Namespace) -> None:
    _, db = _db()
    from .models import ScriptV1
    from .storytelling import lint_script

    pid = _full_id(db, "productions", args.production)
    prod = db.fetch_one("select script, format, target_duration_s from productions where id = %s", (pid,))
    if not prod or not prod["script"]:
        sys.exit("pas de script pour cette production")
    # langues des vidéos de la production (une seule chaîne depuis 0008), sinon celles des chaînes actives
    langs = [r["lang"] for r in db.fetch_all("select distinct lang from videos where production_id = %s", (pid,))] or [
        r["lang"] for r in db.fetch_all("select lang from channels where is_active")
    ]
    langs = langs if prod["format"] == "A_voiceover" else []
    script = ScriptV1.model_validate(prod["script"])
    for s in script.scenes:
        cont = " (continuité)" if s.continues_previous else ""
        print(f"{s.index + 1}. [{s.role or '?'}] {s.duration_s:g} s{cont} · {s.narration.get('fr', '')}")
    issues = lint_script(script, langs, prod["target_duration_s"])
    print("\nConforme aux règles de storytelling." if not issues else "\nProblèmes :\n- " + "\n- ".join(issues))


# ---------------------------------------------------------------------------
# Sous-titres
# ---------------------------------------------------------------------------


def subtitles_list(_: argparse.Namespace) -> None:
    fonts = FontRegistry.scan(WORKER_ROOT / "assets" / "fonts")
    print("Profils intégrés :")
    for name, p in BUILTIN_PROFILES.items():
        print(f"  {name:<9} {p.font_family}, {p.font_size} px, mot actif {p.highlight_mode} {p.highlight_color}, "
              f"{p.position}, {p.max_words} mots, animation {p.animation}")
    print("Polices fournies :", ", ".join(fonts.families()))
    try:
        _, db = _db()
        saved = db.fetch_all("select name, updated_at from subtitle_profiles order by name")
        print("Profils enregistrés :", ", ".join(r["name"] for r in saved) or "aucun")
    except Exception:  # noqa: BLE001 — pas de base configurée : on s'en passe
        print("Profils enregistrés : base non configurée")


def subtitles_preview(args: argparse.Namespace) -> None:
    profile = (
        SubtitleProfile.model_validate(json.loads(Path(args.file).read_text(encoding="utf-8")))
        if args.file
        else resolve_profile(args.profile)
    )
    fonts = FontRegistry.scan(WORKER_ROOT / "assets" / "fonts")
    lines = args.text or SAMPLE[args.lang]
    out = Path(args.out) if args.out else Path(tempfile.gettempdir()) / "yt2_apercu" / f"sous_titres_{profile.name}.mp4"
    work = out.parent
    work.mkdir(parents=True, exist_ok=True)

    speeches: dict[int, Any] = {}
    rate = 24000
    if args.voice:  # vraie voix Kokoro si les modèles sont installés
        from .providers.tts import KokoroTTS

        tts = KokoroTTS(SimpleNamespace(kokoro_voice_fr="ff_siwis", kokoro_voice_en="af_heart",
                                        kokoro_model_path=WORKER_ROOT / "models" / "kokoro-v1.0.onnx",
                                        kokoro_voices_path=WORKER_ROOT / "models" / "voices-v1.0.bin"))  # type: ignore[arg-type]
        for i, text in enumerate(lines):
            sp = tts.speak(text, lang=args.lang, speed=args.speed)
            rate = sp.rate
            speeches[i] = trim_silence(sp.samples, sp.rate)
        scenes = [SceneSpeech(i, 4.0, t, len(speeches[i]) / rate) for i, t in enumerate(lines)]
    else:
        scenes = [SceneSpeech(i, 4.0, t, estimate_speech_s(t, args.lang)) for i, t in enumerate(lines)]
    timeline = plan_timeline(scenes, args.lang)
    titles = [(0.0, timeline.scenes[0].duration, args.title)] if args.title else []
    ass = build_ass([s.words for s in timeline.scenes], profile, titles, fonts=fonts)
    flt = write_subtitles(work, ass, profile, fonts)
    total = timeline.duration_s
    if args.background:
        bg = ["-stream_loop", "-1", "-i", str(Path(args.background).resolve())]
        vchain = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30"
    else:
        bg = ["-f", "lavfi", "-i", f"gradients=s=1080x1920:c0=0x2B3A55:c1=0xC9A66B:x0=0:y0=0:x1=1080:y1=1920:d={total}:speed=0.02"]
        vchain = "[0:v]fps=30"
    cmd = ["ffmpeg", "-y", "-v", "error", *bg]
    amap: list[str] = ["-an"]
    if speeches:
        import soundfile as sf

        sf.write(str(work / "voix.wav"), mix_speech(timeline, speeches, rate), rate)
        cmd += ["-i", "voix.wav"]
        amap = ["-map", "1:a", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-filter_complex", f"{vchain},{flt}[v]", "-map", "[v]", *amap, "-t", f"{total:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out.resolve())]
    subprocess.run(cmd, cwd=work, check=True)
    print(f"Aperçu « {profile.name} » ({total:.1f} s) : {out}")


def subtitles_save(args: argparse.Namespace) -> None:
    profile = SubtitleProfile.model_validate({**json.loads(Path(args.file).read_text(encoding="utf-8")), "name": args.name})
    _, db = _db()
    from psycopg.types.json import Jsonb

    db.execute(
        """insert into subtitle_profiles (name, profile) values (%s, %s)
           on conflict (name) do update set profile = excluded.profile""",
        (args.name, Jsonb(profile.model_dump())),
    )
    print(f"Profil « {args.name} » enregistré (aperçus : yt2 subtitles preview --profile {args.name}). Le montage des vidéos "
          "suit le modèle de l'onglet Montage du dashboard (docs/23-montage.md), qui a ses propres sous-titres.")


# ---------------------------------------------------------------------------
# Storyboard
# ---------------------------------------------------------------------------


def _storyboard(db: Any, pid: str) -> dict[int, list[dict[str, Any]]]:
    rows = db.fetch_all(
        """select id, scene_index, local_path, selected, meta from assets
           where production_id = %s and kind = 'storyboard' order by scene_index, created_at""",
        (pid,),
    )
    out: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["scene_index"], []).append(r)
    return out


def storyboard_show(args: argparse.Namespace) -> None:
    from .models import ScriptV1
    from .steps.storyboard import build_sheet

    settings, db = _db()
    pid = _full_id(db, "productions", args.production)
    prod = db.fetch_one("select status, script from productions where id = %s", (pid,))
    if not prod or not prod["script"]:
        sys.exit("production sans script")
    script = ScriptV1.model_validate(prod["script"])
    board = _storyboard(db, pid)
    print(f"Production {pid} · statut {prod['status']}")
    for s in script.scenes:
        cont = " · continuité (part du clip précédent)" if s.continues_previous else ""
        print(f"\nScène {s.index} [{s.role or '?'}] ({s.duration_s:g} s){cont} — {s.visual_prompt[:110]}")
        for k, a in enumerate(board.get(s.index, [])):
            print(f"   {'✔' if a['selected'] else ' '} image {k} : {a['local_path']}")
    sheet = build_sheet(db, pid, script, settings.data_dir / "productions" / pid / "storyboard" / "planche.png")
    if sheet:
        print(f"\nPlanche : {sheet}")


def storyboard_pick(args: argparse.Namespace) -> None:
    _, db = _db()
    pid = _full_id(db, "productions", args.production)
    board = _storyboard(db, pid)
    for pair in args.choices:
        scene, image = (int(x) for x in pair.split(":"))
        items = board.get(scene, [])
        if not 0 <= image < len(items):
            sys.exit(f"scène {scene} : image {image} inexistante ({len(items)} image(s))")
        db.execute("update assets set selected = (id = %s) where production_id = %s and kind = 'storyboard' and scene_index = %s",
                   (items[image]["id"], pid, scene))
        print(f"Scène {scene} : image {image} retenue")
        derived = db.fetch_all(
            """select distinct scene_index from assets where production_id = %s and kind = 'storyboard'
               and scene_index > %s and meta ? 'edited_from' order by scene_index""",
            (pid, scene),
        )
        if derived:  # chantier en accéléré : les étapes suivantes sont des retouches de celle-ci (docs/15)
            print(f"  étapes retouchées à partir d'elle : refaire avec yt2 storyboard redo {args.production} {scene + 1}")


def storyboard_redo(args: argparse.Namespace) -> None:
    _, db = _db()
    pid = _full_id(db, "productions", args.production)
    db.enqueue("storyboard", production_id=pid, priority=80, payload={"scenes": [int(s) for s in args.scenes]})
    print(f"Nouvelles images demandées pour les scènes {', '.join(args.scenes)}")


def storyboard_reinvent(args: argparse.Namespace) -> None:
    """Comme « Réinventer » dans Création (docs/27) : le scénariste réécrit la scène, puis ses images sont refaites."""
    from .reinvent import NOTE_MAX

    _, db = _db()
    pid = _full_id(db, "productions", args.production)
    payload: dict[str, Any] = {"scenes": [args.scene], "reinvent": True}
    if (args.note or "").strip():
        payload["note"] = args.note.strip()[:NOTE_MAX]
    db.enqueue("storyboard", production_id=pid, priority=80, payload=payload)
    print(f"Scène {args.scene} : le scénariste la réinvente, puis ses images sont refaites (yt2 storyboard show {args.production})")


def storyboard_approve(args: argparse.Namespace) -> None:
    from .dag import enqueue_render_dag

    settings, db = _db()
    pid = _full_id(db, "productions", args.production)
    missing = db.fetch_all(
        """select distinct a.scene_index from assets a where a.production_id = %s and a.kind = 'storyboard'
           and not exists (select 1 from assets b where b.production_id = a.production_id and b.kind = 'storyboard'
                           and b.scene_index = a.scene_index and b.selected)""",
        (pid,),
    )
    if missing:
        sys.exit(f"scènes sans image retenue : {[m['scene_index'] for m in missing]} (yt2 storyboard pick …)")
    print("Storyboard validé :", enqueue_render_dag(db, pid, settings.clip_continuity, settings.continuity_max_chain))


# ---------------------------------------------------------------------------
# Stratégie
# ---------------------------------------------------------------------------


def _strategy(db: Any, slug: str, version: int | None) -> dict[str, Any]:
    row = db.fetch_one(
        f"""select s.*, c.id as cid, c.slug from strategies s join channels c on c.id = s.channel_id
            where c.slug = %s {'and s.version = %s' if version else ''} order by s.version desc limit 1""",  # noqa: S608
        (slug, version) if version else (slug,),
    )
    if not row:
        sys.exit("aucune stratégie trouvée")
    return row


def strategy_show(args: argparse.Namespace) -> None:
    _, db = _db()
    s = _strategy(db, args.channel, args.version)
    print(f"Stratégie v{s['version']} · {s['slug']} · {s['status']} · {s['stats'].get('n', 0)} vidéos sur {s['window_days']} jours")
    print(json.dumps(s["proposal"], ensure_ascii=False, indent=2) if s["proposal"] else "Pas de proposition : données insuffisantes.")


def strategy_decide(args: argparse.Namespace, accept: bool) -> None:
    _, db = _db()
    s = _strategy(db, args.channel, args.version)
    if s["status"] != "proposed":
        sys.exit(f"v{s['version']} est déjà « {s['status']} »")
    if accept and not s["proposal"]:
        sys.exit("rien à appliquer : proposition vide (données insuffisantes)")
    if accept:
        db.execute("update strategies set status = 'superseded' where channel_id = %s and status = 'active'", (s["cid"],))
        slots = (s["proposal"] or {}).get("publish_slots")
        if slots:
            db.execute("update channels set publish_slots = %s::time[] where id = %s", (slots, s["cid"]))
            print("Créneaux de publication mis à jour :", slots)
    db.execute("update strategies set status = %s, decided_at = now() where id = %s", ("active" if accept else "rejected", s["id"]))
    print(f"Stratégie v{s['version']} {'appliquée' if accept else 'refusée'}")


def strategy_run(args: argparse.Namespace) -> None:
    settings, db = _db()
    c = db.fetch_one("select id from channels where slug = %s", (args.channel,))
    if not c:
        sys.exit("chaîne inconnue")
    db.enqueue("strategy", channel_id=c["id"], payload={"window_days": settings.strategy_window_days}, priority=60)
    print("Calcul de stratégie mis en file ; résultat : yt2 strategy show", args.channel)


def seo_redo(args: argparse.Namespace) -> None:
    _, db = _db()
    vid = _full_id(db, "videos", args.video)
    db.enqueue("seo", video_id=vid, priority=60, payload={"force": True})
    print("Réécriture SEO mise en file")


# ---------------------------------------------------------------------------
# Réglages IA (les mêmes que Réglages → Intelligence artificielle du dashboard)
# ---------------------------------------------------------------------------


def settings_show(_: argparse.Namespace) -> None:
    from .settings_store import PROVIDERS, key_slots, load_generation_config, load_llm_config

    settings, db = _db()
    cfg = load_llm_config(settings, db, use_cache=False)
    slots = key_slots(db)
    print(f"Source : {'base (dashboard)' if cfg.source == 'db' else '.env'}")
    for kind, label in (("writer", "Écriture (idées, scénaristes, relecteur)"), ("default", "Autres agents")):
        print(f"{label} : " + " > ".join(f"{e.provider}:{e.model}" for e in cfg.chain(kind)))
    for p in PROVIDERS:
        if p == "ollama":
            print(f"  {p:<10} local")
            continue
        keys = ", ".join(f"n° {s} (…{h})" for s, h in slots.get(p, [])) or ("clé .env" if cfg.key_for(p) else "pas de clé")
        print(f"  {p:<10} clés : {keys}")
    gen = load_generation_config(settings, db, use_cache=False)
    print(f"\nGénération ({'base (dashboard)' if gen.source == 'db' else '.env'}) : images {gen.image_workflow} · vidéo "
          f"{gen.video_workflow} · {gen.storyboard_candidates} image(s) par scène · voix {gen.voices}")


def settings_generation(args: argparse.Namespace) -> None:
    from .providers.video import load_catalog
    from .settings_store import save_generation_settings

    settings, db = _db()
    catalog = load_catalog(settings.comfy_workflow_dir)
    for kind, name in (("image", args.image), ("video", args.video)):
        if name and name not in catalog.get(kind, {}):
            sys.exit(f"modèle {kind} inconnu : {name} (catalogue : {', '.join(catalog.get(kind, {}))})")
    from .providers.tts import split_voice

    voices = {k: ":".join(split_voice(v)) for k, v in (("fr", args.voice_fr), ("en", args.voice_en)) if v}  # « moteur:voix »
    for lang, voice in voices.items():
        known = [e["id"] for e in (catalog.get("voices") or {}).get(lang, [])]
        if voice not in known:
            sys.exit(f"voix {lang} inconnue : {voice} (catalogue : {', '.join(known)})")
    voices = {k: v.removeprefix("kokoro:") for k, v in voices.items()}  # Kokoro : nom seul, comme avant les moteurs multiples
    value = save_generation_settings(
        db, image_workflow=args.image, video_workflow=args.video, storyboard_candidates=args.candidates, voices=voices or None,
    )
    print("Réglages de génération :", json.dumps(value, ensure_ascii=False))


def voice_list(_: argparse.Namespace) -> None:
    """Moteurs de voix du catalogue (installés ou non) et voix proposées par langue (docs/18-voix.md)."""
    from .config import Settings
    from .providers.tts import get_engine, tts_catalog

    settings = Settings()
    catalog = tts_catalog(settings)
    for name, spec in (catalog.get("tts") or {}).items():
        try:
            engine = get_engine(settings, name)
            ok = all((settings.yt2_home / rel).exists() for rel in spec.get("check", [])) and (
                not hasattr(engine, "python") or engine.python.exists())
        except ValueError:
            ok = False
        print(f"{name:<14} {'installé' if ok else 'À INSTALLER':<12} {spec.get('label', '')} · {spec.get('license', '')}")
    for lang, voices in (catalog.get("voices") or {}).items():
        print(f"\n{lang} :")
        for v in voices:
            print(f"  {v['id']:<34} {v.get('label', '')}")


def voice_say(args: argparse.Namespace) -> None:
    """Fait dire une phrase par une voix, sans base de données : fichier .wav (essai d'un moteur fraîchement installé)."""
    import time

    import soundfile as sf

    from .config import Settings
    from .providers.tts import get_engine, split_voice
    from .steps.voice_preview import SAMPLES
    from .timeline import trim_silence

    settings = Settings()
    engine_name, voice = split_voice(args.voice)
    engine = get_engine(settings, engine_name)
    if args.online and hasattr(engine, "online"):
        engine.online = True  # premier essai après installation : le moteur télécharge ses modèles
    text = args.text or SAMPLES[args.lang]
    started = time.monotonic()
    [sp] = engine.speak_many([text], voice=voice, lang=args.lang, speed=args.speed,
                             on_progress=lambda pct, label: print(f"  {pct:3d} % {label}"))
    out = Path(args.out) if args.out else settings.data_dir / "previews" / "voices" / f"cli_{engine_name}_{voice}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    samples = trim_silence(sp.samples, sp.rate)
    sf.write(str(out), samples, sp.rate)
    print(f"{out} : {len(samples) / sp.rate:.1f} s de voix en {time.monotonic() - started:.1f} s ({engine_name}:{voice})")


def remake(args: argparse.Namespace) -> None:
    _, db = _db()
    pid = _full_id(db, "productions", args.production)
    row = db.fetch_one("select remake_production(%s) as id", (pid,))
    print(f"Production {row['id']} créée : même script, modèles des réglages actuels. Suivre : yt2 storyboard show {str(row['id'])[:8]}")


def settings_key(args: argparse.Namespace) -> None:
    from .settings_store import SECRET_NAMES, delete_secret, save_secret

    if args.provider not in SECRET_NAMES:
        sys.exit(f"fournisseur sans clé : {args.provider}")
    settings, db = _db()
    if args.value == "-":  # retirer la clé n° --slot
        delete_secret(db, args.provider, args.slot or 1)
        print(f"Clé {args.provider} n° {args.slot or 1} retirée")
        return
    slot = save_secret(settings, db, args.provider, args.value, args.slot)
    print(f"Clé {args.provider} n° {slot} enregistrée (…{args.value[-4:]}), chiffrée avec CREDENTIALS_KEY")


def settings_llm(args: argparse.Namespace) -> None:
    from .settings_store import save_llm_settings

    _, db = _db()
    value = save_llm_settings(
        db,
        provider=args.provider,
        models={args.provider: args.model} if args.model and args.provider else None,
        fallbacks=[f.strip() for f in args.fallbacks.split(",") if f.strip()] if args.fallbacks else None,
        # modèle d'écriture (idées, scénaristes, relecteur) ; « - » le retire (même modèle que les autres agents)
        writer_models={args.provider: "" if args.writer_model == "-" else args.writer_model}
        if args.writer_model and args.provider else None,
        # chaînes : « gemini:gemini-3.8-flash,gemini:gemini-3.5-flash-lite » (1er choix, 2e choix…) ; « - » la retire
        chains={kind: [] if spec == "-" else [{"provider": p.strip(), "model": m.strip()}
                                              for p, _, m in (x.partition(":") for x in spec.split(",") if x.strip())]
                for kind, spec in (("writer", args.writer_chain), ("default", args.chain)) if spec} or None,
    )
    print("Réglages LLM :", json.dumps(value, ensure_ascii=False))


PROMPT_ORIGIN = {"code": "code", "human": "dashboard", "improve_agent": "agent amélioration"}


def prompts_list(_: argparse.Namespace) -> None:
    """Chaque clé de prompt (agents et consignes communes, worker/prompts.py) : version active et son origine."""
    from .prompts import code_prompts

    _, db = _db()
    rows = db.fetch_all(
        """select agent, max(version) filter (where is_active) as active, max(version) as last,
                  max(version) filter (where created_by = 'code') as last_code,
                  (array_agg(created_by order by version desc) filter (where is_active))[1] as origin
           from prompt_templates group by agent"""
    )
    by_key = {r["agent"]: r for r in rows}
    for key, text in code_prompts().items():
        r = by_key.get(key)
        if not r or r["active"] is None:
            print(f"{key:<20} texte du code (pas encore en base : relancer le worker ou `yt2 prompts sync`)")
            continue
        origin = PROMPT_ORIGIN.get(r["origin"], r["origin"])
        note = " · le code a une version plus récente" if r["last_code"] and r["last_code"] > r["active"] and origin != "code" else ""
        print(f"{key:<20} v{r['active']} ({origin}) sur {r['last']} version(s){note} · {len(text)} car. dans le code")


def prompts_show(args: argparse.Namespace) -> None:
    _, db = _db()
    if args.version:
        row = db.fetch_one("select version, created_by, content from prompt_templates where agent = %s and version = %s",
                           (args.key, args.version))
    else:
        row = db.fetch_one("select version, created_by, content from prompt_templates where agent = %s and is_active", (args.key,))
    if not row:
        sys.exit(f"aucune version pour {args.key}")
    print(f"# {args.key} v{row['version']} ({PROMPT_ORIGIN.get(row['created_by'], row['created_by'])})\n\n{row['content']}")


def prompts_sync(_: argparse.Namespace) -> None:
    from .prompts import sync_code_prompts

    _, db = _db()
    for key, result in sync_code_prompts(db).items():
        print(f"{key:<20} {result}")


def settings_test(args: argparse.Namespace) -> None:
    from .providers.llm import test_provider
    from .settings_store import load_llm_config

    settings, db = _db()
    first = load_llm_config(settings, db, use_cache=False).chain("default")
    name = args.provider or (first[0].provider if first else "gemini")
    print(test_provider(settings, db, name, args.model, key_index=args.key))


def main(argv: list[str] | None = None) -> None:
    utf8_console()
    p = argparse.ArgumentParser(prog="yt2", description="YouTube 2.0 : gestes humains du pipeline")
    sub = p.add_subparsers(dest="group", required=True)

    se = sub.add_parser("series", help="séries de contenu").add_subparsers(dest="cmd", required=True)
    se.add_parser("list").set_defaults(fn=series_list)

    idp = sub.add_parser("ideate", help="lancer l'agent idée d'une série")
    idp.add_argument("series")
    idp.add_argument("--count", type=int, default=6)
    idp.set_defaults(fn=ideate_series)

    co = sub.add_parser("concepts", help="idées proposées par les agents").add_subparsers(dest="cmd", required=True)
    cl = co.add_parser("list")
    cl.add_argument("--status", choices=["proposed", "approved", "rejected", "used"])
    cl.add_argument("--series")
    cl.add_argument("--limit", type=int, default=40)
    cl.set_defaults(fn=concepts_list)
    cs = co.add_parser("show")
    cs.add_argument("id")
    cs.set_defaults(fn=concepts_show)
    for name, status in (("approve", "approved"), ("reject", "rejected")):
        c = co.add_parser(name)
        c.add_argument("ids", nargs="+")
        c.set_defaults(fn=lambda a, st=status: concepts_decide(a, st))

    pr = sub.add_parser("produce", help="créer la production d'un concept")
    pr.add_argument("id")
    pr.add_argument("--format", choices=["A_voiceover", "B_visual"])
    pr.add_argument("--duration", type=int)
    pr.add_argument("--channel", help="slug de la chaîne visée (défaut : celle du concept, sinon la première active)")
    pr.set_defaults(fn=produce)
    rm = sub.add_parser("remake", help="refaire une production avec les modèles des réglages actuels")
    rm.add_argument("production")
    rm.set_defaults(fn=remake)

    wk = sub.add_parser("wiki", help="matière Wikipédia").add_subparsers(dest="cmd", required=True)
    wt = wk.add_parser("today")
    wt.add_argument("--series", default="histoires_wikipedia")
    wt.add_argument("--full", action="store_true", help="afficher les extraits")
    wt.set_defaults(fn=wiki_today)

    sc = sub.add_parser("script", help="scripts").add_subparsers(dest="cmd", required=True)
    sl = sc.add_parser("lint")
    sl.add_argument("production")
    sl.set_defaults(fn=script_lint)

    st = sub.add_parser("subtitles", help="profils de sous-titres").add_subparsers(dest="cmd", required=True)
    st.add_parser("list").set_defaults(fn=subtitles_list)
    pv = st.add_parser("preview")
    pv.add_argument("--profile", default="impact")
    pv.add_argument("--file", help="profil JSON (SubtitleProfile)")
    pv.add_argument("--text", nargs="+", help="une phrase par scène")
    pv.add_argument("--lang", default="fr", choices=["fr", "en"])
    pv.add_argument("--title", default="Le miroir secret", help="texte à l'écran de la première scène ('' = aucun)")
    pv.add_argument("--voice", action="store_true", help="vraie voix Kokoro (modèles requis)")
    pv.add_argument("--speed", type=float, default=1.05)
    pv.add_argument("--background", help="image ou vidéo de fond")
    pv.add_argument("--out")
    pv.set_defaults(fn=subtitles_preview)
    sv = st.add_parser("save")
    sv.add_argument("name")
    sv.add_argument("--file", required=True)
    sv.set_defaults(fn=subtitles_save)

    sb = sub.add_parser("storyboard", help="validation des images").add_subparsers(dest="cmd", required=True)
    for name, fn in (("show", storyboard_show), ("approve", storyboard_approve)):
        c = sb.add_parser(name)
        c.add_argument("production")
        c.set_defaults(fn=fn)
    pk = sb.add_parser("pick")
    pk.add_argument("production")
    pk.add_argument("choices", nargs="+", help="scène:image, ex. 2:1")
    pk.set_defaults(fn=storyboard_pick)
    rd = sb.add_parser("redo")
    rd.add_argument("production")
    rd.add_argument("scenes", nargs="+")
    rd.set_defaults(fn=storyboard_redo)
    ri = sb.add_parser("reinvent")
    ri.add_argument("production")
    ri.add_argument("scene", type=int, help="index de la scène dans le script (yt2 storyboard show)")
    ri.add_argument("note", nargs="?", default="", help="ce qui ne va pas (facultatif)")
    ri.set_defaults(fn=storyboard_reinvent)

    sg = sub.add_parser("strategy", help="propositions de stratégie").add_subparsers(dest="cmd", required=True)
    sh = sg.add_parser("show")
    sh.add_argument("channel")
    sh.add_argument("version", nargs="?", type=int)
    sh.set_defaults(fn=strategy_show)
    for name, accept in (("accept", True), ("reject", False)):
        c = sg.add_parser(name)
        c.add_argument("channel")
        c.add_argument("version", type=int)
        c.set_defaults(fn=lambda a, acc=accept: strategy_decide(a, acc))
    rn = sg.add_parser("run")
    rn.add_argument("channel")
    rn.set_defaults(fn=strategy_run)

    so = sub.add_parser("seo", help="métadonnées").add_subparsers(dest="cmd", required=True)
    rs = so.add_parser("redo")
    rs.add_argument("video")
    rs.set_defaults(fn=seo_redo)

    sg2 = sub.add_parser("settings", help="réglages IA").add_subparsers(dest="cmd", required=True)
    sg2.add_parser("show").set_defaults(fn=settings_show)
    sk = sg2.add_parser("key", help="ajoute une clé (à la suite des autres), ou remplace la clé n° --slot ; « - » la retire")
    sk.add_argument("provider", choices=["gemini", "anthropic", "mistral"])
    sk.add_argument("value")
    sk.add_argument("--slot", type=int, help="numéro de la clé (1 = la première)")
    sk.set_defaults(fn=settings_key)
    sl2 = sg2.add_parser("llm")
    sl2.add_argument("--provider", choices=["gemini", "anthropic", "mistral", "ollama"])
    sl2.add_argument("--model")
    sl2.add_argument("--fallbacks", help="liste séparée par des virgules")
    sl2.add_argument("--writer-model", help="modèle d'écriture du fournisseur (idées, scénaristes, relecteur), « - » pour le retirer")
    sl2.add_argument("--writer-chain", help="chaîne d'écriture, ex. gemini:gemini-3.8-flash,gemini:gemini-3.5-flash-lite")
    sl2.add_argument("--chain", help="chaîne des autres agents, même forme ; « - » pour la retirer")
    sl2.set_defaults(fn=settings_llm)
    sgn = sg2.add_parser("generation", help="modèles d'image, de vidéo et voix (workflows/catalog.json)")
    sgn.add_argument("--image", help="ex. zimage_turbo, qwen_image_21")
    sgn.add_argument("--video", help="ex. wan22_i2v_4step, wan22_i2v_20step")
    sgn.add_argument("--candidates", type=int, choices=[1, 2, 3, 4])
    sgn.add_argument("--voice-fr", help="« moteur:voix », ex. kokoro:ff_siwis (yt2 voice list)")
    sgn.add_argument("--voice-en")
    sgn.set_defaults(fn=settings_generation)
    stt = sg2.add_parser("test")
    stt.add_argument("provider", nargs="?", choices=["gemini", "anthropic", "mistral", "ollama"])
    stt.add_argument("--model")
    stt.add_argument("--key", type=int, help="tester la clé n° N seule (1 = la première)")
    stt.set_defaults(fn=settings_test)

    pp = sub.add_parser("prompts", help="prompts des agents (onglet Agents du dashboard, docs/22)").add_subparsers(
        dest="cmd", required=True)
    pp.add_parser("list").set_defaults(fn=prompts_list)
    ps = pp.add_parser("show")
    ps.add_argument("key")
    ps.add_argument("--version", type=int)
    ps.set_defaults(fn=prompts_show)
    pp.add_parser("sync").set_defaults(fn=prompts_sync)

    vo = sub.add_parser("voice", help="moteurs de voix (docs/18)").add_subparsers(dest="cmd", required=True)
    vo.add_parser("list").set_defaults(fn=voice_list)
    vs = vo.add_parser("say", help="faire dire une phrase par une voix (fichier .wav, sans base)")
    vs.add_argument("voice", help="« moteur:voix », ex. kokoro:ff_siwis")
    vs.add_argument("--lang", default="fr", choices=["fr", "en"])
    vs.add_argument("--text")
    vs.add_argument("--speed", type=float, default=1.0)
    vs.add_argument("--out")
    vs.add_argument("--online", action="store_true", help="autoriser le moteur à télécharger ses modèles (premier essai)")
    vs.set_defaults(fn=voice_say)

    from .cli_formats import register  # hook, sfx, music : formats visuels (docs/15)
    from .cli_gemini import register as register_gemini  # gemini open|status|check|clip|send (docs/17)

    register(sub)
    register_gemini(sub)

    args = p.parse_args(argv)
    if getattr(args, "title", None) == "":
        args.title = None
    args.fn(args)


if __name__ == "__main__":
    main()
