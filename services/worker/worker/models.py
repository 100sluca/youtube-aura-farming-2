"""Modèles Pydantic : miroir de supabase/migrations/0001_init.sql et sorties des agents."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field, model_validator

Lang = Literal["fr", "en"]
VideoFormat = Literal["A_voiceover", "B_visual"]
# Temps du récit portés par chaque scène (worker/storytelling.py) : accroche, mise en place, révélation
# avant 12 s, montée, réponse finale, retour au premier plan.
SceneRole = Literal["hook", "setup", "reveal", "escalation", "payoff", "loop"]
# Recette de fabrication (series.recipe, worker/recipes.py) : story = récit narré (défaut) ; timelapse = chantier
# en accéléré (images clés retouchées en chaîne, première → dernière image) ; tour = visite de maison de luxe ;
# drama = histoire en dialogues (personnages constants d'après leur fiche, répliques dites par le modèle vidéo, docs/35).
Recipe = Literal["story", "timelapse", "tour", "drama"]
# Animation d'une scène : i2v = depuis son image clé ; flf = de son image clé à celle de la scène suivante
# (première + dernière image, Wan 2.2 14B), l'étape du chantier se construit sous les yeux.
ClipMode = Literal["i2v", "flf"]
# Passage à la scène suivante : cut = coupe franche ; whip = coup de fouet flou (visite) ; fade = fondu ;
# zoom = zoom avant.
Transition = Literal["cut", "whip", "fade", "zoom"]
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
    "seo",
    "strategy",
    "storyboard",
    "render",
    "import_channel",
    "voice_preview",
    "montage_preview",
    "analyze",  # agent analyste des performances (migration 0015, docs/25)
    "tiktok_publish",  # publication sur TikTok par Zernio (migration 0023, docs/36)
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


def _by_lang(value: Any) -> Any:
    """Un LLM renvoie parfois un texte seul là où l'on attend {langue: texte} : on le range sous « fr » (langue de la
    chaîne principale) ; le linter signale ensuite les autres langues manquantes et le script repart au LLM."""
    return {"fr": value} if isinstance(value, str) else value


LangText = Annotated[dict[Lang, str], BeforeValidator(_by_lang)]


def _names(value: Any) -> Any:
    """Liste de noms de lieux : un LLM écrit parfois « Bamberg, Kelheim » en une seule chaîne, ou null."""
    if value is None:
        return []
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else value


PlaceNames = Annotated[list[str], BeforeValidator(_names)]


class MapSpec(BaseModel):
    """Scène carte d'un récit (worker/maps.py, docs/24) : la caméra descend de l'espace jusqu'au lieu, dont le tracé se
    dessine. Rendue par le code (images satellite, tracé OpenStreetMap), ni image ni clip d'IA. Les noms sont affichés
    tels quels : ils sont écrits dans la langue de la vidéo."""

    place: str = ""  # le lieu, tel que le titre de sa page Wikipédia (« Canal Rhin-Main-Danube ») ; vide = pas de carte
    ends: PlaceNames = Field(default_factory=list)  # 0 à 2 repères : les deux bouts d'un tracé (« Bamberg », « Kelheim »)
    context: PlaceNames = Field(default_factory=list)  # 0 à 3 grands repères montrés avant de zoomer (« Mer du Nord »)
    # 0 à 3 cours d'eau, routes ou frontières dessinés en bleu : ce que le lieu relie (« Main (rivière) », « Danube ») ;
    # un titre Wikipédia avec sa précision entre parenthèses, affiché sans elle
    lines: PlaceNames = Field(default_factory=list)


class CastMember(BaseModel):
    """Personnage d'un drame (recette drama, docs/35). Sa fiche (une image en pied, faite au storyboard) est donnée en
    référence à chaque plan où il apparaît : il garde la même tête d'un plan à l'autre. Sa voix est décrite au modèle
    vidéo, qui dit ses répliques (MiniMax H3) ; la même description dans chaque clip."""

    key: str  # identifiant court en minuscules (« kiwi », « madame_figue ») : les scènes et les répliques s'y réfèrent
    name: str  # le nom dit dans l'histoire (« Kiwi », « Madame Figue »)
    look: str  # apparence fixe, en anglais : tête (fruit, animal ou visage), âge, silhouette, vêtements, accessoires
    voice: str = ""  # la voix, en anglais (« a soft trembling young male voice »)
    # Voix de synthèse du personnage (« qwen3:perso_humble », workflows/catalog.json) : série en voix constantes
    # (format A) ; le modèle vidéo ne garde pas la même voix d'un clip à l'autre (essai du 28/09, docs/31 §8)
    tts_voice: str = ""
    role: str = ""  # victime, méchant, témoin… (pour Luca et le relecteur)


class DialogueLine(BaseModel):
    """Une réplique d'un drame : dite par le modèle vidéo pendant le plan (une seule voix par plan)."""

    who: str  # clé du personnage qui parle (cast.key)
    text: str  # la réplique, dans la langue de la vidéo, 14 mots au plus
    tone: str = ""  # comment elle est dite, en anglais (« whispers, trembling », « shouts furiously »)


