"""Narration TTS (Kokoro par défaut) pour une vidéo (format A)."""

from __future__ import annotations

from typing import Any

from ..providers.tts import get_tts
from .base import Context, Step


class TTSStep(Step):
    type = "tts"
    lane = "io"  # Kokoro tourne sur CPU ; passer en "gpu" si un modèle GPU est utilisé

    def run(self, ctx: Context) -> dict[str, Any]:
        vid = ctx.job.video_id
        v = ctx.db.fetch_one("select lang, narration_text from videos where id = %s", (vid,))
        assert v and v["narration_text"], "narration_text manquant"
        out = ctx.video_dir(vid) / "narration.wav"
        if out.exists():
            return {"path": str(out), "skipped": True}
        tts = get_tts(ctx.settings)
        ctx.progress(10, f"TTS {v['lang']} · {tts.name}")
        info = tts.synthesize(v["narration_text"], lang=v["lang"], out_path=out, dry_run=ctx.settings.dry_run)
        asset_id = ctx.db.add_asset(
            video_id=vid,
            kind="narration",
            local_path=str(out),
            duration_s=info.duration_s,
            meta={"provider": tts.name, "voice": info.voice},
        )
        ctx.db.execute("update videos set tts_provider = %s, tts_voice = %s where id = %s", (tts.name, info.voice, vid))
        return {"asset_id": str(asset_id), "duration_s": info.duration_s}
