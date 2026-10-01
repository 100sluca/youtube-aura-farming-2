"""Variante d'accroche d'une vidéo montée (docs/49-variante-accroche.md).

Demandé par Luca le 01/10 devant « Zraoua » : la vidéo est bonne, mais son accroche (« Ce village berbère a survécu
2 000 ans contre le désert. ») ne fait rien ressentir ; il veut publier la même vidéo avec deux accroches et laisser
les courbes de rétention trancher. YouTube ne compare pas deux débuts d'une même vidéo : la variante est donc un
autre Short, sur les mêmes clips, dont seules l'accroche et la promesse (les deux premières phrases) changent.

Une production n'a qu'une vidéo par chaîne (index videos_production_channel_key) : la variante est une COPIE de la
production, son script avec la nouvelle accroche, la nouvelle promesse et leur titre d'accroche, et ses clips et images
du storyboard liés sur le disque (lien physique NTFS : aucun octet de plus, et effacer l'une ne casse pas l'autre ; sur
un autre disque, le chemin d'origine est gardé). Sa vidéo reprend la voix, la musique, le titre YouTube choisi et
`variant_of` (migration 0037) la relie à l'originale. Puis voix → montage → contrôle, comme une vidéo neuve ; elle
arrive à valider dans le Dashboard, jamais publiée seule.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from psycopg.types.json import Jsonb

from .hooktitle import clean_hook, lint_hook_title
from .models import ScriptV1
from .storycraft import HOOK_PROMISE_WORDS_MAX, scene_seconds
from .storytelling import HOOK_WORDS_MAX, said_words

log = structlog.get_logger(__name__)

# Colonnes recopiées de la production d'origine (le reste : valeurs par défaut, script et statut posés ici)
PRODUCTION_COLUMNS = (
    "concept_id",
    "format",
    "target_duration_s",
    "style_preset",
    "video_provider",
    "prompt_template_id",
    "series_id",
    "lint",
    "image_workflow",
    "channel_id",
)
COPIED_ASSETS = ("clip", "storyboard")  # au niveau de la production ; voix, montage et affiche sont refaits


@dataclass
class Variant:
    production_id: UUID
    video_id: UUID
    linked: int  # fichiers liés sur le disque
    issues: list[str]  # remarques du correcteur (accroche longue, titre d'accroche…), sans bloquer


def check_texts(hook: str, promise: str, hook_title: str, lang: str = "fr") -> list[str]:
    """Ce que le correcteur du récit dirait de la nouvelle ouverture (storycraft.lint_story), sans bloquer."""
    issues = []
    n_hook, n_promise = len(said_words(hook, lang)), len(said_words(promise, lang))
    if n_hook > HOOK_WORDS_MAX:
        issues.append(f"accroche de {n_hook} mots dits : {HOOK_WORDS_MAX} au plus")
    if n_hook + n_promise > HOOK_PROMISE_WORDS_MAX:
        issues.append(f"accroche et promesse : {n_hook + n_promise} mots dits, {HOOK_PROMISE_WORDS_MAX} au plus (6 s)")
    return issues + lint_hook_title(hook_title, lang)


def variant_script(
    script: ScriptV1, lang: str, hook: str, promise: str, hook_title: str, title: str, on_screen: str | None = None
) -> ScriptV1:
    """Script de la variante : la scène de l'accroche et celle de la promesse disent les nouveaux textes, leur durée
    suit le nouveau texte (même règle que le découpage du conteur) ; récit, titre d'accroche et titre YouTube suivent.
    `on_screen` : texte gravé sur la scène de l'accroche (None : celui d'origine, "" : aucun)."""
    story = script.story
    if story is None or len(story.beats) < 2 or [b.part for b in story.beats[:2]] != ["hook", "promise"]:
        raise ValueError("seul un récit écrit par le conteur (accroche puis promesse) a une variante d'accroche")
    old = {"hook": story.beats[0].text.strip(), "promise": story.beats[1].text.strip()}
    new = {"hook": hook.strip(), "promise": promise.strip()}
    found: dict[str, int] = {}
    for scene in script.scenes[:4]:
        said = scene.narration.get(lang, "").strip()  # type: ignore[call-overload]
        for part, text in old.items():
            if said == text and part not in found:
                found[part] = scene.index
    missing = [p for p in ("hook", "promise") if p not in found]
    if missing:
        raise ValueError(f"scène introuvable pour {', '.join(missing)} : le texte est réparti sur plusieurs scènes")
    scenes = []
    for scene in script.scenes:
        part = next((p for p, i in found.items() if i == scene.index), None)
        if part is None:
            scenes.append(scene)
            continue
        patch: dict[str, Any] = {
            "narration": {**scene.narration, lang: new[part]},
            "duration_s": scene_seconds(len(said_words(new[part], lang))),
        }
        if part == "hook" and on_screen is not None:
            shown = {k: v for k, v in scene.on_screen_text.items() if k != lang}
            patch["on_screen_text"] = {**shown, lang: on_screen.strip()} if on_screen.strip() else shown
        scenes.append(scene.model_copy(update=patch))
    beats = [b.model_copy(update={"text": new[b.part]}) if i < 2 else b for i, b in enumerate(story.beats)]
    hook_titles = {**script.hook_title, lang: clean_hook(hook_title)}
    metadata = dict(script.metadata)
    if lang in metadata:
        metadata[lang] = metadata[lang].model_copy(update={"title": title[:100]})  # type: ignore[index]
    return script.model_copy(
        update={
            "scenes": scenes,
            "hook_title": hook_titles,
            "metadata": metadata,
            "story": story.model_copy(update={"beats": beats, "hook_title": {**story.hook_title, lang: hook_titles[lang]}}),
        }
    )


def link_file(src: Path, dst: Path) -> Path:
    """`dst` lié à `src` (même fichier sur le disque, sans copie) ; impossible (autre disque) : le chemin d'origine."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return dst
    try:
        os.link(src, dst)
        return dst
    except OSError as exc:
        log.warning("variante.lien_impossible", src=str(src), error=str(exc)[:200])
        return src


