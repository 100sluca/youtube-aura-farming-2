"""Prises de voix par lot, à écouter avant de remonter (Retoucher → Plans, docs/49 §7).

Demandé par Luca le 01/10 devant « Tout le collège le détestait » : plusieurs répliques dites en anglais par Gemini, et
une seule « Nouvelle prise de voix » à la fois, chacune refaisant toute la vidéo. Désormais :

1. ses consignes s'écrivent plan par plan et s'enregistrent seules (videos.retouch.drafts, SQL save_plan_note) ;
2. « Nouvelles prises de voix » redit toutes les répliques qui ont une consigne, en un seul job tts (payload `takes`) :
   chaque prise est un fichier à part (asset « take ») réécouté par Whisper, ce qu'il entend et sa ressemblance avec la
   réplique écrite sont notés (une réplique dite en anglais se voit tout de suite) ; la vidéo ne bouge pas ;
3. Luca écoute chaque prise et la valide ou non (videos.retouch.takes[plan].keep, SQL keep_take) : refusée, sa
   consigne se rouvre pour en donner une autre et le plan repart au lot suivant ; validée, on passe au plan suivant ;
4. quand toutes les prises sont décidées, « Refaire la vidéo avec les prises validées » : un job tts (payload
   `apply_takes`) pose les prises validées dans la piste des répliques (les autres restent telles que le dernier calage
   les a découpées), puis un seul montage calé sur les lèvres et le contrôle (SQL apply_takes).

videos.retouch.takes = {plan: {asset_id, note, said, heard, ratio, keep, at, direction, engine, source}} ; une prise
posée passe dans l'historique du plan (videos.retouch.plans).

Puis (01/10, même vidéo) : la consigne ne servait qu'au relecteur de prononciation (speaker.voice_direction, pensé pour
Qwen qui ne joue pas) et n'arrivait jamais à Gemini ; elle s'ajoute désormais au ton de la réplique quand un moteur joue
les voix, et la consigne de jeu reçue (direction) et le moteur qui a parlé (engine) sont notés sur la prise. Et la voix
que le modèle vidéo a donnée au plan dans son clip brut peut devenir une prise (clip_takes, source « clip »).
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from .drama import assign_voices, character_voices, heard_ratio, line_text, transcribe
from .models import ScriptV1
from .providers.llm import get_llm
from .providers.tts import acting_engines, split_voice, tts_catalog
from .settings_store import load_generation_config
from .speaker import voice_direction

log = structlog.get_logger(__name__)

TAKE_OK = 0.6  # ressemblance réplique écrite / entendue au-dessous de laquelle une prise est douteuse (anglais, mots avalés)


def _words(text: str) -> list[str]:
    plain = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").lower()
    return [w for w in re.split(r"[^\w]+|_", plain) if w]


def said_ratio(expected: str, heard: str) -> float:
    """Ressemblance (0 à 1) entre la réplique écrite et ce que Whisper entend : la plus faible de heard_ratio (lettre à
    lettre) et de la part des mots écrits retrouvés. Lettre à lettre seule, une réplique dite en anglais passait
    (« Attention, the ego has arrived » pour « Attention ! L'égout est arrivé ») ; même calcul dans le Dashboard
    (lib/retouch.ts : heardRatio)."""
    want, left = _words(expected), _words(heard)
    found = 0
    for w in want:
        if w in left:
            found += 1
            left.remove(w)
    words = found / len(want) if want else 1.0
    return round(min(heard_ratio(expected, heard), words), 3)


def line_voice(ctx: Any, script: ScriptV1, scene: Any, lang: str, catalog: dict[str, Any]) -> str:
    """La voix d'une réplique : la voix unique choisie dans Retoucher, sinon celle de son personnage."""
    row = ctx.db.fetch_one("select tts_provider, tts_voice from videos where id = %s", (ctx.job.video_id,)) or {}
    if row.get("tts_provider") and row["tts_provider"] != "drama":
        return f"{row['tts_provider']}:{row['tts_voice']}"
    gen = load_generation_config(ctx.settings, ctx.db)
    voices = assign_voices(script.cast, list(character_voices(catalog, lang)))
    return voices.get(scene.lines[0].who if scene.lines else "") or gen.voices.get(lang) or ""


def make_takes(ctx: Any, script: ScriptV1, lang: str, speed: float, notes: dict[int, str], acting: str) -> dict[str, Any]:
    """Une nouvelle prise de chaque réplique de `notes` (plan → consigne), chacune dans son fichier, réécoutée par Whisper ;
    la vidéo ne change pas."""
    import numpy as np
    import soundfile as sf

    from .steps.tts import _SPOKE, _job_key, _persona, _say, mouth_targets, trim_silence

    vid = ctx.job.video_id
    catalog = tts_catalog(ctx.settings)
    acting = acting or load_generation_config(ctx.settings, ctx.db).voice_acting
    # moteur qui joue une consigne libre, comme Gemini (catalog.json : acting.<jeu>.persona) ; les références émues de
    # Qwen ne lisent que le ton écrit par le scénariste
    plays = bool(((catalog.get("acting") or {}).get(acting) or {}).get("persona"))
    row = ctx.db.fetch_one("select retouch from videos where id = %s", (vid,)) or {}
    retouch = dict(row.get("retouch") or {})
    takes = dict(retouch.get("takes") or {})
    folder = ctx.video_dir(vid) / "lines" / "takes"
    folder.mkdir(parents=True, exist_ok=True)
    mouths = mouth_targets(ctx.db, getattr(ctx.job, "production_id", None), script, lang)
    llm = get_llm(ctx.settings, ctx.db) if any(n.strip() for n in notes.values()) else None
    made: list[dict[str, Any]] = []
    for k, (index, note) in enumerate(sorted(notes.items())):
        scene = next((s for s in script.scenes if s.index == index), None)
        text = line_text(scene) if scene else ""
        if not scene or not text:
            continue
        said, factor = voice_direction(llm, text, note) if note.strip() else (text, 1.0)
        voice_id = line_voice(ctx, script, scene, lang, catalog)
        engine, voice = split_voice(voice_id)
        n = len((retouch.get("plans") or {}).get(str(index)) or []) + 1 + (1 if str(index) in takes else 0)
        ctx.progress(5 + int(70 * k / max(1, len(notes))), f"Voix · plan {index + 1} · prise {n}")
        # Consigne de jeu (« plus moqueur, plus fort ») : avec le ton écrit par le scénariste, au moteur qui joue
        tone = "; ".join(p for p in ((scene.lines[0].tone if scene.lines else ""), note.strip() if plays else "") if p)
        persona = _persona(script, scene)
        sp = _say(
            ctx,
            acting_engines(catalog, engine, acting),
            (catalog.get("acting") or {}).get(acting) or {},
            voice,
            lang,
            speed * factor,
            [said],
            [tone],
            [persona],
            seed=1234 + 1000 * n,
            targets=[mouths.get(index) if factor == 1.0 else None],
        )[0]
        path = folder / f"scene_{index:02d}_take_{n}.wav"
        sf.write(str(path), np.asarray(trim_silence(sp.samples, sp.rate), dtype=np.float32), sp.rate)
        made.append(
            {
                "index": index,
                "note": note,
                "said": said,
                "text": text,
                "path": path,
                "voice": voice_id,
                "direction": "; ".join(p for p in (persona if plays else "", tone) if p),
                "engine": _SPOKE.get(_job_key(ctx)) or engine,
            }
        )

    ctx.progress(80, "Réécoute des prises (Whisper)")
    heard = transcribe(ctx.settings, [m["path"] for m in made], lang) if made and not ctx.settings.dry_run else None
    now = datetime.now(UTC).isoformat()
    for i, m in enumerate(made):
        h = (heard[i]["text"] if heard else "") or ""
        ratio = said_ratio(m["text"], h) if heard else None
        asset = ctx.db.add_asset(
            video_id=vid,
            kind="take",
            scene_index=m["index"],
            local_path=str(m["path"]),
            meta={
                "note": m["note"],
                "said": m["said"],
                "heard": h,
                "ratio": ratio,
                "voice": m["voice"],
                "direction": m["direction"],
                "engine": m["engine"],
            },
        )
        takes[str(m["index"])] = {
            "asset_id": str(asset),
            "note": m["note"],
            "said": m["said"],
            "heard": h if heard else None,
            "ratio": ratio,
            "keep": None,  # à écouter : Luca la valide ou non
            "at": now,
            "direction": m["direction"],  # consigne de jeu reçue par la voix, en plus de « en français, mot pour mot »
            "engine": m["engine"],  # moteur qui a vraiment parlé (Gemini, ou son repli si le quota est épuisé)
        }
    drafts = {k: v for k, v in (retouch.get("drafts") or {}).items() if int(k) not in {m["index"] for m in made}}
    ctx.db.execute(
        "update videos set retouch = coalesce(retouch, '{}'::jsonb) || %s::jsonb where id = %s",
        (json.dumps({"takes": takes, "drafts": drafts}, ensure_ascii=False), vid),
    )
    doubtful = [m["index"] for m in made if (takes[str(m["index"])]["ratio"] or 1.0) < TAKE_OK]
    ctx.log("tts.prises", plans=[m["index"] for m in made], douteuses=doubtful)
    return {"takes": [m["index"] for m in made], "doubtful": doubtful, "acting": acting, "retouch": True}


CLIP_NOTE = "Voix du clip (modèle vidéo)"


def voiced_rms(samples: Any, rate: int, threshold: float = 0.012) -> float | None:
    """Niveau moyen (RMS) des passages parlés d'un son (fenêtres de 10 ms au-dessus du seuil) ; None s'il est muet."""
    import numpy as np

    x = np.asarray(samples, dtype=np.float32).reshape(-1)
    win = max(1, rate // 100)
    n = len(x) // win
    if n == 0:
        return None
    rms = np.sqrt(np.mean(x[: n * win].reshape(n, win) ** 2, axis=1))
    voiced = rms[rms > threshold]
    return float(np.sqrt(np.mean(voiced**2))) if len(voiced) else None


def level_like(samples: Any, rate: int, target: float | None) -> Any:
    """Le son au niveau des autres répliques (même RMS parlé, gain borné), sans dépasser 0,98 ; fondus de 15 ms."""
    import numpy as np

    x = np.asarray(samples, dtype=np.float32).reshape(-1).copy()
    own = voiced_rms(x, rate)
    if own and target:
        x *= float(np.clip(target / own, 0.25, 6.0))
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak > 0.98:
        x *= 0.98 / peak
    fade = min(len(x) // 2, int(0.015 * rate))
    if fade:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        x[:fade] *= ramp
        x[-fade:] *= ramp[::-1]
    return x


def clip_takes(ctx: Any, script: ScriptV1, lang: str, scenes: list[int]) -> dict[str, Any]:
    """La voix que le modèle vidéo a donnée au plan dans son clip brut, reprise comme prise (demande de Luca le 01/10 :
    le clip du plan 1 de « Tout le collège le détestait » sonnait mieux que toutes les prises de synthèse). Le son du
    clip, de la première à la dernière parole que Whisper y entend, au niveau des autres répliques ; il s'écoute et se
    valide comme une prise, et le montage le cale sur les lèvres comme les autres (ce sont les siennes)."""
    import numpy as np
    import soundfile as sf

    from .lipsync import cached_lines
    from .media import run

    vid, pid = ctx.job.video_id, getattr(ctx.job, "production_id", None)
    row = ctx.db.fetch_one("select retouch from videos where id = %s", (vid,)) or {}
    retouch = dict(row.get("retouch") or {})
    takes = dict(retouch.get("takes") or {})
    folder = ctx.video_dir(vid) / "lines" / "takes"
    folder.mkdir(parents=True, exist_ok=True)
    found: list[dict[str, Any]] = []
    skipped: dict[int, str] = {}
    for index in sorted(set(scenes)):
        scene = next((s for s in script.scenes if s.index == index), None)
        text = line_text(scene) if scene else ""
        if not text:
            skipped[index] = "plan sans réplique"
            continue
        clip = ctx.db.fetch_one(
            """select local_path from assets where production_id = %s and kind = 'clip' and scene_index = %s
               order by created_at desc limit 1""",
            (pid, index),
        )
        if not clip or not Path(clip["local_path"]).is_file():
            skipped[index] = "clip introuvable sur le PC"
            continue
        n = len((retouch.get("plans") or {}).get(str(index)) or []) + 1 + (1 if str(index) in takes else 0)
        path = folder / f"scene_{index:02d}_clip_{n}.wav"
        ctx.progress(10, f"Son du clip · plan {index + 1}")
        try:
            run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    clip["local_path"],
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "48000",
                    str(path),
                ]
            )
        except RuntimeError:
            skipped[index] = "le clip n'a pas de son"
            continue
        found.append({"index": index, "text": text, "path": path})

    ctx.progress(40, "Paroles du clip (Whisper)")
    heard = transcribe(ctx.settings, [m["path"] for m in found], lang) if found and not ctx.settings.dry_run else None
    cached = cached_lines(ctx.settings, vid)
    levels = [lv for x in (cached[0].values() if cached else []) if (lv := voiced_rms(x, cached[1] if cached else 1))]
    target = float(np.median(levels)) if levels else None
    now = datetime.now(UTC).isoformat()
    made: list[int] = []
    for i, m in enumerate(found):
        x, sr = sf.read(str(m["path"]), dtype="float32")
        x = np.asarray(x, dtype=np.float32).reshape(-1)
        words = (heard[i].get("words") or []) if heard else []
        if heard is not None and not words:
            skipped[m["index"]] = "personne ne parle dans le clip"
            m["path"].unlink(missing_ok=True)
            continue
        if words:  # de la première à la dernière parole, un souffle avant et après
            x = x[max(0, int((float(words[0]["start"]) - 0.08) * sr)) : min(len(x), int((float(words[-1]["end"]) + 0.25) * sr))]
        sf.write(str(m["path"]), np.asarray(level_like(x, sr, target), dtype=np.float32), sr)
        h = (heard[i]["text"] if heard else "") or ""
        ratio = said_ratio(m["text"], h) if heard else None
        asset = ctx.db.add_asset(
            video_id=vid,
            kind="take",
            scene_index=m["index"],
            local_path=str(m["path"]),
            meta={"note": CLIP_NOTE, "said": m["text"], "heard": h, "ratio": ratio, "source": "clip"},
        )
        takes[str(m["index"])] = {
            "asset_id": str(asset),
            "note": CLIP_NOTE,
            "said": m["text"],
            "heard": h if heard else None,
            "ratio": ratio,
            "keep": None,
            "at": now,
            "source": "clip",
        }
        made.append(m["index"])
    if not made:
        why = ", ".join(f"plan {i + 1} : {reason}" for i, reason in sorted(skipped.items()))
        raise RuntimeError(f"aucune voix de clip à reprendre ({why or 'aucun plan demandé'})")
    ctx.db.execute(
        "update videos set retouch = coalesce(retouch, '{}'::jsonb) || %s::jsonb where id = %s",
        (json.dumps({"takes": takes}, ensure_ascii=False), vid),
    )
    ctx.log("tts.voix_du_clip", plans=made, ecartes=skipped)
    return {"clip_takes": made, "skipped": {str(k): v for k, v in skipped.items()}, "retouch": True}


def apply_takes(step: Any, ctx: Any, out: Path, script: ScriptV1, lang: str, scenes: list[int]) -> dict[str, Any]:
    """Pose les prises gardées dans la piste des répliques (les autres répliques restent celles du dernier calage), refait
    la piste et la timeline de l'étape voix ; le montage qui suit recale tout sur les lèvres."""
    import numpy as np
    import soundfile as sf

    from .lipsync import cached_lines
    from .steps.tts import SceneSpeech, mix_speech, plan_timeline

    vid = ctx.job.video_id
    row = ctx.db.fetch_one("select retouch, tts_provider, tts_voice, format from videos where id = %s", (vid,)) or {}
    retouch = dict(row.get("retouch") or {})
    takes = dict(retouch.get("takes") or {})
    if row.get("format") == "B_visual":
        return _clip_voice_overrides(ctx, retouch, takes, scenes)
    cached = cached_lines(ctx.settings, vid)
    if cached is None:
        raise RuntimeError(
            "répliques de la vidéo introuvables (voix refaite depuis le dernier montage ?) : « Refaire la vidéo » d'abord"
        )
    speeches, rate, _ = cached
    applied: list[int] = []
    for index in scenes:
        take = takes.get(str(index)) or {}
        asset = ctx.db.fetch_one("select local_path from assets where id = %s", (take.get("asset_id"),)) if take else None
        if not asset or not Path(asset["local_path"]).is_file():
            ctx.log("tts.prise_absente", level="warn", plan=index)
            continue
        x, sr = sf.read(asset["local_path"], dtype="float32")
        x = np.asarray(x, dtype=np.float32).reshape(-1)
        if sr != rate:
            x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * rate / sr)), np.arange(len(x)), x).astype(np.float32)
        speeches[index] = x
        applied.append(index)
    if not applied:
        raise RuntimeError("aucune prise gardée à poser")
    texts = {s.index: line_text(s) for s in script.scenes}
    timeline = plan_timeline(
        [
            SceneSpeech(s.index, s.duration_s, texts[s.index], len(speeches[s.index]) / rate if s.index in speeches else None)
            for s in script.scenes
        ],
        lang,
    )
    sf.write(str(out), mix_speech(timeline, speeches, rate), rate)
    step._save(ctx, timeline, out, row.get("tts_provider") or "drama", row.get("tts_voice") or "")
    plans = dict(retouch.get("plans") or {})
    for index in applied:
        t = takes.pop(str(index))
        plans[str(index)] = [
            *(plans.get(str(index)) or []),
            {"note": t.get("note") or "", "clip": False, "voice": True, "at": t.get("at")},
        ]
    ctx.db.execute(
        "update videos set retouch = coalesce(retouch, '{}'::jsonb) || %s::jsonb where id = %s",
        (json.dumps({"takes": takes, "plans": plans}, ensure_ascii=False), vid),
    )
    return {"applied": applied, "retouch": True}


