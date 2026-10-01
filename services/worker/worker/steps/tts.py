"""Narration TTS (format A) : une voix par scène, posée sur la timeline, mots horodatés pour les sous-titres.

Drame en voix constantes (recette drama, série en format A, docs/35) : chaque réplique est dite avec la voix de son
personnage (drama.assign_voices : la voix choisie par le scénariste, sinon la plus proche de sa description), un
appel au moteur par voix ; la timeline et la piste se construisent ensuite comme pour une narration.
Jeu des voix (Réglages, catalog.json → acting, docs/41) : le ton de chaque réplique va au moteur, et une voix Qwen
dessinée peut être dite par un moteur qui le joue (références émues, VoiceDesign, Gemini avec repli local). Gemini dit
aussi les narrations (« narration » dans le jeu), la description de la voix en consigne. Le jeu vient, dans l'ordre : de
la retouche qui le demande (payload voice = « acting:gemini », Bibliothèque → Retoucher → Voix), de celui retenu pour la
vidéo (videos.retouch.acting : une nouvelle prise garde le même timbre), des Réglages. Durée visée de chaque réplique :
le temps où la bouche de son clip la dit (lipsync.mouth_seconds), pour que la voix s'y cale sans sonner faux.
"""

from __future__ import annotations

import re
from typing import Any

from psycopg.types.json import Jsonb

from ..cancel import JobCancelled
from ..drama import assign_voices, character_voices, is_drama, line_text
from ..lipsync import cached_lines, mouth_seconds
from ..models import NarrationTimeline, ScriptV1
from ..providers.llm import get_llm
from ..providers.tts import acting_engines, get_engine, resolve_voice, split_voice, tts_catalog, voice_entry
from ..recipes import recipe_for_production
from ..settings_store import load_generation_config
from ..speaker import voice_direction
from ..timeline import SceneSpeech, estimate_speech_s, mix_speech, plan_timeline, trim_silence
from .base import Context, Step


