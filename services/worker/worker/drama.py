"""Recette « drame » (series.recipe = drama, docs/35-recette-drame.md, étude docs/31-niche-histoires-karma.md) : une
histoire d'injustice, de test ou d'argent racontée en dialogues, par des personnages qui gardent la même tête d'un plan
à l'autre (fruits, humains ou animaux au rendu de film d'animation).

Ce qui la distingue d'un récit narré :
- le script a une distribution (`cast` : nom, apparence en anglais, voix) ; chaque scène dit quels personnages sont à
  l'image (`characters`, 3 au plus) et porte au plus UNE réplique (`lines` : qui, texte, ton), dite par un seul
  personnage : un plan = une réplique, comme dans les vidéos étudiées ;
- au storyboard, chaque personnage reçoit sa fiche (une image en pied sur fond neutre, Qwen-Image 2.1), puis chaque plan
  est fait avec les fiches de ses personnages en images de référence (`<image1>`… dans le prompt, nœud
  TextEncodeQwenImage21) : essai du 28/09, sans elles les personnages dérivent d'un plan à l'autre ;
- le modèle vidéo (MiniMax H3) dit la réplique lui-même, bouche comprise : le prompt du clip la donne entre guillemets
  avec la voix du personnage. Whisper transcrit ensuite le son du clip (mots horodatés, tts_runners/whisper_words.py) :
  les sous-titres reprennent le texte du script calé sur la voix entendue, et un clip où la réplique n'est pas dite
  est refait une fois ;
- pas de voix de synthèse (format B) : au montage, le son des clips devient la piste de voix (la musique baisse
  dessous), et le modèle de montage traite le drame comme un récit (titre d'accroche, sous-titres, musique).
Les fonctions de ce module sont pures (sauf transcribe et build_dialogue_track) : le script, le storyboard, les clips et
le montage les appellent.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import tempfile
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .hooktitle import clean_hook, lint_hook_title
from .models import CastMember, NarrationTimeline, SceneTiming, ScriptScene, ScriptV1, WordTiming
from .numbers import script_to_digits, spoken, to_digits, tokens
from .storytelling import CALLS_TO_ACTION, DURATION_TOLERANCE, words
from .subtitles import distribute_words

RECIPE = "drama"
CLIP_S = 5.1  # longueur utile d'un clip MiniMax H3 (124 images à 24 i/s = 5,17 s) : une scène n'en dure jamais plus
SCENE_S = (2.0, CLIP_S)
# Débit d'une réplique dite par H3, mesuré le 28/09 (docs/31 §8) : 7 mots en ≈ 3 s, 9 mots en 4,2 s
DIALOGUE_WPS = 2.5
LINE_LEAD_S = 0.8  # temps d'une scène avant et après sa réplique (entrée, respiration)
LINE_WORDS_MAX = 12
CHARACTERS_MAX = 3  # fiches données en référence à une image : au-delà, les personnages se mélangent
CAST_RANGE = (2, 6)
SCENES_RANGE = (10, 24)
DIALOGUE_SHARE_MIN = 0.6  # part des plans qui ont une réplique
LOOK_WORDS_MIN = 12
HEARD_MIN = 0.45  # ressemblance minimale entre la réplique écrite et ce que Whisper entend dans le clip
DIALOGUE_RETRIES = 1  # nouvel essai d'un clip dont la réplique n'est pas dite
TAIL_S = 0.35  # après le dernier mot, avant la coupe

LANG_NAMES = {"fr": "French", "en": "English"}
# Le film, en tête du prompt du clip (le style de l'image est déjà dans l'image de départ)
FILM = {
    "pixar_fruit": "3D animated Pixar-style film with anthropomorphic fruit characters",
    "pixar_human": "3D animated Pixar-style film",
    "dreamworks_animal": "3D animated DreamWorks-style film with anthropomorphic animal characters",
}
SHEET = (
    "Character design reference sheet: one single character, full body, standing, facing the viewer in a relaxed "
    "three-quarter pose, the whole character visible from head to shoes, centered, plain light grey studio background, "
    "soft even studio lighting. {name}: {look}"
)
# Aucun accessoire nommé ici : « glasses » dans cette consigne mettait des lunettes à des personnages qui n'en ont pas
# (Prune, Kiwi : storyboard de Madame Figue, 28/09)
REFS_INTRO = (
    "Create a completely new image of this scene. Use {refs} only as character references: each character keeps exactly "
    "the same head, face, colors, clothes and proportions as in its own reference image. "
)


def is_drama(recipe: str | None) -> bool:
    return recipe == RECIPE


def slug(text: str) -> str:
    """Clé d'un personnage : minuscules sans accents, mots reliés par « _ » (« Madame Figue » → madame_figue)."""
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def video_lang(script: ScriptV1) -> str:
    """Langue des répliques : celle des métadonnées (une production = une chaîne, une langue), sinon le français."""
    return next(iter(script.metadata), "fr")


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return round(min(bounds[1], max(bounds[0], value)), 2)