def _clip_voice_overrides(ctx: Any, retouch: dict[str, Any], takes: dict[str, Any], scenes: list[int]) -> dict[str, Any]:
    """Drame en voix des clips (docs/49 §11) : rien à refaire dans une piste de voix ; chaque prise validée est notée
    pour son plan (videos.retouch.lines), et le montage qui suit la pose à la place du son du clip."""
    lines = dict(retouch.get("lines") or {})
    plans = dict(retouch.get("plans") or {})
    applied = []
    for index in scenes:
        take = takes.pop(str(index), None)
        if not take:
            continue
        lines[str(index)] = take["asset_id"]
        plans[str(index)] = [
            *(plans.get(str(index)) or []),
            {"note": take.get("note") or "", "clip": False, "voice": True, "at": take.get("at")},
        ]
        applied.append(index)
    if not applied:
        raise RuntimeError("aucune prise validée à poser")
    ctx.db.execute(
        "update videos set retouch = coalesce(retouch, '{}'::jsonb) || %s::jsonb where id = %s",
        (json.dumps({"takes": takes, "plans": plans, "lines": lines}, ensure_ascii=False), ctx.job.video_id),
    )
    ctx.log("tts.repliques_remplacees", plans=applied)
    return {"applied": applied, "clip_voices": True, "retouch": True}