class TTSStep(Step):
    type = "tts"
    # Voie GPU : les moteurs de voix autres que Kokoro chargent un modèle PyTorch (carte ou RAM) qui ne tient pas à côté
    # d'un rendu Wan ; le montage attend de toute façon tous les clips, la voix ne retarde donc pas la vidéo.
    lane = "gpu"

    def run(self, ctx: Context) -> dict[str, Any]:
        vid = ctx.job.video_id
        v = ctx.db.fetch_one(
            """select v.lang, v.timeline, v.production_id, v.retouch, v.tts_provider, v.tts_voice, p.script, c.voice_speed
               from videos v join productions p on p.id = v.production_id
               join channels c on c.id = v.channel_id where v.id = %s""",
            (vid,),
        )
        assert v and v["script"], "script manquant"
        out = ctx.video_dir(vid) / "narration.wav"
        # Retouche (Bibliothèque → Retoucher, docs/34) : voix choisie à la main pour cette vidéo, refaite même si elle existe
        # (« acting:gemini » : les voix des personnages gardées, jouées par un autre moteur, docs/41 §8)
        requested = str(ctx.job.payload.get("voice") or "").strip()
        acting = requested.split(":", 1)[1] if requested.startswith("acting:") else ""
        forced = "" if acting else requested
        acting = acting or str((v.get("retouch") or {}).get("acting") or "")
        retake = ctx.job.payload.get("scene")  # Retoucher → Plans (docs/38 §6) : une seule réplique redite
        if out.exists() and v["timeline"] and not requested and retake is None:  # idempotence
            return {"path": str(out), "skipped": True}
        if retake is not None:
            return self._retake(
                ctx,
                out,
                ScriptV1.model_validate(v["script"]),
                v["lang"],
                float(v["voice_speed"] or ctx.settings.kokoro_speed),
                int(retake),
                acting,
            )

        lang = v["lang"]
        script = ScriptV1.model_validate(v["script"])
        speed = float(v["voice_speed"] or ctx.settings.kokoro_speed)
        drama = is_drama(recipe_for_production(ctx.db, v["production_id"]))
        if forced:  # une voix choisie à la main (Retoucher → Voix) est dite telle quelle, sans jeu
            voices, acting = {lang: forced}, ""
        else:  # sinon les Réglages du dashboard (« moteur:voix »), sinon .env
            gen = load_generation_config(ctx.settings, ctx.db)
            voices, acting = gen.voices, acting or gen.voice_acting
            if drama:
                return self._drama(ctx, out, script, lang, speed, acting)
            # récit rejoué depuis la retouche : la dernière voix choisie pour lui, sinon sa voix actuelle (pas les Réglages)
            picked = str((v.get("retouch") or {}).get("voice") or "")
            if requested and (picked or (v.get("tts_provider") and v.get("tts_voice"))):
                voices = {lang: picked or f"{v['tts_provider']}:{v['tts_voice']}"}
        # drame retouché : la voix choisie dit les répliques seules, jamais le nom de qui parle
        texts = {s.index: (line_text(s) if drama else s.narration.get(lang, "")).strip() for s in script.scenes}
        tts, voice = resolve_voice(ctx.settings, voices, lang)
        # Gemini dit aussi les récits (la voix Qwen choisie → sa voix Gemini) ; les autres jeux laissent la voix telle quelle
        catalog = tts_catalog(ctx.settings) if acting else {}
        play = narration_acting(catalog, acting) if acting else {}
        engines = acting_engines(catalog, tts.name, acting) if play else []

        if ctx.settings.dry_run:
            scenes = [
                SceneSpeech(s.index, s.duration_s, texts[s.index], estimate_speech_s(texts[s.index], lang)) for s in script.scenes
            ]
            timeline = plan_timeline(scenes, lang)
            out.write_bytes(b"")
        else:
            import soundfile as sf

            speeches: dict[int, Any] = {}
            spoken = [s.index for s in script.scenes if texts[s.index]]
            ctx.progress(5, f"Voix · {engines[0] if engines else tts.name}")
            progress = lambda pct, label: ctx.progress(5 + int(0.8 * pct), f"Voix · {label}")  # noqa: E731
            if engines:
                persona = voice_description(catalog, f"{tts.name}:{voice}") if play.get("persona") else ""
                results = _say(
                    ctx,
                    engines,
                    play,
                    voice,
                    lang,
                    speed,
                    [texts[i] for i in spoken],
                    [NARRATION_PACE] * len(spoken),
                    [persona] * len(spoken),
                    on_progress=progress,
                )
            else:
                results = tts.speak_many([texts[i] for i in spoken], voice=voice, lang=lang, speed=speed, on_progress=progress)
            rate = results[0].rate if results else 24000
            for i, sp in zip(spoken, results, strict=True):
                speeches[i] = trim_silence(sp.samples, sp.rate)
            if engines and speeches:
                planned = sum(s.duration_s for s in script.scenes if s.index in speeches)
                said_s = sum(len(x) for x in speeches.values()) / rate
                factor = brisk_factor(said_s, planned)
                if factor > 1.0:  # Gemini lit trop lentement (30/09 : 109 s pour 71 s prévues) : même voix, plus vite
                    speeches = {i: tempo(x, rate, factor) for i, x in speeches.items()}
                    ctx.log(
                        "tts.narration_acceleree", facteur=round(factor, 2), dite_s=round(said_s, 1), prevue_s=round(planned, 1)
                    )
            scenes = [
                SceneSpeech(s.index, s.duration_s, texts[s.index], len(speeches[s.index]) / rate if s.index in speeches else None)
                for s in script.scenes
            ]
            timeline = plan_timeline(scenes, lang)
            ctx.progress(90, "Piste de narration")
            sf.write(str(out), mix_speech(timeline, speeches, rate), rate)

        self._save(ctx, timeline, out, tts.name, voice)
        spoken_by = _SPOKE.pop(_job_key(ctx), tts.name)
        stretched = [s.index for s, sc in zip(script.scenes, timeline.scenes, strict=True) if sc.duration > s.duration_s + 0.01]
        if stretched:
            ctx.log("tts.scenes_allongees", scenes=stretched, duree_totale=timeline.duration_s)
        return {
            "duration_s": timeline.duration_s,
            "words": len(timeline.words),
            "stretched_scenes": stretched,
            "voice": f"{tts.name}:{voice}",
            "spoken_by": spoken_by,  # moteur qui a vraiment parlé (Gemini, son repli ou le moteur de la voix)
            **({"acting": acting} if play else {}),
            **({"acting_failed": dead} if (dead := warn_fallback(ctx, acting)) else {}),
            **({"retouch": True} if requested else {}),
        }

    def _drama(self, ctx: Context, out: Any, script: ScriptV1, lang: str, speed: float, acting: str) -> dict[str, Any]:
        """Répliques d'un drame, chacune avec la voix de son personnage (un appel au moteur par voix, le modèle se charge
        une fois par voix) ; scènes sans réplique : silence (la musique et le son du plan les portent). `acting` : le jeu
        des voix (catalog.json → acting)."""
        catalog = tts_catalog(ctx.settings)
        gen = load_generation_config(ctx.settings, ctx.db)
        voices = assign_voices(script.cast, list(character_voices(catalog, lang)))
        default = gen.voices.get(lang) or ""
        texts = {s.index: line_text(s) for s in script.scenes}
        # comment chaque réplique est dite (« whispers, trembling ») : un moteur qui joue les émotions s'en sert (docs/41)
        tones = {s.index: (s.lines[0].tone if s.lines else "") for s in script.scenes}
        personas = {s.index: _persona(script, s) for s in script.scenes}
        # le temps où la bouche de chaque clip dit sa réplique (clips déjà faits : retouche, ou voix après les clips)
        targets = mouth_targets(ctx.db, getattr(ctx.job, "production_id", None), script, lang)
        by_voice: dict[str, list[int]] = {}
        for s in script.scenes:
            if texts[s.index]:
                who = s.lines[0].who if s.lines else ""
                by_voice.setdefault(voices.get(who) or default, []).append(s.index)
        ctx.log("tts.voix_personnages", voix=voices, jeu=acting, bouches=len(targets))
        if ctx.settings.dry_run:
            scenes = [
                SceneSpeech(s.index, s.duration_s, texts[s.index], estimate_speech_s(texts[s.index], lang)) for s in script.scenes
            ]
            timeline = plan_timeline(scenes, lang)
            out.write_bytes(b"")
        else:
            import numpy as np
            import soundfile as sf

            speeches: dict[int, Any] = {}
            rate = 24000
            for k, (voice_id, idxs) in enumerate(by_voice.items()):
                engine, voice = split_voice(voice_id)
                ctx.progress(5 + int(80 * k / max(1, len(by_voice))), f"Voix · {voice_id} ({len(idxs)} répliques)")
                results = _say(
                    ctx,
                    acting_engines(catalog, engine, acting),
                    (catalog.get("acting") or {}).get(acting) or {},
                    voice,
                    lang,
                    speed,
                    [texts[i] for i in idxs],
                    [tones[i] for i in idxs],
                    [personas[i] for i in idxs],
                    targets=[targets.get(i) for i in idxs],
                )
                for i, sp in zip(idxs, results, strict=True):
                    x = trim_silence(sp.samples, sp.rate)
                    if speeches and sp.rate != rate:  # moteurs de fréquences différentes : tout à la première
                        x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * rate / sp.rate)), np.arange(len(x)), x)
                    elif not speeches:
                        rate = sp.rate
                    speeches[i] = x
            scenes = [
                SceneSpeech(s.index, s.duration_s, texts[s.index], len(speeches[s.index]) / rate if s.index in speeches else None)
                for s in script.scenes
            ]
            timeline = plan_timeline(scenes, lang)
            ctx.progress(90, "Piste des répliques")
            sf.write(str(out), mix_speech(timeline, speeches, rate), rate)
        self._save(ctx, timeline, out, "drama", ", ".join(f"{k}={v}" for k, v in voices.items()))
        dead = warn_fallback(ctx, acting)
        return {
            "duration_s": timeline.duration_s,
            "words": len(timeline.words),
            "voices": voices,
            "acting": acting,
            **({"acting_failed": dead} if dead else {}),
        }

    def _retake(
        self, ctx: Context, out: Any, script: ScriptV1, lang: str, speed: float, index: int, acting: str = ""
    ) -> dict[str, Any]:
        """Nouvelle prise d'une réplique d'un drame (Retoucher → Plans, docs/38 §6) : la même voix avec une autre graine,
        la consigne de Luca en prononciation ou en débit (speaker.voice_direction) ; les autres répliques restent telles
        que le dernier calage les a découpées (lipsync.cached_lines). La piste et la timeline de l'étape voix sont
        refaites, le montage recale ensuite les voix sur les bouches (la transcription des répliques inchangées est gardée).
        `acting` : le jeu retenu pour cette vidéo (videos.retouch.acting), sinon celui des Réglages : même timbre que les
        autres répliques."""
        vid, payload = ctx.job.video_id, ctx.job.payload
        cached = cached_lines(ctx.settings, vid)
        if cached is None:
            raise RuntimeError(
                "répliques de la vidéo introuvables (voix refaite depuis le dernier montage ?) : "
                "« Refaire la vidéo » d'abord, puis redire la réplique"
            )
        speeches, rate, _ = cached
        scene = next((s for s in script.scenes if s.index == index), None)
        text = line_text(scene) if scene else ""
        if not scene or not text:
            raise RuntimeError(f"le plan {index + 1} n'a pas de réplique à redire")
        row = ctx.db.fetch_one("select tts_provider, tts_voice from videos where id = %s", (vid,)) or {}
        catalog = tts_catalog(ctx.settings)
        gen = load_generation_config(ctx.settings, ctx.db)
        acting = acting or gen.voice_acting
        if row.get("tts_provider") and row["tts_provider"] != "drama":  # voix unique choisie dans Retoucher
            voice_id = f"{row['tts_provider']}:{row['tts_voice']}"
        else:
            voices = assign_voices(script.cast, list(character_voices(catalog, lang)))
            voice_id = voices.get(scene.lines[0].who) or gen.voices.get(lang) or ""
        note = str(payload.get("note") or "").strip()
        said, factor = voice_direction(get_llm(ctx.settings, ctx.db), text, note) if note else (text, 1.0)
        take = int(payload.get("take") or 1)
        ctx.log("tts.nouvelle_prise", scene=index, voix=voice_id, prise=take, consigne=note, lu=said, debit=factor)
        if ctx.settings.dry_run:
            out.write_bytes(b"")
            return {"scene": index, "take": take, "voice": voice_id, "dry_run": True}
        import numpy as np
        import soundfile as sf

        engine, voice = split_voice(voice_id)
        ctx.progress(10, f"Voix · plan {index + 1} · prise {take + 1}")
        mouth = mouth_targets(ctx.db, getattr(ctx.job, "production_id", None), script, lang).get(index)
        sp = _say(
            ctx,
            acting_engines(catalog, engine, acting),
            (catalog.get("acting") or {}).get(acting) or {},
            voice,
            lang,
            speed * factor,
            [said],
            [scene.lines[0].tone if scene.lines else ""],
            [_persona(script, scene)],
            seed=1234 + 1000 * take,
            targets=[mouth if factor == 1.0 else None],  # un débit demandé par Luca prime sur la bouche
        )[0]
        x = trim_silence(sp.samples, sp.rate)
        if sp.rate != rate:
            x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * rate / sp.rate)), np.arange(len(x)), x)
        speeches[index] = np.asarray(x, dtype=np.float32)
        texts = {s.index: line_text(s) for s in script.scenes}
        scenes = [
            SceneSpeech(s.index, s.duration_s, texts[s.index], len(speeches[s.index]) / rate if s.index in speeches else None)
            for s in script.scenes
        ]
        timeline = plan_timeline(scenes, lang)
        ctx.progress(80, "Piste des répliques")
        sf.write(str(out), mix_speech(timeline, speeches, rate), rate)
        self._save(ctx, timeline, out, row.get("tts_provider") or "drama", row.get("tts_voice") or voice_id)
        return {
            "scene": index,
            "take": take,
            "voice": voice_id,
            "spoken": said,
            "speed": factor,
            "acting": acting,
            **({"acting_failed": dead} if (dead := warn_fallback(ctx, acting)) else {}),
            "retouch": True,
        }

    def _save(self, ctx: Context, timeline: NarrationTimeline, out: Any, provider: str, voice: str) -> None:
        vid = ctx.job.video_id
        ctx.db.add_asset(
            video_id=vid,
            kind="narration",
            local_path=str(out),
            duration_s=timeline.duration_s,
            meta={"provider": provider, "voice": voice, "aligner": timeline.aligner},
        )
        ctx.db.execute(
            "update videos set tts_provider = %s, tts_voice = %s, timeline = %s where id = %s",
            (provider, voice, Jsonb(timeline.model_dump()), vid),
        )


