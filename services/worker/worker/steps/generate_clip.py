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
gardé dans assets.meta.qc. Drames (docs/35) : même contrôle, pour un texte écrit à l'image par le modèle vidéo (la
réplique en sous-titre, vu le 29/09).

Texte voulu dans l'image (scene.image_text, docs/57 §5) : le prompt le garde immobile, trois images du clip sont relues
lettre à lettre (worker/image_text.py), toujours, et le clip est refait s'il le déforme ; s'il le déforme encore, le plan
devient un plan fixe en lente avancée sur l'image vérifiée du storyboard (le plan n'a pas de réplique à perdre).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .. import quotes
from ..drama import (
    CLIP_STYLE,
    DIALOGUE_RETRIES,
    clip_prompt,
    heard_ratio,
    invented_words,
    is_drama,
    line_said,
    line_text,
    transcribe,
    video_lang,
)
from ..image_text import check_clip as check_clip_text
from ..image_text import merge, motion_clause, still_clip
from ..keyframe_qc import CLIP_SYSTEM, KeyframeVerdict, check_clip
from ..media import last_frame
from ..models import ScriptScene, ScriptV1
from ..prompts import prompt_text
from ..providers.llm import get_llm, get_vision_llm
from ..providers.video import ClipInfo, first_last_variant, get_video_provider, quality_variant, text_to_video_fallback
from ..recipes import chain_next, is_visual, motion_prompt, recipe_for_production, spec, video_negative
from ..settings_store import load_generation_config
from ..speaker import director_note, locate, shot_members
from .base import Context, Step