def _keys(value: Any) -> Any:
    """Clés de personnages : un LLM écrit parfois « kiwi, prune » en une seule chaîne, ou null."""
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split(",")
    return [str(v).strip().lower() for v in value if str(v).strip()] if isinstance(value, list) else value


CastKeys = Annotated[list[str], BeforeValidator(_keys)]


class ScriptScene(BaseModel):
    index: int
    role: SceneRole | None = None  # rôle narratif de la scène, vérifié par lint_script()
    # 1 s au moins : une étape de chantier en accéléré ne dure qu'une seconde et demie (docs/15 §10)
    duration_s: float = Field(ge=1, le=8)
    # True : le clip part de la dernière image du clip précédent (même lieu, action qui continue) ;
    # False : coupe, le clip part de sa propre image de storyboard. Voir CLIP_CONTINUITY (config.py).
    continues_previous: bool = False
    visual_prompt: str  # description de la PREMIÈRE image de la scène (storyboard), en anglais
    # Mouvement de caméra et action pendant la scène (image → vidéo), en anglais ; absent = visual_prompt
    motion_prompt: str | None = None
    narration: LangText = Field(default_factory=dict)
    on_screen_text: LangText = Field(default_factory=dict)
    # Bruitages : étiquettes séparées par des virgules, prises dans le vocabulaire de worker/sfx.py
    # (« excavator, birds »), placées sur la durée de la scène par le montage.
    sfx: str | None = None
    # Image clé obtenue en RETOUCHANT celle d'une autre scène (anglais, modèle de retouche) : même cadre. Absent =
    # image générée depuis visual_prompt.
    edit_prompt: str | None = None
    # Scène dont l'image est retouchée (index) ; absent = la précédente. Le chantier se construit À REBOURS : le
    # bâtiment fini est généré, chaque étape antérieure est une retouche de la suivante (worker/recipes.py).
    edit_from: int | None = None
    clip_mode: ClipMode = "i2v"
    transition: Transition = "cut"
    # Visite (recette tour) : plan de la maison, parcours d'une pièce à la suivante
    interior: bool | None = None  # pièce intérieure (murs et plafond visibles) ou vue extérieure
    floor: int | None = None  # niveau (0 = rez-de-chaussée) : la visite monte, elle ne redescend pas
    leads_to: str | None = None  # l'ouverture vers la pièce suivante, visible dans l'image (anglais)
    # Passage d'une pièce à la suivante, inséré par le code (recipes.normalize_script) : pas d'image clé, le clip part
    # de l'image où s'arrête la pièce précédente et finit sur l'image clé de la suivante (première + dernière image)
    passage: bool = False
    # Récits : scène carte (lieu réel situé depuis l'espace), rendue par le code au lieu de l'image et du clip d'IA
    map: MapSpec | None = None
    # Drame (docs/35) : personnages à l'image (clés du cast, 3 au plus : leurs fiches servent de références à l'image) et
    # la réplique du plan (celle qu'un seul personnage dit, le modèle vidéo la fait parler)
    characters: CastKeys = Field(default_factory=list)
    lines: list[DialogueLine] = Field(default_factory=list)

    @property
    def is_map(self) -> bool:
        return bool(self.map and self.map.place.strip())


class LangMetadata(BaseModel):
    title: str = Field(max_length=100)
    description: str = Field(max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=30)


class ScriptV1(BaseModel):
    version: Literal[1] = 1
    # 24 au plus : une visite de 9 pièces compte aussi ses 8 passages (recipes.normalize_script)
    scenes: list[ScriptScene] = Field(min_length=4, max_length=24)
    loop_note: str | None = None
    metadata: dict[Lang, LangMetadata]
    # Ambiance musicale choisie par l'agent script : nom d'un sous-dossier de DATA_DIR/music
    # (epic, calm, suspense, upbeat, emotional, mysterious…). Absent = pas de musique.
    music_mood: str | None = None
    # Titre d'accroche gravé en haut de l'écran, façon MJClipIt (worker/hooktitle.py) : 3 à 8 mots, parlé.
    hook_title: LangText = Field(default_factory=dict)
    # Le lieu en une phrase (anglais), ajoutée à chaque image : même maison, même chantier d'un plan à l'autre.
    # Visite : les matériaux et la lumière de toute la maison.
    design_bible: str | None = None
    # Visite : le paysage vu par toutes les fenêtres (anglais), identique dans chaque pièce.
    view: str | None = None
    # Drame : les personnages de l'histoire (fiche image et voix de chacun, docs/35)
    cast: list[CastMember] = Field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return sum(s.duration_s for s in self.scenes)

    def member(self, key: str) -> CastMember | None:
        return next((m for m in self.cast if m.key == key), None)


class ScriptReview(BaseModel):
    """Relecture éditoriale d'un récit avant le storyboard (steps/script.py, prompt script_review) : enjeu compris,
    promesses tenues, conflit et humain, faits du dossier. Les problèmes repartent au scénariste pour une réécriture."""

    ok: bool = False
    problems: list[str] = Field(default_factory=list)


