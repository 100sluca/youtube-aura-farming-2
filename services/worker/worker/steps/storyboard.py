"""Storyboard : une ou plusieurs images 9:16 par scène, avant toute animation (route image → vidéo).

Première porte humaine (docs/09 §2.1) : relire six images coûte quelques secondes, alors qu'une vidéo
refusée coûte une nuit de calcul. Le step génère `storyboard_candidates` images par scène (la première
est retenue par défaut), fabrique une planche de contact, puis :
- STORYBOARD_REVIEW=true : met la production en `storyboard_review` et alerte ; `yt2 storyboard …`
  permet de choisir une autre image, de refaire une scène, puis d'approuver ;
- STORYBOARD_REVIEW=false : met directement en file le rendu (clips, voix, montage).
Payload optionnel : {"scenes": [2, 4]} pour ne refaire que certaines scènes (« Refaire » dans Création) ; avec
"reinvent": true (« Réinventer », remarque de Luca dans "note"), le scénariste réécrit d'abord ces scènes (plan,
narration, texte à l'écran : worker/reinvent.py, docs/27) et leurs anciennes images quittent la planche. L'image
retenue d'une scène ne change qu'une fois la nouvelle faite : une panne de ComfyUI ne laisse pas la scène sans image.
"reason" (facultatif) : pourquoi ces scènes sont refaites quand ce n'est pas Luca qui l'a demandé (affiché dans
Création). « Arrêter » (Création, docs/16 §3) passe le job en `cancelled` : les images retenues à ce moment restent.

Formats visuels (worker/recipes.py, docs/15) : l'image d'une scène qui a un `edit_prompt` est une RETOUCHE de
l'image retenue d'une autre scène (recipes.edit_source ; chantier : le bâtiment fini est généré en premier, chaque
étape antérieure retouche la suivante). Les images sont donc faites dans l'ordre des retouches
(recipes.keyframe_order), une seule par scène : chaque image clé est contrôlée par un modèle de vision
(worker/keyframe_qc.py) et refaite si elle est refusée (KEYFRAME_QC_RETRIES fois au plus). Si toutes les images
passent le contrôle, le rendu part sans attendre la revue humaine (STORYBOARD_AUTOPASS) ; sinon la production
attend la revue avec la liste des problèmes. Refaire une image refait aussi les retouches qui en dérivent.

Pilote automatique (productions.autopilot, worker/autopilot.py, docs/46) : personne ne valide. Une image par plan, jugée
par le modèle de vision (récits et drames : avec l'image du plan précédent, pour la continuité) et refaite tant qu'elle
est refusée, AUTOPILOT_TRIES essais au plus ; après le dernier, tant pis : le rendu part avec le dernier essai.
"""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from .. import cancel
from ..dag import continuity_plan, enqueue_render_dag
from ..drama import CHARACTERS_MAX, is_drama, sheet_prompt, slug
from ..drama import scene_prompt as drama_scene_prompt
from ..keyframe_qc import QC_SYSTEM, KeyframeVerdict, check_continuity, check_keyframe
from ..media import contact_sheet
from ..models import ScriptV1
from ..prompts import prompt_text
from ..providers.llm import get_llm, get_vision_llm
from ..providers.video import ComfyImage, ComfyImageEdit
from ..recipes import (
    edit_dependents,
    edit_instruction,
    edit_source,
    image_prompt,
    is_visual,
    keyframe_order,
    recipe_for_production,
)
from ..reinvent import reinvent_scene, shot_number
from ..settings_store import load_generation_config
from ..sources.wikipedia import source_dossier
from .base import Context, Step

AUTOPILOT_TRIES = 4  # essais par image en pilote automatique (demande de Luca, 30/09 : 4 au plus, pas de boucle sans fin)