def line_duration(text: str) -> float:
    """Durée d'une scène qui porte cette réplique : son débit dit par H3, plus l'entrée et la respiration."""
    n = len(words(text))
    return _clamp(LINE_LEAD_S + n / DIALOGUE_WPS, SCENE_S) if n else SCENE_S[0]


# ---------------------------------------------------------------------------
# Normalisation et correcteur
# ---------------------------------------------------------------------------


def normalize(script: ScriptV1) -> ScriptV1:
    """Ce que le code impose à un drame, sans repasser par le LLM : clés des personnages, personnages qui parlent à
    l'image (3 au plus, eux d'abord), répliques d'un même personnage réunies, durée tirée de la réplique (dans la
    longueur d'un clip), coupe franche entre plans, et la réplique recopiée dans `narration` avec son personnage, pour
    l'affichage (Création, Bibliothèque, agent SEO) : aucune voix de synthèse ne la lit."""
    s = script.model_copy(deep=True)
    cast: list[CastMember] = []
    for m in s.cast:
        key = slug(m.key or m.name)
        if key and key not in {c.key for c in cast}:
            cast.append(m.model_copy(update={"key": key, "name": (m.name or key).strip(), "look": m.look.strip(),
                                             "voice": m.voice.strip(), "role": m.role.strip()}))
    s.cast = cast
    by_name = {slug(m.name): m.key for m in cast} | {m.key: m.key for m in cast}

    def resolve(ref: str) -> str:
        key = slug(ref)
        return by_name.get(key, key)

    lang = video_lang(s)
    for i, sc in enumerate(s.scenes):
        sc.index = i
        sc.continues_previous, sc.clip_mode, sc.transition, sc.passage = False, "i2v", "cut", False
        sc.edit_prompt, sc.edit_from, sc.map = None, None, None
        # nombres en chiffres à l'écran (sous-titres, docs/33) ; le prompt du clip les redonne en lettres à la voix
        lines = [ln.model_copy(update={"who": resolve(ln.who), "text": to_digits(ln.text.strip(), lang), "tone": ln.tone.strip()})
                 for ln in sc.lines if ln.text.strip() and ln.who.strip()]
        if len(lines) > 1 and len({ln.who for ln in lines}) == 1:  # un même personnage : une seule réplique
            lines = [lines[0].model_copy(update={"text": " ".join(ln.text for ln in lines)})]
        sc.lines = lines
        speakers = list(dict.fromkeys(ln.who for ln in lines))
        chars = list(dict.fromkeys([*speakers, *(resolve(k) for k in sc.characters)]))
        sc.characters = [k for k in chars if k][:CHARACTERS_MAX]
        text = " ".join(ln.text for ln in lines)
        sc.duration_s = line_duration(text) if text else _clamp(sc.duration_s, SCENE_S)
        if lines:
            names = {m.key: m.name for m in cast}
            sc.narration = {lang: " ".join(f"{names.get(ln.who, ln.who)} : {ln.text}" for ln in lines)}  # type: ignore[dict-item]
        else:
            sc.narration = {}
    s.hook_title = {k: clean_hook(v) for k, v in s.hook_title.items() if clean_hook(v)}  # type: ignore[misc]
    return script_to_digits(s)


