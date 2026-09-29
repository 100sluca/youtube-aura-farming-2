"""Le conteur des récits (docs/37-conteur-des-recits.md) : l'histoire s'écrit d'abord EN ENTIER, comme un conteur la
dirait, puis se découpe en plans.

Demandé par Luca le 29/09 devant « Le trésor de Begrâm » (production 3a600c14, 40 s) : huit phrases de faits posés les
uns après les autres (« En 1937, une cache secrète livre… », « La chambre 10 dévoile… », « Joseph et Ria Hackin mettent
au jour… »), sans héros, sans enjeu ni fil, trop court pour comprendre ce qui s'est passé. Cause : le scénariste
écrivait les scènes une à une dans le JSON du script (image, mouvement, narration, texte à l'écran), si bien que chaque
scène devenait un fait isolé, et 40 s ne laissaient pas la place au contexte. Désormais, pour les récits narrés :

1. le conteur (prompt « script », onglet Agents) écrit l'histoire seule (StoryDraft) : l'idée unique, le moteur
   (enquête, ironie dramatique…), le héros et son enjeu, la DERNIÈRE PHRASE d'abord, puis les temps du récit (accroche,
   promesse, contexte, conflit, renversement, réponse, chute), chacun avec ce qu'on voit ; il suit les règles du récit
   (storytelling.RULES, clé rules_storytelling) : les 3 C, l'enjeu, « donc » et « pourtant », montrer plutôt que dire,
   une seule idée, l'accroche sans délai suivie d'une promesse, l'ironie dramatique, des mots d'enfant de 10 ans ;
2. lint_story mesure ce qui se mesure (budget de mots de la durée cible, accroche courte, promesse, contexte avant
   12 s, phrases de 18 mots au plus, rythme fait de phrases courtes ET longues, pas de « et ensuite », chute courte,
   peu de nombres) et le relecteur (prompt script_review) juge le reste avec la checklist ; une réécriture, une
   reprise ;
3. split_scenes découpe le texte en scènes, phrase par phrase, sans en changer un mot : 16 mots dits au plus par scène,
   jamais à cheval sur deux temps, la première phrase de l'accroche seule dans la première scène ; la durée d'une
   scène suit sa narration (débit mesuré de la voix) ;
4. le réalisateur (prompt script_shots) décide les plans (ShotList) : image de départ, mouvement, texte à l'écran,
   scène carte, continuité, musique, métadonnées ; build_script assemble le ScriptV1, que vérifie encore
   storytelling.lint_script.
Les durées cibles des récits passent de 30-40 s à 75 s (migration 0022) : 1 min à 1 min 30, de quoi poser le contexte.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from .hooktitle import clean_hook, lint_hook_title
from .models import LangMetadata, MapSpec, ScriptScene, ScriptV1, ShotList, StoryDraft
from .numbers import to_digits
from .storytelling import (
    BANNED_OPENERS,
    CALLS_TO_ACTION,
    EMPTY_SUPERLATIVES,
    HOOK_WORDS_MAX,
    ON_SCREEN_WORDS_MAX,
    REVEAL_DEADLINE_S,
    SENTENCE_WORDS_MAX,
    said_words,
    sentences,
    words,
)
from .timeline import LEAD_IN, TAIL, WORDS_PER_SECOND

SPEECH_RATE = 3.2  # mots dits par seconde : voix Qwen3-TTS « mystère » à 1,05 (mesuré le 28/09, docs/24)
BUDGET_WPS = 2.9  # mots dits par seconde de VIDÉO, respirations entre les scènes comprises (plan de découpage)
BUDGET_RANGE = (0.85, 1.12)  # part du budget de mots admise
SCENE_WORDS_MAX = 16  # mots dits par scène : au-delà, la phrase suivante ouvre une nouvelle scène
SCENE_S = (2.0, 8.0)  # durée d'une scène (ScriptScene : 8 s au plus)
SCENES_MAX = 24  # ScriptV1
SHORT_SENTENCE, LONG_SENTENCE = 5, 12  # mots dits : phrase qui claque, phrase qui déroule (rythme de Gary Provost)
RHYTHM_SHARE = 0.15  # au moins 15 % de phrases courtes et 15 % de longues, dès 8 phrases
ENDING_WORDS_MAX = 12  # la chute : sèche
HOOK_PROMISE_WORDS_MAX = 22  # accroche + promesse : 6 s (Jenny Hoyos : les deux lignes en 3 s environ, en voix off)
PROMISE_WITHIN = 3  # la promesse vient dans les 3 premiers temps (accroche, promesse…)
NUMBERS_PER_10S = 1.0  # nombres par tranche de 10 s de la durée cible : dates inutiles et chiffres secondaires coupés
NUMBERS_MIN = 4
MAP_FORBIDDEN_ROLES = ("hook", "loop")  # l'accroche montre le sujet de près ; la boucle renvoie au premier plan

# Rôle des scènes (lint_script, rôles historiques du storytelling) selon le temps du récit ; la première scène de
# contexte devient la révélation (« reveal » : la première réponse concrète, avant 12 s), la dernière scène la boucle.
PART_ROLES = {
    "hook": "setup",
    "promise": "setup",
    "context": "setup",
    "conflict": "escalation",
    "twist": "escalation",
    "payoff": "payoff",
    "ending": "payoff",
}
PART_NAMES = {
    "hook": "accroche",
    "promise": "promesse",
    "context": "contexte",
    "conflict": "conflit",
    "twist": "renversement",
    "payoff": "réponse",
    "ending": "chute",
}

AND_THEN = {
    "fr": re.compile(r"(^\W*(ensuite|puis|après ça|après cela|et après)\b)|\bet (ensuite|puis)\b", re.I),
    "en": re.compile(r"(^\W*(then|after that|next)\b)|\band then\b", re.I),
}
_NUMBER = re.compile(r"\d{1,3}(?:[   .]\d{3})+(?!\d)|\d+(?:[.,]\d+)?")


# ---------------------------------------------------------------------------------------------------------------------
# Budget et nettoyage
# ---------------------------------------------------------------------------------------------------------------------


def word_budget(target_s: float) -> tuple[int, int, int]:
    """(minimum, visé, maximum) de mots dits pour une vidéo de `target_s` secondes."""
    aim = round(target_s * BUDGET_WPS)
    return round(aim * BUDGET_RANGE[0]), aim, round(aim * BUDGET_RANGE[1])


def normalize_draft(draft: StoryDraft, lang: str = "fr") -> StoryDraft:
    """Ce que le code impose au récit sans repasser par le LLM : espaces, temps vides retirés, nombres en chiffres
    (règle de Luca, docs/33), titre d'accroche nettoyé."""
    d = draft.model_copy(deep=True)
    for b in d.beats:
        b.text = to_digits(re.sub(r"[ \t\r\n]+", " ", b.text).strip(), lang)
        b.show = re.sub(r"[ \t\r\n]+", " ", b.show).strip()
    d.beats = [b for b in d.beats if b.text]
    d.ending = to_digits(d.ending.strip(), lang)
    d.hook_title = {k: clean_hook(to_digits(v, k)) for k, v in d.hook_title.items() if clean_hook(v)}  # type: ignore[misc]
    return d


