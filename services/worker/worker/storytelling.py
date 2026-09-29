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
Refonte du 29/09 (docs/37, « Le trésor de Begrâm » : des faits juxtaposés, sans héros ni fil) : RULES devient l'art du
récit, commun à toute histoire (les 3 C, l'enjeu, « donc » et « pourtant », montrer plutôt que dire, une seule idée,
l'accroche suivie d'une promesse, l'ironie dramatique, la fin écrite en premier, la checklist), donné à l'agent idées,
au conteur des récits (worker/storycraft.py), à son relecteur, à la scène réinventée et au scénariste des drames ; les
règles de l'image passent dans IMAGE_RULES (clé rules_images), celles de la voix dans le prompt du conteur. lint_script
vérifie toujours le script découpé ; storycraft.lint_story vérifie le récit avant le découpage.
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

RULES = """RÈGLES DU RÉCIT (toute histoire : racontée en voix off ou jouée en dialogues)

Un Short retient quand on comprend tout de suite de quoi il parle, qu'on veut la suite et qu'on ressent quelque
chose. Une liste de faits ne retient personne, même vrais, même étonnants : il faut une histoire.

1. UNE SEULE IDÉE. Tout le récit sert une idée ou une émotion unique (une ironie, une injustice, une obstination, un
   prix payé). Ce qui ne la nourrit pas est coupé : dates qui ne font que dater, grades, noms secondaires, chiffres
   de décor. Mieux vaut une histoire bien racontée que cinq faits.
2. LES 3 C. Contexte : le point de départ, le héros (une personne, un groupe, un animal) et son monde, assez pour
   qu'un spectateur qui ne connaît rien sache qui, où, quand et ce que le héros veut. Conflit : l'élément
   déclencheur, l'obstacle, ce qui s'oppose ou tourne mal ; sans friction, pas d'histoire. Conclusion : la
   résolution et ce qui a changé (une transformation, un prix payé, une ironie), jamais une morale plaquée.
3. L'ENJEU. On sait vite ce que le héros veut et ce qu'il perd s'il échoue (sa vie, sa fortune, son honneur, des
   années, ses petits). Plus la perte est concrète, plus on reste.
4. « MAIS » ET « DONC » (la règle des auteurs de South Park). Chaque temps découle du précédent : c'est une
   conséquence (donc, alors) ou un obstacle (mais, pourtant, sauf que) : « il veut X, donc il tente Y, mais Z
   arrive, donc il doit… ». La règle porte sur le lien entre les événements, pas sur le mot : si deux temps se
   relient par « et ensuite », il manque une cause ou un obstacle, et changer le mot n'y suffit pas. Une chronologie
   d'encyclopédie se réécrit en causes et en obstacles. Le conflit ouvre une question, le contexte qui suit la
   referme, un nouveau « mais » en ouvre une autre : c'est la danse, un rebondissement toutes les 7 à 8 secondes.
5. MONTRER, PAS DIRE. Des actions et des détails qu'on voit, qu'on entend, qu'on touche, au lieu d'adjectifs
   d'émotion : pas « il était désespéré » mais « il vend sa montre pour payer une semaine de fouilles de plus » ;
   pas « un trésor incroyable » mais « 400 pièces d'or cousues dans la doublure d'un manteau ».
6. L'ACCROCHE SANS DÉLAI. Dès la 1re phrase, on sait exactement de quoi on parle (un objet, un lieu, une personne,
   un événement concret) et on sent un contraste : ce qu'on croit contre ce qui est, un paradoxe, une erreur énorme,
   un prix absurde. Les 4 erreurs qui font passer à la vidéo suivante : le délai (le sujet arrive après une phrase
   d'introduction : supprime-la), la confusion (une phrase qui se lit de deux façons : relis-la seule), le
   hors-sujet (rien ne promet une histoire qu'on ne connaît pas), le désintérêt (aucune question ouverte). Une bonne
   accroche ferait un bon titre ; elle se comprend même sans le son, parce que l'image montre au même instant ce que
   dit la phrase. Pas de « saviez-vous », pas de « vous n'allez pas le croire » sans le sujet.
   La 2e phrase est une PROMESSE : elle annonce la fin sans la donner (« Pourtant, personne n'a le droit d'en toucher
   une seule pièce. ») ; la fin la tient. À elles deux, 6 secondes au plus.
7. LES BOUCLES OUVERTES. Chaque réponse ouvre une nouvelle question. Un mot qui intrigue (secret, maudit, interdit,
   controversé) est expliqué par un fait concret au plus tard dans le temps suivant. Aucune promesse sans réponse.
   Un mécanisme peut tirer jusqu'au bout : 3 tentatives annoncées, un compte à rebours, une question posée au début.
   Tiens la promesse, puis tords la fin quand le dossier le permet : l'attente comblée, puis la surprise.
8. L'IRONIE DRAMATIQUE, quand l'histoire s'y prête : le spectateur voit ce que le héros ignore ou refuse de voir (la
   solution évidente, le piège, le traître). Il a envie de crier « ne fais pas ça » et reste pour voir le choc. En
   4 temps : l'erreur ou le paradoxe en accroche ; l'évidence, ce que tout le monde aurait fait ; le héros qui
   s'entête et double la mise ; le retour de bâton, où il finit par faire ce qu'il aurait dû, après avoir tout perdu.
9. DES HUMAINS ET UN ANGLE RARE. Un nom, un geste, une décision, une phrase dite (tirée des sources) : on s'attache
   à quelqu'un, pas à un bâtiment. Pour un objet ou un lieu, le héros est celui qui le cherche, le construit, le
   défend ou le perd ; pour un animal, l'animal lui-même : ce qu'il veut (manger, survivre, protéger ses petits) et
   ce qui l'en empêche. Un sujet connu se raconte par l'angle que personne ne prend (ce qu'il a coûté, l'erreur
   derrière, la personne oubliée).
10. SIMPLE ET RYTHMÉ. Des mots qu'un enfant de 10 ans comprend (CM2 au plus) ; un mot savant ou technique se
    remplace, ou s'explique par une action. Le ton d'une histoire qu'on raconte à un ami, pas d'une encyclopédie.
    Des phrases de longueurs variées : une courte qui claque (« Personne ne revient. »), une moyenne, une longue qui
    déroule, puis une courte ; écrites l'une sous l'autre, leurs bords sont dentelés, jamais alignés. Nombres et
    années en chiffres (« 852 morts », « en 1937 ») : la voix les lit en lettres ; un nombre qui porte l'enjeu ou le
    contraste se garde, un nombre de décor se coupe.
11. LA FIN S'ÉCRIT EN PREMIER, avec l'accroche. La dernière phrase (chute sèche, ironie, twist ou retour à
    l'accroche) décide de tout le reste ; elle doit pouvoir être partagée seule et, comme le Short repart en boucle,
    elle peut préparer la première. Le récit s'arrête dès que la promesse est tenue et la chute dite : pas de résumé,
    pas de morale, pas de question au public, pas d'appel à s'abonner ; chaque seconde de trop fait partir du monde.

CHECKLIST avant de rendre : le sujet est-il dit dans les 2 premières secondes ? Relue seule, l'accroche se lit-elle
d'une seule façon ? La 2e phrase annonce-t-elle une fin que le récit tient ? Un spectateur qui ne connaît rien
comprend-il qui, où, quand et pourquoi ça compte ? Chaque temps est-il une conséquence ou un obstacle du précédent, ou
reste-t-il un « et ensuite », une suite de dates ? Chaque phrase sert-elle l'idée unique ? Les dates, grades et
chiffres de décor sont-ils coupés ? Le texte s'arrête-t-il net après la chute ?"""

# Règles de l'image des récits (clé rules_images) : données au réalisateur (storycraft.SHOTS_PROMPT) et à la scène
# réinventée ; elles faisaient la 4e partie de RULES jusqu'au 29/09.
IMAGE_RULES = """RÈGLES DE L'IMAGE (une image de départ, puis quelques secondes d'animation par scène)
- La 1re image montre exactement ce que dit l'accroche (l'objet, le lieu, la personne), dès la 1re seconde : la voix,
  le titre et l'image disent la même chose.
- Chaque image montre ce que dit la narration à ce moment-là : une action, un geste, un objet précis, une
  conséquence visible ; jamais une illustration vague de l'ambiance.
- Chaque image se rattache au sujet au premier coup d'œil : un détail (mécanisme, matière, outil) se montre sur le
  sujet et dans son décor, jamais seul sur fond neutre. Un objet, un lieu ou un personnage qui revient est décrit
  avec les mêmes mots d'une scène à l'autre : le modèle d'image ne connaît que le prompt de sa scène.
- Une seule action ou un seul mouvement de caméra par scène, lent et lisible (travelling avant, panoramique,
  mécanisme qui s'ouvre, animal qui frappe) ; rien n'apparaît, rien ne se transforme.
- Un changement visuel à chaque scène : alterner plan large, plan moyen et gros plan, changer d'échelle ou d'angle.
- L'image la plus spectaculaire est gardée pour le renversement ou la réponse ; le dernier plan renvoie au premier.
- Récits historiques : l'époque se voit (costumes, outils, engins, matériaux du moment raconté).
- Lieu réel : une scène carte le situe (vue de l'espace, zoom, tracé) ; elle est rendue par le code.
- Personnes réelles : jamais de visage reconnaissable (de dos, de trois quarts dans l'ombre, les mains, une
  silhouette), toujours la même tenue d'une scène à l'autre.
- Cadrage vertical pour un téléphone : sujet centré, fort contraste, sans texte dans l'image.
- Texte à l'écran seulement pour un chiffre ou un mot-clé que dit la narration, 5 mots au plus."""

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