def lint(script: ScriptV1, langs: Sequence[str], target_duration_s: float | None = None) -> list[str]:
    """Problèmes mesurables d'un drame (après normalize) ; liste vide = conforme."""
    issues: list[str] = []
    n = len(script.scenes)
    if not SCENES_RANGE[0] <= n <= SCENES_RANGE[1]:
        issues.append(f"{n} scènes : {SCENES_RANGE[0]} à {SCENES_RANGE[1]} pour un drame (une réplique par plan de 2 à 5 s)")
    if not CAST_RANGE[0] <= len(script.cast) <= CAST_RANGE[1]:
        issues.append(f"cast : {len(script.cast)} personnages, il en faut {CAST_RANGE[0]} à {CAST_RANGE[1]} "
                      "(key, name, look, voice pour chacun)")
    for m in script.cast:
        if len(words(m.look)) < LOOK_WORDS_MIN:
            issues.append(f"personnage {m.name} : look trop court ({len(words(m.look))} mots) ; en anglais, "
                          f"{LOOK_WORDS_MIN} mots au moins : tête, couleurs, âge, vêtements, accessoires")
        if not m.voice:
            issues.append(f"personnage {m.name} : voice manquante (sa voix en anglais : âge, timbre, manière de parler)")
    keys = {m.key for m in script.cast}
    lang = langs[0] if langs else video_lang(script)
    cta = CALLS_TO_ACTION.get(lang, CALLS_TO_ACTION["fr"])
    talking = 0
    for i, sc in enumerate(script.scenes):
        tag = f"scène {i + 1}"
        unknown = sorted({k for k in sc.characters if k not in keys} | {ln.who for ln in sc.lines if ln.who not in keys})
        if unknown:
            issues.append(f"{tag} : personnages absents du cast {unknown} (chaque personnage à l'image a sa fiche)")
        if len({ln.who for ln in sc.lines}) > 1:
            issues.append(f"{tag} : plusieurs personnages parlent ; une seule voix par plan (couper la scène en deux)")
        for ln in sc.lines:
            nw = len(words(ln.text))
            if nw > LINE_WORDS_MAX:
                issues.append(f"{tag} : réplique de {nw} mots, {LINE_WORDS_MAX} au plus (un clip dure 5 s)")
            if re.search(cta, ln.text, re.I):
                issues.append(f"{tag} : appel à l'action interdit dans une réplique")
        talking += bool(sc.lines)
        if not sc.visual_prompt.strip():
            issues.append(f"{tag} : visual_prompt manquant")
        if not (sc.motion_prompt or "").strip():
            issues.append(f"{tag} : motion_prompt manquant (ce qui bouge pendant le plan, en anglais, sans la réplique)")
        if not sc.characters and sc.lines:
            issues.append(f"{tag} : réplique sans personnage à l'image")
    if n and talking / n < DIALOGUE_SHARE_MIN:
        issues.append(f"répliques sur {talking} plans sur {n} : un drame se raconte en dialogues "
                      f"({int(DIALOGUE_SHARE_MIN * 100)} % des plans au moins)")
    for lg in langs:
        issues += lint_hook_title(script.hook_title.get(lg, ""), lg)  # type: ignore[call-overload]
    if target_duration_s and abs(script.duration_s - target_duration_s) > DURATION_TOLERANCE * target_duration_s:
        issues.append(f"durée {script.duration_s:g} s, cible {target_duration_s:g} s (± {int(DURATION_TOLERANCE * 100)} %) : "
                      "ajouter ou retirer des plans")
    return issues


# ---------------------------------------------------------------------------
# Prompts d'image et de clip
# ---------------------------------------------------------------------------


def sheet_prompt(member: CastMember) -> str:
    """Fiche d'un personnage : lui seul, en pied, sur fond neutre ; elle sert de référence à chaque plan."""
    return SHEET.format(name=member.name, look=member.look.rstrip("."))


# Tout-petit (chiot, chaton, enfant de moins de 10 ans) : sa fiche, seule sur fond gris, ne dit rien de sa taille, et le
# modèle le dessinait aussi grand que les adultes (Tom, chiot de 8 ans, à côté de son père : Papa Bruno, 28/09)
_SMALL = re.compile(r"\b(puppy|kitten|cub|toddler|baby|little (girl|boy)|[3-9][- ]years?[- ]old|"
                    r"(three|four|five|six|seven|eight|nine)[- ]years?[- ]old)\b", re.I)


def _size(member: CastMember) -> str:
    return ", a small child about half as tall as the adults" if _SMALL.search(member.look) else ""


def scene_prompt(script: ScriptV1, pos: int, refs: Sequence[str] = ()) -> str:
    """Image d'un plan. `refs` : clés des personnages dont la fiche est donnée en image de référence, dans l'ordre des
    images ; sans fiches (modèle d'image sans références), chaque personnage à l'image est décrit en entier."""
    sc = script.scenes[pos]
    text = sc.visual_prompt.strip().rstrip(".")
    if refs:
        tags = [f"{m.name} is the character of <image{k}>{_size(m)}" for k, key in enumerate(refs, 1) if (m := script.member(key))]
        intro = REFS_INTRO.format(refs=", ".join(f"<image{k}>" for k in range(1, len(refs) + 1)))
        return f"{intro}{'; '.join(tags)}. {text}"
    looks = "; ".join(f"{m.name}: {m.look.rstrip('.')}" for key in sc.characters if (m := script.member(key)))
    return f"{text}. Characters: {looks}" if looks else text