def story_words(draft: StoryDraft, lang: str = "fr") -> int:
    return sum(len(said_words(b.text, lang)) for b in draft.beats)


# ---------------------------------------------------------------------------------------------------------------------
# Découpage en scènes
# ---------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Chunk:
    """Une scène du découpage : sa narration (phrases du récit, mot pour mot), son temps, son rôle, sa durée."""

    index: int
    beat: int  # position du temps dans draft.beats
    part: str
    role: str
    text: str
    said: int  # mots dits (un nombre compte pour les mots qui le disent)
    duration_s: float
    show: str


def scene_seconds(said: int) -> float:
    """Durée d'une scène qui dit `said` mots : la voix, le silence avant elle et la respiration après (timeline), au
    dixième supérieur ; jamais moins que ce qu'admet le correcteur (3 mots par seconde)."""
    s = max(said / SPEECH_RATE + LEAD_IN + TAIL, said / WORDS_PER_SECOND)
    return min(SCENE_S[1], max(SCENE_S[0], math.ceil(s * 10 - 1e-9) / 10))


def _groups(text: str, lang: str, words_max: int, first_alone: bool) -> list[list[str]]:
    sents = sentences(text)
    groups: list[list[str]] = []
    if first_alone and sents:
        groups.append([sents[0]])
        sents = sents[1:]
    cur: list[str] = []
    n = 0
    for s in sents:
        k = len(said_words(s, lang))
        if cur and n + k > words_max:
            groups.append(cur)
            cur, n = [], 0
        cur.append(s)
        n += k
    if cur:
        groups.append(cur)
    return groups


def split_scenes(draft: StoryDraft, lang: str = "fr", words_max: int = SCENE_WORDS_MAX) -> list[Chunk]:
    """Le récit en scènes, phrase par phrase, sans changer un mot : les phrases d'un même temps se regroupent jusqu'à
    `words_max` mots dits ; une scène n'est jamais à cheval sur deux temps ; la première phrase de l'accroche est seule
    (le correcteur la veut courte). Au-delà de 24 scènes, le regroupement s'élargit."""
    raw: list[tuple[int, str, str, str]] = []  # (temps, part, texte, show)
    for b, beat in enumerate(draft.beats):
        for g in _groups(beat.text, lang, words_max, first_alone=not raw):
            raw.append((b, beat.part, " ".join(g), beat.show))
    if len(raw) > SCENES_MAX and words_max < 40:
        return split_scenes(draft, lang, words_max + 4)
    roles = ["hook" if k == 0 else PART_ROLES.get(part, "escalation") for k, (_, part, _, _) in enumerate(raw)]
    reveal = next((k for k, r in enumerate(raw) if k > 0 and r[1] == "context"), None)
    if reveal is None:  # pas de temps « contexte » : la première réponse après l'accroche et la promesse
        reveal = next((k for k, r in enumerate(raw) if k > 0 and r[1] not in ("hook", "promise")), None)
    if reveal is not None:
        roles[reveal] = "reveal"
    if len(raw) > 1:
        roles[-1] = "loop"
    out = []
    for k, (b, part, text, show) in enumerate(raw):
        n = len(said_words(text, lang))
        out.append(Chunk(index=k, beat=b, part=part, role=roles[k], text=text, said=n, duration_s=scene_seconds(n), show=show))
    return out