def make_variant(
    db: Any,
    data_dir: Path,
    video_id: str | UUID,
    *,
    hook: str,
    promise: str,
    hook_title: str,
    title: str,
    on_screen: str | None = None,
    description: str | None = None,
) -> Variant:
    v = db.fetch_one("select * from videos where id = %s", (video_id,))
    if not v:
        raise ValueError(f"vidéo introuvable : {video_id}")
    if v["format"] != "A_voiceover" or not v["final_asset_id"] or v.get("files_deleted_at"):
        raise ValueError("il faut un récit narré déjà monté, dont les fichiers sont sur le PC")
    if not (v.get("tts_provider") and v.get("tts_voice")):
        raise ValueError("voix de la vidéo d'origine inconnue")
    p = db.fetch_one("select * from productions where id = %s", (v["production_id"],))
    lang = v["lang"]
    script = variant_script(ScriptV1.model_validate(p["script"]), lang, hook, promise, hook_title, title, on_screen)
    issues = check_texts(hook, promise, hook_title, lang)

    cols = ", ".join(PRODUCTION_COLUMNS)
    pid = db.fetch_one(
        f"""insert into productions ({cols}, script, status, autopilot)
            select {cols}, %s, 'assembling', false from productions where id = %s returning id""",  # noqa: S608
        (Jsonb(script.model_dump(mode="json")), p["id"]),
    )["id"]

    linked = 0
    dest = data_dir / "productions" / str(pid)
    assets = db.fetch_all(
        """select * from assets where production_id = %s and video_id is null and kind::text = any(%s)
           order by created_at""",
        (p["id"], list(COPIED_ASSETS)),
    )
    for a in assets:
        path = a["local_path"]
        if path and Path(path).exists():
            src = Path(path)
            home = data_dir / "productions" / str(p["id"])
            got = link_file(src, dest / (src.relative_to(home) if src.is_relative_to(home) else src.name))
            linked += got != src
            path = str(got)
        db.execute(
            """insert into assets (production_id, kind, scene_index, storage_bucket, storage_path, local_path,
                                   duration_s, width, height, bytes, meta, created_at)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                pid,
                a["kind"],
                a["scene_index"],
                a["storage_bucket"],
                a["storage_path"],
                path,
                a["duration_s"],
                a["width"],
                a["height"],
                a["bytes"],
                Jsonb(a["meta"] or {}),
                a["created_at"],
            ),
        )

    seo = dict(v.get("seo") or {})
    if seo:
        titles = [t for t in seo.get("titles") or [] if t.get("title") != title]
        seo |= {"titles": [{"angle": "variante d'accroche", "title": title}, *titles], "chosen": 0}
    narration = " ".join(s.narration.get(lang, "") for s in script.scenes if s.narration.get(lang))  # type: ignore[call-overload]
    vid = db.fetch_one(
        """insert into videos (production_id, channel_id, lang, format, status, title, description, tags, narration_text,
                               seo, subtitle_profile, origin, music_track, audio_mix, variant_of)
           values (%s, %s, %s, %s, 'rendering', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
        (
            pid,
            v["channel_id"],
            lang,
            v["format"],
            title[:100],
            description or v["description"],
            v["tags"],
            narration,
            Jsonb(seo) if seo else None,
            v["subtitle_profile"],
            v["origin"],
            v["music_track"],
            Jsonb(v["audio_mix"]) if v["audio_mix"] is not None else None,
            v["id"],
        ),
    )["id"]

    # la voix d'origine, telle quelle (sans jeu) : seule l'ouverture doit différer entre les deux vidéos
    voice = f"{v['tts_provider']}:{v['tts_voice']}"
    tts = db.enqueue("tts", production_id=pid, video_id=vid, payload={"voice": voice}, priority=20, max_attempts=2)
    asm = db.enqueue("assemble", production_id=pid, video_id=vid, depends_on=[tts], priority=20, max_attempts=2)
    db.enqueue("qa", production_id=pid, video_id=vid, depends_on=[asm], priority=20)
    log.info("variante.creee", origine=str(v["id"]), video=str(vid), production=str(pid), lies=linked)
    return Variant(pid, vid, linked, issues)


def remove_variant_dir(data_dir: Path, production_id: UUID) -> None:
    """Dossier d'une variante abandonnée (liens seulement : les fichiers de l'originale restent)."""
    shutil.rmtree(data_dir / "productions" / str(production_id), ignore_errors=True)
