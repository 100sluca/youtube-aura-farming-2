"""Mes scénarios (docs/59, demande de Luca du 02/10) : Luca écrit une idée ou un scénario libre dans Création → « Mon
scénario », une équipe d'agents le met en forme et la vidéo se fabrique comme un drame.

Le scénario de Luca devient une idée (concepts.scenario : son texte et ses choix) du thème caché « Mes scénarios »
(series mes_scenarios, recette drama, migration 0048) ; la production part tout de suite (submit_scenario). Au script,
l'équipe remplace le scénariste des drames (steps/script.py, _write_scenario) :
1. le metteur en scène (prompt scenario_adapt) lit le scénario et le met en forme (ScenarioPlan) : les temps de
   l'histoire dans l'ordre avec le passage du texte de Luca que chacun réalise, les personnages et leur apparence, le
   style visuel, les paroles (muet, quelques répliques, dialogues), la durée, le titre d'accroche, ce qu'il a décidé là
   où le texte ne disait rien (choices) et ce qui sera dur à filmer (risks). Le plan est gardé dans concepts.scenario.plan
   pour que Luca voie ce que l'équipe a compris ;
2. le scénariste (prompt script_scenario) écrit les plans (ScriptV1 d'un drame : distribution, une action par plan de
   2 à 5 s, répliques seulement si les paroles le prévoient) ; le code les normalise comme un drame (normalize) ;
3. le correcteur (lint) et le relecteur de fidélité (prompt scenario_review), qui compare le script au texte de Luca,
   le font réécrire (deux fois au plus, la première réécriture est relue à son tour).
Ensuite tout est celui d'un drame : fiches des personnages et storyboard à valider dans Création, clips MiniMax H3 qui
disent les répliques et font le son des plans, montage avec titre d'accroche, sous-titres et musique.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from . import drama
from .hooktitle import lint_hook_title
from .models import CastMember, ScriptV1
from .storytelling import CALLS_TO_ACTION, DURATION_TOLERANCE, words

SERIES = "mes_scenarios"
SCENES_RANGE = (5, 24)
CAST_RANGE = (1, 6)
DURATION_RANGE = (20, 90)
DURATION_DEFAULT = 45
REVIEW_PROBLEMS_MAX = 8
Speech = Literal["muet", "repliques", "dialogues"]
SPEECH_LABELS: dict[str, str] = {
    "muet": "sans paroles : tout passe par le jeu, les regards et les sons",
    "repliques": "quelques répliques courtes (1 à 4), là où elles servent le gag ou l'émotion",
    "dialogues": "l'histoire se raconte aussi en paroles, une réplique par plan au plus",
}
# Styles visuels proposés au metteur en scène (clés de providers/video.STYLE_PRESETS) et dans Création. Réaliste par
# défaut (Luca, 02/10 : « sur les vidéos de chien, je voulais des vidéos réalistes ») ; l'animation sur demande
STYLES: dict[str, str] = {
    "cinematic_real": "prise de vue réelle photoréaliste : de vrais gens et de vrais animaux dans une vraie maison",
    "pixar_human": "film d'animation 3D façon Pixar et Disney : humains et animaux stylisés, grands yeux expressifs",
    "dreamworks_animal": "film d'animation façon DreamWorks : animaux qui se tiennent debout et portent des vêtements",
    "pixar_fruit": "film d'animation façon Pixar : des fruits à visage humain, sur un corps habillé",
}
STYLE_DEFAULT = "cinematic_real"
REAL_STYLES = frozenset({"cinematic_real"})


class ScenarioBrief(BaseModel):
    """Ce que Luca envoie depuis Création (concepts.scenario) : son texte, et ses choix s'il en impose (« auto » ou
    absent : l'équipe décide)."""

    text: str
    title: str = ""
    style: str = "auto"
    speech: str = "auto"
    duration_s: int | None = None

    def imposed(self) -> list[str]:
        out: list[str] = []
        if self.style in STYLES:
            out.append(f"style imposé : {self.style} ({STYLES[self.style]})")
        if self.speech in SPEECH_LABELS:
            out.append(f"paroles imposées : {self.speech} ({SPEECH_LABELS[self.speech]})")
        if self.duration_s:
            out.append(f"durée imposée : {self.duration_s} s")
        if self.title.strip():
            out.append(f"titre voulu : {self.title.strip()}")
        return out