QUOTE = quotes.RECIPE


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
        # idempotence ; payload « redo » : clip refait quand même (texte écrit à l'image, 29/09), le nouveau prime au montage
        if existing and not ctx.job.payload.get("redo"):
            return {"asset_id": str(existing["id"]), "skipped": True}
        # Scène carte dont l'image du storyboard est la carte : le clip est rendu par le code, sans modèle vidéo
        if scene.is_map and self._map_storyboard(ctx, pid, idx):
            done = self._map_clip(ctx, pid, script, scene)
            if done:
                return done
        # Citation (docs/58) : série en « zoom » (défaut), zoom lent sur l'image retenue, rendu par le code ; en « clip »,
        # le modèle vidéo l'anime (suite du step), puis _fit_quote le ralentit pour tenir la durée du texte
        if recipe == QUOTE and quotes.production_options(ctx.db, pid)["motion"] == "zoom":
            return self._quote_zoom(ctx, pid, scene)

        provider = get_video_provider(
            ctx.settings, prod["video_provider"] or load_generation_config(ctx.settings, ctx.db).video_provider, db=ctx.db
        )
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
            end_pos = chain_next(script, pos)  # le plan large suivant de la même vue (lieu insolite : pas un gros plan)
            if scene.clip_mode == "flf" and end_pos is not None:
                nxt = ctx.db.fetch_one(
                    """select local_path from assets where production_id = %s and kind = 'storyboard'
                       and scene_index = %s and selected order by created_at desc limit 1""",
                    (pid, script.scenes[end_pos].index),
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

        # Drame (docs/35) : le modèle vidéo dit la réplique du plan, avec la voix du personnage ; le style est dans l'image.
        # Les personnages sont désignés par ce qui se voit et, à plusieurs, par leur place dans l'image (Gemini la lit) ;
        # une consigne de Luca pour ce plan (Retoucher → Plans : payload « note ») devient une note de réalisation
        style = prod["style_preset"]
        if is_drama(recipe) and image is not None:
            where, note = self._direction(ctx, script, scene, image)
            prompt = clip_prompt(script, pos, video_lang(script), prod["style_preset"], where, note)
            style = CLIP_STYLE.get(prod["style_preset"] or "", "animation_motion")  # prise de vue réelle (docs/59)

        # Texte voulu dans l'image de départ (docs/57 §5) : il ne bouge pas, ne change pas ; rien d'autre ne s'écrit
        it = scene.image_text if image is not None and not continues else None
        if it is not None:
            prompt = f"{prompt.rstrip(' .')}. {motion_clause(it)}"
        text_kw: dict[str, Any] = {"allowed_text": it.text} if it is not None else {}

        extra_negative = video_negative(script, pos, recipe)
        if extra_negative and isinstance(getattr(provider, "negative", None), str):  # n'agit qu'avec CFG > 1 (mélange, 20 passes)
            provider.negative = f"{provider.negative}, {extra_negative}"
        out = clips_dir / f"scene_{idx:02d}.mp4"
        ctx.progress(
            5,
            f"Clip {idx + 1} · {provider.name}"
            + (
                " · continuité"
                if continues
                else " · première + dernière image"
                if end_image
                else " · depuis l'image"
                if image
                else ""
            ),
        )
        # Formats visuels : le clip est regardé par le modèle de vision (personne, appareil de tournage ou objet inventés,
        # worker/keyframe_qc.py) et refait une fois s'il est refusé (docs/15 §10) ; drame : texte écrit par le modèle
        # vidéo (la réplique en sous-titre, 29/09)
        qc = (
            get_vision_llm(ctx.settings, ctx.db)
            if (is_visual(recipe) or is_drama(recipe)) and image is not None and ctx.settings.clip_qc and not ctx.settings.dry_run
            else None
        )
        # le texte voulu est relu même quand le contrôle des clips est coupé : un texte déformé ne part jamais
        text_qc = (qc or self._vision(ctx)) if it is not None and not ctx.settings.dry_run else None
        verdict: KeyframeVerdict | None = None
        text_ok = True
        still = False
        # Gemini en ligne (durée imposée, asynchrone) : verdict noté, jamais de nouvel essai. Le job repart du début après
        # chaque attente (Postpone) : une reprise ici redemanderait une vidéo à chaque passage, sans fin, sur le quota
        retries = 0 if fixed else max(0, ctx.settings.clip_qc_retries, 1 if it is not None else 0)

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
                **text_kw,
            )

        if it is not None and image is not None and text_qc is None and not ctx.settings.dry_run:
            # personne pour relire le texte : pas de clip d'IA qui pourrait le déformer, le plan fixe sur l'image vérifiée
            ctx.log("clip.texte_sans_relecture", level="warn", scene=idx, texte=it.text)
            dur, w, h = still_clip(image, out, scene.duration_s)
            info, still, text_ok = ClipInfo(dur, w, h), True, True
        else:
            for attempt in range(1 + (retries if (qc or text_qc) else 0)):
                info = render()
                if image is None or not (qc or text_qc):
                    break
                verdict = None
                if qc and (is_visual(recipe) or is_drama(recipe)):
                    try:
                        verdict = check_clip(
                            qc,
                            out,
                            image,
                            script,
                            pos,
                            recipe,
                            clips_dir / "qc",
                            system=prompt_text(ctx.db, "clip_qc", CLIP_SYSTEM),
                        )  # onglet Agents du dashboard
                    except Exception as exc:  # noqa: BLE001  le contrôle est un filet, pas une étape bloquante
                        ctx.log("clip.controle_indisponible", level="warn", scene=idx, erreur=str(exc)[:300])
                        if it is None:
                            break
                if it is not None and text_qc is not None:
                    reading = self._read_clip_text(ctx, text_qc, out, clips_dir / "qc", it, idx)
                    text_ok = reading.ok
                    verdict = merge(verdict, reading)
                if verdict is None or verdict.ok:
                    break
                ctx.log("clip.refuse", level="warn", scene=idx, essai=attempt + 1, problemes=verdict.problems)
            if it is not None and image is not None and not text_ok and not ctx.settings.dry_run:
                ctx.log("clip.texte_plan_fixe", level="warn", scene=idx, texte=it.text)
                dur, w, h = still_clip(image, out, scene.duration_s)
                info, still = ClipInfo(dur, w, h), True
        # Drame : ce que dit le clip (Whisper : mots, passages parlés, langue) ; une réplique qui n'est pas dite, ou pas
        # dans la langue de la vidéo, fait refaire le clip (DIALOGUE_RETRIES) ; un plan muet où le modèle invente des
        # paroles aussi (docs/70 §6). Voix des clips (format B) : sous-titres et piste de voix ; voix constantes
        # (format A) : la voix du personnage est calée sur la bouche du clip au montage (worker/lipsync.py, 29/09).
        lang = video_lang(script)
        listen = is_drama(recipe) and not ctx.settings.dry_run
        dialogue = self._dialogue(ctx, out, scene, script) if listen else None
        for retry in range(DIALOGUE_RETRIES):
            if dialogue is None or (line_said(dialogue, lang) if scene.lines else not dialogue.get("invented")):
                break
            ctx.log(
                "clip.replique_absente" if scene.lines else "clip.paroles_inventees",
                level="warn",
                scene=idx,
                essai=retry + 1,
                attendu=dialogue["expected"],
                entendu=dialogue["heard"],
                ressemblance=dialogue["ratio"],
                langue=dialogue.get("lang"),
            )
            info = render()
            if qc and image is not None and verdict is not None:  # le nouvel essai repasse le contrôle (texte écrit…)
                try:
                    verdict = check_clip(
                        qc, out, image, script, pos, recipe, clips_dir / "qc", system=prompt_text(ctx.db, "clip_qc", CLIP_SYSTEM)
                    )
                    if not verdict.ok:
                        ctx.log("clip.refuse", level="warn", scene=idx, essai="réplique", problemes=verdict.problems)
                except Exception as exc:  # noqa: BLE001
                    ctx.log("clip.controle_indisponible", level="warn", scene=idx, erreur=str(exc)[:300])
            dialogue = self._dialogue(ctx, out, scene, script)
        if recipe == QUOTE and not ctx.settings.dry_run:  # citation animée : ralentie pour tenir la durée du texte
            info = self._fit_quote(ctx, out, scene.duration_s, info)
        asset_id = ctx.db.add_asset(
            production_id=pid,
            kind="clip",
            scene_index=idx,
            local_path=str(out),
            duration_s=info.duration_s,
            width=info.width,
            height=info.height,
            meta={
                "provider": provider.name,
                "seed": info.seed,
                "prompt": prompt,
                "image": str(image) if image else None,
                "continues": continues,
                "end_image": str(end_image) if end_image else None,
                **({"qc": verdict.model_dump()} if verdict else {}),
                **({"dialogue": dialogue} if dialogue else {}),
                **({"image_text": it.text, "text_ok": text_ok} if it is not None else {}),
                **({"fallback": "still"} if still else {}),
            },
        )
        return {
            "asset_id": str(asset_id),
            "provider": provider.name,
            "from_image": bool(image),
            "continues": continues,
            "first_last": bool(end_image),
            **({"qc": verdict.model_dump()} if verdict else {}),
            **({"dialogue": {k: dialogue[k] for k in ("expected", "heard", "ratio")}} if dialogue else {}),
        }

    @staticmethod
    def _vision(ctx: Context) -> Any:
        try:
            return get_vision_llm(ctx.settings, ctx.db)
        except Exception as exc:  # noqa: BLE001
            ctx.log("clip.relecteur_indisponible", level="warn", erreur=str(exc)[:300])
            return None

    @staticmethod
    def _read_clip_text(ctx: Context, llm: Any, clip: Path, workdir: Path, it: Any, idx: int) -> KeyframeVerdict:
        """Relecture du texte voulu sur trois images du clip ; une relecture impossible compte comme un échec."""
        try:
            return check_clip_text(llm, clip, workdir, it)
        except Exception as exc:  # noqa: BLE001
            ctx.log("clip.relecture_impossible", level="warn", scene=idx, erreur=str(exc)[:300])
            return KeyframeVerdict(ok=False, problems=["relecture du texte impossible"])

    @staticmethod
    def _direction(ctx: Context, script: ScriptV1, scene: ScriptScene, image: Path) -> tuple[dict[str, str], str]:
        """Place des personnages dans l'image de départ (à plusieurs) et note de réalisation tirée de la consigne de Luca
        (payload « note ») ; rien de tout ça en simulation ou sans modèle de vision."""
        instruction = str(ctx.job.payload.get("note") or "").strip()
        members = shot_members(script, scene)
        if ctx.settings.dry_run or (len(members) < 2 and not instruction):
            return {}, instruction
        llm = get_vision_llm(ctx.settings, ctx.db) or get_llm(ctx.settings, ctx.db)
        where = locate(llm, image, members)
        if where:
            ctx.log("clip.personnages_places", scene=scene.index, places=where)
        note = director_note(llm, script, scene, instruction, image, where) if instruction else ""
        if instruction:
            ctx.log("clip.consigne", scene=scene.index, consigne=instruction, note=note)
        return where, note

    @staticmethod
    def _dialogue(ctx: Context, clip: Path, scene: ScriptScene, script: ScriptV1) -> dict[str, Any] | None:
        """Ce que Whisper entend dans le clip d'un drame (mots horodatés, pour les sous-titres), sa langue et sa
        ressemblance avec la réplique écrite ; un plan muet est écouté sans langue imposée, et `invented` donne les mots
        qu'il ne devrait pas dire. None si la transcription n'est pas possible (environnement d'évaluation absent,
        échec) : le montage répartit alors la réplique sur le plan."""
        try:
            heard = transcribe(ctx.settings, [clip], video_lang(script) if scene.lines else None)
        except Exception as exc:  # noqa: BLE001  la transcription est un filet, jamais une étape bloquante
            ctx.log("clip.transcription_indisponible", level="warn", scene=scene.index, erreur=str(exc)[:300])
            return None
        if not heard:
            ctx.log(
                "clip.transcription_absente",
                level="warn",
                scene=scene.index,
                raison="environnement tts/eval (Whisper) non installé : install_tts.ps1 -Engine eval",
            )
            return None
        expected = line_text(scene)
        out = {
            "expected": expected,
            "heard": heard[0]["text"],
            "words": heard[0]["words"],
            "speech": heard[0].get("speech") or [],
            "ratio": heard_ratio(expected, heard[0]["text"]) if expected else 1.0,
            "lang": heard[0].get("lang"),
            "lang_p": heard[0].get("lang_p"),
        }
        if not expected:
            out["invented"] = invented_words(heard[0]["words"])
        return out

    @staticmethod
    def _quote_zoom(ctx: Context, pid: Any, scene: ScriptScene) -> dict[str, Any]:
        """Clip d'une citation en « zoom » (worker/quotes.py) : l'image retenue, zoom ou glissement très lent rendu image
        par image sur le processeur, sans modèle vidéo (≈ 10 s de calcul)."""
        row = ctx.db.fetch_one(
            """select local_path from assets where production_id = %s and kind = 'storyboard'
               and scene_index = %s and selected order by created_at desc limit 1""",
            (pid, scene.index),
        )
        if not row:
            raise RuntimeError("citation : aucune image retenue au storyboard")
        image = Path(row["local_path"])
        out = ctx.production_dir(pid) / "clips" / f"scene_{scene.index:02d}.mp4"
        move = quotes.move_for(str(pid))
        ctx.progress(5, f"Citation · zoom lent ({move})")
        if ctx.settings.dry_run:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"")
            duration = scene.duration_s
        else:
            duration = quotes.render_still_clip(image, out, scene.duration_s, move=move)
        asset_id = ctx.db.add_asset(
            production_id=pid,
            kind="clip",
            scene_index=scene.index,
            local_path=str(out),
            duration_s=duration,
            width=quotes.W,
            height=quotes.H,
            meta={"provider": "quote_zoom", "move": move, "image": str(image), "prompt": f"Zoom lent ({move})"},
        )
        return {"asset_id": str(asset_id), "provider": "quote_zoom", "from_image": True, "continues": False, "first_last": False}

    @staticmethod
    def _fit_quote(ctx: Context, out: Path, duration_s: float, info: ClipInfo) -> ClipInfo:
        """Citation animée : le clip du modèle vidéo (≈ 5 s) ralenti, au besoin en aller-retour, jusqu'à la durée du texte."""
        cmd = quotes.fit_command(out, out.with_name(f"{out.stem}_fit.mp4"), duration_s, float(info.duration_s or 0))
        if not cmd:
            return info
        fitted = Path(cmd[-1])
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:  # le montage tiendra la dernière image : moins beau, pas bloquant
            ctx.log("clip.citation_ralenti_rate", level="warn", erreur=(exc.stderr or b"")[-300:].decode(errors="replace"))
            return info
        fitted.replace(out)
        ctx.log("clip.citation_ralentie", natif=info.duration_s, duree=duration_s)
        return ClipInfo(duration_s=duration_s, width=info.width, height=info.height, seed=info.seed)

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
                duration = maps.render_clip(
                    plan,
                    out,
                    scene.duration_s,
                    cache_root=ctx.settings.data_dir / "maps",
                    user_agent=ctx.settings.effective_wikipedia_user_agent,
                    font_path=maps.font_for(ctx.settings),
                    lang=lang,
                )
        except Exception as exc:  # noqa: BLE001
            ctx.log("clip.carte_indisponible", level="warn", scene=scene.index, lieu=scene.map.place, erreur=str(exc)[:300])
            return None
        asset_id = ctx.db.add_asset(
            production_id=pid,
            kind="clip",
            scene_index=scene.index,
            local_path=str(out),
            duration_s=duration,
            width=maps.W,
            height=maps.H,
            meta={"provider": "map", "prompt": f"Carte : {scene.map.place}", "map": scene.map.model_dump()},
        )
        return {"asset_id": str(asset_id), "provider": "map", "from_image": False, "continues": False, "first_last": False}