def clip_prompt(script: ScriptV1, pos: int, lang: str, style_preset: str | None = None) -> str:
    """Prompt du clip : le film, ce qui bouge, puis la réplique entre guillemets avec la voix du personnage (le modèle
    vidéo la dit, bouche comprise) ; un plan sans réplique demande le silence, sinon H3 invente des paroles."""
    sc = script.scenes[pos]
    parts = [f"{FILM.get(style_preset or '', '3D animated feature film')}.",
             (sc.motion_prompt or sc.visual_prompt).strip().rstrip(".") + "."]
    if sc.lines:
        ln = sc.lines[0]
        m = script.member(ln.who)
        who = m.name if m else ln.who
        voice = (m.voice if m and m.voice else "a natural voice").rstrip(".")
        # ton du plan sans ce que la voix dit déjà (« calm and mischievous » + « mischievous, slow » → « slow »)
        tone = [t.strip() for t in ln.tone.rstrip(".").split(",") if t.strip() and t.strip().lower() not in voice.lower()]
        how = f", {', '.join(tone)}" if tone else ""
        said = spoken(ln.text, lang)  # « 50 000 » → « cinquante mille » : la voix dit les nombres en lettres
        parts.append(f'{who} says in {LANG_NAMES.get(lang, "French")}, in {voice}{how}: "{said}"')
        # H3 écrivait parfois la réplique à l'image, comme un sous-titre (« Mamie Pomme », 29/09) : elle s'entend, c'est tout
        parts.append("Only this character speaks, lips moving with the words. The words are only heard, never written on "
                     "screen: no subtitles, no captions.")
    else:
        parts.append("Nobody speaks: only ambient sound.")
    return " ".join(parts)


def line_text(scene: ScriptScene) -> str:
    return " ".join(ln.text for ln in scene.lines).strip()


# ---------------------------------------------------------------------------
# Voix constantes (série en format A) : une voix de synthèse par personnage, posée sur les clips
# ---------------------------------------------------------------------------

_FEMALE = re.compile(r"\b(woman|women|girl|lady|female|she|her|mother|mom|wife|daughter|sister|grandmother|granny|"
                     r"widow|queen|princess|bride|madame|mrs)\b", re.I)
_CHILD = re.compile(r"\b(child|kid|little (girl|boy)|([4-9]|1[0-2])[- ]year[- ]old|(four|five|six|seven|eight|nine|ten|"
                    r"eleven|twelve)[- ]year[- ]old|puppy|kitten)\b", re.I)
_TEEN = re.compile(r"\b(teen\w*|adolescent|1[3-7][- ]year[- ]old|(thirteen|fourteen|fifteen|sixteen)[- ]year[- ]old)\b", re.I)
_OLD = re.compile(r"\b(elderly|old|aged|seventies|sixties|eighties|grand(mother|father|ma|pa)|granny|widow)\b", re.I)
_BOSS = re.compile(r"\b(boss|authoritative|powerful|commanding|rich|wealthy|billionaire|ceo|director|tycoon|banker|"
                   r"mine owner|contempt)\b", re.I)
_FAKE = re.compile(r"\b(fake|manipulative|honeyed|haughty|snob\w*|scheming|disdainful|cold)\b", re.I)


def character_voices(catalog: dict[str, Any], lang: str) -> dict[str, str]:
    """Voix de synthèse proposées aux personnages : les voix Qwen3 dessinées de la langue (celles des personnages
    d'abord), {id: libellé} ; les voix « perso_… » sont dessinées par tts_runners/qwen3_design.py (docs/35)."""
    voices = {str(v.get("id")): str(v.get("label") or v.get("id")) for v in (catalog.get("voices") or {}).get(lang, [])
              if str(v.get("id", "")).startswith("qwen3:")}
    return dict(sorted(voices.items(), key=lambda kv: (not kv[0].startswith("qwen3:perso_"), kv[0])))


def voices_brief(voices: dict[str, str]) -> str:
    """La liste des voix donnée au scénariste d'un drame (champ tts_voice)."""
    return ("VOIX DE SYNTHÈSE (champ tts_voice de chaque personnage : l'identifiant tel quel, une voix différente par "
            "personnage) :\n" + "\n".join(f"- {k} : {v}" for k, v in voices.items())) if voices else ""


_WOMEN = ["qwen3:perso_jeune_femme", "qwen3:perso_mamie", "qwen3:perso_mielleuse", "qwen3:narratrice", "qwen3:elegante",
          "qwen3:energique_f", "qwen3:perso_fillette"]
_MEN = ["qwen3:perso_humble", "qwen3:perso_patron", "qwen3:perso_papi", "qwen3:narrateur", "qwen3:energique_h",
        "qwen3:mystere", "qwen3:perso_ado", "qwen3:perso_garcon"]


