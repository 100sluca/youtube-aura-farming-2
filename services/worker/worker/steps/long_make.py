"""Job long_make (voie gpu) : la fabrication des vidéos longues (docs/63).

payload.action, toujours avec long_id :
- images {chapter} : les images 16:9 des plans du chapitre (Qwen-Image ou le modèle des Réglages, 1664 × 928), la
  1re image de ses clips, ses cartes ; contrôle par la vision, une image ratée refaite une fois ;
- clip {idx} : le clip d'un plan, depuis son image (MiniMax H3 ou le modèle des Réglages, en 832 × 480) ;
- thumbnails : les miniatures des concepts de l'emballage, texte posé par le code, notées par la vision ;
- voice : la voix finale (prises gardées nettoyées, modificateur si demandé), puis le montage en file ;
- render : le montage 16:9 (attend que les images et les clips soient faits), puis la vidéo à regarder.
"""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from ..longform import captions, flow, render, voice, voice_mod
from ..longform import music as long_music
from ..longform.models import ImageChecks, MapSpec, ThumbReview
from ..longform.motion import chapter_card
from ..longform.prompts import IMAGE_CHECK_PROMPT, THUMB_CHECK_PROMPT
from ..longform.thumbnail import compose, small
from ..longform.write import more_thumb_concepts
from ..media import probe_duration, video_encode_args
from ..montage import font_registry
from ..postpone import Postpone
from ..prompts import prompt_text
from ..providers.llm import get_vision_llm
from ..providers.video import ComfyImage, ComfyVideo
from ..settings_store import load_generation_config
from .base import Context, Step

IMAGE_STYLE = (
    "cinematic widescreen 16:9 film still, photorealistic, rich natural light, sharp detail, no text, no letters, no watermark"
)
THUMB_STYLE = (
    "YouTube thumbnail image, 16:9, one clear main subject, dramatic high-contrast lighting, vivid complementary colors, "
    "bright overall exposure, clean uncluttered background, no text, no letters, no logo, no watermark"
)
CLIP_S = 5.0
QC_BATCH = 6
SHOT_TRIES = 3


def size_of(value: str, default: tuple[int, int]) -> tuple[int, int]:
    try:
        w, h = str(value).lower().replace("×", "x").split("x")
        return int(w), int(h)
    except ValueError:
        return default


