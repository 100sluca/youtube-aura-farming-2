"""Génération d'un clip par scène (ComfyUI ou fournisseur cloud). Voie GPU."""

from __future__ import annotations

from typing import Any

from ..models import ScriptV1
from ..providers.video import get_video_provider
from .base import Context, Step


class GenerateClipStep(Step):
    type = "generate_clip"
    lane = "gpu"

    def run(self, ctx: Context) -> dict[str, Any]:
        pid = ctx.job.production_id
        idx = int(ctx.job.payload["scene_index"])
        prod = ctx.db.fetch_one("select script, style_preset, video_provider from productions where id = %s", (pid,))
        assert prod and prod["script"], "script manquant"
        scene = ScriptV1.model_validate(prod["script"]).scenes[idx]

        existing = ctx.db.fetch_one(
            "select id, local_path from assets where production_id = %s and kind = 'clip' and scene_index = %s",
            (pid, idx),
        )
        if existing:  # idempotence
            return {"asset_id": str(existing["id"]), "skipped": True}

        out = ctx.production_dir(pid) / "clips" / f"scene_{idx:02d}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        provider = get_video_provider(ctx.settings, prod["video_provider"])
        ctx.progress(5, f"Clip {idx + 1} · {provider.name}")
        info = provider.generate(
            prompt=scene.visual_prompt,
            style_preset=prod["style_preset"],
            duration_s=scene.duration_s,
            out_path=out,
            on_progress=lambda p: ctx.progress(5 + int(p * 0.9), f"Clip {idx + 1} · {p} %"),
            dry_run=ctx.settings.dry_run,
        )
        asset_id = ctx.db.add_asset(
            production_id=pid,
            kind="clip",
            scene_index=idx,
            local_path=str(out),
            duration_s=info.duration_s,
            width=info.width,
            height=info.height,
            meta={"provider": provider.name, "seed": info.seed, "prompt": scene.visual_prompt},
        )
        return {"asset_id": str(asset_id), "provider": provider.name}