class ScenarioBeat(BaseModel):
    """Un temps de l'histoire, dans l'ordre : ce qui s'y passe et le passage du scénario de Luca qu'il réalise."""

    what: str  # ce qui se passe, en français, une phrase
    shown: str = ""  # ce qu'on voit : cadre, qui est à l'image, le détail qui compte
    why: str = ""  # installation, gag, tension, retournement, chute
    from_text: str = ""  # passage du texte de Luca, recopié ; vide pour un temps ajouté


class ScenarioPlan(BaseModel):
    """La mise en forme du metteur en scène (prompt scenario_adapt), avant les plans."""

    title: str
    logline: str = ""
    genre: str = ""
    style: str = STYLE_DEFAULT
    style_why: str = ""
    speech: Speech = "muet"
    duration_s: int = DURATION_DEFAULT
    # le décor en anglais, repris avec les mêmes mots dans chaque image : la même pièce d'un plan à l'autre
    setting: str = ""
    cast: list[CastMember] = Field(min_length=1, max_length=8)
    beats: list[ScenarioBeat] = Field(min_length=2, max_length=30)
    hook_title: str = ""
    choices: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    @field_validator("speech", mode="before")
    @classmethod
    def _speech(cls, v: Any) -> str:
        t = drama.slug(str(v or ""))
        if t.startswith("dialog"):
            return "dialogues"
        if t.startswith(("repl", "quelq", "few", "line")):
            return "repliques"
        return "muet"


def settle(plan: ScenarioPlan, brief: ScenarioBrief) -> ScenarioPlan:
    """Les choix imposés par Luca l'emportent sur ceux du metteur en scène ; un style inconnu redevient le style par
    défaut, la durée reste dans les bornes d'un Short."""
    p = plan.model_copy(deep=True)
    if brief.style in STYLES:
        p.style = brief.style
    elif p.style not in STYLES:
        p.style = STYLE_DEFAULT
    if brief.speech in SPEECH_LABELS:
        p.speech = brief.speech  # type: ignore[assignment]
    duration = brief.duration_s or p.duration_s or DURATION_DEFAULT
    p.duration_s = int(min(DURATION_RANGE[1], max(DURATION_RANGE[0], duration)))
    if brief.title.strip():
        p.title = brief.title.strip()
    for m in p.cast:
        m.name = _ROLE_SUFFIX.sub("", m.name.strip()) or m.name.strip()  # « Biscuit le chien » → « Biscuit »
        m.key = drama.slug(m.key or m.name)
    return p


# Le prénom seul : le rôle collé derrière (« Biscuit le chien », « Hugo, le maître ») passerait dans chaque prompt anglais
_ROLE_SUFFIX = re.compile(r"(?<=\w)[\s,]+(?:(?:le|la|les)\s+|l['’])\w.*$", re.I)


# ---------------------------------------------------------------------------
# Messages des agents
# ---------------------------------------------------------------------------


def brief_text(brief: ScenarioBrief) -> str:
    imposed = brief.imposed()
    return f'SCÉNARIO DE LUCA (texte d\'origine, la référence) :\n"""{brief.text.strip()}"""' + (
        "\nChoix de Luca à respecter : " + " ; ".join(imposed) if imposed else "\nChoix de Luca : aucun, l'équipe décide."
    )


def styles_text() -> str:
    return "STYLES VISUELS (champ style : la clé telle quelle) :\n" + "\n".join(f"- {k} : {v}" for k, v in STYLES.items())