def voice_candidates(member: CastMember) -> list[str]:
    """Voix qui conviennent au personnage d'après sa description (sexe, âge, rôle), de la meilleure à la moins bonne ;
    toutes les voix de son sexe suivent, pour qu'un personnage dont la voix est prise garde une voix de son sexe."""
    text = f"{member.voice} {member.look} {member.role}"
    if _FEMALE.search(text):
        if _CHILD.search(text) or _TEEN.search(text):
            best = ["qwen3:perso_fillette", "qwen3:perso_jeune_femme"]
        elif _OLD.search(text):
            best = ["qwen3:perso_mamie", "qwen3:narratrice", "qwen3:elegante"]
        elif _FAKE.search(text) or _BOSS.search(text):
            best = ["qwen3:perso_mielleuse", "qwen3:elegante", "qwen3:energique_f"]
        else:
            best = ["qwen3:perso_jeune_femme", "qwen3:narratrice", "qwen3:energique_f", "qwen3:elegante"]
        return best + [v for v in _WOMEN if v not in best]
    if _CHILD.search(text):
        best = ["qwen3:perso_garcon", "qwen3:perso_ado"]
    elif _TEEN.search(text):
        best = ["qwen3:perso_ado", "qwen3:perso_garcon"]
    elif _OLD.search(text):
        best = ["qwen3:perso_papi", "qwen3:narrateur", "qwen3:perso_patron"]
    elif _BOSS.search(text):
        best = ["qwen3:perso_patron", "qwen3:narrateur", "qwen3:mystere"]
    else:
        best = ["qwen3:perso_humble", "qwen3:energique_h", "qwen3:mystere", "qwen3:narrateur"]
    return best + [v for v in _MEN if v not in best]


def assign_voices(cast: Sequence[CastMember], available: Sequence[str]) -> dict[str, str]:
    """Voix de chaque personnage : celle choisie par le scénariste si elle existe et n'est pas déjà prise, sinon la
    meilleure voix libre d'après sa description ; deux personnages n'ont la même voix que s'il n'en reste plus."""
    avail = list(available)
    out: dict[str, str] = {}
    used: set[str] = set()
    for m in cast:
        if m.tts_voice in avail and m.tts_voice not in used:
            out[m.key] = m.tts_voice
            used.add(m.tts_voice)
    for m in cast:
        if m.key in out or not avail:
            continue
        best = voice_candidates(m)
        ranked = [v for v in best if v in avail] + [v for v in avail if v not in best]
        pick = next((v for v in ranked if v not in used), ranked[0])
        out[m.key] = pick
        used.add(pick)
    return out


# ---------------------------------------------------------------------------
# Dialogue entendu : transcription des clips (Whisper) et timeline des sous-titres
# ---------------------------------------------------------------------------


