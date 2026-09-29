"""Retouche d'une vidéo montée (Bibliothèque → Retoucher, docs/34-retouche.md).

Luca corrige à la main, pour une vidéo seulement, ce que le montage automatique a fait : le titre d'accroche, le texte
des sous-titres (« treize cent cinquante » → « 1 350 »), la musique et son départ, les niveaux du mixage, et la voix
(refaite par le step tts, payload « voice »). Les corrections vivent dans videos.retouch (migration 0020) ; le step
assemble les applique à chaque montage, « Refaire le montage » compris. Rien ne change pour les autres vidéos : modèle
de montage, prompts et réglages restent tels quels.

videos.retouch (jsonb ; null = aucune retouche) :
- hook_title : titre d'accroche affiché ; absent ou vide = celui du montage automatique (script) ;
- hook_display : {"duration_s": s} = titre éphémère, affiché s secondes puis effacé en fondu ; {"duration_s": null} =
  toute la vidéo ; absent = la durée du modèle de montage ;
- subtitles : {index de la scène : texte affiché} ; absent = les mots de la voix (la voix lit toujours la narration) ;
- music : {"track": identifiant | null, "start_s": s | null} ; absent = choix du montage, track null = sans musique ;
- audio : niveaux voice_db, music_db, duck_db, solo_db, sfx_db ; absents = ceux du modèle de montage ;
- voice : dernière voix demandée (« moteur:voix »), pour l'écran de retouche.

Un texte retouché est final : il ne repasse pas par la conversion en chiffres (worker/numbers.py), Luca a le dernier mot.
Ses mots sont recalés sur les temps des mots de la voix : un mot inchangé garde son temps, un passage réécrit prend le
temps des mots qu'il remplace, un mot ajouté partage le temps de son voisin.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

import structlog
from pydantic import BaseModel, Field, ValidationError

from .models import WordTiming
from .montage import AudioLayer
from .music import Track
from .numbers import NBSP, tokens
from .subtitles import normalize_text, strip_emojis

log = structlog.get_logger(__name__)

LEVELS = ("voice_db", "music_db", "duck_db", "solo_db", "sfx_db")


class MusicChoice(BaseModel):
    track: str | None = None  # None : sans musique
    start_s: float | None = Field(None, ge=0, le=3600)  # départ dans le fichier ; None : celui de la piste


class HookDisplay(BaseModel):
    """Durée d'affichage du titre d'accroche de cette vidéo (demande de Luca, 29/09 : un titre éphémère sur les drames)."""

    duration_s: float | None = Field(None, ge=1, le=3600)  # éphémère : secondes, fondu compris ; None : toute la vidéo


class Retouch(BaseModel):
    hook_title: str | None = None
    hook_display: HookDisplay | None = None  # absent : la durée du modèle de montage
    subtitles: dict[str, str] = Field(default_factory=dict)
    music: MusicChoice | None = None
    audio: dict[str, float] = Field(default_factory=dict)
    voice: str | None = None

    def __bool__(self) -> bool:
        return bool(self.parts())

    def parts(self) -> list[str]:
        """Ce qui est retouché (journal et résultat du job)."""
        out = []
        if (self.hook_title or "").strip():
            out.append("titre d'accroche")
        if self.hook_display is not None:
            d = self.hook_display.duration_s
            out.append(f"titre d'accroche éphémère ({d:g} s)" if d else "titre d'accroche sur toute la vidéo")
        if self.subtitles:
            out.append(f"sous-titres ({len(self.subtitles)} scène{'s' if len(self.subtitles) > 1 else ''})")
        if self.music is not None:
            out.append("musique")
        if any(k in LEVELS for k in self.audio):
            out.append("mixage")
        if self.voice:
            out.append("voix")
        return out

    def hook(self, auto: str) -> str:
        """Titre d'accroche affiché : celui de la retouche, sinon `auto` (celui du montage automatique)."""
        text = (self.hook_title or "").strip()
        return text or auto

    def subtitle_words(self, words_by_scene: list[list[WordTiming]], scene_indexes: Sequence[int]) -> list[list[WordTiming]]:
        """Mots des sous-titres, ceux des scènes retouchées remplacés par le texte de Luca recalé sur la voix."""
        if not self.subtitles:
            return words_by_scene
        out = []
        for i, words in enumerate(words_by_scene):
            text = self.subtitles.get(str(scene_indexes[i])) if i < len(scene_indexes) else None
            out.append(retime(words, text) if text is not None and words else words)
        return out

    def audio_layer(self, base: AudioLayer) -> AudioLayer:
        """Niveaux du modèle de montage, remplacés par ceux de la retouche ; hors bornes : ceux du modèle."""
        patch = {k: v for k, v in self.audio.items() if k in LEVELS and v is not None}
        if not patch:
            return base
        try:
            return AudioLayer.model_validate({**base.model_dump(), **patch})
        except ValidationError as exc:
            log.warning("retouche.niveaux_invalides", error=str(exc)[:300])
            return base


