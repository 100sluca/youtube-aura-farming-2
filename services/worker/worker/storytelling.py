"""Storytelling addictif : les règles communes à toutes les séries, injectées dans les prompts et vérifiées en code.

Deux usages :
- RULES : le texte donné aux agents idée et script, avec le brief de la série (worker/series.py) ;
- lint_script() : ce qui se mesure est vérifié après coup. Un script en défaut repart une fois au LLM avec
  la liste des problèmes (steps/script.py) ; les problèmes restants sont conservés dans productions.lint.

D'où viennent ces règles : la rétention d'un Short se joue dans les 3 premières secondes, puis à chaque
question refermée (il faut en ouvrir une autre), et à la fin (un dernier plan qui renvoie au premier fait
repartir la lecture). S'y ajoutent les contraintes de ce pipeline : une voix de synthèse (phrases courtes,
pas de sigles), des scènes de 5 s générées par IA (un seul mouvement par plan) et un écran de téléphone.
Voir docs/12-series-de-contenu-et-storytelling.md.

Section « enjeu et émotion » ajoutée le 28/09 après la vidéo du canal Rhin-Main-Danube (docs/24) : « controversé »
annoncé sans jamais dire pourquoi, ni à quoi sert le canal, ni ce qui était en jeu ; 1,4 s de blanc par scène. Ce qui
ne se mesure pas (promesse tenue, enjeu compris) est vérifié par la relecture éditoriale (steps/script.py).
Règle « image rattachée au sujet » ajoutée le 28/09 après le storyboard du miroir secret (docs/27) : « un pivot
invisible » illustré par un mécanisme seul, sans le miroir ; une scène ratée se réinvente dans Création.
Règle « nombres en chiffres » du 28/09 (docs/33) : ils s'affichent en chiffres (« 852 morts », pas « huit cent
cinquante-deux ») ; la voix les lit en toutes lettres et le correcteur compte les mots qu'elle dit (worker/numbers.py).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from .models import ScriptV1
from .numbers import script_to_digits, spoken
from .timeline import WORDS_PER_SECOND

HOOK_WORDS_MAX = 14  # première phrase du Short
SENTENCE_WORDS_MAX = 18  # au-delà, une voix de synthèse perd l'auditeur
ON_SCREEN_WORDS_MAX = 5
REVEAL_DEADLINE_S = 12.0  # la scène « reveal » doit commencer avant
DURATION_TOLERANCE = 0.25  # écart admis à la durée cible
NARRATION_FILL_MIN = 0.7  # part de la durée couverte par la voix, au moins (sinon des blancs cassent le rythme)
MAP_SCENES_MAX = 1
MAP_DURATION_S = (4.0, 7.0)  # la descente depuis l'espace puis le tracé : ni précipités, ni interminables
ROLES = ("hook", "setup", "reveal", "escalation", "payoff", "loop")

RULES = """RÈGLES DU STORYTELLING (Shorts racontés de 30 à 50 s, voix de synthèse, images générées par IA)

La rétention se joue en trois temps : retenir dans les 3 premières secondes, ne jamais refermer une
question sans en ouvrir une autre, et finir sur un plan qui renvoie au début pour que le Short reparte.
Mais on ne reste que si l'on comprend l'ENJEU : ce que c'est, pourquoi ça compte, ce qui s'y est joué.

1. STRUCTURE : une scène de 4 à 6 s par tranche de 5 s de la durée cible (6 scènes pour 30 s, 8 pour
40 s), chacune avec un rôle (champ role) :
- hook (scène 1, 0-3 s) : la promesse ou la contradiction, en une phrase de 14 mots au plus, concrète
  (un chiffre, un lieu, un nom). Elle crée une question dans la tête du spectateur sans la poser.
  L'image montre le sujet immédiatement : pas d'introduction, pas de « bonjour », pas de « saviez-vous ».
- setup (scène 2) : ce que c'est, où c'est et pourquoi ça compte (à quoi ça sert, ce qui est en jeu).
  Pour un lieu réel, c'est la scène carte. Elle se termine sur une boucle ouverte.
