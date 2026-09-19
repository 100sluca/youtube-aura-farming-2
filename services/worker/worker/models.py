"""Modèles Pydantic : miroir de supabase/migrations/0001_init.sql et sorties des agents."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

Lang = Literal["fr", "en"]
VideoFormat = Literal["A_voiceover", "B_visual"]
JobType = Literal[
    "ideate",
    "script",
    "generate_clip",
    "tts",
    "assemble",
    "qa",
    "upload",
    "sync_metrics",
    "sync_retention",
    "sync_comments",
    "improve",
]


class Job(BaseModel):
    id: UUID
    type: JobType
    status: str
    priority: int
    production_id: UUID | None = None
    video_id: UUID | None = None
    channel_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    attempts: int = 0
    max_attempts: int = 3
    created_at: datetime


# ---- Script (productions.script, version 1) --------------------------------


class ScriptScene(BaseModel):
    index: int
    duration_s: float = Field(ge=2, le=8)
    visual_prompt: str
    narration: dict[Lang, str] = Field(default_factory=dict)
    on_screen_text: dict[Lang, str] = Field(default_factory=dict)
    sfx: str | None = None


class LangMetadata(BaseModel):
    title: str = Field(max_length=100)
    description: str = Field(max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=30)


class ScriptV1(BaseModel):
    version: Literal[1] = 1
    scenes: list[ScriptScene] = Field(min_length=4, max_length=14)
    loop_note: str | None = None
    metadata: dict[Lang, LangMetadata]

    @property
    def duration_s(self) -> float:
        return sum(s.duration_s for s in self.scenes)


# ---- Agent idée -------------------------------------------------------------


class Idea(BaseModel):
    title: str
    hook: str
    category: str
    premise: str
    visual_beats: list[str] = Field(min_length=3, max_length=8)
    score: float = Field(ge=0, le=100)


class IdeaBatch(BaseModel):
    ideas: list[Idea]


# ---- Contrôle qualité -------------------------------------------------------


class QACheck(BaseModel):
    name: str
    ok: bool
    value: float | str | None = None
    detail: str | None = None


class QAReport(BaseModel):
    ok: bool
    checks: list[QACheck]
    duration_s: float
    loudness_lufs: float | None = None
