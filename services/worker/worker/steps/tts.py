"""Narration TTS (format A) : une voix par scène, posée sur la timeline, mots horodatés pour les sous-titres.

Drame en voix constantes (recette drama, série en format A, docs/35) : chaque réplique est dite avec la voix de son
personnage (drama.assign_voices : la voix choisie par le scénariste, sinon la plus proche de sa description), un
appel au moteur par voix ; la timeline et la piste se construisent ensuite comme pour une narration.
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from ..drama import assign_voices, character_voices, is_drama, line_text
from ..models import NarrationTimeline, ScriptV1
from ..providers.tts import get_engine, resolve_voice, split_voice, tts_catalog
from ..recipes import recipe_for_production
from ..settings_store import load_generation_config
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
            """select v.lang, v.timeline, v.production_id, p.script, c.voice_speed
               from videos v join productions p on p.id = v.production_id
               join channels c on c.id = v.channel_id where v.id = %s""",
            (vid,),
        )
        assert v and v["script"], "script manquant"
        out = ctx.video_dir(vid) / "narration.wav"
        # Retouche (Bibliothèque → Retoucher, docs/34) : voix choisie à la main pour cette vidéo, refaite même si elle existe
        forced = str(ctx.job.payload.get("voice") or "").strip()
        if out.exists() and v["timeline"] and not forced:  # idempotence
            return {"path": str(out), "skipped": True}

        lang = v["lang"]
        script = ScriptV1.model_validate(v["script"])
        speed = float(v["voice_speed"] or ctx.settings.kokoro_speed)
        if not forced and is_drama(recipe_for_production(ctx.db, v["production_id"])):  # une retouche garde sa voix unique
            return self._drama(ctx, out, script, lang, speed)
        texts = {s.index: s.narration.get(lang, "").strip() for s in script.scenes}
        # voix : celle de la retouche, sinon les Réglages du dashboard (« moteur:voix »), sinon .env
        voices = {lang: forced} if forced else load_generation_config(ctx.settings, ctx.db).voices
        tts, voice = resolve_voice(ctx.settings, voices, lang)

        if ctx.settings.dry_run:
            scenes = [SceneSpeech(s.index, s.duration_s, texts[s.index], estimate_speech_s(texts[s.index], lang)) for s in script.scenes]
            timeline = plan_timeline(scenes, lang)
            out.write_bytes(b"")
        else:
            import soundfile as sf

            speeches: dict[int, Any] = {}
            spoken = [s.index for s in script.scenes if texts[s.index]]
            ctx.progress(5, f"Voix · {tts.name}")
            results = tts.speak_many(
                [texts[i] for i in spoken], voice=voice, lang=lang, speed=speed,
                on_progress=lambda pct, label: ctx.progress(5 + int(0.8 * pct), f"Voix · {label}"),
            )
            rate = results[0].rate if results else 24000
            for i, sp in zip(spoken, results, strict=True):
                speeches[i] = trim_silence(sp.samples, sp.rate)
            scenes = [
                SceneSpeech(s.index, s.duration_s, texts[s.index], len(speeches[s.index]) / rate if s.index in speeches else None)
                for s in script.scenes
            ]
            timeline = plan_timeline(scenes, lang)
            ctx.progress(90, "Piste de narration")
            sf.write(str(out), mix_speech(timeline, speeches, rate), rate)

        self._save(ctx, timeline, out, tts.name, voice)
        stretched = [s.index for s, sc in zip(script.scenes, timeline.scenes, strict=True) if sc.duration > s.duration_s + 0.01]
        if stretched:
            ctx.log("tts.scenes_allongees", scenes=stretched, duree_totale=timeline.duration_s)
        return {"duration_s": timeline.duration_s, "words": len(timeline.words), "stretched_scenes": stretched,
                "voice": f"{tts.name}:{voice}", **({"retouch": True} if forced else {})}

    def _drama(self, ctx: Context, out: Any, script: ScriptV1, lang: str, speed: float) -> dict[str, Any]:
        """Répliques d'un drame, chacune avec la voix de son personnage (un appel au moteur par voix, le modèle se charge
        une fois par voix) ; scènes sans réplique : silence (la musique et le son du plan les portent)."""
        voices = assign_voices(script.cast, list(character_voices(tts_catalog(ctx.settings), lang)))
        default = load_generation_config(ctx.settings, ctx.db).voices.get(lang) or ""
        texts = {s.index: line_text(s) for s in script.scenes}
        by_voice: dict[str, list[int]] = {}
        for s in script.scenes:
            if texts[s.index]:
                who = s.lines[0].who if s.lines else ""
                by_voice.setdefault(voices.get(who) or default, []).append(s.index)
        ctx.log("tts.voix_personnages", voix=voices)
        if ctx.settings.dry_run:
            scenes = [SceneSpeech(s.index, s.duration_s, texts[s.index], estimate_speech_s(texts[s.index], lang)) for s in script.scenes]
            timeline = plan_timeline(scenes, lang)
            out.write_bytes(b"")
        else:
            import numpy as np
            import soundfile as sf

            speeches: dict[int, Any] = {}
            rate = 24000
            for k, (voice_id, idxs) in enumerate(by_voice.items()):
                engine, voice = split_voice(voice_id)
                tts = get_engine(ctx.settings, engine)
                ctx.progress(5 + int(80 * k / max(1, len(by_voice))), f"Voix · {voice_id} ({len(idxs)} répliques)")
                results = tts.speak_many([texts[i] for i in idxs], voice=voice, lang=lang, speed=speed)
                for i, sp in zip(idxs, results, strict=True):
                    x = trim_silence(sp.samples, sp.rate)
                    if speeches and sp.rate != rate:  # moteurs de fréquences différentes : tout à la première
                        x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * rate / sp.rate)), np.arange(len(x)), x)
                    elif not speeches:
                        rate = sp.rate
                    speeches[i] = x
            scenes = [SceneSpeech(s.index, s.duration_s, texts[s.index], len(speeches[s.index]) / rate if s.index in speeches else None)
                      for s in script.scenes]
            timeline = plan_timeline(scenes, lang)
            ctx.progress(90, "Piste des répliques")
            sf.write(str(out), mix_speech(timeline, speeches, rate), rate)
        self._save(ctx, timeline, out, "drama", ", ".join(f"{k}={v}" for k, v in voices.items()))
        return {"duration_s": timeline.duration_s, "words": len(timeline.words), "voices": voices}

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