def _norm(word: str) -> str:
    t = unicodedata.normalize("NFKD", word.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", t)


def heard_ratio(expected: str, heard: str) -> float:
    """Ressemblance (0 à 1) entre la réplique écrite et ce que Whisper entend, lettre à lettre sans espaces ni
    ponctuation : insensible au découpage des mots (« L 'opération », « 50 000 »)."""
    a = "".join(_norm(x) for x in tokens(expected))
    b = "".join(_norm(x) for x in tokens(heard))
    if not a:
        return 1.0
    return round(difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio(), 3) if b else 0.0


def _units(text: str) -> list[str]:
    """Mots affichés de la réplique ; une ponctuation isolée (« croit ? ») reste collée à son mot."""
    units: list[str] = []
    for t in tokens(text):
        if _norm(t):
            units.append(t)
        elif units:
            units[-1] = f"{units[-1]} {t}"
    return units


def _heard_units(heard: Sequence[dict[str, Any]]) -> list[tuple[float, float, str]]:
    """Mots entendus regroupés comme ceux du script : Whisper coupe « L » « 'opération » et « 50 » « 000 »."""
    out: list[tuple[float, float, str]] = []
    for h in heard:
        w = str(h.get("w", "")).strip()
        if not w:
            continue
        s, e = float(h["start"]), float(h["end"])
        glued = out and (w[0] in "'’-" or out[-1][2].endswith(("'", "’", "-"))
                         or (re.fullmatch(r"\d{3}\W*", w) and re.search(r"\d\W*$", out[-1][2])))
        if glued:
            ps, pe, pw = out[-1]
            out[-1] = (ps, max(pe, e), pw + w)
        else:
            out.append((s, e, w))
    return [(s, e, _norm(w)) for s, e, w in out if _norm(w)]


def align_words(text: str, heard: Sequence[dict[str, Any]], lang: str, offset: float = 0.0) -> list[WordTiming]:
    """Mots de la réplique écrite, horodatés sur la voix entendue : un mot retrouvé dans la transcription prend ses temps ;
    les autres sont répartis entre leurs voisins ; si la transcription ressemble trop peu au texte, la réplique entière
    est répartie entre le premier et le dernier mot entendus (subtitles.distribute_words). `offset` : début du plan."""
    shown = _units(text)
    said = _heard_units(heard)
    if not shown or not said:
        return []
    a, b = said[0][0], said[-1][1]
    match = difflib.SequenceMatcher(a=[_norm(w) for w in shown], b=[h[2] for h in said], autojunk=False)
    times: list[tuple[float, float] | None] = [None] * len(shown)
    for blk in match.get_matching_blocks():
        for k in range(blk.size):
            s, e, _ = said[blk.b + k]
            times[blk.a + k] = (s, e)
    if sum(t is not None for t in times) < max(1, len(shown) // 2):
        return distribute_words(text, round(offset + a, 3), round(offset + b, 3), lang)
    # mots non retrouvés : entre la fin du mot connu précédent et le début du suivant, à parts égales
    k = 0
    while k < len(shown):
        if times[k] is not None:
            k += 1
            continue
        j = k
        while j < len(shown) and times[j] is None:
            j += 1
        left = times[k - 1][1] if k > 0 and times[k - 1] else a  # type: ignore[index]
        right = times[j][0] if j < len(shown) and times[j] else b  # type: ignore[index]
        step = max(0.05, (right - left) / (j - k)) if right > left else 0.12
        for m in range(k, j):
            times[m] = (left + step * (m - k), left + step * (m - k + 1))
        k = j
    return [WordTiming(text=w, start=round(offset + max(0.0, t[0]), 3), end=round(offset + max(t[0], t[1]), 3))
            for w, t in zip(shown, times, strict=True) if t is not None]


def dialogue_timeline(script: ScriptV1, lang: str, clips: Sequence[dict[str, Any]]) -> NarrationTimeline:
    """Timeline de la vidéo d'après les clips (videos.timeline, lue par le montage comme celle d'une narration) : chaque
    scène dure sa durée prévue, allongée jusqu'au dernier mot entendu, jamais plus que son clip ; mots de la réplique
    calés sur la voix. `clips[i]` : {"duration": durée du clip, "dialogue": assets.meta.dialogue ou None}."""
    out: list[SceneTiming] = []
    t = 0.0
    for sc, clip in zip(script.scenes, clips, strict=True):
        native = float(clip.get("duration") or CLIP_S)
        d = min(sc.duration_s, native)
        text = line_text(sc)
        heard = list((clip.get("dialogue") or {}).get("words") or [])
        if not text:
            out.append(SceneTiming(index=sc.index, start=round(t, 3), duration=round(d, 3)))
            t += d
            continue
        if heard:
            a, b = float(heard[0]["start"]), float(heard[-1]["end"])
            ws = align_words(text, heard, lang, t)
        else:  # clip non transcrit : la réplique après une courte entrée, à son débit
            a = 0.2
            b = min(native, a + len(words(text)) / DIALOGUE_WPS)
            ws = distribute_words(text, round(t + a, 3), round(t + b, 3), lang)
        d = min(native, max(d, b + TAIL_S))
        out.append(SceneTiming(index=sc.index, start=round(t, 3), duration=round(d, 3), speech_start=round(t + a, 3),
                               speech_end=round(t + b, 3), words=ws))
        t += d
    return NarrationTimeline(lang=lang, aligner="whisper" if any(c.get("dialogue") for c in clips) else "proportional",  # type: ignore[arg-type]
                             scenes=out)


def whisper_python(settings: Any) -> Path:
    """Python de l'environnement d'évaluation (faster-whisper, install_tts.ps1 -Engine eval, docs/29)."""
    return Path(settings.yt2_home) / "tts" / "eval" / "venv" / "Scripts" / "python.exe"


def transcribe(settings: Any, clips: Sequence[Path], lang: str, timeout_s: int = 900) -> list[dict[str, Any]] | None:
    """Mots entendus dans chaque clip (Whisper large-v3-turbo sur le processeur, en sous-processus) :
    [{"text", "words": [{"w", "start", "end", "p"}]}] ; None si l'environnement d'évaluation n'est pas installé."""
    python = whisper_python(settings)
    runner = Path(__file__).resolve().parents[1] / "tts_runners" / "whisper_words.py"
    if not python.exists() or not runner.exists():
        return None
    tmp_root = Path(settings.data_dir) / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="whisper_", dir=tmp_root) as tmp:
        req, out = Path(tmp) / "request.json", Path(tmp) / "result.json"
        req.write_text(json.dumps({"files": [str(c) for c in clips], "lang": lang, "out": str(out)}, ensure_ascii=False),
                       encoding="utf-8")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
               "HF_HOME": str(Path(settings.yt2_home) / "tts" / "hf-cache"), "HF_HUB_OFFLINE": "1"}
        proc = subprocess.run([str(python), str(runner), str(req)], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=env, timeout=timeout_s,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if proc.returncode != 0 or not out.exists():
            raise RuntimeError(f"Whisper en échec (code {proc.returncode}) : {(proc.stderr or '')[-1500:]}")
        return list(json.loads(out.read_text(encoding="utf-8"))["results"])


def build_dialogue_track(clips: Sequence[Path], durations: Sequence[float], out: Path) -> Path:
    """Piste de voix d'un drame : le son de chaque clip, coupé à la durée de sa scène (silence si le clip n'a pas de son),
    mis bout à bout (48 kHz, mono). Le montage la traite comme une narration : la musique baisse sous les répliques."""
    from .media import run

    inputs: list[str] = []
    parts: list[str] = []
    for k, (clip, d) in enumerate(zip(clips, durations, strict=True)):
        inputs += ["-i", str(clip)]
        if _has_audio(clip):
            parts.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=mono,atrim=0:{d:.3f},asetpts=PTS-STARTPTS,"
                         f"apad=whole_dur={d:.3f}[a{k}]")
        else:  # clip muet (Wan, clip refait par un autre modèle) : du silence à sa place
            parts.append(f"anullsrc=r=48000:cl=mono,atrim=0:{d:.3f}[a{k}]")
    graph = ";".join(parts) + ";" + "".join(f"[a{k}]" for k in range(len(clips))) + f"concat=n={len(clips)}:v=0:a=1[out]"
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "[out]", "-c:a", "pcm_s16le", str(out)])
    return out