def _persona(script: ScriptV1, scene: Any) -> str:
    """La voix du personnage qui parle, décrite par le scénariste (« a warm elderly female voice in her seventies ») :
    un moteur qui ne connaît pas le personnage (Gemini) la reçoit avec le ton de la réplique."""
    member = script.member(scene.lines[0].who) if scene.lines else None
    return member.voice if member else ""


def _say(
    ctx: Context,
    engines: list[str],
    acting: dict[str, Any],
    voice: str,
    lang: str,
    speed: float,
    texts: list[str],
    tones: list[str],
    personas: list[str],
    seed: int | None = None,
    targets: list[float | None] | None = None,
    on_progress: Any = None,
) -> list[Any]:
    """Les répliques d'une voix, dites par le premier moteur du jeu des voix qui réussit (docs/41) : Gemini, puis son
    repli local si le quota gratuit est épuisé ; un Arrêter de Luca n'est jamais rattrapé par le repli. `targets` : durée
    de la bouche de chaque réplique (seul un moteur qui règle son débit s'en sert)."""
    dead = _EXHAUSTED.setdefault(_job_key(ctx), set())
    for n, name in enumerate(engines):
        if name in dead and n < len(engines) - 1:  # quota du jour déjà épuisé dans ce job : pas de requêtes perdues
            continue
        said = tones
        if acting.get("persona") and name == acting.get("engine"):
            said = [f"{p}; {t}" if p and t else t or p for p, t in zip(personas, tones, strict=True)]
        extra: dict[str, Any] = {"seed": seed} if seed is not None else {}
        if targets and any(targets):
            extra["targets"] = targets
        if on_progress is not None:
            extra["on_progress"] = on_progress
        try:
            out = get_engine(ctx.settings, name).speak_many(texts, voice=voice, lang=lang, speed=speed, tones=said, **extra)
            _SPOKE[_job_key(ctx)] = name
            return out
        except JobCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 — le repli prend la main, l'erreur reste dans le journal du job
            if n == len(engines) - 1:
                raise
            ctx.log("tts.jeu_repli", moteur=name, repli=engines[n + 1], erreur=str(exc)[-300:])
            if _DAILY_QUOTA.search(str(exc)):
                dead.add(name)
    raise RuntimeError("aucun moteur de voix")


