"""Upload YouTube (résumable) en private + publishAt, puis statut scheduled."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..youtube.client import YouTubeClient
from .base import Context, Step


class UploadStep(Step):
    type = "upload"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        vid = ctx.job.video_id
        v = ctx.db.fetch_one(
            """select v.*, a.local_path from videos v left join assets a on a.id = v.final_asset_id
               where v.id = %s""",
            (vid,),
        )
        assert v, "vidéo introuvable"
        if v["youtube_video_id"]:  # idempotence stricte : jamais deux uploads
            return {"youtube_video_id": v["youtube_video_id"], "skipped": True}
        assert v["status"] in ("ready", "uploading"), f"statut {v['status']} : upload refusé"
        assert v["scheduled_at"], "scheduled_at manquant"
        ctx.db.set_status("videos", vid, "uploading")

        if ctx.settings.dry_run:
            yt_id = f"dry_{uuid4().hex[:11]}"
        else:
            yt = YouTubeClient.for_channel(ctx.settings, ctx.db, v["channel_id"])
            yt_id = yt.upload(
                path=v["local_path"],
                title=v["title"] or "Short",
                description=v["description"] or "",
                tags=v["tags"] or [],
                publish_at=v["scheduled_at"],
                lang=v["lang"],
                on_progress=lambda p: ctx.progress(int(p * 100), f"Upload {int(p * 100)} %"),
            )
        ctx.db.execute(
            """update videos set youtube_video_id = %s, youtube_publish_at = scheduled_at, status = 'scheduled'
               where id = %s""",
            (yt_id, vid),
        )
        ctx.db.record_quota(v["channel_id"], "videos.insert", 1600)
        return {"youtube_video_id": yt_id}