class LongMakeStep(Step):
    type = "long_make"
    lane = "gpu"

    def run(self, ctx: Context) -> dict[str, Any]:
        p = ctx.job.payload
        lv = flow.get_long(ctx.db, p["long_id"])
        action = p.get("action")
        if action == "images":
            return self._images(ctx, lv, int(p["chapter"]))
        if action == "clip":
            return self._clip(ctx, lv, int(p["idx"]))
        if action == "thumbnails":
            return self._thumbnails(ctx, lv)
        if action == "voice":
            return self._voice(ctx, lv)
        if action == "render":
            return self._render(ctx, lv)
        if action == "music":
            made = long_music.generate(ctx.settings, p.get("mood", "mystere"), int(p.get("count", 1)), log=ctx.log)
            return {"tracks": [m.name for m in made]}
        raise ValueError(f"action inconnue : {action}")

    # ---- Images ---------------------------------------------------------------------------------------------------------

    def _image_model(self, ctx: Context) -> ComfyImage:
        gen = load_generation_config(ctx.settings, ctx.db)
        model = ComfyImage(ctx.settings, gen.image_workflow)
        model.width, model.height = size_of(flow.long_settings(ctx.db).get("image_size"), (1664, 928))
        return model

    def _gen_image(self, ctx: Context, model: ComfyImage, lv: dict[str, Any], shot: dict[str, Any]) -> tuple[Path, float]:
        bible = (lv.get("script") or {}).get("design_bible") or ""
        prompt = ". ".join(x.strip().rstrip(".") for x in (shot["visual_prompt"], bible, IMAGE_STYLE) if x)
        out = Path(lv["dir"]) / "images" / f"shot_{shot['idx']:04d}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        model.generate(
            prompt=prompt, style_preset=None, out_path=out, seed=random.randint(0, 2**31), dry_run=ctx.settings.dry_run
        )
        return out, round(time.perf_counter() - t0, 1)

    def _map(self, ctx: Context, lv: dict[str, Any], shot: dict[str, Any]) -> Path | None:
        """Carte du plan (worker/maps.py) en 1920 × 1080 ; None en cas d'échec (image d'IA à la place)."""
        from .. import maps

        out = Path(lv["dir"]) / "clips" / f"shot_{shot['idx']:04d}_carte.mp4"
        try:
            plan = maps.scene_plan(ctx.settings, MapSpec.model_validate(shot["map"]), "fr")
            maps.render_clip(
                plan,
                out,
                6.0,
                cache_root=ctx.settings.data_dir / "maps",
                user_agent=ctx.settings.effective_wikipedia_user_agent,
                font_path=maps.font_for(ctx.settings),
                lang="fr",
                size=(1920, 1080),
            )
            return out
        except Exception as exc:  # noqa: BLE001
            ctx.log("long.carte_indisponible", level="warn", plan=shot["idx"], erreur=str(exc)[:300])
            return None

    def _images(self, ctx: Context, lv: dict[str, Any], chapter: int) -> dict[str, Any]:
        shots = ctx.db.fetch_all(
            """select * from long_shots where long_id = %s and chapter = %s and status <> 'skipped'
               and (image_path is null or status = 'failed') and attempts < %s order by idx""",
            (lv["id"], chapter, SHOT_TRIES),
        )
        model = self._image_model(ctx) if shots else None
        made = 0
        for i, s in enumerate(shots):
            ctx.progress(int(85 * i / max(1, len(shots))), f"Chapitre {chapter + 1} : image {i + 1}/{len(shots)}")
            ctx.db.execute("update long_shots set status = 'running', attempts = attempts + 1 where id = %s", (s["id"],))
            if s["kind"] == "map" and s.get("map"):
                clip = self._map(ctx, lv, s)
                if clip:
                    ctx.db.execute(
                        "update long_shots set clip_path = %s, image_path = coalesce(image_path, %s), status = 'done' where id = %s",
                        (str(clip), None, s["id"]),
                    )
                    continue
            try:
                assert model is not None
                path, gen_s = self._gen_image(ctx, model, lv, s)
            except Exception as exc:  # noqa: BLE001 — une image ratée ne bloque pas le chapitre
                ctx.db.execute("update long_shots set status = 'failed', error = %s where id = %s", (str(exc)[:500], s["id"]))
                ctx.log("long.image_ratee", level="warn", plan=s["idx"], erreur=str(exc)[:300])
                continue
            done = "running" if s["kind"] == "clip" else "done"  # un clip reste à faire depuis cette image
            ctx.db.execute(
                "update long_shots set image_path = %s, gen_s = %s, status = %s, error = null, updated_at = now() where id = %s",
                (str(path), gen_s, done, s["id"]),
            )
            made += 1
        redone = self._check_chapter(ctx, lv, chapter, model)
        return {"images": made, "redone": redone}

    def _check_chapter(self, ctx: Context, lv: dict[str, Any], chapter: int, model: ComfyImage | None) -> int:
        """Contrôle des images du chapitre par la vision (6 par appel) ; une image ratée est refaite une fois."""
        vision = get_vision_llm(ctx.settings, ctx.db)
        rows = ctx.db.fetch_all(
            """select * from long_shots where long_id = %s and chapter = %s and image_path is not null and qc is null
               order by idx""",
            (lv["id"], chapter),
        )
        if not vision or not rows or ctx.settings.dry_run:
            return 0
        system = prompt_text(ctx.db, "long_image_check", IMAGE_CHECK_PROMPT)
        redone = 0
        for start in range(0, len(rows), QC_BATCH):
            batch = rows[start : start + QC_BATCH]
            ctx.progress(88, f"Chapitre {chapter + 1} : contrôle des images")
            user = "\n".join(f"Image {k} : {r['visual_prompt']}" for k, r in enumerate(batch))
            try:
                res: ImageChecks = vision.complete_json(system, user, ImageChecks, images=[Path(r["image_path"]) for r in batch])
            except Exception as exc:  # noqa: BLE001 — contrôle indisponible : les images restent
                ctx.log("long.controle_indisponible", level="warn", erreur=str(exc)[:300])
                return redone
            verdicts = {c.index: c for c in res.checks}
            for k, r in enumerate(batch):
                c = verdicts.get(k)
                qc = {"ok": True} if c is None else {"ok": c.ok, "problem": c.problem}
                if c is not None and not c.ok and model is not None and (r["attempts"] or 0) < SHOT_TRIES:
                    try:
                        path, gen_s = self._gen_image(ctx, model, lv, r)
                        qc = {"ok": True, "redone": True, "first_problem": c.problem}
                        ctx.db.execute(
                            "update long_shots set image_path = %s, gen_s = %s, attempts = attempts + 1 where id = %s",
                            (str(path), gen_s, r["id"]),
                        )
                        redone += 1
                    except Exception as exc:  # noqa: BLE001
                        ctx.log("long.image_refaite_ratee", level="warn", plan=r["idx"], erreur=str(exc)[:200])
                ctx.db.execute("update long_shots set qc = %s where id = %s", (Jsonb(qc), r["id"]))
        return redone

    # ---- Clips ----------------------------------------------------------------------------------------------------------

    def _clip(self, ctx: Context, lv: dict[str, Any], idx: int) -> dict[str, Any]:
        s = ctx.db.fetch_one("select * from long_shots where long_id = %s and idx = %s", (lv["id"], idx))
        assert s, f"plan {idx} introuvable"
        if s.get("clip_path") and Path(s["clip_path"]).exists():
            return {"skipped": True}
        if not s.get("image_path"):
            path, gen_s = self._gen_image(ctx, self._image_model(ctx), lv, s)
            ctx.db.execute("update long_shots set image_path = %s, gen_s = %s where id = %s", (str(path), gen_s, s["id"]))
            s["image_path"] = str(path)
        gen = load_generation_config(ctx.settings, ctx.db)
        provider = ComfyVideo(ctx.settings, gen.video_workflow)
        provider.width, provider.height = size_of(flow.long_settings(ctx.db).get("clip_size"), (832, 480))
        out = Path(lv["dir"]) / "clips" / f"shot_{idx:04d}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        bible = (lv.get("script") or {}).get("design_bible") or ""
        prompt = ". ".join(
            x.strip().rstrip(".")
            for x in (s.get("motion") or "", s["visual_prompt"], bible, "cinematic, smooth slow motion")
            if x
        )
        t0 = time.perf_counter()
        try:
            info = provider.generate(
                prompt=prompt,
                style_preset=None,
                duration_s=CLIP_S,
                out_path=out,
                on_progress=lambda pct: ctx.progress(int(pct), f"Clip du plan {idx + 1}"),
                dry_run=ctx.settings.dry_run,
                image_path=Path(s["image_path"]),
            )
        except Exception as exc:  # noqa: BLE001 — le plan garde son image animée
            ctx.db.execute(
                "update long_shots set status = 'done', error = %s where id = %s",
                (f"clip raté, image gardée : {exc}"[:500], s["id"]),
            )
            raise
        ctx.db.execute(
            "update long_shots set clip_path = %s, status = 'done', qc = coalesce(qc, '{}'::jsonb) || %s, error = null where id = %s",
            (str(out), Jsonb({"clip_s": round(info.duration_s, 2), "clip_gen_s": round(time.perf_counter() - t0, 1)}), s["id"]),
        )
        return {"clip": out.name, "seconds": round(time.perf_counter() - t0)}

    # ---- Miniatures -----------------------------------------------------------------------------------------------------

    def _thumbnails(self, ctx: Context, lv: dict[str, Any]) -> dict[str, Any]:
        """Miniatures : les 3 concepts de l'emballage la première fois ; « more » : de nouveaux concepts dans le style
        de la niche, AJOUTÉS à celles qui existent (Luca garde celles qu'il aime, docs/63 §9) ; « only » : une
        miniature refaite à sa place."""
        p = ctx.job.payload
        existing = list((lv.get("thumbnail") or {}).get("candidates") or [])
        more = int(p.get("more") or 0)
        if more:
            ctx.progress(5, "Nouveaux concepts de miniature (style de la niche)")
            concepts = more_thumb_concepts(ctx, lv, existing, more)
        elif p.get("only") is not None and int(p["only"]) < len(existing):
            concepts = [{**existing[int(p["only"])], "text_side": existing[int(p["only"])].get("side")}]
        else:
            pack = lv.get("packaging") or {}
            concepts = list(pack.get("thumbnails") or [])[:3]
            if not concepts and (lv.get("idea") or {}).get("thumbnail"):
                concepts = [lv["idea"]["thumbnail"]]
        model = self._image_model(ctx)
        folder = Path(lv["dir"]) / "miniatures"
        folder.mkdir(parents=True, exist_ok=True)
        rnd = 1 + max((int(c.get("round") or 1) for c in existing), default=0)
        made: list[dict[str, Any]] = []
        for n, c in enumerate(concepts):
            ctx.progress(10 + int(75 * n / max(1, len(concepts))), f"Miniature {n + 1}/{len(concepts)}")
            stamp = f"{int(time.time())}_{n}"
            base = folder / f"fond_{stamp}.png"
            side = c.get("text_side") or "left"
            space = {
                "left": "empty space on the left third",
                "right": "empty space on the right third",
                "top": "empty sky at the top",
            }.get(side, "empty space for a title")
            model.generate(
                prompt=f"{c.get('prompt', '')}. {THUMB_STYLE}, {space}",
                style_preset=None,
                out_path=base,
                seed=random.randint(0, 2**31),
                dry_run=ctx.settings.dry_run,
            )
            out = folder / f"miniature_{stamp}.jpg"
            compose(base, c.get("text") or "", side, out, ctx.settings.fonts_dir)
            made.append(
                {
                    "file": str(out),
                    "base": str(base),
                    "idea": c.get("idea", ""),
                    "text": c.get("text", ""),
                    "side": side,
                    "prompt": c.get("prompt", ""),
                    "round": rnd,
                    "kept": False,
                    "ab": False,
                }
            )
        self._score_thumbnails(ctx, lv, made)
        # Luca a pu garder, cocher ou choisir pendant ce temps : on part de l'état en base
        current = dict(flow.get_long(ctx.db, lv["id"]).get("thumbnail") or {})
        cands: list[dict[str, Any]] = list(current.get("candidates") or [])
        if p.get("only") is not None and int(p["only"]) < len(cands) and made:
            k = int(p["only"])
            cands[k] = {**made[0], "kept": cands[k].get("kept", False), "ab": cands[k].get("ab", False)}
        else:
            cands.extend(made)
        best = max(range(len(cands)), key=lambda i: float(cands[i].get("score") or 0)) if cands else 0
        chosen = current.get("chosen") if current.get("picked_by") == "luca" else best
        flow.update_long(ctx.db, lv["id"], thumbnail={**current, "candidates": cands, "chosen": chosen})
        return {"made": len(made), "thumbnails": len(cands), "best": best}

    def _score_thumbnails(self, ctx: Context, lv: dict[str, Any], cands: list[dict[str, Any]]) -> None:
        vision = get_vision_llm(ctx.settings, ctx.db)
        files = [Path(c["file"]) for c in cands if c.get("file")]
        if not vision or not files or ctx.settings.dry_run:
            return
        smalls = [small(f, f.with_name(f.stem + "_petit.jpg")) for f in files]
        pack = lv.get("packaging") or {}
        titles = pack.get("titles") or []
        title = titles[min(int(pack.get("chosen") or 0), len(titles) - 1)]["title"] if titles else lv["subject"]
        try:
            res: ThumbReview = vision.complete_json(
                prompt_text(ctx.db, "long_thumb_check", THUMB_CHECK_PROMPT), f"TITRE : {title}", ThumbReview, images=smalls
            )
        except Exception as exc:  # noqa: BLE001
            ctx.log("long.miniatures_non_notees", level="warn", erreur=str(exc)[:300])
            return
        for sc in res.scores:
            if 0 <= sc.index < len(cands):
                cands[sc.index]["score"] = sc.score
                cands[sc.index]["note"] = sc.note

    # ---- Voix ---------------------------------------------------------------------------------------------------------

    def _voice(self, ctx: Context, lv: dict[str, Any]) -> dict[str, Any]:
        cfg = flow.long_settings(ctx.db)
        settings_voice = dict(lv.get("voice") or {})
        modifier = bool(settings_voice.get("modifier", cfg.get("voice_modifier")))
        target = settings_voice.get("modifier_voice") or cfg.get("modifier_voice") or "qwen3:narrateur"
        paras = [p for c in lv["script"]["chapters"] for p in c["paragraphs"]]
        takes = {
            r["para"]: r
            for r in ctx.db.fetch_all(
                """select distinct on (para) * from long_takes where long_id = %s and chosen and status <> 'failed'
                   order by para, take desc""",
                (lv["id"],),
            )
        }
        missing = [p["key"] for p in paras if p["key"] not in takes]
        if missing:
            raise RuntimeError(f"{len(missing)} paragraphe(s) sans prise : {', '.join(missing[:12])}")
        folder = Path(lv["dir"]) / "voix" / "finale"
        out: dict[str, Any] = {}
        for i, p in enumerate(paras):
            ctx.progress(int(60 * i / len(paras)), f"Voix : paragraphe {i + 1}/{len(paras)}")
            t = takes[p["key"]]
            res = voice.clean_take(Path(t["path"]), folder / f"{p['key']}.wav", t.get("check_result") or {}, ctx.settings)
            out[p["key"]] = {**res, "take": t["take"]}
        made_with: dict[str, Any] = {
            "modifier": modifier,
            "voice": target if modifier else "",
            "cleaning": voice.CLEANING_VERSION,
        }
        if modifier and target.startswith(voice_mod.PREFIX):  # réglage de Luca (Studio du modificateur, docs/67)
            params = voice_mod.profile_params(ctx.db, target)
            if params is None:
                raise RuntimeError(f"réglage du modificateur introuvable : {target}")
            made_with["params"] = params
            for i, v in enumerate(out.values()):
                ctx.progress(65 + int(30 * i / len(out)), f"Modificateur : paragraphe {i + 1}/{len(out)}")
                src = Path(v["path"])
                dst = src.with_name(src.stem + "_reglee.wav")
                ratio = voice_mod.apply(src, dst, params, settings=ctx.settings)
                v.update(path=str(dst), original=str(src))
                if ratio != 1.0:  # débit changé : les mots et la durée suivent
                    v["duration_s"] = round(v["duration_s"] * ratio, 3)
                    v["words"] = [
                        {**w, "start": round(w["start"] * ratio, 3), "end": round(w["end"] * ratio, 3)} for w in v["words"]
                    ]
        elif modifier:
            ref = voice.modifier_reference(ctx.settings, target)
            if not ref:
                raise RuntimeError(f"voix d'arrivée du modificateur introuvable : {target}")
            ctx.progress(65, "Modificateur de voix (Chatterbox VC)")
            items = [(Path(v["path"]), Path(v["path"]).with_name(Path(v["path"]).stem + "_vc.wav")) for v in out.values()]
            voice.convert_voices(ctx.settings, items, ref, Path(lv["dir"]) / "voix" / "vc")
            for (src, dst), key in zip(items, list(out), strict=True):
                converted = dst.with_suffix(".voix.wav")
                final = src.with_name(src.stem + "_modifiee.wav")
                voice.to_mono48(converted, final)
                out[key]["path"] = str(final)
                out[key]["original"] = str(src)
        flow.update_long(
            ctx.db,
            lv["id"],
            voice={
                **settings_voice,
                "modifier": modifier,
                "modifier_voice": target if modifier else "",
                # ce que la voix finale a réellement reçu : le choix ci-dessus peut changer ensuite (setVoiceModifier)
                "made_with": made_with,
                "paragraphs": out,
                "done_at": time.time(),
            },
        )
        if not flow.pending(ctx.db, lv["id"], "long_make", actions=("render",)):
            flow.enqueue_make(ctx.db, lv, "render", priority=85)
        return {"paragraphs": len(out), "modifier": modifier}

    # ---- Montage -------------------------------------------------------------------------------------------------------

    def _render(self, ctx: Context, lv: dict[str, Any]) -> dict[str, Any]:
        busy = [
            j for j in flow.pending(ctx.db, lv["id"], "long_make", actions=("images", "clip", "voice")) if j["id"] != ctx.job.id
        ]
        if busy:
            raise Postpone(
                "images, clips ou voix pas encore faits", 600, label=f"Montage : attend {len(busy)} tâche(s) d'images et de clips"
            )
        script = lv["script"]
        vo = (lv.get("voice") or {}).get("paragraphs") or {}
        assert vo, "voix finale absente : terminer l'enregistrement dans le Studio voix"
        flow.update_long(ctx.db, lv["id"], stage="assembling", error=None)
        flow.set_production_status(ctx.db, lv, "assembling")
        paras = []
        for c in script["chapters"]:
            for p in c["paragraphs"]:
                v = vo[p["key"]]
                paras.append(
                    render.Para(
                        key=p["key"], chapter=c["index"], path=Path(v["path"]), duration=float(v["duration_s"]), words=v.get("words") or [],
                        script_words=len(p["text"].split()),
                    )
                )  # fmt: skip
        shots = ctx.db.fetch_all(
            "select * from long_shots where long_id = %s and (image_path is not null or clip_path is not null) order by idx",
            (lv["id"],),
        )
        for s in shots:
            s["clip_s"] = ((s.get("qc") or {}).get("clip_s")) or 0
            if s.get("clip_path") and not Path(s["clip_path"]).exists():
                s["clip_path"] = None
        spans, total = render.place_paragraphs(paras)
        timed = render.plan_shots(paras, shots, spans, total)
        assert timed, "aucun plan avec une image"
        folder = Path(lv["dir"]) / "rendu"
        cards = {
            c["index"]: chapter_card(
                c["index"], c.get("title") or "", folder / f"chapitre_{c['index']}.png", ctx.settings.fonts_dir
            )
            for c in script["chapters"]
            if c["index"] >= 1 and c.get("title")
        }
        nvenc = video_encode_args("auto")[1] == "h264_nvenc"
        segments = render.render_segments(
            timed,
            folder / "plans",
            cards,
            nvenc=nvenc,
            progress=lambda d, n: ctx.progress(int(70 * d / n), f"Montage : plan {d}/{n}"),
        )
        ctx.progress(72, "Montage : assemblage de l'image")
        video = render.concat(segments, folder / "image.mp4")
        subtitled = bool(flow.long_settings(ctx.db).get("subtitles", True))
        if subtitled:  # le texte lu, gravé en bas de l'image (docs/63 §12)
            ctx.progress(73, "Montage : sous-titres")
            texts = {p["key"]: p["text"] for c in script["chapters"] for p in c["paragraphs"]}
            subdir = folder / "sous-titres"
            flt = captions.write(captions.timeline_words(paras, texts, spans), subdir, font_registry(ctx.settings))
            video = captions.burn(
                video,
                subdir,
                flt,
                folder / "image_sous-titree.mp4",
                total,
                nvenc=nvenc,
                progress=lambda f: ctx.progress(73 + int(3 * f), f"Montage : sous-titres ({int(100 * f)} %)"),
            )
        ctx.progress(76, "Montage : voix")
        voice_wav = render.voice_track(paras, spans, total, folder / "voix.wav")
        mood = (lv.get("packaging") or {}).get("music_mood")
        pool: list[Path] = []
        for m in long_music.pick_moods(mood):
            pool = long_music.tracks(ctx.settings.data_dir, m)
            if pool:
                break
        if not pool:
            ctx.progress(78, "Musique de fond : génération (ACE-Step)")
            first = long_music.pick_moods(mood)[0]
            pool = long_music.generate(ctx.settings, first, long_music.TRACKS_PER_MOOD, log=ctx.log)
        ctx.progress(82, "Montage : musique")
        music_wav = render.music_track(render.playlist(pool, total, str(lv["id"])), total, folder / "musique.wav")
        ctx.progress(86, "Montage : mixage")
        audio = render.mix(voice_wav, music_wav, folder / "son.m4a")
        final = render.mux(video, audio, folder / "finale.mp4")
        ctx.progress(92, "Aperçu et image de la vidéo")
        poster = render.poster(final, folder / "poster.jpg", at_s=min(2.0, total / 2))
        light = render.preview(final, folder / "apercu.mp4")
        duration = probe_duration(final) or total
        titles = {c["index"]: c.get("title") or f"Chapitre {c['index']}" for c in script["chapters"]}
        titles[0] = titles.get(0) or "Introduction"
        marks = [{"at": round(at, 2), "title": t} for at, t in render.chapter_marks(timed, titles)]
        video_id = self._video_row(ctx, lv, final, light, poster, duration)
        timeline = {
            "total_s": round(total, 2),
            "chapters": marks,
            "paragraphs": {k: list(v) for k, v in spans.items()},
            "shots": [{"idx": t.idx, "start": t.start, "end": t.end, "kind": "clip" if t.clip else "image"} for t in timed],
            "music_mood": mood,
            "subtitles": subtitled,
        }
        flow.update_long(ctx.db, lv["id"], timeline=timeline, stage="review", video_id=video_id)
        ctx.db.execute("update long_videos set rendered_at = now() where id = %s", (lv["id"],))
        flow.set_production_status(ctx.db, lv, "ready")
        title = ((lv.get("packaging") or {}).get("titles") or [{"title": lv["subject"]}])[0]["title"]
        flow.mail(
            ctx.db,
            ctx.settings,
            f"🎬 Vidéo longue prête : {title}",
            f"« {title} » est montée ({int(duration // 60)} min {int(duration % 60):02d} s). Regarde-la, choisis le titre et la "
            f"miniature, puis programme-la dans la page Vidéos longues.\n\n{ctx.settings.dashboard_url.rstrip('/')}/long/{lv['id']}",
            image=poster,
        )
        return {"duration_s": round(duration, 1), "shots": len(timed), "chapters": len(marks)}

    @staticmethod
    def _video_row(ctx: Context, lv: dict[str, Any], final: Path, light: Path, poster: Path, duration: float) -> Any:
        pack = lv.get("packaging") or {}
        titles = pack.get("titles") or [{"title": lv["subject"]}]
        title = titles[min(int(pack.get("chosen") or 0), len(titles) - 1)]["title"][:100]
        vid = lv.get("video_id")
        if not vid:
            row = ctx.db.fetch_one(
                """insert into videos (production_id, channel_id, lang, format, status, title, description, tags, origin,
                                       duration_s, slot_pinned, narration_text)
                   values (%s, %s, 'fr', 'A_voiceover', 'review', %s, %s, %s, 'long', %s, true, %s) returning id""",
                (
                    lv["production_id"],
                    lv["channel_id"],
                    title,
                    pack.get("description") or "",
                    list(pack.get("tags") or [])[:30],
                    round(duration, 2),
                    "\n\n".join(p["text"] for c in lv["script"]["chapters"] for p in c["paragraphs"])[:100000],
                ),
            )
            vid = row["id"]
        ids = {}
        for kind, path in (("final", final), ("preview", light), ("poster", poster)):
            ids[kind] = ctx.db.add_asset(
                production_id=lv["production_id"], video_id=vid, kind=kind, local_path=str(path),
                duration_s=round(duration, 2) if kind != "poster" else None, width=1920 if kind == "final" else None,
                height=1080 if kind == "final" else None, meta={"long_id": str(lv["id"])},
            )  # fmt: skip
        ctx.db.execute(
            """update videos set final_asset_id = %s, preview_asset_id = %s, poster_asset_id = %s, duration_s = %s,
                      status = case when youtube_video_id is null then 'review' else status end where id = %s""",
            (ids["final"], ids["preview"], ids["poster"], round(duration, 2), vid),
        )
        return vid