# Quota gratuit du jour épuisé (« limit: 10 requests per day » pour gemini-3.8-flash-tts, 30/09) : inutile de réessayer
# ce moteur pour les autres voix du même job, il ne reviendra qu'au prochain jour de quota
_DAILY_QUOTA = re.compile(r"per day|PerDay", re.I)
_EXHAUSTED: dict[Any, set[str]] = {}
# Moteur qui a vraiment dit la narration d'un job (Gemini ou son repli) : noté dans le résultat du job, à côté de la voix
# choisie (01/10 : « Bakélite » affichait qwen3:mystere alors que Gemini l'avait lue)
_SPOKE: dict[Any, str] = {}


def _job_key(ctx: Any) -> Any:
    return getattr(getattr(ctx, "job", None), "id", None)


def warn_fallback(ctx: Context, acting: str) -> list[str]:
    """Moteurs du jeu des voix abandonnés dans ce job (quota du jour) : une alerte pour Luca, qui croyait entendre
    Gemini (30/09 : la retouche « Gemini » était dite par le repli local sans qu'il le sache). Renvoie ces moteurs."""
    dead = sorted(_EXHAUSTED.pop(_job_key(ctx), set()))
    if dead:
        title = ctx.db.fetch_one("select title from videos where id = %s", (ctx.job.video_id,)) or {}
        ctx.db.alert(
            "warning",
            f"Voix {acting} : quota du jour épuisé",
            f"« {title.get('title') or ctx.job.video_id} » a été dite par la voix locale de repli, pas par {', '.join(dead)}. "
            "Le quota gratuit revient chaque jour vers 9 h ; Retoucher → Voix pour la refaire ensuite.",
            video_id=ctx.job.video_id,
        )
    return dead


