"""Sorties des agents des vidéos longues (docs/63) et script en chapitres (long_videos.script)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..models import MapSpec

LongFormat = Literal["mystere", "epoque", "libre"]
TextSide = Literal["left", "right", "top", "bottom"]
# Mouvement d'une image fixe animée (worker/longform/motion.py)
Move = Literal["in", "out", "left", "right", "up", "down"]
MOVES: tuple[str, ...] = ("in", "out", "left", "right", "up", "down")


def _as_list(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, str):
        return [v.strip() for v in value.split("|") if v.strip()] if "|" in value else [value.strip()] if value.strip() else []
    return value


# ---- Sujet et emballage ---------------------------------------------------------------------------------------------


class ThumbConcept(BaseModel):
    """Une miniature : l'image est générée SANS texte ; le texte (0 à 4 mots) est posé par le code en police grasse."""

    idea: str = ""  # ce que montre la miniature, en français, pour Luca
    prompt: str  # l'image, en anglais : sujet unique en gros plan, contraste, une émotion, place libre pour le texte
    text: str = ""  # 0 à 4 mots, chiffres, jamais le titre ; vide = aucun texte
    text_side: TextSide = "left"  # où poser le texte : la zone que l'image laisse libre


class Proof(BaseModel):
    """Une vidéo qui a déjà marché sur ce sujet (la preuve qu'il intéresse), prise dans la liste fournie à l'agent."""

    title: str
    views: int | None = None
    channel: str = ""
    url: str = ""


