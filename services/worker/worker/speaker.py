"""Qui parle dans un plan de drame, tel que le modèle vidéo le voit (docs/38 §5).

MiniMax H3 lit « Api says in French… » sans savoir qui est Api : sur les plans à deux personnages de « Mamie Pomme »,
il a fait parler la mère 4 fois sur 5 (contrôle Gemini du 29/09 ; Luca l'avait vu). Chaque plan décrit donc ses
personnages par ce qui se voit (le début de leur fiche et leur premier vêtement) et, quand ils sont plusieurs, par
leur place dans l'image de départ (Gemini la lit) ; les autres gardent la bouche fermée. Le contrôle des clips vérifie
ensuite que c'est la bonne bouche qui bouge, et une consigne de Luca pour un plan (Bibliothèque → Retoucher → Plans)
devient une note de réalisation en anglais pour le modèle vidéo.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

from .models import CastMember, ScriptScene, ScriptV1

log = structlog.get_logger(__name__)

_GARMENT = re.compile(r"\b(suit|dress|gown|tuxedo|coat|tailcoat|jacket|hoodie|cardigan|uniform|shirt|boubou|apron|"
                      r"sweater|overalls|headscarf|scarf|veil|t-shirt|jeans|trousers|robe|blouse|vest|waistcoat)\b", re.I)
TAG_WORDS = 14  # le début de la fiche jusqu'à ≈ 14 mots : qui il est et sa tête


def visual_tag(m: CastMember) -> str:
    """Ce que le modèle vidéo voit d'un personnage : le début de sa fiche et son premier vêtement (« a 30-year-old lawyer
    whose whole head is a perfect shiny polished red apple with a small green leaf, a tailored navy suit »)."""
    parts = [p.strip() for p in re.split(r",\s*", m.look or "") if p.strip()]
    if not parts:
        return m.name
    out, i = [parts[0]], 1
    while i < len(parts) and sum(len(p.split()) for p in out) < TAG_WORDS:
        out.append(parts[i])
        i += 1
    if not any(_GARMENT.search(p) for p in out):
        worn = next((p for p in parts[i:] if _GARMENT.search(p)), None)
        if worn:
            out.append(worn)
    return ", ".join(out)


def shot_members(script: ScriptV1, scene: ScriptScene) -> list[CastMember]:
    """Les personnages visibles du plan, celui qui parle d'abord."""
    who = scene.lines[0].who if scene.lines else None
    keys = ([who] if who else []) + [k for k in scene.characters if k != who]
    return [m for k in keys if (m := script.member(k))]


def legend(members: Sequence[CastMember], where: dict[str, str] | None = None) -> str:
    """« Characters in this shot: Api is a 30-year-old lawyer… , on the left; Mamie Pomme is … » ; vide sans personnage."""
    if not members:
        return ""
    where = where or {}
    items = [f"{m.name} is {visual_tag(m)}" + (f", {where[m.key]}" if where.get(m.key) else "") for m in members]
    return "Characters in this shot: " + "; ".join(items) + "."


def listeners(members: Sequence[CastMember]) -> str:
    """Les autres personnages du plan se taisent (« Mamie Pomme keeps her mouth closed… ») ; vide s'il n'y en a pas."""
    names = [m.name for m in members[1:]]
    if not names:
        return ""
    who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"
    return f"{who} {'keeps' if len(names) == 1 else 'keep'} their mouth closed and only listen{'s' if len(names) == 1 else ''}."


class Placement(BaseModel):
    key: str
    where: str = Field(description="en anglais, 2 à 6 mots : « on the left », « in the center, in the background »")


class Placements(BaseModel):
    characters: list[Placement] = Field(default_factory=list)


LOCATE_SYSTEM = """You look at the first frame of an animated film shot and say where each listed character is in the
frame, in 2 to 6 English words (« on the left », « on the right », « in the center, in the foreground »). Use only the
characters listed; if one is not visible, leave it out. Answer in JSON."""


def locate(llm: Any, image: Path, members: Sequence[CastMember]) -> dict[str, str]:
    """Place de chaque personnage dans l'image de départ (modèle de vision) ; {} si un seul personnage ou en cas d'échec :
    le plan garde alors les seules descriptions."""
    if len(members) < 2 or llm is None or not image.is_file():
        return {}
    user = "Characters:\n" + "\n".join(f"- key {m.key}: {visual_tag(m)}" for m in members)
    try:
        found = llm.complete_json(LOCATE_SYSTEM, user, Placements, images=[image])
    except Exception as exc:  # noqa: BLE001  une aide pour le modèle vidéo, jamais une étape bloquante
        log.warning("personnages.place_inconnue", error=str(exc)[:200])
        return {}
    keys = {m.key for m in members}
    return {p.key: " ".join(p.where.split()[:8]).strip(" .") for p in found.characters if p.key in keys and p.where.strip()}