def plan_text(plan: ScenarioPlan) -> str:
    """La mise en scène, lisible par le scénariste et le relecteur."""
    cast = "\n".join(f"- {m.key} · {m.name} ({m.role or '—'}) : {m.look} · voix : {m.voice or '—'}" for m in plan.cast)
    beats = "\n".join(
        f"{k}. {b.what}"
        + (f" · on voit : {b.shown}" if b.shown else "")
        + (f" · ({b.why})" if b.why else "")
        + (f" · texte de Luca : « {b.from_text} »" if b.from_text else " · temps ajouté")
        for k, b in enumerate(plan.beats, 1)
    )
    parts = [
        f"MISE EN SCÈNE : « {plan.title} » · {plan.logline}",
        f"Genre : {plan.genre or '—'} · Style : {plan.style} ({STYLES.get(plan.style, '')}) · Paroles : {plan.speech} "
        f"({SPEECH_LABELS[plan.speech]}) · Durée visée : {plan.duration_s} s · Titre d'accroche : {plan.hook_title or '—'}",
        f"Décor (anglais, à reprendre avec ces mots dans chaque image, la partie que le plan montre) : {plan.setting or '—'}",
        f"Personnages :\n{cast}",
        f"Temps de l'histoire, dans l'ordre :\n{beats}",
    ]
    if plan.choices:
        parts.append("Décidé par le metteur en scène :\n" + "\n".join(f"- {c}" for c in plan.choices))
    if plan.risks:
        parts.append("Difficultés de tournage et parade :\n" + "\n".join(f"- {r}" for r in plan.risks))
    return "\n".join(parts)


def script_listing(script: ScriptV1) -> str:
    """Les plans tels que le relecteur les lit : personnages, réplique, image et mouvement."""
    rows = []
    for k, sc in enumerate(script.scenes, 1):
        who = ", ".join(m.name if (m := script.member(c)) else c for c in sc.characters) or "personne"
        said = drama.speaker_line(script, sc)
        rows.append(
            f"Plan {k} ({sc.duration_s:g} s) · à l'image : {who}"
            + (f" · réplique : {said}" if said else " · sans réplique")
            + f"\n  image : {sc.visual_prompt}\n  mouvement : {sc.motion_prompt or '—'}"
        )
    cast = "\n".join(f"- {m.key} · {m.name} : {m.look}" for m in script.cast)
    hook = " / ".join(f"{k} : {v}" for k, v in script.hook_title.items())
    return f"Personnages :\n{cast}\nTitre d'accroche : {hook or '—'}\nDurée : {script.duration_s:g} s\n" + "\n".join(rows)


# ---------------------------------------------------------------------------
# Normalisation et correcteur
# ---------------------------------------------------------------------------


def normalize(script: ScriptV1, plan: ScenarioPlan) -> ScriptV1:
    """Ce qu'impose le code : la mécanique d'un drame (drama.normalize : clés, personnages qui parlent à l'image, durées,
    narration = la réplique seule) ; sans paroles, aucune réplique ; la distribution garde l'apparence du metteur en
    scène quand le scénariste la raccourcit (c'est elle que recopie chaque fiche)."""
    s = script.model_copy(deep=True)
    if plan.speech == "muet":
        for sc in s.scenes:
            sc.lines = []
    looks = {m.key: m for m in plan.cast}
    for m in s.cast:
        ref = looks.get(drama.slug(m.key or m.name))
        if ref and len(words(ref.look)) > len(words(m.look)):
            m.look = ref.look
        if ref and not m.voice and ref.voice:
            m.voice = ref.voice
        m.look = four_legs(real_look(m.look, plan.style), plan.style)
    return drama.normalize(s)


_CARTOON = re.compile(r"[\s,]*\b(cartoon[- ]?like|cartoonish|cartoon|pixar[- ]style|animated|stylized)\b", re.I)


def real_look(look: str, style: str) -> str:
    """Prise de vue réelle : l'apparence sans les mots de dessin animé (« highly expressive cartoon-like eyes » →
    « highly expressive eyes »), qui tireraient la fiche, puis chaque plan, vers l'animation."""
    if style not in REAL_STYLES:
        return look
    return re.sub(r"\s{2,}", " ", _CARTOON.sub("", look)).strip(" ,")


_ANIMAL = re.compile(
    r"\b(dog|puppy|cat|kitten|terrier|retriever|labrador|poodle|bulldog|spaniel|shepherd|husky|corgi|beagle|dachshund|"
    r"chihuahua|pug|rabbit|bunny|fox|horse|pony|pig|goat|sheep|cow|hamster|guinea pig)s?\b",
    re.I,
)
_HUMANLIKE = re.compile(
    r"\b(anthropomorphic|upright|hind legs|human body|clothes|shirt|jacket|dress|overalls|suit|sweater)\b", re.I
)
REAL_ANIMAL = ", a real four-legged animal that always stays on all four paws, never standing upright"