- reveal (avant la 12e seconde) : la première réponse concrète, qui ouvre aussitôt une nouvelle question.
- escalation (une ou plusieurs scènes) : l'obstacle, le conflit, le prix payé : chiffres, comparaisons,
  conséquences, un renversement amené par « mais » ou « sauf que ». Chaque scène se termine sur un
  élément non résolu.
- payoff (avant-dernière scène) : la réponse finale et l'image la plus forte ; la phrase que l'on retient.
- loop (dernière scène) : le dernier plan renvoie au premier (même lieu, même objet, même cadrage) et la
  dernière phrase rebondit sur l'accroche, pour que la relecture soit naturelle. Jamais d'appel à l'action
  (abonne-toi, like, commente) : il casse la boucle.

2. ENJEU ET ÉMOTION (ce qui fait qu'on s'attache) :
- Avant la 10e seconde, le spectateur sait ce que c'est, où c'est, et pourquoi ça compte : à quoi ça
  sert, ce que ça change, ce qui était en jeu. Sans enjeu, les faits ne sont qu'une liste.
- Chaque promesse est tenue : un mot qui intrigue (« controversé », « secret », « maudit », « fou »,
  « personne ne savait ») est expliqué par un fait concret dans la même scène ou la suivante. Jamais un
  mystère annoncé puis laissé sans réponse.
- Un conflit : ce qui s'y opposait (la nature, l'argent, des adversaires, le temps) et ce que ça a coûté
  (des années, des vies, un paysage, une fortune).
- De l'humain : qui l'a voulu, qui s'y est opposé, qui l'a payé ; un nom, une date, une citation courte
  tirée des sources.
- Une échelle qu'on ressent : comparer à du connu (« 2 fois la tour Eiffel », « de la mer du Nord à
  la mer Noire »).
- Le ton d'un conteur, pas d'une encyclopédie : faire ressentir l'obstination, l'absurde, la perte ou la
  fierté par les faits, pas par des adjectifs.
- Chaque scène apporte une information nouvelle : aucune phrase de remplissage (« ce projet colossal »,
  « une histoire fascinante »), aucune redite.

3. VOIX (le texte sera lu par une voix de synthèse, environ 3 mots par seconde) :
- Phrases de 4 à 16 mots, une idée par phrase, présent de narration, voix active.
- Le texte remplit la scène sans la déborder : 10 à 15 mots par scène de 5 s. Les blancs cassent le rythme.
- Du concret à chaque scène : un chiffre, un lieu, une matière, un nom. « 300 bouteilles » plutôt que
  « beaucoup de bouteilles ».
- Les phrases s'enchaînent par « mais » et « donc », jamais par « et puis ».
- Pas d'adjectifs empilés ni de superlatifs vides (incroyable, hallucinant) : le fait est plus fort que le
  commentaire. Pas de sigles, pas de parenthèses ; une date se dit par son année seule, sans le jour ni le mois.
- Nombres et années TOUJOURS en chiffres, jamais en toutes lettres, comme ils s'affichent dans les sous-titres
  (« 852 morts », « en 1994 », « 1 350 tonnes », « 3 millions », « 19e siècle », « 40 % ») ; la voix les lit en
  toutes lettres d'elle-même. Un nombre compte pour les mots qui le disent (« 1994 » : mille neuf cent
  quatre-vingt-quatorze).