def load_retouch(db: Any, video_id: Any) -> Retouch:
    """Retouche d'une vidéo ; vide si aucune, si la migration 0020 manque ou si elle est illisible (le montage continue)."""
    try:
        row = db.fetch_one("select to_jsonb(v) -> 'retouch' as retouch from videos v where v.id = %s", (video_id,))
    except Exception as exc:  # noqa: BLE001
        log.warning("retouche.illisible", error=str(exc)[:200])
        return Retouch()
    raw = (row or {}).get("retouch")
    if not raw:
        return Retouch()
    try:
        return Retouch.model_validate(raw)
    except ValidationError as exc:
        log.warning("retouche.invalide", video=str(video_id), error=str(exc)[:300])
        return Retouch()


def forced_music(tracks: Sequence[Track], choice: MusicChoice) -> tuple[Track | None, dict[str, Any]] | None:
    """Musique choisie à la main, même coupée ou hors des formats de la piste ; None si la piste n'est plus dans le
    dossier (le montage reprend alors son propre choix)."""
    if not choice.track:
        return None, {"reason": "sans musique (retouche)"}
    track = next((t for t in tracks if t.id == choice.track and t.path is not None), None)
    if track is None:
        log.warning("retouche.musique_absente", track=choice.track)
        return None
    if choice.start_s is not None:
        track = replace(track, start_s=choice.start_s)
    return track, {"reason": "choisie à la main (retouche)"}


# ---- Sous-titres : texte retouché recalé sur les mots de la voix -------------------------------------------------------

_INNER_SPACE = re.compile(r"(?<=\d)[  ](?=\d)")
_NUMBER = re.compile(r"\d[\d ,.]*")
# Symboles et grands nombres gardés avec leur nombre, dans la même légende (« 30 % », « 2 milliards », « 170 km »)
_GLUED = {"%", "€", "$", "£", "°", "°c", "m€", "md€", "mds€", "million", "millions", "milliard", "milliards", "km", "km²",
          "km/h", "m", "m²", "cm", "mm", "kg"}


def display_tokens(text: str) -> list[str]:
    """Mots affichés d'un texte retouché, coupés sur les espaces normales ; un nombre écrit par groupes (« 1 350 ») reste
    un seul mot, son espace devient insécable (comme au montage automatique, worker/numbers.py), et un symbole ou
    « millions » reste collé à son nombre."""
    clean = strip_emojis(text or "").replace(" ", NBSP)
    out: list[str] = []
    for tok in tokens(clean):
        if not tok.strip(" " + NBSP):
            continue
        tok = _INNER_SPACE.sub(NBSP, tok)
        if out and _NUMBER.fullmatch(out[-1]) and tok.rstrip(".,;:!?…»”\"')").lower() in _GLUED:
            out[-1] = f"{out[-1]}{NBSP}{tok}"
        else:
            out.append(tok)
    return out


def _spread(texts: Sequence[str], start: float, end: float) -> list[WordTiming]:
    """Mots répartis sur [start, end] au prorata de leur longueur (même poids que subtitles.distribute_words)."""
    if not texts:
        return []
    end = max(end, start + 0.04 * len(texts))
    weights = [max(1, sum(ch.isalnum() for ch in t)) + 1.5 for t in texts]
    unit = (end - start) / sum(weights)
    out, t = [], start
    for text, w in zip(texts, weights, strict=True):
        out.append(WordTiming(text=text, start=round(t, 3), end=round(t + w * unit, 3)))
        t += w * unit
    return out


def retime(words: Sequence[WordTiming], text: str) -> list[WordTiming]:
    """Mots du texte retouché d'une scène, recalés sur les mots horodatés de la voix (`words`) : un mot inchangé (casse,
    accents et ponctuation ignorés) garde son temps ; un passage réécrit (« treize cent cinquante » → « 1 350 ») prend
    le temps des mots qu'il remplace ; un mot ajouté partage le temps du mot d'avant (du suivant en tête de scène). Texte
    vide : aucun sous-titre pour la scène."""
    new = display_tokens(text)
    if not new or not words:
        return []
    old_keys = [normalize_text(w.text) for w in words]
    new_keys = [normalize_text(t) for t in new]
    out: list[WordTiming] = []
    ahead: list[str] = []  # mots ajoutés en tête de scène : ils partagent le temps du premier mot suivant
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_keys, new_keys, autojunk=False).get_opcodes():
        if tag == "equal":
            placed = [WordTiming(text=new[j1 + k], start=words[i1 + k].start, end=words[i1 + k].end) for k in range(i2 - i1)]
        elif tag == "replace":
            placed = _spread(new[j1:j2], words[i1].start, words[i2 - 1].end)
        elif tag == "insert":
            if out:
                last = out.pop()
                out.extend(_spread([last.text, *new[j1:j2]], last.start, last.end))
            else:
                ahead.extend(new[j1:j2])
            continue
        else:  # delete : le temps des mots retirés reste à la légende d'avant
            continue
        if ahead and placed:
            first = placed.pop(0)
            placed = [*_spread([*ahead, first.text], first.start, first.end), *placed]
            ahead = []
        out.extend(placed)
    if ahead:  # tous les anciens mots retirés et rien d'autre : le temps de la scène parlée
        out = _spread(ahead, words[0].start, words[-1].end)
    return out