class LongIdea(BaseModel):
    subject: str  # le sujet en une phrase concrète
    format: LongFormat = "mystere"
    title: str  # le titre YouTube, 60 caractères au plus
    alt_titles: list[str] = Field(default_factory=list, max_length=4)
    hook: str  # la première phrase de la vidéo
    promise: str  # ce que la vidéo promet de révéler (tenu à la fin)
    angle: str = ""  # l'angle que personne ne prend
    why: str = ""  # pourquoi un inconnu cliquerait, et pourquoi il resterait
    thumbnail: ThumbConcept
    wikipedia: list[str] = Field(default_factory=list)  # titres de pages Wikipédia en français (1 à 4)
    wikipedia_en: list[str] = Field(default_factory=list)  # pages anglaises en plus (0 à 3)
    score: float = Field(50, ge=0, le=100)
    proof: list[Proof] = Field(default_factory=list, max_length=3)  # vidéos qui ont déjà marché sur ce sujet
    new_angle: str = ""  # ce que notre vidéo explique autrement que celles qui ont marché

    _lists = field_validator("alt_titles", "wikipedia", "wikipedia_en", mode="before")(_as_list)

    @field_validator("proof", mode="before")
    @classmethod
    def _proofs(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [{"title": v} if isinstance(v, str) else v for v in value][:3]
        return [] if value is None else value


class LongIdeaBatch(BaseModel):
    ideas: list[LongIdea]


# ---- Plan et texte --------------------------------------------------------------------------------------------------


class ChapterPlan(BaseModel):
    title: str  # le titre du chapitre (écran de chapitre, description) : 2 à 6 mots qui donnent envie
    goal: str  # ce que le chapitre raconte, révèle ou fait basculer
    beats: list[str] = Field(default_factory=list)  # les faits et événements, dans l'ordre, avec leur source [n]
    question: str = ""  # la question ouverte sur laquelle il s'arrête (la relance vers le suivant)
    minutes: float = Field(2.5, gt=0, le=12)

    _beats = field_validator("beats", mode="before")(_as_list)


class Outline(BaseModel):
    central_idea: str
    engine: str = ""
    protagonist: str = ""
    stakes: str = ""
    promise: str = ""
    ending: str  # la dernière phrase, écrite avant tout le reste
    hook: str = ""  # l'ouverture des 30 premières secondes, en 2-3 phrases
    chapters: list[ChapterPlan] = Field(min_length=3, max_length=12)


class Paragraph(BaseModel):
    text: str  # ce que Luca lit, mot pour mot
    show: str = ""  # ce qu'on voit pendant ce paragraphe, en français


class ChapterText(BaseModel):
    index: int
    title: str = ""
    paragraphs: list[Paragraph] = Field(min_length=1)


class ChapterBatch(BaseModel):
    chapters: list[ChapterText] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _single(cls, data: Any) -> Any:
        """Un LLM renvoie parfois un seul chapitre à plat."""
        if isinstance(data, dict) and "chapters" not in data and "paragraphs" in data:
            return {"chapters": [data]}
        return data


class ReviewProblem(BaseModel):
    chapter: int = 0
    paragraph: int | None = None
    problem: str
    fix: str = ""


class LongReview(BaseModel):
    ok: bool = False
    problems: list[ReviewProblem] = Field(default_factory=list)
    strengths: str = ""

    @field_validator("problems", mode="before")
    @classmethod
    def _strings(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [{"problem": v} if isinstance(v, str) else v for v in value]
        return value


# ---- Plans du réalisateur ---------------------------------------------------------------------------------------------


class ShotSpec(BaseModel):
    para: str  # clé du paragraphe (« c2p3 »)
    at_word: int = Field(0, ge=0)  # le plan commence quand la voix dit ce mot du paragraphe (0 = son début)
    kind: Literal["image", "clip", "map"] = "image"
    visual_prompt: str  # l'image, en anglais (le départ du clip pour un clip)
    motion: str = ""  # image : in, out, left, right, up, down ; clip : l'action ou le mouvement, en anglais
    map: MapSpec | None = None

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: Any) -> Any:
        v = str(value or "image").lower().strip()
        return v if v in ("image", "clip", "map") else "image"


class ShotBatch(BaseModel):
    shots: list[ShotSpec] = Field(min_length=1)
    design_bible: str | None = None


# ---- Publication ----------------------------------------------------------------------------------------------------


class TitleOption(BaseModel):
    title: str
    angle: str = ""


class Packaging(BaseModel):
    titles: list[TitleOption] = Field(min_length=2, max_length=6)
    chosen: int = Field(0, ge=0)
    description: str  # sans les chapitres ni les sources : le code les ajoute
    tags: list[str] = Field(default_factory=list, max_length=30)
    hashtags: list[str] = Field(default_factory=list, max_length=5)
    pinned_comment: str = ""
    thumbnails: list[ThumbConcept] = Field(default_factory=list, max_length=4)
    music_mood: str | None = None

    @field_validator("titles", mode="before")
    @classmethod
    def _titles(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [{"title": v} if isinstance(v, str) else v for v in value]
        return value


class ThumbConcepts(BaseModel):
    thumbnails: list[ThumbConcept] = Field(min_length=1, max_length=6)


class ThumbStyle(BaseModel):
    """Le style des miniatures qui marchent dans la niche, tel que la vision le voit."""

    style: str  # le style commun, en français, en quelques phrases
    rules: list[str] = Field(default_factory=list, max_length=12)  # règles concrètes à suivre


# ---- Vérification des faits -----------------------------------------------------------------------------------------

FactStatus = Literal["confirmed", "hypothesis", "unsupported", "contradicted"]


class FactClaim(BaseModel):
    chapter: int = 0
    paragraph: int | None = None
    claim: str  # le fait tel que le script le dit
    status: FactStatus = "confirmed"
    source: str = ""  # les numéros de source du dossier qui le confirment (« [1], [4] »)
    fix: str = ""  # la correction si le fait n'est pas confirmé tel quel

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, value: Any) -> Any:
        v = str(value or "confirmed").lower().strip()
        return v if v in ("confirmed", "hypothesis", "unsupported", "contradicted") else "unsupported"


class FactCheck(BaseModel):
    claims: list[FactClaim] = Field(default_factory=list)
    summary: str = ""


class ThumbScore(BaseModel):
    index: int
    score: float = Field(ge=0, le=10)
    note: str = ""


class ThumbReview(BaseModel):
    scores: list[ThumbScore] = Field(default_factory=list)


class ImageCheck(BaseModel):
    index: int
    ok: bool = True
    problem: str = ""


class ImageChecks(BaseModel):
    checks: list[ImageCheck] = Field(default_factory=list)
