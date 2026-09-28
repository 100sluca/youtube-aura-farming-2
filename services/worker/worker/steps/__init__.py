"""Registre des steps : un par type de job. `lane` = "gpu" (sérialisé) ou "io" (parallèle)."""

from __future__ import annotations

from .analyze import AnalyzeStep
from .assemble import AssembleStep
from .base import Context, Step
from .generate_clip import GenerateClipStep
from .ideate import IdeateStep
from .import_channel import ImportChannelStep
from .improve import ImproveStep
from .montage_preview import MontagePreviewStep
from .qa import QAStep
from .render import RenderStep
from .script import ScriptStep
from .seo import SeoStep
from .storyboard import StoryboardStep
from .strategy import StrategyStep
from .sync import SyncCommentsStep, SyncMetricsStep, SyncRetentionStep
from .tiktok_publish import TikTokPublishStep
from .tts import TTSStep
from .upload import UploadStep
from .voice_preview import VoicePreviewStep

REGISTRY: dict[str, Step] = {
    s.type: s
    for s in (
        IdeateStep(),
        ScriptStep(),
        StoryboardStep(),
        RenderStep(),
        GenerateClipStep(),
        TTSStep(),
        SeoStep(),
        AssembleStep(),
        QAStep(),
        UploadStep(),
        SyncMetricsStep(),
        SyncRetentionStep(),
        SyncCommentsStep(),
        ImproveStep(),
        StrategyStep(),
        ImportChannelStep(),
        VoicePreviewStep(),
        MontagePreviewStep(),
        AnalyzeStep(),
        TikTokPublishStep(),
    )
}

__all__ = ["REGISTRY", "Context", "Step"]