# Rythme d'un récit lu par le jeu des voix (Gemini) : 30/09, « Bakélite » lue à 1,5 mot/s (122 s au lieu de 75) avec la
# voix « mystère », que Gemini a prise pour une lecture lente ; un Short se lit à ≈ 2,7 mots/s
NARRATION_PACE = "a brisk, gripping YouTube Shorts storyteller pace, about 3 words per second, only short pauses"


BRISK_MAX = 1.35  # au-delà, la voix accélérée sonne pressée


def brisk_factor(said_s: float, planned_s: float) -> float:
    """Accélération d'une narration jouée trop lente : 1 si elle tient dans 110 % du temps prévu par le script, sinon de
    quoi revenir au temps prévu, BRISK_MAX au plus."""
    if planned_s <= 0 or said_s <= planned_s * 1.1:
        return 1.0
    return min(BRISK_MAX, said_s / planned_s)


def tempo(samples: Any, rate: int, factor: float) -> Any:
    """La même voix `factor` fois plus vite, hauteur conservée (FFmpeg atempo)."""
    import subprocess

    import numpy as np

    out = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "f32le",
            "-ar",
            str(rate),
            "-ac",
            "1",
            "-i",
            "pipe:0",
            "-filter:a",
            f"atempo={factor:.3f}",
            "-f",
            "f32le",
            "-ar",
            str(rate),
            "-ac",
            "1",
            "pipe:1",
        ],
        input=np.asarray(samples, dtype=np.float32).tobytes(),
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(out, dtype=np.float32).copy()