class StoryboardStep(Step):
    type = "storyboard"
    lane = "gpu"

    def run(self, ctx: Context) -> dict[str, Any]:
        pid = ctx.job.production_id
        assert pid, "storyboard : production_id requis"
        prod = ctx.db.fetch_one(
            """select p.script, p.style_preset, p.image_workflow, p.autopilot, c.title from productions p
               left join concepts c on c.id = p.concept_id where p.id = %s""",
            (pid,),
        )
        assert prod and prod["script"], "script manquant"
        script = ScriptV1.model_validate(prod["script"])
        gen = load_generation_config(ctx.settings, ctx.db)
        only = {int(i) for i in ctx.job.payload.get("scenes", [])}
        sdir = ctx.production_dir(pid) / "storyboard"
        sdir.mkdir(parents=True, exist_ok=True)
        # Le modèle d'image est celui de la production (figé au script), sinon celui des réglages
        workflow = prod["image_workflow"] or gen.image_workflow
        ctx.db.execute("update productions set image_workflow = coalesce(image_workflow, %s) where id = %s", (workflow, pid))
        image = ComfyImage(ctx.settings, workflow)
        recipe = recipe_for_production(ctx.db, pid)
        visual = is_visual(recipe)
        autopilot = bool(prod.get("autopilot"))
        # « Réinventer » : le scénariste réécrit d'abord les scènes demandées ; relancé après une panne des images, le job
        # ne les réécrit pas une seconde fois (payload « reinvented » au lieu de « reinvent »)
        reinvented: list[dict[str, Any]] = list(ctx.job.payload.get("reinvented") or [])
        if only and ctx.job.payload.get("reinvent"):
            script, reinvented = self._reinvent(ctx, pid, script, recipe, only)
        # Drame (docs/35) : d'abord la fiche de chaque personnage (refaite à la demande : payload « characters », avec les
        # plans où il apparaît), puis chaque plan avec les fiches de ses personnages en images de référence
        sheets: dict[str, Path] = {}
        if is_drama(recipe):
            redo = {slug(str(k)) for k in ctx.job.payload.get("characters") or []}
            if redo:
                only = only | {s.index for s in script.scenes if set(s.characters) & redo}
            sheets = self._sheets(ctx, pid, script, image, prod["style_preset"], sdir, redo)
        sources = [edit_source(script, pos) for pos in range(len(script.scenes))]
        editor = ComfyImageEdit(ctx.settings) if any(s is not None for s in sources) else None
        if only and editor:  # une image clé refaite invalide les retouches qui en dépendent : on les refait aussi
            only = edit_dependents(script, only)
        # Formats visuels : une image par scène, contrôlée et refaite au besoin (au lieu de plusieurs candidates)
        # Pilote automatique : pareil pour les récits et les drames, jugés sur leur continuité d'un plan à l'autre
        checked_kind = visual or autopilot
        n = 1 if checked_kind else max(1, int(ctx.job.payload.get("candidates", gen.storyboard_candidates)))
        qc = (
            get_vision_llm(ctx.settings, ctx.db)
            if (checked_kind and ctx.settings.keyframe_qc and not ctx.settings.dry_run)
            else None
        )
        tries = (AUTOPILOT_TRIES if autopilot else 1 + max(0, ctx.settings.keyframe_qc_retries)) if qc else 1
        # Une scène qui prolonge la précédente part de la dernière image de son clip : pas d'image à valider
        # (formats visuels : seuls les passages d'une visite prolongent le clip précédent, recipes._normalize_tour)
        mode = "script" if visual else ctx.settings.clip_continuity
        chained = continuity_plan(script, mode, ctx.settings.continuity_max_chain)
        order = keyframe_order(script) if visual else list(range(len(script.scenes)))
        verdicts: dict[int, KeyframeVerdict | None] = {}
        made = 0
        for step_no, pos in enumerate(order):
            scene = script.scenes[pos]
            if only and scene.index not in only:
                continue
            if chained[pos] and not only:
                continue
            has = ctx.db.fetch_one(
                "select count(*) as n from assets where production_id = %s and kind = 'storyboard' and scene_index = %s",
                (pid, scene.index),
            )
            if has and has["n"] and not only:  # idempotence : scène déjà illustrée
                # arrêt du worker entre l'enregistrement de l'image et son choix : la dernière image devient la retenue
                # (sans ça, « Valider » refuserait la scène, docs/42)
                ctx.db.execute(
                    """update assets set selected = true where id = (
                         select id from assets where production_id = %s and kind = 'storyboard' and scene_index = %s
                         order by created_at desc limit 1)
                       and not exists (select 1 from assets where production_id = %s and kind = 'storyboard'
                         and scene_index = %s and selected)""",
                    (pid, scene.index, pid, scene.index),
                )
                continue
            src = sources[pos] if editor else None
            source = self._selected(ctx, pid, script.scenes[src].index) if src is not None else None
            if src is not None and not source:
                raise RuntimeError(
                    f"scène {scene.index} : retouche demandée mais la scène {script.scenes[src].index} n'a pas d'image retenue"
                )
            shot = shot_number(script, scene.index)  # le numéro que Luca voit dans Création
            # Scène carte (récits) : rendue par le code, une seule image ; en cas d'échec, l'image d'IA habituelle
            if scene.is_map and source is None:
                ctx.progress(5 + int(85 * step_no / len(order)), f"Scène {shot} · carte")
                if self._map_image(ctx, pid, script, scene, sdir):
                    made += 1
                    continue
            for k in range(n):
                chosen: Any = None
                for attempt in range(tries):
                    label = f"Scène {shot} · image {k + 1}/{n}" + (f" · essai {attempt + 1}" if attempt else "")
                    ctx.progress(5 + int(85 * step_no / len(order)), label)
                    seed = random.randint(0, 2**31)
                    t0 = time.monotonic()  # temps de l'image, contrôle compris (fiche de la vidéo, docs/45)
                    out = sdir / f"scene_{scene.index:02d}_{seed}.png"
                    if source and editor:  # retouche de l'image clé source, même cadre
                        instruction = edit_instruction(script, pos, recipe)
                        editor.edit(
                            image_path=source,
                            instruction=instruction,
                            description=image_prompt(script, pos, recipe),
                            style_preset=prod["style_preset"],
                            out_path=out,
                            seed=seed,
                            dry_run=ctx.settings.dry_run,
                        )
                        if editor.fallback_reason:
                            ctx.log(
                                "storyboard.retouche_repli",
                                level="warn",
                                scene=scene.index,
                                provider=editor.name,
                                raison=editor.fallback_reason,
                            )
                        meta = {
                            "candidate": k,
                            "seed": seed,
                            "prompt": instruction,
                            "provider": editor.name,
                            "edited_from": str(source),
                        }
                        size = (editor.width, editor.height)
                    elif sheets:  # drame : les fiches des personnages à l'image, citées <image1>… (docs/31 §8)
                        keys = [c for c in scene.characters if c in sheets][:CHARACTERS_MAX] if image.references else []
                        prompt = drama_scene_prompt(script, pos, keys)
                        image.generate(
                            prompt=prompt,
                            style_preset=prod["style_preset"],
                            out_path=out,
                            seed=seed,
                            dry_run=ctx.settings.dry_run,
                            refs=[sheets[c] for c in keys],
                        )
                        meta = {"candidate": k, "seed": seed, "prompt": prompt, "provider": image.name, "refs": keys}
                        size = (image.width, image.height)
                    else:
                        prompt = image_prompt(script, pos, recipe) if visual else scene.visual_prompt
                        image.generate(
                            prompt=prompt,
                            style_preset=prod["style_preset"],
                            out_path=out,
                            seed=seed,
                            dry_run=ctx.settings.dry_run,
                        )
                        meta = {"candidate": k, "seed": seed, "prompt": prompt, "provider": image.name}
                        size = (image.width, image.height)
                    if not qc:
                        verdict = None
                    elif visual:
                        verdict = self._check(ctx, qc, out, script, pos, recipe, source)
                    else:
                        verdict = self._check_continuity(ctx, qc, out, script, pos, pid)
                    if verdict is not None:
                        meta["qc"] = verdict.model_dump()
                    meta["gen_s"] = round(time.monotonic() - t0, 1)
                    asset = ctx.db.add_asset(
                        production_id=pid,
                        kind="storyboard",
                        scene_index=scene.index,
                        local_path=str(out),
                        width=size[0],
                        height=size[1],
                        selected=False,
                        meta=meta,
                    )
                    made += 1
                    chosen = asset
                    verdicts[scene.index] = verdict
                    if verdict is None or verdict.ok:
                        break
                    ctx.log(
                        "storyboard.image_refusee", level="warn", scene=scene.index, essai=attempt + 1, problemes=verdict.problems
                    )
                if k == 0 and chosen is not None:  # retenue : l'image acceptée, sinon le dernier essai
                    self._select(ctx, pid, scene.index, chosen, stoppable=bool(only))

        if editor and not ctx.settings.dry_run:  # les clips (Wan 14B) partiront d'une mémoire vide
            editor.client.free()
        sheet = self._sheet(ctx, pid, script, sdir)
        chained_scenes = [s.index + 1 for s, c in zip(script.scenes, chained, strict=True) if c]
        failed = {i: v.problems for i, v in verdicts.items() if v is not None and not v.ok}
        checked = bool(qc) and bool(verdicts) and all(v is not None for v in verdicts.values())
        # une scène refaite ou réinventée pendant la revue revient toujours à Luca, même si son image passe le contrôle
        autopass = not only and (autopilot or (visual and ctx.settings.storyboard_autopass and checked and not failed))
        qc_info = {"checked": checked, "refused": failed} if qc else {"checked": False}
        redone = {"reinvented": [{"scene": e["scene"], "idea": e.get("idea", "")} for e in reinvented]} if reinvented else {}
        if ctx.settings.storyboard_review and not autopass:
            ctx.db.set_status("productions", pid, "storyboard_review")
            problems = "".join(f"\nScène {i + 1} : {' ; '.join(p)}" for i, p in sorted(failed.items()))
            ideas = "".join(f"Scène {e.get('shot', e['scene'])} réinventée : {e.get('idea') or '—'}\n" for e in reinvented)
            ctx.db.alert(
                "warning",
                f"Storyboard à valider : {prod['title'] or pid}",
                ideas
                + (f"Contrôle automatique : images refusées après {tries} essais{problems}\n" if failed else "")
                + f"Planche : {sheet}\nChoisir : yt2 storyboard pick {pid} <scène>:<image>\n"
                f'Refaire : yt2 storyboard redo {pid} <scène>\nRéinventer : yt2 storyboard reinvent {pid} <scène> ["remarque"]\n'
                f"Valider : yt2 storyboard approve {pid}"
                + (
                    f"\nScènes en continuité (sans image, partent du clip précédent) : {chained_scenes}" if chained_scenes else ""
                ),
                production_id=pid,
            )
            return {
                "images": made,
                "sheet": str(sheet) if sheet else None,
                "review": True,
                "chained": chained_scenes,
                "qc": qc_info,
                **redone,
            }
        if autopilot and not only:
            ctx.log("storyboard.pilote_automatique", images=made, refusees_gardees=sorted(failed))
        elif autopass:
            ctx.log("storyboard.controle_ok", images=made, scenes=len(verdicts))
        return {
            "images": made,
            "sheet": str(sheet) if sheet else None,
            "review": False,
            "chained": chained_scenes,
            "qc": qc_info,
            **redone,
            **enqueue_render_dag(ctx.db, pid, ctx.settings.clip_continuity, ctx.settings.continuity_max_chain),
        }

    @staticmethod
    def _reinvent(ctx: Context, pid: Any, script: ScriptV1, recipe: str, only: set[int]) -> tuple[ScriptV1, list[dict[str, Any]]]:
        """« Réinventer » (Création, docs/27) : le scénariste réécrit chaque scène demandée (worker/reinvent.py) ; le script
        est enregistré et les anciennes images de ces scènes quittent la planche (elles illustraient une scène qui
        n'existe plus ; leurs fichiers partent avec la production). Le job garde ce qu'il a réécrit (payload
        « reinvented ») : relancé après une panne des images, il ne réécrit pas une seconde fois, et la prochaine
        réinvention de la scène évite ces versions."""
        llm = get_llm(ctx.settings, ctx.db, writer=True)
        note = str(ctx.job.payload.get("note") or "")

        def dossier(sources: list[dict[str, Any]]) -> str:  # pages sources des séries documentaires (cache du script)
            try:
                return source_dossier(
                    sources, ctx.settings.data_dir / "sources" / "wikipedia", ctx.settings.effective_wikipedia_user_agent
                )
            except Exception as exc:  # noqa: BLE001
                ctx.log("storyboard.dossier_indisponible", level="warn", erreur=str(exc)[:300])
                return ""

        entries: list[dict[str, Any]] = []
        for index in sorted(only):
            ctx.progress(2, f"Scène {shot_number(script, index)} · le scénariste réinvente le plan")
            script, entry = reinvent_scene(ctx.db, llm, pid, script, recipe, index, note, dossier=dossier)
            entries.append(entry)
            ctx.log("storyboard.scene_reinventee", scene=entry["shot"], idee=entry["idea"], problemes=entry["issues"])
        ctx.log("storyboard.reinvention_modeles", modeles=list(getattr(llm, "used", [])))
        ctx.db.execute("update productions set script = %s where id = %s", (Jsonb(script.model_dump()), pid))
        for v in ctx.db.fetch_all("select id, lang from videos where production_id = %s and archived_at is null", (pid,)):
            text = " ".join(s.narration.get(v["lang"], "") for s in script.scenes).strip() or None  # type: ignore[call-overload]
            ctx.db.execute("update videos set narration_text = %s where id = %s", (text, v["id"]))
        ctx.db.execute(
            "delete from assets where production_id = %s and kind = 'storyboard' and scene_index = any(%s)", (pid, sorted(only))
        )
        ctx.db.execute(
            "update jobs set payload = (payload - 'reinvent') || jsonb_build_object('reinvented', %s::jsonb) where id = %s",
            (Jsonb(entries), ctx.job.id),
        )
        return script, entries

    @staticmethod
    def _sheets(
        ctx: Context, pid: Any, script: ScriptV1, image: ComfyImage, style_preset: str | None, sdir: Path, redo: set[str]
    ) -> dict[str, Path]:
        """Fiche de chaque personnage d'un drame (docs/35) : lui seul, en pied, sur fond neutre (assets kind
        'character', meta.key). Faite une fois, gardée pour les « Refaire » de scène ; refaite pour les clés de `redo`.
        Renvoie la fiche retenue de chaque personnage."""
        out: dict[str, Path] = {}
        for k, member in enumerate(script.cast):
            row = ctx.db.fetch_one(
                """select local_path from assets where production_id = %s and kind = 'character' and meta->>'key' = %s
                   and selected order by created_at desc limit 1""",
                (pid, member.key),
            )
            if row and member.key not in redo and (ctx.settings.dry_run or Path(row["local_path"]).exists()):
                out[member.key] = Path(row["local_path"])
                continue
            ctx.progress(2 + int(3 * k / max(1, len(script.cast))), f"Fiche de {member.name}")
            seed = random.randint(0, 2**31)
            path = sdir / f"character_{member.key}_{seed}.png"
            prompt = sheet_prompt(member)
            image.generate(prompt=prompt, style_preset=style_preset, out_path=path, seed=seed, dry_run=ctx.settings.dry_run)
            asset = ctx.db.add_asset(
                production_id=pid,
                kind="character",
                local_path=str(path),
                width=image.width,
                height=image.height,
                selected=False,
                meta={"key": member.key, "name": member.name, "seed": seed, "prompt": prompt, "provider": image.name},
            )
            if member.key not in redo:
                ctx.db.execute(
                    "update assets set selected = (id = %s) where production_id = %s and kind = 'character' and meta->>'key' = %s",
                    (asset, pid, member.key),
                )
            elif not ctx.db.execute(  # fiche refaite pendant la revue : pas si « Arrêter » a été cliqué entre-temps
                """update assets set selected = (id = %s) where production_id = %s and kind = 'character' and meta->>'key' = %s
                   and exists (select 1 from jobs where id = %s and status = 'running')""",
                (asset, pid, member.key, ctx.job.id),
            ):
                raise cancel.JobCancelled("Refaire arrêté depuis Création : la fiche retenue reste")
            out[member.key] = path
        return out

    @staticmethod
    def _select(ctx: Context, pid: Any, scene_index: int, asset_id: Any, stoppable: bool = False) -> None:
        """L'image retenue de la scène, et elle seule. `stoppable` (Refaire pendant la revue) : seulement si le job n'a pas
        été arrêté depuis Création (« Arrêter », docs/16 §3) ; sinon les images affichées restent et le job s'arrête ici,
        sans attendre le prochain point de contrôle (le statut n'est relu que toutes les 5 s)."""
        if not stoppable:
            ctx.db.execute(
                "update assets set selected = (id = %s) where production_id = %s and kind = 'storyboard' and scene_index = %s",
                (asset_id, pid, scene_index),
            )
            return
        if not ctx.db.execute(
            """update assets set selected = (id = %s) where production_id = %s and kind = 'storyboard' and scene_index = %s
               and exists (select 1 from jobs where id = %s and status = 'running')""",
            (asset_id, pid, scene_index, ctx.job.id),
        ):
            raise cancel.JobCancelled("Refaire arrêté depuis Création : les images retenues restent")

    @staticmethod
    def _check(
        ctx: Context, qc: Any, out: Path, script: ScriptV1, pos: int, recipe: str, source: Path | None
    ) -> KeyframeVerdict | None:
        """Verdict du contrôle ; None si le modèle de vision n'a pas pu répondre (la revue humaine reste alors due).
        Prompt du contrôleur : version active de la clé keyframe_qc (onglet Agents du dashboard, worker/prompts.py)."""
        try:
            return check_keyframe(qc, out, script, pos, recipe, source, system=prompt_text(ctx.db, "keyframe_qc", QC_SYSTEM))
        except Exception as exc:  # noqa: BLE001
            ctx.log("storyboard.controle_indisponible", level="warn", scene=script.scenes[pos].index, erreur=str(exc)[:300])
            return None

    @staticmethod
    def _check_continuity(ctx: Context, qc: Any, out: Path, script: ScriptV1, pos: int, pid: Any) -> KeyframeVerdict | None:
        """Récit ou drame en pilote automatique : l'image jugée avec l'image retenue du dernier plan illustré avant elle."""
        previous, previous_pos = None, None
        for before in range(pos - 1, -1, -1):
            previous = StoryboardStep._selected(ctx, pid, script.scenes[before].index)
            if previous is not None:
                previous_pos = before
                break
        try:
            return check_continuity(
                qc,
                out,
                previous,
                script,
                pos,
                system=prompt_text(ctx.db, "keyframe_qc", QC_SYSTEM),
                previous_pos=previous_pos,
            )
        except Exception as exc:  # noqa: BLE001
            ctx.log("storyboard.controle_indisponible", level="warn", scene=script.scenes[pos].index, erreur=str(exc)[:300])
            return None

    @staticmethod
    def _map_image(ctx: Context, pid: Any, script: ScriptV1, scene: Any, sdir: Path) -> bool:
        """Image de la scène carte (worker/maps.py, docs/24) : la fin de la scène, tout tracé. False si la carte ne peut pas
        se faire (lieu introuvable, réseau) : la scène passe alors par l'image d'IA de son visual_prompt."""
        from .. import maps  # numpy (extra « tts ») : chargé pour les seules scènes carte

        out = sdir / f"scene_{scene.index:02d}_carte.png"
        lang = next(iter(script.metadata), "fr")
        try:
            if ctx.settings.dry_run:
                out.write_bytes(b"")
            else:
                plan = maps.scene_plan(ctx.settings, scene.map, lang)
                maps.render_still(
                    plan,
                    out,
                    cache_root=ctx.settings.data_dir / "maps",
                    user_agent=ctx.settings.effective_wikipedia_user_agent,
                    font_path=maps.font_for(ctx.settings),
                    lang=lang,
                    duration_s=scene.duration_s,
                )
        except Exception as exc:  # noqa: BLE001
            ctx.log("storyboard.carte_indisponible", level="warn", scene=scene.index, lieu=scene.map.place, erreur=str(exc)[:300])
            return False
        asset = ctx.db.add_asset(
            production_id=pid,
            kind="storyboard",
            scene_index=scene.index,
            local_path=str(out),
            width=maps.W,
            height=maps.H,
            selected=False,
            meta={"candidate": 0, "provider": "map", "prompt": f"Carte : {scene.map.place}", "map": scene.map.model_dump()},
        )
        StoryboardStep._select(ctx, pid, scene.index, asset)
        return True

    @staticmethod
    def _selected(ctx: Context, pid: Any, scene_index: int) -> Path | None:
        row = ctx.db.fetch_one(
            """select local_path from assets where production_id = %s and kind = 'storyboard' and scene_index = %s
               and selected order by created_at desc limit 1""",
            (pid, scene_index),
        )
        return Path(row["local_path"]) if row else None

    @staticmethod
    def _sheet(ctx: Context, pid: Any, script: ScriptV1, sdir: Path) -> Path | None:
        if ctx.settings.dry_run:
            return None
        return build_sheet(ctx.db, pid, script, sdir / "planche.png")


def edit_chain_closure(script: ScriptV1, only: set[int]) -> set[int]:
    """Scènes à refaire quand on refait `only` : chaque retouche dépend de l'image qu'elle retouche, donc refaire une
    image oblige à refaire celles qui en dérivent (recipes.edit_dependents ; le CLI s'en sert aussi)."""
    return edit_dependents(script, only)


def build_sheet(db: Any, pid: Any, script: ScriptV1, out: Path) -> Path | None:
    rows, selected = [], []
    for scene in script.scenes:
        assets = db.fetch_all(
            """select local_path, selected from assets where production_id = %s and kind = 'storyboard'
               and scene_index = %s order by created_at""",
            (pid, scene.index),
        )
        paths = [Path(a["local_path"]) for a in assets if Path(a["local_path"]).exists()]
        rows.append(paths)
        sel = [i for i, a in enumerate(a for a in assets if Path(a["local_path"]).exists()) if a["selected"]]
        selected.append(sel[0] if sel else None)
    if not any(rows):
        return None
    return contact_sheet(rows, selected, out)