def estimated_starts(chunks: Sequence[Chunk]) -> list[float]:
    t, starts = 0.0, []
    for c in chunks:
        starts.append(t)
        t += c.duration_s
    return starts


# ---------------------------------------------------------------------------------------------------------------------
# Correcteur du récit
# ---------------------------------------------------------------------------------------------------------------------


def lint_story(draft: StoryDraft, lang: str = "fr", target_s: float | None = None, shared: bool = True) -> list[str]:
    """Problèmes mesurables du récit ; liste vide = conforme. `shared=False` : seulement ce que lint_script ne voit pas
    une fois le récit découpé (structure du récit, rythme, « et ensuite », chute, nombres), pour les garder avec le
    script sans doublon."""
    issues: list[str] = []
    beats = draft.beats
    parts = [b.part for b in beats]
    if not beats:
        return ["récit vide"]
    if parts[0] != "hook":
        issues.append("le récit doit commencer par l'accroche (part « hook ») : le sujet et un contraste, sans délai")
    if parts[-1] != "ending":
        issues.append("le récit doit finir par la chute (part « ending ») : la dernière phrase, écrite en premier")
    if "promise" not in parts[:PROMISE_WITHIN]:
        issues.append(
            "pas de promesse juste après l'accroche (part « promise ») : une phrase qui annonce ce qu'on va "
            "découvrir sans le donner, tenue par la réponse"
        )
    if "context" not in parts:
        issues.append("pas de contexte (part « context ») : qui, où, quand, ce que le héros veut et pourquoi ça compte")
    if "conflict" not in parts:
        issues.append("pas de conflit (part « conflict ») : l'obstacle, ce qui s'oppose au héros ou tourne mal")
    elif "context" in parts and parts.index("context") > parts.index("conflict"):
        issues.append("le contexte vient après le conflit : pose d'abord qui, où, quand et ce que le héros veut")

    tagged = [(i, s) for i, b in enumerate(beats) for s in sentences(b.text)]
    lens = [len(said_words(s, lang)) for _, s in tagged]
    and_then = sorted({i + 1 for i, s in tagged if AND_THEN.get(lang, AND_THEN["fr"]).search(s)})
    if and_then:
        issues.append(
            f"« et ensuite » ou « puis » (temps {', '.join(map(str, and_then))}) : c'est une liste ; chaque "
            "temps est une conséquence (« donc », « alors ») ou un obstacle (« mais », « sauf que ») du précédent"
        )
    opening = [k for (i, _), k in zip(tagged, lens, strict=True) if beats[i].part in ("hook", "promise")]
    if sum(opening) > HOOK_PROMISE_WORDS_MAX:
        issues.append(
            f"accroche et promesse : {sum(opening)} mots dits, {HOOK_PROMISE_WORDS_MAX} au plus (6 s) : "
            "une phrase chacune, le sujet tout de suite"
        )
    if len(lens) >= 8:
        need = max(2, math.ceil(RHYTHM_SHARE * len(lens)))
        short = sum(1 for n in lens if n <= SHORT_SENTENCE)
        long = sum(1 for n in lens if n >= LONG_SENTENCE)
        if short < need or long < need:
            issues.append(
                f"rythme monotone : {len(lens)} phrases dont {short} courtes ({SHORT_SENTENCE} mots ou moins) "
                f"et {long} longues ({LONG_SENTENCE} mots ou plus) ; il en faut au moins {need} de chaque, "
                "alternées (une phrase qui claque après une phrase qui déroule)"
            )
    if tagged and lens[-1] > ENDING_WORDS_MAX:
        issues.append(f"chute de {lens[-1]} mots : {ENDING_WORDS_MAX} au plus, sèche, sans morale ni formule de fin")
    if target_s:
        numbers = len(_NUMBER.findall(" ".join(b.text for b in beats)))
        limit = max(NUMBERS_MIN, round(target_s / 10 * NUMBERS_PER_10S))
        if numbers > limit:
            issues.append(
                f"{numbers} nombres dans le récit : {limit} au plus ; garde ceux qui servent l'idée centrale, "
                "coupe les dates qui ne font que dater et les chiffres secondaires"
            )
    for lang_key, title in (draft.hook_title or {}).items():
        issues += lint_hook_title(title, lang_key) if lang_key == lang else []
    if lang not in (draft.hook_title or {}):
        issues += lint_hook_title("", lang)
    if target_s:
        lo, aim, hi = word_budget(target_s)
        total = sum(lens)
        if total < lo:
            issues.append(
                f"{total} mots dits pour {target_s:g} s, trop court : le récit est raccourci, on ne comprend pas ; "
                f"vise {aim} mots (entre {lo} et {hi}) : ajoute environ {aim - total} mots de contexte (qui, où, "
                "pourquoi ça compte) ou un rebondissement du dossier, sans délayer"
            )
        elif total > hi:
            issues.append(
                f"{total} mots dits pour {target_s:g} s, trop long ; vise {aim} mots (entre {lo} et {hi}) : "
                f"retire environ {total - aim} mots, en coupant ce qui ne sert pas l'idée centrale"
            )
    if not shared:
        return issues

    first = tagged[0][1] if tagged else ""
    n = lens[0] if lens else 0
    if n > HOOK_WORDS_MAX:
        issues.append(f"accroche de {n} mots dits : {HOOK_WORDS_MAX} au plus, en une phrase (la promesse vient après)")
    if re.search(BANNED_OPENERS.get(lang, BANNED_OPENERS["fr"]), first, re.I):
        issues.append("accroche qui commence par une formule interdite (bonjour, aujourd'hui, saviez-vous…) : le sujet d'abord")
    long_ones = [(i + 1, k) for (i, _), k in zip(tagged, lens, strict=True) if k > SENTENCE_WORDS_MAX]
    if long_ones:
        where = ", ".join(f"temps {i} ({k} mots)" for i, k in long_ones[:4])
        issues.append(f"phrases trop longues pour la voix : {where} ; {SENTENCE_WORDS_MAX} mots dits au plus")
    text = " ".join(b.text for b in beats)
    if re.search(CALLS_TO_ACTION.get(lang, CALLS_TO_ACTION["fr"]), text, re.I):
        issues.append("appel à l'action interdit (abonnement, like, commentaire, partage) : il casse la boucle")
    m = re.search(EMPTY_SUPERLATIVES.get(lang, EMPTY_SUPERLATIVES["fr"]), text, re.I)
    if m:
        issues.append(f"superlatif vide « {m.group(0)} » : montre le fait qui le prouve")
    chunks = split_scenes(draft, lang)
    starts = estimated_starts(chunks)
    ctx = next((k for k, c in enumerate(chunks) if c.part == "context"), None)
    if ctx is not None and starts[ctx] > REVEAL_DEADLINE_S:
        issues.append(
            f"le contexte commence vers {starts[ctx]:.0f} s : avant {REVEAL_DEADLINE_S:.0f} s (accroche d'une "
            "phrase, promesse d'une phrase)"
        )
    return issues


