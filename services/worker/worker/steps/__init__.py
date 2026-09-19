"""Registre des steps : un par type de job. `lane` = "gpu" (sérialisé) ou "io" (parallèle)."""

from __future__ import annotations

from .assemble import AssembleStep
from .base import Context, Step
from .generate_clip import GenerateClipStep
from .ideate import IdeateStep
from .improve import ImproveStep
from .qa import QAStep
from .script import ScriptStep
from .sync import SyncCommentsStep, SyncMetricsStep, SyncRetentionStep
from .tts import TTSStep
from .upload import UploadStep

REGISTRY: dict[str, Step] = {
    s.type: s
    for s in (
        IdeateStep(),
        ScriptStep(),
        GenerateClipStep(),
        TTSStep(),
        AssembleStep(),
        QAStep(),
        UploadStep(),
        SyncMetricsStep(),
        SyncRetentionStep(),
        SyncCommentsStep(),
        ImproveStep(),
    )
}

__all__ = ["REGISTRY", "Context", "Step"]
