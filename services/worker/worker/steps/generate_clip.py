"""Génération d'un clip par scène (ComfyUI ou fournisseur cloud). Voie GPU.

Avec un workflow image → vidéo (ex. comfy_wan22_5b_i2v), le clip part d'une image et le prompt décrit
le mouvement (motion_prompt). L'image de départ est :
- la dernière image du clip précédent si la scène le prolonge (payload continues, docs/12 §4) ;
- sinon l'image de storyboard retenue pour la scène ;
- sinon, repli sur la variante texte → vidéo du même modèle si elle existe.

Scène « première + dernière image » (clip_mode flf, chantier en accéléré, docs/15) : le clip va de l'image clé
de la scène à celle de la scène suivante, avec la variante flf2v du modèle vidéo (même nombre de passes) ; sans
image suivante ou sans variante, repli sur l'image → vidéo classique.

Formats visuels : chaque clip est contrôlé par un modèle de vision (CLIP_QC, keyframe_qc.check_clip) et refait
CLIP_QC_RETRIES fois s'il fait apparaître une personne, un appareil de tournage ou un objet étranger ; le verdict est
gardé dans assets.meta.qc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..drama import DIALOGUE_RETRIES, HEARD_MIN, clip_prompt, heard_ratio, is_drama, line_text, transcribe, video_lang
from ..keyframe_qc import CLIP_SYSTEM, KeyframeVerdict, check_clip
from ..media import last_frame
from ..models import ScriptScene, ScriptV1
from ..prompts import prompt_text
from ..providers.llm import get_vision_llm
from ..providers.video import first_last_variant, get_video_provider, quality_variant, text_to_video_fallback
from ..recipes import is_visual, motion_prompt, recipe_for_production, spec
from ..settings_store import load_generation_config
from .base import Context, Step


class GenerateClipStep(Step):
    type = "generate_clip"
    lane = "gpu"

    def run(self, ctx: Context) -> dict[str, Any]:
        pid = ctx.job.production_id
        idx = int(ctx.job.payload["scene_index"])
        continues = bool(ctx.job.payload.get("continues"))
        prod = ctx.db.fetch_one("select script, style_preset, video_provider, format from productions where id = %s", (pid,))
        assert prod and prod["script"], "script manquant"
        script = ScriptV1.model_validate(prod["script"])
        pos, scene = next((i, s) for i, s in enumerate(script.scenes) if s.index == idx)
        recipe = recipe_for_production(ctx.db, pid)

        existing = ctx.db.fetch_one(
            "select id, local_path from assets where production_id = %s and kind = 'clip' and scene_index = %s",
            (pid, idx),
        )
        if existing:  # idempotence
            return {"asset_id": str(existing["id"]), "skipped": True}
        # Scène carte dont l'image du storyboard est la carte : le clip est rendu par le code, sans modèle vidéo
        if scene.is_map and self._map_storyboard(ctx, pid, idx):
            done = self._map_clip(ctx, pid, script, scene)
            if done:
                return done

        provider = get_video_provider(ctx.settings, prod["video_provider"] or load_generation_config(ctx.settings, ctx.db).video_provider,
                                      db=ctx.db)
        # Recette qui demande une variante du modèle (visite : mélange avec négatif, sans passants, docs/15 §10)
        variant = quality_variant(ctx.settings, provider.name, spec(recipe).video_variant) if is_visual(recipe) else None
        if variant:
            provider = get_video_provider(ctx.settings, variant, db=ctx.db)
        # Clips de durée imposée (Gemini en ligne : 4 à 10 s, docs/17) : le montage les coupe à la durée de la scène
        fixed = bool(getattr(provider, "fixed_length", False))
        clips_dir = ctx.production_dir(pid) / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        image: Path | None = None
        prompt = scene.visual_prompt
        if provider.image_to_video and continues:
            prev = ctx.db.fetch_one(
                """select local_path, duration_s from assets where production_id = %s and kind = 'clip' and scene_index = %s
                   order by created_at desc limit 1""",
                (pid, idx - 1),
            )
            if not prev:
                raise RuntimeError(f"scène {idx} : continuité demandée mais le clip de la scène {idx - 1} manque")
            image = clips_dir / f"scene_{idx - 1:02d}_last.png"
            if ctx.settings.dry_run:
                image.write_bytes(b"")
            else:
                offset = 0.05
                # passage d'une visite (ou clip de durée imposée) : le montage coupe le clip précédent à la durée de sa
                # scène, la suite part donc de l'image où il est coupé, pas de sa fin
                if (fixed or is_visual(recipe)) and pos > 0 and prev["duration_s"]:
                    offset = max(0.05, float(prev["duration_s"]) - script.scenes[pos - 1].duration_s)
                last_frame(Path(prev["local_path"]), image, offset_s=offset)
            prompt = scene.motion_prompt or scene.visual_prompt
            ctx.log("clip.continuite", scene=idx, depuis=str(prev["local_path"]))
        elif provider.image_to_video:
            row = ctx.db.fetch_one(
                """select local_path from assets where production_id = %s and kind = 'storyboard'
                   and scene_index = %s and selected order by created_at desc limit 1""",
                (pid, idx),
            )
            if row:
                image, prompt = Path(row["local_path"]), scene.motion_prompt or scene.visual_prompt
            else:
                alt = text_to_video_fallback(ctx.settings, provider.name)
                if not alt:
                    raise RuntimeError(f"scène {idx} : aucune image de storyboard retenue et pas de variante texte → vidéo")
                ctx.log("clip.repli_texte_video", scene=idx, provider=alt)
                provider = get_video_provider(ctx.settings, alt)

        end_image: Path | None = None
        if is_visual(recipe) and image is not None:
            prompt = motion_prompt(script, pos, recipe)
            if scene.clip_mode == "flf" and pos + 1 < len(script.scenes):
                nxt = ctx.db.fetch_one(
                    """select local_path from assets where production_id = %s and kind = 'storyboard'
                       and scene_index = %s and selected order by created_at desc limit 1""",
                    (pid, script.scenes[pos + 1].index),
                )
                # Gemini en ligne reçoit lui-même les deux images (au mieux : rien ne garantit qu'il finisse exactement
                # sur la seconde, docs/17) ; ComfyUI passe par la variante flf2v du modèle
                native = bool(getattr(provider, "first_last", False))
                flf = None if native else first_last_variant(ctx.settings, provider.name)
                if nxt and (native or flf):  # le clip se termine sur l'image clé de l'étape suivante
                    if flf:
                        provider = get_video_provider(ctx.settings, flf)
                    end_image = Path(nxt["local_path"])
                else:
                    ctx.log("clip.flf_indisponible", level="warn", scene=idx, variante=flf, image_suivante=bool(nxt))

        # Drame (docs/35) : le modèle vidéo dit la réplique du plan, avec la voix du personnage ; le style est dans l'image
        style = prod["style_preset"]
        if is_drama(recipe) and image is not None:
            prompt, style = clip_prompt(script, pos, video_lang(script), prod["style_preset"]), "animation_motion"

        extra_negative = spec(recipe).video_negative if is_visual(recipe) else ""
        if extra_negative and isinstance(getattr(provider, "negative", None), str):  # n'agit qu'avec CFG > 1 (mélange, 20 passes)
            provider.negative = f"{provider.negative}, {extra_negative}"
        out = clips_dir / f"scene_{idx:02d}.mp4"
        ctx.progress(5, f"Clip {idx + 1} · {provider.name}" + (" · continuité" if continues else " · première + dernière image"
                     if end_image else " · depuis l'image" if image else ""))
        # Formats visuels : le clip est regardé par le modèle de vision (personne, appareil de tournage ou objet inventés,
        # worker/keyframe_qc.py) et refait une fois s'il est refusé (docs/15 §10)
        qc = (get_vision_llm(ctx.settings, ctx.db)
              if is_visual(recipe) and image is not None and ctx.settings.clip_qc and not ctx.settings.dry_run else None)
        verdict: KeyframeVerdict | None = None
        # Gemini en ligne (durée imposée, asynchrone) : verdict noté, jamais de nouvel essai. Le job repart du début après
        # chaque attente (Postpone) : une reprise ici redemanderait une vidéo à chaque passage, sans fin, sur le quota
        retries = 0 if fixed else max(0, ctx.settings.clip_qc_retries)
        def render() -> Any:
            return provider.generate(
                prompt=prompt,
                style_preset=style,
                duration_s=scene.duration_s,
                out_path=out,
                on_progress=lambda p: ctx.progress(5 + int(p * 0.9), f"Clip {idx + 1} · {p} %"),
                dry_run=ctx.settings.dry_run,
                image_path=image,
                end_image_path=end_image,
            )

        for attempt in range(1 + (retries if qc else 0)):
            info = render()
            if not qc or image is None:
                break
            try:
                verdict = check_clip(qc, out, image, script, pos, recipe, clips_dir / "qc",
                                     system=prompt_text(ctx.db, "clip_qc", CLIP_SYSTEM))  # onglet Agents du dashboard
            except Exception as exc:  # noqa: BLE001  le contrôle est un filet, pas une étape bloquante
                ctx.log("clip.controle_indisponible", level="warn", scene=idx, erreur=str(exc)[:300])
                verdict = None
                break
            if verdict.ok:
                break
            ctx.log("clip.refuse", level="warn", scene=idx, essai=attempt + 1, problemes=verdict.problems)
        # Drame en voix des clips (format B) : ce que dit le clip (Whisper) ; une réplique qui n'est pas dite fait refaire le
        # clip (DIALOGUE_RETRIES). En voix constantes (format A), la voix de synthèse remplace le son du clip.
        clip_voice = is_drama(recipe) and prod["format"] == "B_visual" and bool(scene.lines) and not ctx.settings.dry_run
        dialogue = self._dialogue(ctx, out, scene, script) if clip_voice else None
        for retry in range(DIALOGUE_RETRIES):
            if dialogue is None or dialogue["ratio"] >= HEARD_MIN:
                break
            ctx.log("clip.replique_absente", level="warn", scene=idx, essai=retry + 1, attendu=dialogue["expected"],
                    entendu=dialogue["heard"], ressemblance=dialogue["ratio"])
            info = render()
            dialogue = self._dialogue(ctx, out, scene, script)
        asset_id = ctx.db.add_asset(
            production_id=pid,
            kind="clip",
            scene_index=idx,
            local_path=str(out),
            duration_s=info.duration_s,
            width=info.width,
            height=info.height,
            meta={"provider": provider.name, "seed": info.seed, "prompt": prompt, "image": str(image) if image else None,
                  "continues": continues, "end_image": str(end_image) if end_image else None,
                  **({"qc": verdict.model_dump()} if verdict else {}), **({"dialogue": dialogue} if dialogue else {})},
        )
        return {"asset_id": str(asset_id), "provider": provider.name, "from_image": bool(image), "continues": continues,
                "first_last": bool(end_image), **({"qc": verdict.model_dump()} if verdict else {}),
                **({"dialogue": {k: dialogue[k] for k in ("expected", "heard", "ratio")}} if dialogue else {})}

    @staticmethod
    def _dialogue(ctx: Context, clip: Path, scene: ScriptScene, script: ScriptV1) -> dict[str, Any] | None:
        """Ce que Whisper entend dans le clip d'un drame (mots horodatés, pour les sous-titres) et sa ressemblance avec la
        réplique écrite. None si la transcription n'est pas possible (environnement d'évaluation absent, échec) : le
        montage répartit alors la réplique sur le plan."""
        try:
            heard = transcribe(ctx.settings, [clip], video_lang(script))
        except Exception as exc:  # noqa: BLE001  la transcription est un filet, jamais une étape bloquante
            ctx.log("clip.transcription_indisponible", level="warn", scene=scene.index, erreur=str(exc)[:300])
            return None
        if not heard:
            ctx.log("clip.transcription_absente", level="warn", scene=scene.index,
                    raison="environnement tts/eval (Whisper) non installé : install_tts.ps1 -Engine eval")
            return None
        expected = line_text(scene)
        return {"expected": expected, "heard": heard[0]["text"], "words": heard[0]["words"],
                "ratio": heard_ratio(expected, heard[0]["text"])}

    @staticmethod
    def _map_storyboard(ctx: Context, pid: Any, idx: int) -> bool:
        """L'image retenue de la scène est-elle la carte ? (sinon la carte a échoué au storyboard : clip d'IA habituel)"""
        row = ctx.db.fetch_one(
            """select meta->>'provider' as provider from assets where production_id = %s and kind = 'storyboard'
               and scene_index = %s and selected order by created_at desc limit 1""",
            (pid, idx),
        )
        return bool(row and row["provider"] == "map")

    @staticmethod
    def _map_clip(ctx: Context, pid: Any, script: ScriptV1, scene: Any) -> dict[str, Any] | None:
        """Clip de la scène carte (worker/maps.py, docs/24), sur le processeur ; None en cas d'échec (clip d'IA à la place)."""
        from .. import maps  # numpy (extra « tts ») : chargé pour les seules scènes carte

        out = ctx.production_dir(pid) / "clips" / f"scene_{scene.index:02d}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        lang = next(iter(script.metadata), "fr")
        ctx.progress(5, f"Clip {scene.index + 1} · carte de « {scene.map.place} »")
        try:
            if ctx.settings.dry_run:
                out.write_bytes(b"")
                duration = scene.duration_s
            else:
                plan = maps.scene_plan(ctx.settings, scene.map, lang)
                duration = maps.render_clip(plan, out, scene.duration_s, cache_root=ctx.settings.data_dir / "maps",
                                            user_agent=ctx.settings.effective_wikipedia_user_agent,
                                            font_path=maps.font_for(ctx.settings), lang=lang)
        except Exception as exc:  # noqa: BLE001
            ctx.log("clip.carte_indisponible", level="warn", scene=scene.index, lieu=scene.map.place, erreur=str(exc)[:300])
            return None
        asset_id = ctx.db.add_asset(
            production_id=pid, kind="clip", scene_index=scene.index, local_path=str(out), duration_s=duration,
            width=maps.W, height=maps.H, meta={"provider": "map", "prompt": f"Carte : {scene.map.place}", "map": scene.map.model_dump()},
        )
        return {"asset_id": str(asset_id), "provider": "map", "from_image": False, "continues": False, "first_last": False}