# ---------------------------------------------------------------------------------------------------------------------
# Ce que lisent le relecteur et le réalisateur
# ---------------------------------------------------------------------------------------------------------------------


def story_listing(draft: StoryDraft, lang: str = "fr") -> str:
    """Le récit tel que le relecteur et le réalisateur le lisent : l'intention, puis les temps numérotés."""
    chunks = split_scenes(draft, lang)
    total = sum(c.duration_s for c in chunks)
    head = [
        f"Idée centrale : {draft.central_idea or '—'}",
        f"Moteur : {draft.engine or '—'}",
        f"Héros et ce qu'il veut : {draft.protagonist or '—'}",
        f"Enjeu (ce qu'il risque) : {draft.stakes or '—'}",
        f"Dernière phrase, écrite en premier : {draft.ending or '—'}",
        f"Titre d'accroche : {draft.hook_title.get(lang) or '—'}",  # type: ignore[call-overload]
        f"Récit ({story_words(draft, lang)} mots dits, environ {total:.0f} s une fois dit) :",
    ]
    body = [
        f"{i + 1}. [{PART_NAMES.get(b.part, b.part)}] {b.text}" + (f"\n   on voit : {b.show}" if b.show else "")
        for i, b in enumerate(draft.beats)
    ]
    return "\n".join([*head, *body])