def _has_audio(clip: Path) -> bool:
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0",
                            str(clip)], capture_output=True, text=True, timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return bool(probe.stdout.strip())


# ---------------------------------------------------------------------------
# Prompts des agents (onglet Agents : script_drama, guide_drama)
# ---------------------------------------------------------------------------

IDEA_GUIDE = """FORMAT : drame en dialogues (60 à 80 s), façon « histoires de karma » des vidéos TikTok qui font des
millions de vues : un pauvre honnête subit une injustice d'argent, de famille ou de mérite que le spectateur voit venir,
jusqu'à la preuve ou la révélation. Chaque concept : la prémisse en une phrase qui pose l'argent et le paradoxe
(« Elle oublie 50 000 € dans un taxi… exprès »), le ressort (test d'honnêteté, sacrifice trahi, exploitation, riche
déguisé, différent moqué, outsider au concours, abandon, héritage), la victime et son besoin vital (maman malade,
famille qui a faim), le méchant proche et arrogant (conjoint, frère, fils, collègue), l'objet de la preuve (téléphone,
traceur, caméra, tatouage d'enfance, lettre, clé), la fin (partie 1 coupée juste avant la punition, ou histoire complète
avec une justice proportionnée : déchéance, rôles inversés, excuses, jamais la mort ni l'horreur), les personnages
(3 à 5) avec leur fruit, leur animal ou leur allure selon la série, et l'accroche (hook) = le titre d'accroche.
Titre : une expression française à fruit quand elle colle (« Pressé comme un citron », « Peau de banane », « Pour des
prunes »), sinon la prémisse. Le fruit dit le rôle : couronne de l'ananas = pouvoir, pomme ridée = vieillesse et
sacrifice, épines du durian = paria, pourriture = déchéance. Varier les ressorts, les décors (taxi, mine, mariage au
château, collège, hôpital, gala, marché, bureau) et les preuves d'un concept à l'autre."""