def narration_acting(catalog: dict[str, Any], acting: str) -> dict[str, Any]:
    """Le jeu des voix s'il vaut aussi pour les narrations (« narration » : Gemini, qui lit un récit avec la description
    de la voix Qwen choisie) ; {} sinon : un récit n'a pas de ton par scène, les autres jeux n'y changent rien."""
    spec = (catalog.get("acting") or {}).get(acting) or {}
    return spec if spec.get("narration") and spec.get("engine") else {}


def voice_description(catalog: dict[str, Any], voice_id: str) -> str:
    """La description d'une voix Qwen dessinée (params.design.instruct : âge, timbre, accent, manière) ; "" sinon."""
    entry = voice_entry(catalog, voice_id) or {}
    return str(((entry.get("params") or {}).get("design") or {}).get("instruct") or "")


def mouth_targets(db: Any, production_id: Any, script: ScriptV1, lang: str) -> dict[int, float]:
    """Scène → temps où la bouche de son clip dit la réplique (s), d'après la transcription gardée avec le clip
    (assets.meta.dialogue : faite à la fabrication d'un drame en voix constantes, ou par un calage d'avant) ; les scènes
    sans clip transcrit n'y sont pas."""
    if not production_id:
        return {}
    try:
        rows = db.fetch_all(
            """select distinct on (scene_index) scene_index, meta->'dialogue' as dialogue from assets
               where production_id = %s and kind = 'clip' order by scene_index, created_at desc""",
            (production_id,),
        )
    except Exception:  # noqa: BLE001 — sans les clips, les voix se disent à leur rythme
        return {}
    by_scene = {int(r["scene_index"]): r["dialogue"] for r in rows if r.get("scene_index") is not None}
    out: dict[int, float] = {}
    for s in script.scenes:
        text = line_text(s)
        seconds = mouth_seconds(text, lang, by_scene.get(s.index)) if text else None
        if seconds:
            out[s.index] = seconds
    return out