- « Vous » et « imaginez » au plus deux fois par Short.
- Séries documentaires : chaque affirmation vient du dossier fourni (faits de l'idée et pages sources) ;
  aucun chiffre, nom, date ou citation inventé. Dans le doute, dire moins.

4. IMAGE (une image de départ puis quelques secondes d'animation par scène) :
- Le sujet est reconnaissable dès la première image de la scène 1. L'image la plus spectaculaire est
  réservée à la révélation ou au payoff.
- Chaque image se rattache au sujet au premier coup d'œil : un détail (mécanisme, matière, outil) se
  montre sur le sujet et dans son décor, jamais seul sur fond neutre ; un objet qui revient d'une scène
  à l'autre est décrit avec les mêmes mots (le modèle d'image ne connaît que le prompt de sa scène).
- Une seule action ou un seul mouvement de caméra par scène, lent et lisible : travelling avant,
  panoramique, mécanisme qui s'ouvre, animal qui frappe.
- Un changement visuel toutes les 3 à 5 secondes : d'une scène à l'autre, changer de valeur de plan
  (large puis gros plan) ou d'échelle.
- Récits historiques : l'époque se voit (costumes, outils, engins et matériaux du moment raconté).
- Lieu réel : une scène carte le situe (vue de l'espace, zoom, tracé) ; elle est rendue par le code.
- Cadrage vertical pour un téléphone : sujet centré, gros plans, fort contraste, sans texte dans l'image,
  sans visage reconnaissable.
- Texte à l'écran seulement pour un chiffre ou un mot-clé, 5 mots au plus."""

BANNED_OPENERS = {
    "fr": r"^\W*(bonjour|salut|hello|coucou|bienvenue|aujourd'hui|dans cette vidéo|saviez[- ]vous|savez[- ]vous|est-ce que vous saviez)",
    "en": r"^\W*(hello|hi there|hey guys|hey everyone|welcome|today|in this video|did you know|do you know)",
}
# Formes d'appel seulement : « partage » seul refusait « la ligne de partage des eaux » (canal Rhin-Main-Danube, 28/09 :
# le fait a disparu à la reprise), « commente » seul refusait « il commente ».
CALLS_TO_ACTION = {
    "fr": r"\b(abonne[- ]toi|abonnez[- ]vous|abonnement|likez?|commentez|en commentaires?|partagez|partage[rz]? (cette|la) vidéo"
          r"|n'oubliez pas de|cliquez?)\b",
    "en": r"\b(subscribe|hit the like|like this video|comment below|share this|don't forget to|click the)\b",
}
EMPTY_SUPERLATIVES = {
    "fr": r"\b(incroyable|hallucinant|époustouflant|de ouf|dingue)\b",
    "en": r"\b(insane|mind-blowing|unbelievable|crazy)\b",
}


def words(text: str) -> list[str]:
    return re.findall(r"[\w'’-]+", text)


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s]


def scene_words_max(duration_s: float) -> int:
    """Mots prononçables dans la scène sans l'allonger (respiration comprise)."""
    return max(4, int(duration_s * WORDS_PER_SECOND))


def said_words(text: str, lang: str = "fr") -> list[str]:
    """Mots que dit la voix : un nombre en chiffres compte pour ses mots (« 1992 » : mille neuf cent quatre-vingt-douze)."""
    return words(spoken(text, lang))


def lint_hook(hook: str, lang: str = "fr") -> list[str]:
    issues = []
    n = len(said_words(hook, lang))
    if n > HOOK_WORDS_MAX:
        issues.append(f"accroche de {n} mots : {HOOK_WORDS_MAX} au plus")
    if re.search(BANNED_OPENERS.get(lang, BANNED_OPENERS["fr"]), hook, re.I):
        issues.append("accroche qui commence par une formule interdite (bonjour, aujourd'hui, saviez-vous…)")
    return issues


def lint_script(script: ScriptV1, langs: Sequence[str] = ("fr",), target_duration_s: float | None = None) -> list[str]:
    """Problèmes mesurables d'un script ; liste vide = conforme. `langs` : langues dont la narration est vérifiée
    (aucune pour un format B, sans voix)."""
    issues: list[str] = []
    scenes = script.scenes
    starts: list[float] = []
    t = 0.0
    for s in scenes:
        starts.append(t)
        t += s.duration_s

    if any(s.role for s in scenes):
        if scenes[0].role != "hook":
            issues.append("la scène 1 doit avoir le rôle hook")
        if scenes[-1].role != "loop":
            issues.append("la dernière scène doit avoir le rôle loop (retour au premier plan)")
        reveal = next((i for i, s in enumerate(scenes) if s.role == "reveal"), None)
        if reveal is None:
            issues.append("aucune scène de rôle reveal")
        elif starts[reveal] > REVEAL_DEADLINE_S:
            issues.append(
                f"la révélation (scène {reveal + 1}) commence à {starts[reveal]:.0f} s : "
                f"elle doit commencer avant {REVEAL_DEADLINE_S:.0f} s"
            )
    else:
        issues.append("aucun rôle de scène (role : hook, setup, reveal, escalation, payoff, loop)")

    for lang in langs:
        openers = BANNED_OPENERS.get(lang, BANNED_OPENERS["fr"])
        cta = CALLS_TO_ACTION.get(lang, CALLS_TO_ACTION["fr"])
        vague = EMPTY_SUPERLATIVES.get(lang, EMPTY_SUPERLATIVES["fr"])
        for i, s in enumerate(scenes):
            tag = f"[{lang}] scène {i + 1}"
            text = s.narration.get(lang, "").strip()  # type: ignore[call-overload]
            if not text:
                if i == 0:
                    issues.append(f"{tag} : pas de narration, l'accroche doit être dite")
                continue
            said = spoken(text, lang)  # mots dits par la voix : « 1992 » en compte 4
            digits = " ; un nombre compte pour les mots qui le disent" if said != text else ""
            n = len(words(said))
            if i == 0 and n > HOOK_WORDS_MAX:
                issues.append(f"{tag} : accroche de {n} mots, {HOOK_WORDS_MAX} au plus{digits}")
            if i == 0 and re.search(openers, text, re.I):
                issues.append(f"{tag} : commence par une formule interdite (bonjour, aujourd'hui, saviez-vous…)")
            if re.search(cta, text, re.I):
                issues.append(f"{tag} : appel à l'action interdit (abonnement, like, commentaire, partage)")
            long = [len(words(x)) for x in sentences(said) if len(words(x)) > SENTENCE_WORDS_MAX]
            if long:
                issues.append(f"{tag} : phrase de {max(long)} mots, {SENTENCE_WORDS_MAX} au plus{digits}")
            limit = scene_words_max(s.duration_s)
            if n > limit:
                issues.append(f"{tag} : {n} mots pour {s.duration_s:g} s, {limit} au plus (la voix déborderait){digits}")
            m = re.search(vague, text, re.I)
            if m:
                issues.append(f"{tag} : superlatif vide « {m.group(0)} », remplacer par un fait")
            ost = s.on_screen_text.get(lang, "").strip()  # type: ignore[call-overload]
            if ost and len(words(ost)) > ON_SCREEN_WORDS_MAX:
                issues.append(f"{tag} : texte à l'écran de {len(words(ost))} mots, {ON_SCREEN_WORDS_MAX} au plus")
        total = sum(len(said_words(s.narration.get(lang, ""), lang)) for s in scenes)  # type: ignore[call-overload]
        floor = int(NARRATION_FILL_MIN * script.duration_s * WORDS_PER_SECOND)
        if total < floor:
            issues.append(
                f"[{lang}] narration trop maigre : {total} mots pour {script.duration_s:g} s, au moins {floor} "
                "(10 à 15 mots par scène de 5 s, une information nouvelle dans chacune)"
            )

    maps = [i for i, s in enumerate(scenes) if s.is_map]
    if len(maps) > MAP_SCENES_MAX:
        issues.append(f"{len(maps)} scènes carte (scènes {', '.join(str(i + 1) for i in maps)}) : une seule par Short")
    if target_duration_s and abs(script.duration_s - target_duration_s) > DURATION_TOLERANCE * target_duration_s:
        issues.append(f"durée {script.duration_s:g} s, cible {target_duration_s:g} s (± {int(DURATION_TOLERANCE * 100)} %)")
    if not (script.loop_note or "").strip():
        issues.append("loop_note manquant : dire comment le dernier plan renvoie au premier")
    return issues


def normalize_story(script: ScriptV1) -> ScriptV1:
    """Ce que le code impose aux récits, sans repasser par le LLM : une scène carte vide n'en est pas une ; une scène
    carte dure de 4 à 7 s ; elle ne prolonge pas le clip précédent et la scène qui la suit ne part pas de sa dernière
    image (la carte n'est pas un plan filmé) ; un nombre écrit en lettres passe en chiffres (worker/numbers.py)."""
    script_to_digits(script)
    lo, hi = MAP_DURATION_S
    after_map = False
    for s in script.scenes:
        if s.map is not None and not s.is_map:
            s.map = None
        if s.is_map:
            s.duration_s = min(hi, max(lo, s.duration_s))
            s.continues_previous = False
        elif after_map:
            s.continues_previous = False
        after_map = s.is_map
    return script


def feedback(issues: Sequence[str]) -> str:
    """Message de reprise pour le LLM."""
    return "Le script précédent viole ces règles, corrige-les toutes en gardant le reste :\n- " + "\n- ".join(issues)