class SceneDraft(BaseModel):
    """Ce que le scénariste réécrit d'une scène réinventée pendant la revue du storyboard (worker/reinvent.py) ; rôle,
    durée et mécanique de la scène (index, retouche, passage) restent ceux de l'ancienne."""

    visual_prompt: str
    motion_prompt: str | None = None
    narration: LangText = Field(default_factory=dict)
    on_screen_text: LangText = Field(default_factory=dict)
    sfx: str | None = None
    edit_prompt: str | None = None  # chantier : la retouche de l'étape suivante
    interior: bool | None = None  # visite
    floor: int | None = None
    leads_to: str | None = None
    map: MapSpec | None = None  # récit : scène carte, s'il n'y en a pas d'autre
    characters: CastKeys = Field(default_factory=list)  # drame : personnages à l'image
    lines: list[DialogueLine] = Field(default_factory=list)  # drame : la réplique du plan


class SceneRewrite(BaseModel):
    """Réponse de l'agent scene_rewrite : la scène réécrite et, pour Luca, le nouveau plan en une phrase."""

    idea: str = ""
    scene: SceneDraft

    @model_validator(mode="before")
    @classmethod
    def _flat(cls, data: Any) -> Any:
        """Un LLM renvoie parfois les champs de la scène à plat, sans « scene » autour."""
        if isinstance(data, dict) and "scene" not in data and "visual_prompt" in data:
            return {"idea": data.get("idea", ""), "scene": {k: v for k, v in data.items() if k != "idea"}}
        return data


# ---- Narration horodatée (videos.timeline) ----------------------------------


class WordTiming(BaseModel):
    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)


class SceneTiming(BaseModel):
    index: int
    start: float = Field(ge=0)  # début de la scène sur la timeline de la vidéo
    duration: float = Field(gt=0)  # durée effective (≥ durée prévue, allongée si la narration déborde)
    speech_start: float | None = None  # bornes de la voix dans la scène, en temps absolu
    speech_end: float | None = None
    words: list[WordTiming] = Field(default_factory=list)


class NarrationTimeline(BaseModel):
    """Écrite par le step tts, lue par assemble (durées des scènes, sous-titres)."""

    version: Literal[1] = 1
    lang: Lang
    aligner: str = "proportional"  # proportional | whisper
    scenes: list[SceneTiming]

    @property
    def duration_s(self) -> float:
        return max((s.start + s.duration for s in self.scenes), default=0.0)

    @property
    def words(self) -> list[WordTiming]:
        return [w for s in self.scenes for w in s.words]


# ---- Agent SEO (videos.seo) --------------------------------------------------


class TitleVariant(BaseModel):
    title: str = Field(max_length=100)
    angle: str = Field(description="levier : curiosité, chiffre, question, avant/après, défi…")


class SeoPack(BaseModel):
    titles: list[TitleVariant] = Field(min_length=2, max_length=5)
    chosen: int = Field(0, ge=0, description="index du titre retenu dans titles")
    description: str = Field(max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=40)
    hashtags: list[str] = Field(default_factory=list, max_length=8)
    pinned_comment: str | None = Field(None, max_length=500)


# ---- Agent stratégie (strategies.proposal) ------------------------------------


class CategoryWeight(BaseModel):
    category: str
    weight: float = Field(ge=0, le=3, description="1 = inchangé, 0 = arrêter, 2 = doubler")
    reason: str


class StrategyProposal(BaseModel):
    summary: str
    category_weights: list[CategoryWeight] = Field(default_factory=list)
    hook_guidelines: list[str] = Field(default_factory=list, max_length=6)
    title_patterns: list[str] = Field(default_factory=list, max_length=6)
    avoid: list[str] = Field(default_factory=list, max_length=6)
    publish_slots: list[str] | None = Field(None, description="créneaux HH:MM, seulement si les données le justifient")
    target_duration_s: int | None = Field(None, ge=15, le=60)
    experiments: list[str] = Field(default_factory=list, max_length=3)
    confidence: Literal["faible", "moyenne", "bonne"] = "faible"


# ---- Sources et faits (séries documentaires : Wikipédia) ---------------------


class SourceRef(BaseModel):
    """Une page source conservée avec le concept (concepts.sources) : titre, URL, révision consultée."""

    title: str
    url: str
    lang: str = "fr"
    kind: str = "wikipedia"
    revision: int | None = None


class Fact(BaseModel):
    """Un fait utilisable dans le script, avec le numéro de sa source (concepts.facts)."""

    claim: str
    source: int = Field(0, ge=0, description="index de la source : [n] dans la matière fournie, puis dans concepts.sources")


# ---- Agent idée -------------------------------------------------------------


class Idea(BaseModel):
    title: str
    hook: str
    category: str
    premise: str
    visual_beats: list[str] = Field(min_length=3, max_length=8)
    score: float = Field(ge=0, le=100)
    angle: str | None = Field(None, description="ressort narratif : mystère, renversement, record, David contre Goliath…")
    facts: list[Fact] = Field(default_factory=list, max_length=12)


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