def scenes_listing(chunks: Sequence[Chunk]) -> str:
    """Les scènes à filmer, telles que le réalisateur les reçoit."""
    lines = []
    for c, start in zip(chunks, estimated_starts(chunks), strict=True):
        lines.append(
            f"index {c.index} · {c.role} · {c.duration_s:g} s (à {start:.0f} s) · temps {c.beat + 1} "
            f"({PART_NAMES.get(c.part, c.part)})\n   narration : « {c.text} »"
            + (f"\n   à montrer (conteur) : {c.show}" if c.show else "")
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------------------------------
# Assemblage du script
# ---------------------------------------------------------------------------------------------------------------------


def missing_shots(chunks: Sequence[Chunk], shots: ShotList) -> list[int]:
    have = {s.index for s in shots.shots if s.visual_prompt.strip()}
    return [c.index for c in chunks if c.index not in have]


def build_script(
    draft: StoryDraft, chunks: Sequence[Chunk], shots: ShotList, lang: str, langs: Sequence[str], title: str = ""
) -> ScriptV1:
    """Le ScriptV1 d'un récit : la narration du conteur, mot pour mot, scène par scène, et les plans du réalisateur.
    Une scène sans plan prend ce que le conteur voulait y montrer ; une seule scène carte, jamais sur l'accroche ni sur
    la boucle (proposée là, elle passe à la révélation : le contexte qui dit où c'est) ; la première scène et la boucle
    sont des coupes ; un texte à l'écran de plus de 5 mots est retiré (il est facultatif)."""
    by_index = {s.index: s for s in shots.shots}
    maps = [
        (c, by_index[c.index].map)
        for c in chunks
        if c.index in by_index and by_index[c.index].map and by_index[c.index].map.place.strip()
    ]  # type: ignore[union-attr]
    map_at: dict[int, MapSpec] = {}
    if maps:
        where, spec = next(((c, m) for c, m in maps if c.role not in MAP_FORBIDDEN_ROLES), maps[0])
        if where.role in MAP_FORBIDDEN_ROLES:
            reveal = next((c.index for c in chunks if c.role == "reveal"), None)
            if reveal is not None:
                map_at[reveal] = spec  # type: ignore[assignment]
        else:
            map_at[where.index] = spec  # type: ignore[assignment]
    scenes: list[ScriptScene] = []
    for c in chunks:
        shot = by_index.get(c.index)
        narration = {lang: c.text}
        on_screen: dict[str, str] = {}
        if shot:
            for other in langs:
                text = (shot.narration.get(other) or "").strip()  # type: ignore[call-overload]
                if other != lang and text:
                    narration[other] = text
            on_screen = {
                k: v.strip() for k, v in shot.on_screen_text.items() if v and v.strip() and len(words(v)) <= ON_SCREEN_WORDS_MAX
            }
        visual = (shot.visual_prompt.strip() if shot and shot.visual_prompt.strip() else "") or c.show or c.text
        scenes.append(
            ScriptScene(
                index=c.index,
                role=c.role,  # type: ignore[arg-type]
                duration_s=c.duration_s,
                continues_previous=bool(shot and shot.continues_previous) and c.index > 0 and c.role != "loop",
                visual_prompt=visual,
                motion_prompt=(shot.motion_prompt or "").strip() or None if shot else None,
                narration=narration,  # type: ignore[arg-type]
                on_screen_text=on_screen,  # type: ignore[arg-type]
                map=map_at.get(c.index),
            )
        )
    metadata = dict(shots.metadata)
    if lang not in metadata:
        name = (draft.hook_title.get(lang) or title or draft.ending or "Histoire vraie")[:100]  # type: ignore[call-overload]
        metadata[lang] = LangMetadata(title=name, description=" ".join(b.text for b in draft.beats[:2])[:5000])  # type: ignore[index]
    loop_note = (
        shots.loop_note or ""
    ).strip() or f"La dernière phrase (« {draft.ending} ») renvoie à l'accroche ; le dernier plan reprend le premier."
    return ScriptV1(
        scenes=scenes,
        loop_note=loop_note,
        metadata=metadata,  # type: ignore[arg-type]
        music_mood=shots.music_mood,
        hook_title=dict(draft.hook_title),
        design_bible=(shots.design_bible or "").strip() or None,
        story=draft,
    )


def told_story(script: dict | None, lang: str = "fr") -> str:
    """Le texte dit d'un script publié (exemple de ton pour le conteur) : son récit s'il en a un, sinon ses narrations."""
    if not isinstance(script, dict):
        return ""
    story = script.get("story") or {}
    beats = story.get("beats") if isinstance(story, dict) else None
    if beats:
        return " ".join(str(b.get("text") or "") for b in beats if isinstance(b, dict)).strip()
    return " ".join(
        str((s.get("narration") or {}).get(lang) or "") for s in script.get("scenes") or [] if isinstance(s, dict)
    ).strip()


def polish_request(issues: Sequence[str]) -> str:
    """Message de la dernière passe : la forme seule (rythme, longueurs, budget), le fond relu ne bouge pas."""
    return (
        "Le correcteur a mesuré ces écarts de FORME :\n- " + "\n- ".join(issues) + "\n\nCorrige-les sans toucher au "
        "fond : garde chaque fait, chaque temps, leur ordre, l'idée centrale et la dernière phrase. Coupe une phrase "
        "longue en deux ; ajoute une phrase courte qui claque (5 mots ou moins) là où l'histoire bascule ; raccourcis "
        "l'accroche ou la promesse ; ajoute ou retire des mots de contexte pour tenir le budget. N'ajoute aucun fait, "
        "aucune pensée ni aucune circonstance qui ne soit pas dans le dossier. Rends l'histoire entière."
    )


def rewrite_request(issues: Sequence[str], problems: Sequence[str]) -> str:
    """Message de réécriture du récit : les corrections de fond du relecteur, puis les écarts mesurables."""
    parts = []
    if problems:
        parts.append("Le relecteur demande ces corrections (le fond du récit) :\n- " + "\n- ".join(problems))
    if issues:
        parts.append("Le correcteur a mesuré ces écarts :\n- " + "\n- ".join(issues))
    return "\n\n".join(parts) + "\n\nRéécris l'histoire en entier en appliquant tout cela, en gardant ce qui marche."


# ---------------------------------------------------------------------------------------------------------------------
# Prompts (onglet Agents : script = le conteur, script_review = le relecteur, script_shots = le réalisateur)
# ---------------------------------------------------------------------------------------------------------------------

STORY_PROMPT = """Tu es le conteur d'une chaîne YouTube Shorts d'histoires racontées en voix off (9:16) : tu sais faire d'une
page d'encyclopédie une histoire qu'on écoute jusqu'au bout. Tu écris L'HISTOIRE, pas les images : le texte que la voix
de synthèse dira, mot pour mot, du premier au dernier ; le réalisateur la découpera ensuite en plans. Tu reçois le
thème et son brief, les règles du récit, l'idée (accroche, angle, prémisse), ses faits sourcés, le DOSSIER (les pages
sources entières, version anglaise comprise) et la durée visée avec son budget de mots.

MÉTHODE, dans l'ordre des champs du JSON :
1. central_idea : cherche dans le dossier l'histoire qui se cache derrière le sujet (qui a voulu quelque chose, ce qui
   s'y est opposé, ce que ça a coûté, l'ironie ou le renversement), puis dis en une phrase l'idée ou l'émotion unique
   que tout le récit va servir. Même sujet que l'idée, mais tu prends le meilleur angle que le dossier permet.
2. engine : le moteur du récit — enquête (un mystère, des indices, la réponse), ironie dramatique (le spectateur voit
   ce que le héros refuse de voir), course contre la montre, trésor sous les yeux, l'erreur à un million, David
   contre Goliath, l'obstination d'une vie, l'arroseur arrosé…
3. protagonist : le héros et ce qu'il veut ; stakes : ce qu'il perd s'il échoue, en concret. Un sujet sans héros en a
   un : celui qui l'a cherché, construit, défendu ou perdu ; pour un animal, l'animal lui-même (ou sa proie).
4. ending : la DERNIÈRE PHRASE, écrite avant le milieu du récit, 12 mots au plus : la chute sèche, l'ironie, le twist
   ou le retour à l'accroche, assez forte pour être partagée seule ; comme le Short repart en boucle, elle peut
   préparer la première phrase. Tout le récit y mène.
5. beats : le récit, temps par temps (part), chacun avec son texte (text) et ce qu'on voit (show) :
   - hook : UNE phrase de 14 mots au plus : le sujet concret dès les premiers mots et un contraste (ce qu'on croit
     contre ce qui est, un paradoxe, un prix absurde, une erreur énorme). Relis-la seule : si elle peut se lire de
     deux façons, réécris-la.
   - promise : UNE phrase qui annonce la fin sans la donner (« Pourtant, personne n'a le droit d'en toucher une seule
     pièce. ») ; un fait de plus (« personne n'y avait touché depuis 2 000 ans ») n'est pas une promesse. La réponse
     la tiendra. Accroche et promesse tiennent en 6 s : 22 mots dits au plus à elles deux.
   - context : le point de départ, pour un spectateur qui ne connaît rien : qui, où (un repère connu : un pays, une
     ville, une distance), quand (l'année ou le siècle, une fois), ce que le héros veut et pourquoi ça compte. Il
     commence avant la 12e seconde ; sa 1re phrase fait la transition sans casser le rythme, une phrase de récit qui
     relance (« Alors, il fait l'impensable. »), jamais « c'est parti » ni « laissez-moi vous expliquer ». Assez de
     contexte pour tout comprendre, sans cours d'histoire.
   - conflict (un ou plusieurs temps, le cœur du récit, la moitié environ) : la danse des « mais » et des « donc » :
     l'obstacle, la tentative, l'imprévu, la complication, le prix payé ; un rebondissement toutes les 7 à 8 s, une
     relance quand l'histoire s'installe (« Et ça empire. ») ; 1 à 4 phrases par temps, chacun finit sur une question
     ouverte.
   - twist (facultatif, avant ou après la réponse) : le renversement qu'on n'a pas vu venir, tiré du dossier.
   - payoff : la réponse à la promesse, le moment le plus fort.
   - ending : la phrase d'ending, mot pour mot ; rien après.
   En ironie dramatique : context = l'évidence (ce que tout le monde aurait fait), conflict = le héros s'entête et
   double la mise, payoff = le retour de bâton.
   show : ce qu'on VOIT pendant ce temps, en français, concret et filmable (un lieu, une action, un objet, un geste,
   l'époque) : le « montrer » du récit. Celui du hook montre le sujet lui-même, de près, dès la première image :
   jamais une carte ni une vue de l'espace (la carte d'un lieu réel vient au contexte).
6. hook_title : le titre d'accroche gravé à l'écran (règles fournies).

ÉCRITURE (le texte est lu par une voix de synthèse, environ 3 mots par seconde) :
- Tiens le budget de mots DITS du message : trop court, le récit est raccourci et on ne comprend pas ; trop long, il
  traîne. Un nombre compte pour les mots qui le disent (« 1937 » = mille neuf cent trente-sept = 4 mots).
- Phrases de 3 à 16 mots, 18 au plus ; présent de narration, voix active, une idée par phrase. Le rythme se compte :
  au moins 1 phrase sur 5 fait 5 mots ou moins (« Personne ne revient. », « Il reste 3 jours. »), placée après une
  longue, là où l'histoire bascule ; au moins 1 sur 5 fait 12 mots ou plus.
- Nombres et années en chiffres (« 852 morts », « en 1937 », « 2 000 ans ») ; une date se dit par son année seule.
  Pas de sigle, pas de parenthèse, pas d'énumération.
- Séries documentaires : chaque fait, nom, nombre, date ou citation vient des faits ou du DOSSIER ; rien de complété
  de mémoire. Tu n'inventes rien pour dramatiser : ni motivation, ni pensée, ni émotion, ni réplique, ni circonstance
  (comment quelqu'un est mort, combien de temps une chose a duré, un geste que le dossier ne décrit pas). Le héros veut
  ce que ses actes montrent ; quand le dossier reste vague (« disparaissent tragiquement »), tu restes vague. Tu
  racontes l'enjeu, l'ironie, ce que ça change ; dans le doute, dis moins. La tension vient de l'ordre des faits et des
  « mais », pas d'inventions.

EXEMPLE DE CONSTRUCTION (le galion San José, pour la forme seulement ; les faits de ton récit viennent de ton dossier) :
hook « Ce bateau au fond de la mer transporte des milliards en or. » → promise « Pourtant, personne n'a le droit d'en
toucher une seule pièce. » → context « En 1708, le galion espagnol San José quitte l'Amérique, chargé d'or et
d'émeraudes pour payer une guerre. » → conflict « Mais près des côtes de Colombie, une flotte anglaise l'attaque. Le
navire explose. Il coule avec presque tout son équipage. Pendant 300 ans, tout le monde le cherche. » → payoff « En
2015, des robots sous-marins le retrouvent enfin. Intact. » → twist « Mais au lieu d'enrichir quelqu'un, le trésor
déclenche une bataille de tribunaux entre plusieurs pays. » → ending « L'or est toujours au fond de l'eau. »

Réponds uniquement en JSON conforme à StoryDraft : {"central_idea": "…", "engine": "…", "protagonist": "…", "stakes":
"…", "ending": "…", "beats": [{"part": "hook", "text": "…", "show": "…"}, …], "hook_title": {"fr": "…"}}."""

REVIEW_PROMPT = """Tu es le rédacteur en chef d'une chaîne YouTube Shorts d'histoires racontées. Tu relis L'HISTOIRE d'un
Short (le texte que dira la voix, temps par temps) avant qu'elle soit découpée en plans, à la place d'un spectateur qui
ne connaît rien au sujet et qui décroche dès qu'il s'ennuie ou ne comprend plus. Tu ne réécris pas : tu dis précisément
ce qui ne va pas et quoi faire, en t'appuyant sur le dossier quand il y en a un.
Vérifie, dans cet ordre :
1. Accroche : le sujet concret est-il dit dès la 1re phrase, avec un contraste qui intrigue ? Relue seule, se lit-elle
   d'une seule façon, ferait-elle un bon titre ? La 2e phrase annonce-t-elle la fin, et le récit la tient-il ?
2. Contexte : vers la 12e seconde, un spectateur qui ne connaît rien sait-il qui, où, quand, ce que le héros veut et
   pourquoi ça compte ? Manque-t-il un repère pour comprendre la suite ? Un récit raccourci, qui juxtapose des faits
   sans les relier, est le défaut n° 1.
3. Fil : chaque temps est-il une conséquence (donc) ou un obstacle (mais) du précédent ? Changer le mot ne suffit
   pas : relève toute juxtaposition de faits, tout « et ensuite », toute date qui ne sert qu'à dater. Y a-t-il un
   rebondissement toutes les 7 à 8 secondes, ou un passage qui s'installe sans relance ?
4. Enjeu et conflit : sait-on ce que le héros risque ? L'obstacle est-il concret, avec sa raison ? Le dossier
   contient-il un conflit, une ironie ou un renversement plus fort que le récit n'utilise pas ?
5. Une seule idée : tout sert-il l'idée centrale ? Relève les détails, noms, grades et chiffres secondaires à couper.
6. Montrer : les émotions passent-elles par des actions et des détails concrets, ou par des adjectifs ?
7. Langue et rythme : des mots qu'un enfant de 10 ans comprend ? Des phrases de longueurs variées ?
8. Fin : la dernière phrase claque-t-elle, pourrait-elle être partagée seule, renvoie-t-elle à l'accroche ? Le récit
   s'arrête-t-il dès que la promesse est tenue et la chute dite ?
9. Exactitude : chaque fait, nom, nombre, date ou citation est-il dans les faits ou le dossier ? Relève aussi ce qui
   est inventé pour dramatiser : une motivation, une pensée, une émotion, une durée, un geste, une circonstance (une
   mort « au combat » quand le dossier dit seulement « disparus »). Le titre d'accroche dit-il vrai, sans contresens ?
ok = true seulement si l'histoire peut partir telle quelle. problems : 8 au plus, du plus grave au moins grave, chacun
avec le temps visé et la correction attendue (« temps 3 : on ne sait pas ce que risquent les fouilleurs ; dire ce qui
les menace, le dossier le raconte »).
Réponds uniquement en JSON : {"ok": true ou false, "problems": ["…"]}."""

SHOTS_PROMPT = """Tu es le réalisateur d'un YouTube Short (9:16) raconté en voix off. L'histoire est écrite et relue ; le code
l'a découpée en scènes, phrase par phrase. Pour chaque scène tu reçois son numéro (index), son rôle, sa durée, son
temps dans le récit, sa narration (qui ne change pas) et ce que le conteur veut y montrer. Tu décides les PLANS : pour
chaque scène, une image de départ et un mouvement qu'un modèle d'image puis un modèle vidéo réussissent, et qui
MONTRENT ce que dit la narration à ce moment-là. Tu ne réécris pas la narration.
Pour chaque scène (shots : une entrée par index reçu, dans l'ordre, sans en sauter) :
- visual_prompt, en anglais : la PREMIÈRE image, décrite comme une photo de cinéma (sujet, action figée, lieu, époque,
  matières, lumière, valeur de plan, objectif), sans texte, sans visage reconnaissable ;
- motion_prompt, en anglais : le seul mouvement de la scène à partir de cette image (caméra ou action), lent ;
- on_screen_text (facultatif, souvent vide) : 5 mots au plus, un nombre en chiffres ou un mot-clé que la narration
  dit à ce moment ;
- continues_previous : voir la consigne de continuité ;
- map : la scène carte (plus bas), sinon absent ;
- narration : SEULEMENT si le message demande d'autres langues que celle du récit, la traduction de la narration de
  la scène dans chacune ; sinon {}.
Ensemble :
- design_bible, en anglais, une phrase : ce qui est commun à toutes les images (l'époque, le lieu, la lumière, le
  rendu, la tenue du héros) ; le code l'ajoute à chaque image, ne la recopie pas dans les visual_prompt.
- Une histoire suivie en images : le héros, le lieu et l'objet principal gardent la même description d'une scène à
  l'autre ; chaque scène change de valeur de plan ou d'échelle par rapport à la précédente.
- La scène 1 montre le sujet de l'accroche dès la première image ; l'image la plus forte va au renversement ou à la
  réponse ; la dernière scène renvoie visuellement à la première (même lieu, même objet, même cadrage) : loop_note
  dit comment.
SCÈNE CARTE (champ map) : quand le sujet a un lieu réel (ville, île, canal, fleuve, monument, montagne, route d'une
expédition), UNE scène, de préférence celle du contexte qui dit où c'est, est une carte rendue par le code : la caméra
descend de l'espace jusqu'au lieu, dont le tracé se dessine. map.place = le lieu, tel que le titre de sa page
Wikipédia (« Canal Rhin-Main-Danube ») ; map.ends = 0 à 2 repères aux deux bouts d'un tracé (["Bamberg", "Kelheim"]) ;
map.context = 0 à 3 grands repères montrés avant le zoom pour situer (["Mer du Nord", "Mer Noire"]) ; map.lines = 0 à
3 fleuves, routes ou frontières que le lieu relie (titres Wikipédia). Les repères s'affichent tels quels : écris-les
dans la langue de la vidéo. Son visual_prompt décrit quand même le lieu vu du ciel (secours). Choisis une scène d'au
moins 3 s, jamais la scène 1 (l'accroche montre le sujet lui-même, de près) ni la dernière ; aucune carte pour un
sujet sans lieu précis.
music_mood : l'ambiance de la musique de fond, prise dans la liste MUSIQUE DE FOND (identifiant tel quel), selon
l'émotion de l'histoire. metadata : brouillon par langue (titre ≤ 60 caractères, description qui raconte le début sans
donner la fin, 10 tags), affiné ensuite par l'agent SEO.
Réponds uniquement en JSON conforme à ShotList : {"design_bible": "…", "shots": [{"index": 0, "visual_prompt": "…",
"motion_prompt": "…", "on_screen_text": {}, "continues_previous": false, "narration": {}}, …], "loop_note": "…",
"music_mood": "…", "metadata": {"fr": {"title": "…", "description": "…", "tags": ["…"]}}}."""