def requirement(script: ScriptV1, scene: ScriptScene) -> str | None:
    """Exigence du contrôle des clips (keyframe_qc) pour un plan dialogué à plusieurs : la bonne bouche bouge."""
    members = shot_members(script, scene)
    if not scene.lines or len(members) < 2:
        return None
    speaker, others = members[0], members[1:]
    return (f"C'est {speaker.name} ({visual_tag(speaker)}) qui parle : sa bouche est ouverte ou en mouvement sur au moins "
            f"une des images 2 à 4 ; " + " ; ".join(f"{o.name} ({visual_tag(o)}) garde la bouche fermée" for o in others)
            + " sur les images 2 à 4.")


class DirectorNote(BaseModel):
    note: str = Field(description="1 à 3 phrases en anglais pour le modèle vidéo")


NOTE_SYSTEM = """You turn a French instruction from the video's author into a short director's note, in English, for an
image-to-video model (MiniMax H3) that animates the first frame of a shot and makes one character say a line. You get
the characters of the shot (what they look like), who must speak, the line, and the instruction. Write 1 to 3 plain
sentences that the video model can act on: who speaks and where they are in the frame, who stays silent with a closed
mouth, gestures, expressions, camera. Never quote the line itself, never ask for text or subtitles on screen, never
name a character without describing them. Answer in JSON."""


def director_note(llm: Any, script: ScriptV1, scene: ScriptScene, instruction: str, image: Path | None = None,
                  where: dict[str, str] | None = None) -> str:
    """La consigne de Luca pour ce plan (« c'est l'ananas qui parle, pas la mère »), en note de réalisation anglaise ;
    en cas d'échec du modèle de langue, la consigne telle quelle (Qwen3-VL, l'encodeur de H3, lit aussi le français)."""
    instruction = " ".join((instruction or "").split())[:600]
    if not instruction:
        return ""
    members = shot_members(script, scene)
    who = members[0].name if scene.lines and members else "nobody"
    user = (f"{legend(members, where)}\nSpeaker: {who}.\nLine: {' '.join(ln.text for ln in scene.lines) or '(none)'}\n"
            f"What moves in the shot: {scene.motion_prompt or scene.visual_prompt}\nAuthor's instruction (French): {instruction}")
    try:
        out = llm.complete_json(NOTE_SYSTEM, user, DirectorNote, images=[image] if image and image.is_file() else [])
        note = " ".join(out.note.split())
    except Exception as exc:  # noqa: BLE001
        log.warning("personnages.note_non_traduite", error=str(exc)[:200])
        note = ""
    return note or f"Director's note (in French): {instruction}"


class VoiceDirection(BaseModel):
    spoken: str = Field(description="la réplique telle que la voix doit la lire : mêmes mots, même sens")
    speed: float = Field(1.0, ge=0.8, le=1.2, description="débit : 0,8 plus lent, 1 inchangé, 1,2 plus rapide")


VOICE_SYSTEM = """Tu règles la lecture d'une réplique française par une voix de synthèse (Qwen3-TTS) qui garde le timbre de
son personnage et ne sait pas jouer une émotion sur commande. D'après la consigne de l'auteur, tu peux seulement :
réécrire la réplique POUR LA PRONONCIATION (« Api » → « A-pi », un nom étranger écrit comme il se dit), ajouter une
ponctuation qui donne des pauses ou de l'élan (« … », « , », « ! »), et changer le débit (0,8 à 1,2). Tu ne changes
jamais le sens, l'ordre ni le choix des mots ; les nombres restent comme ils sont. Si la consigne demande autre chose
(une émotion, une autre voix), rends la réplique telle quelle et le débit à 1. Réponds en JSON."""


def voice_direction(llm: Any, line: str, instruction: str) -> tuple[str, float]:
    """La consigne de Luca pour une nouvelle prise de voix (« dis A-pi », « plus lentement ») : le texte que lit la voix
    (les sous-titres gardent la réplique écrite) et son débit ; la réplique telle quelle en cas d'échec."""
    instruction = " ".join((instruction or "").split())[:600]
    if not instruction or llm is None:
        return line, 1.0
    try:
        out = llm.complete_json(VOICE_SYSTEM, f"Réplique : {line}\nConsigne de l'auteur : {instruction}", VoiceDirection)
    except Exception as exc:  # noqa: BLE001
        log.warning("personnages.consigne_voix_ignoree", error=str(exc)[:200])
        return line, 1.0
    spoken = " ".join(out.spoken.split()) or line
    return spoken, round(min(1.2, max(0.8, out.speed)), 2)