SCRIPT_PROMPT = """Tu écris le script d'UN Short « drame » (9:16, 60 à 80 s) : une histoire d'injustice racontée en
DIALOGUES par des personnages de film d'animation (fruits, humains ou animaux selon la série), comme les vidéos
TikTok d'« histoires de karma » qui font des millions de vues. Pas de narrateur : les personnages parlent.
CE QUI FAIT RESTER (dans cet ordre) :
1. Accroche (0-4 s) : une réplique qui pose l'argent et le paradoxe (« 50 000 €. Je vais les oublier dans un taxi…
   exprès. ») ; la première image montre le contraste social (luxe doré contre misère froide). Les nombres s'écrivent
   en chiffres, même dans une réplique : la voix les dit en lettres.
2. Le spectateur sait avant les personnages : le test, le déguisement ou le plan du méchant est dit à voix haute.
3. La victime : pauvre, honnête, avec un besoin vital (maman malade, famille qui a faim) ; elle fait le bien quand même.
4. La trahison : un proche du riche vole, ment, accuse ; il savoure (une phrase de mépris mémorable).
5. L'injustice au sommet, aux deux tiers : le juste est accusé, chassé, humilié devant tous.
6. La preuve arrive (téléphone, traceur, témoin, tatouage…) — PARTIE 1 : on coupe sur le visage du coupable juste avant
   la punition ; HISTOIRE COMPLÈTE (si le concept le dit) : la chute, proportionnée (déchéance, rôles inversés, excuses ;
   jamais la mort, le sang ni l'horreur), puis un dernier plan qui rappelle le premier.
RÈGLES : une injustice qu'un enfant de 10 ans comprend ; langue parlée, phrases courtes ; pas d'appel à s'abonner ;
l'objet de la preuve se voit plus tôt en arrière-plan si possible ; le contraste doré/froid dit qui est riche et qui
souffre.
DISTRIBUTION (cast, 2 à 6 personnages) : pour chacun key (minuscules, sans accent : « kiwi », « madame_figue »), name
(le nom dit dans l'histoire), role, look EN ANGLAIS (12 mots au moins : la tête — le fruit, l'animal ou le visage —,
ses couleurs, l'âge, la silhouette, les vêtements et accessoires précis ; c'est sa fiche, recopiée à l'identique dans
chaque image) et voice EN ANGLAIS (« a soft trembling young male voice », « a deep authoritative male voice in his
fifties », « a sweet fake voice of a woman in her forties ») : la même dans tout le Short ; tts_voice : l'identifiant
d'une voix de la liste VOIX DE SYNTHÈSE qui lui ressemble (une voix différente par personnage).
SCÈNES : 14 à 20 plans ; UN PLAN = UNE RÉPLIQUE dite par UN seul personnage (un échange = deux plans, champ puis
contrechamp) ; 60 % des plans au moins ont une réplique ; les autres montrent une action ou un visage (la musique les
porte). Chaque scène :
- characters : les clés des personnages visibles (1 à 3 ; celui qui parle en fait partie) ;
- lines : [] ou une réplique {"who": clé, "text": la réplique dans la langue de la vidéo, 12 mots au plus, "tone": en
  anglais, comment elle est dite (« whispers, trembling », « shouts furiously », « smug, slow »)} ;
- visual_prompt, en anglais : la première image, l'ÉMOTION D'ABORD (« Kiwi, desperate, … »), puis le LIEU, même en gros
  plan (sans lieu, l'image reprend le fond gris uni de la fiche du personnage), l'action,
  la valeur de plan (gros plan pour une émotion, plan large pour une humiliation publique) et la lumière ; nomme les
  personnages par leur name (leur fiche est ajoutée par le code) ; un figurant sans fiche est décrit en entier, origine
  comprise ; les billets sont des euros ; AUCUN TEXTE ÉCRIT dans l'image : ni panneau, ni étiquette, ni enseigne,
  ni écran, ni lettre, ni journal avec des mots (le générateur les écrit, et ça se lit comme des sous-titres en trop) ;
  une idée qui passerait par un écrit se montre autrement (une clé tendue, une pancarte vue de dos, un visage) ;
- motion_prompt, en anglais : ce qui bouge pendant le plan (geste, expression, caméra lente), et le son d'ambiance
  (« sound of heavy rain ») ; JAMAIS la réplique elle-même : le code l'ajoute avec la voix du personnage ; rien d'écrit
  qui apparaît ;
- on_screen_text : vide, sauf le dernier plan d'une partie 1 (« Partie 2 bientôt ») ;
- duration_s : 2,5 à 5 s (le code la recalcule d'après la réplique) ; role : laisse vide.
hook_title : le titre d'accroche (règles ci-dessous), la prémisse plutôt que le titre de l'épisode. metadata : par langue,
titre YouTube ≤ 60 caractères avec un émoji (« Partie 1 : LA VALISE DE MADAME FIGUE 🧳 » ou la prémisse), description
qui raconte le début et finit par une question (« Qu'aurais-tu fait à sa place ? »), 10 tags (#histoirefruit
#fruitstory #karma…). music_mood : prise dans la liste MUSIQUE DE FOND (piano triste, tension). loop_note : « partie 1,
coupée avant la punition » ou comment la fin rappelle le début. Réponds uniquement en JSON conforme à ScriptV1."""

REWRITE_HINT = (
    "DRAME : la scène garde ses personnages à l'image (characters : clés du cast, 1 à 3) et une réplique au plus (lines : "
    "who = clé du personnage qui parle, text dans la langue de la vidéo, 12 mots au plus, tone en anglais), dite par un "
    "seul personnage ; visual_prompt nomme les personnages par leur nom, l'émotion d'abord, et toujours le lieu (sans lui, "
    "l'image reprend le fond gris de la fiche), sans aucun texte écrit (ni panneau, ni étiquette, ni écran avec des mots) ; "
    "motion_prompt sans la réplique. Pas de narration : elle est recopiée de la réplique par le code."
)