def four_legs(look: str, style: str) -> str:
    """Un vrai animal (chien, chat…) reste à quatre pattes : sa fiche le dessine ainsi (drama.SHEET_FOUR_LEGS) et chaque
    plan la reprend ; sans cette précision, la fiche le mettait debout sur ses pattes arrière (Biscuit, 02/10). Pas pour
    les styles où les animaux sont humanisés (DreamWorks, fruits), ni pour un animal décrit habillé ou debout."""
    if style in ("dreamworks_animal", "pixar_fruit") or not _ANIMAL.search(look) or _HUMANLIKE.search(look):
        return look
    return look if drama.FOUR_LEGS.search(look) else look.rstrip(". ") + REAL_ANIMAL


def lint(script: ScriptV1, langs: Sequence[str], target_duration_s: float | None, speech: str) -> list[str]:
    """Problèmes mesurables du script d'un scénario (après normalize) ; liste vide = conforme. Comme un drame, sans la
    part de plans dialogués : un scénario peut se jouer sans un mot."""
    issues: list[str] = []
    n = len(script.scenes)
    if not SCENES_RANGE[0] <= n <= SCENES_RANGE[1]:
        issues.append(f"{n} plans : {SCENES_RANGE[0]} à {SCENES_RANGE[1]} (une action par plan de 2 à 5 s)")
    if not CAST_RANGE[0] <= len(script.cast) <= CAST_RANGE[1]:
        issues.append(f"cast : {len(script.cast)} personnages, {CAST_RANGE[0]} à {CAST_RANGE[1]} (key, name, look pour chacun)")
    speakers = {ln.who for sc in script.scenes for ln in sc.lines}
    for m in script.cast:
        if len(words(m.look)) < drama.LOOK_WORDS_MIN:
            issues.append(
                f"personnage {m.name} : look trop court ({len(words(m.look))} mots) ; en anglais, {drama.LOOK_WORDS_MIN} mots "
                "au moins : espèce et race ou âge, silhouette, couleurs, pelage ou visage, vêtements"
            )
        if m.key in speakers and not m.voice:
            issues.append(f"personnage {m.name} : il parle, voice manquante (sa voix en anglais : âge, timbre)")
    keys = {m.key for m in script.cast}
    lang = langs[0] if langs else drama.video_lang(script)
    cta = CALLS_TO_ACTION.get(lang, CALLS_TO_ACTION["fr"])
    for i, sc in enumerate(script.scenes):
        tag = f"plan {i + 1}"
        unknown = sorted({k for k in sc.characters if k not in keys} | {ln.who for ln in sc.lines if ln.who not in keys})
        if unknown:
            issues.append(f"{tag} : personnages absents du cast {unknown} (chaque personnage à l'image a sa fiche)")
        if len({ln.who for ln in sc.lines}) > 1:
            issues.append(f"{tag} : plusieurs personnages parlent ; une seule voix par plan (couper en deux plans)")
        for ln in sc.lines:
            nw = len(words(ln.text))
            if nw > drama.LINE_WORDS_MAX:
                issues.append(f"{tag} : réplique de {nw} mots, {drama.LINE_WORDS_MAX} au plus (un clip dure 5 s)")
            if re.search(cta, ln.text, re.I):
                issues.append(f"{tag} : appel à l'action interdit dans une réplique")
        if not sc.visual_prompt.strip():
            issues.append(f"{tag} : visual_prompt manquant")
        if not (sc.motion_prompt or "").strip():
            issues.append(f"{tag} : motion_prompt manquant (l'action du plan, en anglais, sans la réplique)")
    talking = sum(bool(sc.lines) for sc in script.scenes)
    if speech == "repliques" and talking > max(4, n // 3):
        issues.append(f"répliques sur {talking} plans : « quelques répliques » = 4 au plus, là où elles servent")
    for lg in langs:
        issues += lint_hook_title(script.hook_title.get(lg, ""), lg)  # type: ignore[call-overload]
    if target_duration_s and abs(script.duration_s - target_duration_s) > DURATION_TOLERANCE * target_duration_s:
        issues.append(
            f"durée {script.duration_s:g} s, cible {target_duration_s:g} s (± {int(DURATION_TOLERANCE * 100)} %) : "
            "ajouter ou retirer des plans, sans retirer d'action du scénario"
        )
    return issues


def review_problems(ok: bool, problems: Sequence[str]) -> list[str]:
    kept = [p.strip() for p in problems if p.strip()][:REVIEW_PROBLEMS_MAX]
    return [] if ok else kept


def rewrite_request(issues: Sequence[str], problems: Sequence[str]) -> str:
    parts = ["RÉÉCRIS LE SCRIPT EN ENTIER en corrigeant ce qui suit, sans perdre aucune action du scénario de Luca."]
    if problems:
        parts.append("Remarques du relecteur (fidélité, lisibilité, faisabilité) :\n" + "\n".join(f"- {p}" for p in problems))
    if issues:
        parts.append("Écarts mesurés par le correcteur :\n" + "\n".join(f"- {i}" for i in issues))
    return "\n\n".join(parts)


def plan_summary(plan: ScenarioPlan) -> dict[str, Any]:
    """Ce que Création montre de la mise en scène (concepts.scenario.plan)."""
    return plan.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Prompts des agents (onglet Agents : scenario_adapt, script_scenario, scenario_review)
# ---------------------------------------------------------------------------

MAKING = """Comment la vidéo sera fabriquée (pour décider juste) :
- chaque plan est un clip de 2 à 5 s, animé depuis une image : UNE action simple et lisible par plan (« le chien
  pousse la porte du frigo avec sa truffe », pas « il ouvre le frigo, prend le gâteau et le mange ») ; une action
  longue se coupe en plusieurs plans (plan large, gros plan sur le détail, réaction) ;
- chaque personnage a une fiche (une image de lui en pied) donnée en référence à chaque plan où il apparaît : il garde
  la même tête d'un plan à l'autre ; 3 personnages au plus dans un même plan ;
- le modèle vidéo fait le son du plan (ambiance, bruits) et peut faire dire une réplique courte (12 mots au plus) à un
  personnage, bouche comprise ; un animal ne parle pas, sauf si le scénario le veut : il joue avec son corps, ses
  yeux, ses oreilles, sa queue ;
- aucun texte écrit dans l'image ; le montage ajoute un titre d'accroche en haut de l'écran, les sous-titres des
  répliques et une musique."""

ADAPT_PROMPT = f"""Tu es le metteur en scène d'une petite équipe qui réalise les idées de Luca en Shorts verticaux
(9:16, 20 à 90 s, TikTok et YouTube). Luca t'envoie un SCÉNARIO LIBRE, écrit vite, avec ses mots. Ton travail : le
comprendre et le mettre en forme pour que le scénariste en écrive les plans, SANS LE TRAHIR. Le scénario de Luca prime
sur tout : chaque action qu'il décrit se retrouve à l'écran, dans son ordre ; tu n'enlèves rien d'important et tu
n'ajoutes rien qui change l'histoire. Tu complètes seulement ce qu'il ne dit pas (décor, apparence, cadrage, rythme,
petits temps qui rendent une action lisible) et tu le notes dans choices.

{MAKING}

CE QUI FAIT UN BON SHORT : la situation comprise dès la première image (qui, où, ce qu'il veut) ; le spectateur en sait
plus que les personnages (il voit le chien comploter, la mère ne voit rien) ; chaque gag a sa préparation et sa chute ;
le rythme s'accélère quand l'action devient urgente ; la dernière image est la chute, et rappelle la première quand
l'histoire boucle (même cadre, même pose).

Ce que tu rends (JSON) :
- title : le titre de la vidéo, en français, court (celui de Luca s'il en donne un) ;
- logline : l'histoire en une phrase ;
- genre : comédie muette, comédie, émotion, suspense… ;
- style : la clé d'un des STYLES VISUELS proposés : celui de Luca s'il l'impose ; sinon cinematic_real (prise de vue
  réelle : c'est ce que Luca veut pour ses histoires d'animaux et de familles), un style d'animation seulement si son
  texte le demande ou si l'histoire est impossible en vrai (fruits qui parlent, animaux debout et habillés) ;
  style_why : pourquoi, en une phrase ;
- speech : « muet » (aucune réplique : regards, jeu, sons), « repliques » (1 à 4 répliques courtes, là où elles
  servent) ou « dialogues » (l'histoire se raconte aussi en paroles) ; celui de Luca s'il l'impose ;
- duration_s : la durée qui sert l'histoire (celle de Luca s'il l'impose) : assez pour que chaque temps se lise, jamais
  de remplissage ; souvent 35 à 60 s ;
- setting, EN ANGLAIS : le décor de l'histoire en une ou deux phrases, ce qui ne change pas d'un plan à l'autre (la
  pièce, sa disposition, les meubles et objets qui comptent, leurs couleurs, la lumière : « a bright open-plan living
  room: a light grey fabric sofa facing an open kitchen with a tall white fridge, oak floor, large window on the left,
  afternoon light ») ; tout objet dont l'histoire a besoin y est (le frigo, la lampe, le parc à jouets) ;
- cast : chaque personnage : key (minuscules sans accent : « biscuit », « marc »), name : un PRÉNOM court (« Biscuit »,
  « Marc », « Léa »), même si l'histoire ne le dit jamais : il désigne le personnage dans les prompts anglais (jamais
  « Le chien » ni « La maman »), role (« le chien », « la maman »), look EN ANGLAIS (12 mots au moins : espèce et race ou âge, taille, silhouette, couleurs, pelage
  ou visage et coiffure, vêtements ; précis, il sera recopié tel quel dans chaque image ; en prise de vue réelle, un
  vrai chien ou une vraie personne : aucun trait de dessin animé, jamais « cartoon eyes »), voice EN ANGLAIS (s'il parle :
  âge, timbre, manière ; sinon « does not speak ») ;
- beats : les temps de l'histoire, dans l'ordre, chacun : what (ce qui se passe, une phrase en français), shown (ce
  qu'on voit : cadre, qui est à l'image, le détail qui compte), why (installation, gag, tension, retournement, chute),
  from_text (le passage du scénario de Luca qu'il réalise, recopié mot pour mot ; vide pour un temps que tu ajoutes) ;
  tous les passages d'action du texte de Luca doivent apparaître dans un from_text ;
- hook_title : le titre d'accroche affiché en haut de l'écran pendant la vidéo (3 à 8 mots, parlé, qui donne envie de
  voir la fin sans la dire) ;
- choices : ce que tu as décidé là où le scénario ne disait rien ou était ambigu, une phrase chacun (« le maître mange
  une part de gâteau au chocolat », « le canapé fait face à la cuisine ouverte, pour que le chien voie le frigo ») ;
- risks : ce qui sera difficile à filmer et comment le scénariste doit s'y prendre (« les yeux qui bougent seuls : gros
  plan sur la tête immobile, un seul mouvement des yeux par plan »).
Réponds uniquement en JSON."""

SCRIPT_PROMPT = f"""Tu écris le script d'UN Short vertical (9:16) qui réalise le SCÉNARIO DE LUCA, mis en forme par le
metteur en scène (MISE EN SCÈNE : temps de l'histoire, personnages, style, paroles, durée). Fidélité d'abord : chaque
temps de la mise en scène devient un ou plusieurs plans, dans l'ordre, et chaque action du scénario de Luca se voit à
l'écran ; rien d'ajouté qui change l'histoire.

{MAKING}

DISTRIBUTION (cast) : celle de la mise en scène, recopiée (key, name, role, look, voice ; même key, même look) ;
tts_voice : pour un personnage qui parle, l'identifiant d'une voix de la liste VOIX DE SYNTHÈSE qui lui ressemble
(une voix différente par personnage), sinon vide.
SCÈNES : un plan = UNE action simple et lisible de 2 à 5 s ; une action longue se coupe en plusieurs plans (plan large
qui situe, gros plan sur le détail, réaction) : « il ouvre le frigo, pose l'assiette, referme et s'en va » = 3 ou 4
plans, jamais un. Chaque scène :
- characters : les clés des personnages visibles (0 à 3) ; un personnage à l'image est TOUJOURS dans characters (sa
  fiche le garde identique) ; un plan de détail sans personne (la porte du frigo, la lampe) peut n'en avoir aucun ;
- lines : [] sauf si la mise en scène prévoit des paroles (« repliques » ou « dialogues ») et que ce plan en porte une :
  {{"who": clé, "text": dans la langue de la vidéo, 12 mots au plus, "tone": en anglais, comment elle est dite}} ;
  jamais de réplique en « muet » ; un animal ne parle pas, sauf si le scénario le veut ;
- visual_prompt, en anglais : la PREMIÈRE image du plan, un instant figé (jamais une suite d'actions) : l'intention ou
  l'émotion d'abord (« the dog, pretending to
  doze, eyes half open… »), puis le LIEU, toujours, avec les mots du DÉCOR de la mise en scène, la partie que le plan
  montre (« in the bright open-plan living room, on the light grey fabric sofa facing the open kitchen »), qui est où, la valeur de plan (gros
  plan pour un regard, plan large pour situer) et la lumière ; nomme les personnages par leur name ; AUCUN texte écrit
  dans l'image (ni panneau, ni étiquette, ni écran avec des mots) ;
- motion_prompt, en anglais : ce qui bouge pendant le plan, UNE action précise et physique (« the dog's head stays
  perfectly still while only its eyes slowly follow the man walking from left to right »), la caméra (fixe le plus
  souvent) et le son d'ambiance (« sound of the fridge door opening, a soft hum ») ; jamais la réplique ;
- on_screen_text : vide ; image_text : absent ; duration_s : 2 à 5 s (le code recalcule celle des plans qui ont une
  réplique) ; role : vide.
La première image pose la situation (qui, où, ce qu'il veut) ; la dernière est la chute, et rappelle la première quand
la mise en scène le prévoit (même cadre, même pose).
hook_title : celui de la mise en scène, une entrée par langue (règles ci-dessous). metadata : par langue, titre YouTube
≤ 60 caractères avec un émoji, description de 2 phrases qui finit par une question, 10 tags. music_mood : prise dans
la liste MUSIQUE DE FOND selon le genre (malice, comédie, tension, émotion). loop_note : comment la fin rappelle le
début. Réponds uniquement en JSON conforme à ScriptV1."""

REVIEW_PROMPT = """Tu relis le script d'un Short avant que ses images soient faites. Il doit réaliser le SCÉNARIO DE
LUCA (son texte d'origine est fourni : c'est ta référence, avant la mise en scène). Vérifie, dans cet ordre :
1. Fidélité : chaque action du scénario de Luca est-elle à l'écran, dans son ordre, sans contresens ? Rien d'important
   n'est-il oublié, ni ajouté au point de changer l'histoire ? Cite l'action manquante ou trahie.
2. Lisibilité : comprend-on l'histoire sans le texte de Luca, image par image ? La situation se voit-elle dès le premier
   plan ? Chaque gag a-t-il sa préparation ? La chute est-elle le dernier plan, bien visible ?
3. Faisabilité : une seule action par plan (un clip dure 5 s au plus ; ne relève pas les durées, le code les borne) :
   relève CHAQUE plan dont le mouvement enchaîne plusieurs gestes (« ouvre, pose, referme et s'en va ») ;
   tous les personnages visibles sont dans characters ; le décor et les personnages sont décrits avec les mêmes mots
   d'un plan à l'autre ; aucun texte écrit dans l'image ; aucune réplique pour un personnage qui ne parle pas.
4. Paroles : le choix de la mise en scène (muet, quelques répliques, dialogues) est respecté.
ok = true si rien d'important ne cloche. Sinon problems : 8 au plus, chacun précis et actionnable (« plan 7 : le chien
prend le gâteau ET le mange : couper en deux plans », « l'enfant qui se relève péniblement, dans le scénario, n'est
pas montré »). Réponds uniquement en JSON : {"ok": bool, "problems": [...]}."""
