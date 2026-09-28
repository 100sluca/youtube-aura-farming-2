from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Literal
from uuid import UUID

from .. import cancel
from ..config import Settings
from ..db import Db
from ..models import Job


@dataclass
class Context:
    """Ce qu'un step reçoit : le job, la base, la config, et des raccourcis progression/journal."""

    job: Job
    db: Db
    settings: Settings

    def progress(self, pct: int, label: str | None = None) -> None:
        cancel.check()  # arrêt demandé depuis le dashboard : le step s'arrête ici (worker/cancel.py)
        self.db.heartbeat(self.job.id, max(0, min(100, pct)), label)

    def log(self, message: str, level: str = "info", **data: Any) -> None:
        self.db.log(self.job.id, level, message, data or None)

    def enqueue(self, type_: str, **kwargs: Any) -> UUID:
        return self.db.enqueue(type_, **kwargs)

    def production_dir(self, production_id: UUID) -> Path:
        p = self.settings.data_dir / "productions" / str(production_id)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def video_dir(self, video_id: UUID) -> Path:
        p = self.settings.data_dir / "videos" / str(video_id)
        p.mkdir(parents=True, exist_ok=True)
        return p


class Step:
    """Classe de base. Un step est idempotent : il vérifie sa sortie avant de recalculer."""

    type: ClassVar[str]
    # gpu : un job à la fois ; io : plusieurs en parallèle ; preview : aperçus de quelques secondes demandés depuis le
    # dashboard, pris tout de suite par leur propre fil, même pendant un long job GPU (worker/main.py : preview_lane)
    lane: ClassVar[Literal["gpu", "io", "preview"]] = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        raise NotImplementedError
