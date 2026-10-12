"""Les agents de la page Recherche (docs/60-recherche-niches.md, docs/64-que-faire.md) : sorties, prompts, messages.

- le classeur (`research_classify`, chaîne « default ») : pour chaque Short trouvé, son format, la recette de chez nous
  la plus proche et l'effort qu'il nous demanderait, d'après le titre, les chiffres et la miniature ;
- l'analyste vidéo (`research_watch`, Gemini qui regarde la vidéo YouTube elle-même, providers/gemini_video.py) :
  accroche, structure seconde par seconde, pourquoi ça marche, et la même mécanique transposée en une idée à nous ;
- l'adaptateur (`research_adapt`, Gemini qui regarde la vidéo) : la version fidèle en français, même sujet, même
  déroulé, même accroche, avec nos mots (docs/64 §3) ;
- le stratège (`research_brief`, chaîne « writer ») : les niches à lancer, LA vidéo à faire maintenant, les vidéos à
  reproduire, les formats rapides, les niches à ajouter à la veille, d'après les chiffres calculés par le code
  (worker/research.py) ; il répond aussi aux questions de Luca (`research_ask`).
Les chiffres viennent toujours du code ; les agents classent, expliquent et proposent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field

FORMATS = (
    "chantier en accéléré",
    "visite",
    "histoire jouée",
    "récit narré",
    "faits / liste",
    "citation",
    "quiz / jeu",
    "comparaison",
    "satisfying",
    "tuto / astuce",
    "humour / sketch",
    "vraie personne face caméra",
    "extrait / compilation",
    "jeu vidéo",
    "animaux filmés",
    "autre",
)
RECIPES = ("timelapse", "tour", "story", "drama", "quote", "none")
RECIPE_HELP = {
    "timelapse": "chantier ou rénovation en accéléré : caméra fixe, un ouvrier, une étape toutes les 2 à 3 s, du « avant » "
    "au « après » (images retouchées l'une depuis l'autre puis animées)",
    "tour": "visite d'une maison de luxe pièce par pièce, voix off et prix",
    "story": "récit narré en voix off sur des plans animés : histoire vraie, lieu étrange, fait insolite, « et si »",
    "drama": "histoire jouée par des personnages qui gardent la même tête d'un plan à l'autre (fruits, animaux, familles, "
    "style réaliste ou Pixar), répliques dites par les clips ou sans paroles ; aussi « Mon scénario »",
    "quote": "une phrase écrite au milieu d'une image qui porte l'émotion, sans voix, 6 à 13 s",
    "none": "aucune de nos recettes",
}
EFFORT_HELP = """Effort pour nous (1 à 5) :
1 = une de nos recettes le fait telle quelle (même format, même style) ;
2 = une recette le fait avec un réglage (nouveau thème, nouveau guide d'idées) ;
3 = faisable avec nos briques mais il faut une recette nouvelle (quelques jours de travail) ;
4 = difficile pour l'IA générative d'aujourd'hui (texte lisible partout, mains précises, foule, sport, vraie personne connue) ;
5 = impossible sans tournage réel, visage d'un créateur, jeu vidéo ou contenu d'autrui."""


def recipes_block(machine_hours: Mapping[str, float] | None = None) -> str:
    lines = []
    for k in RECIPES:
        h = (machine_hours or {}).get(k)
        lines.append(f"- {k} : {RECIPE_HELP[k]}" + (f" (≈ {h:.1f} h de machine par vidéo, mesuré)" if h else ""))
    return "NOS RECETTES (champ recipe : la clé telle quelle) :\n" + "\n".join(lines)


def series_block(series: Sequence[Mapping[str, Any]]) -> str:
    """Nos thèmes actifs : slug, nom, recette (le champ series des agents prend un slug de cette liste ou rien)."""
    if not series:
        return ""
    return "NOS THÈMES (champ series : le slug tel quel, ou vide) :\n" + "\n".join(
        f"- {s['slug']} ({s['recipe']}) : {s['name']}" for s in series
    )


# ---- Le classeur -----------------------------------------------------------------------------------------------------


class VideoLabel(BaseModel):
    ref: str = Field(description="référence de la vidéo : V1, V2…")
    format: str = Field(description="un des FORMATS, tel quel")
    niche: str = Field("", description="la niche en 2 à 5 mots, en français (« abris souterrains en accéléré »)")
    recipe: str = Field("none", description="la recette de chez nous la plus proche, ou none")
    series: str = Field("", description="le slug du thème de chez nous le plus proche, ou vide")
    effort: int = Field(3, description="1 à 5, voir l'échelle")
    ai_made: bool | None = Field(None, description="fabriquée par IA générative ? null si on ne peut pas le dire")
    faceless: bool | None = Field(None, description="sans visage de créateur ?")
    angle: str = Field("", description="ce qui arrête le pouce, en une phrase courte")


class LabelBatch(BaseModel):
    videos: list[VideoLabel] = Field(default_factory=list)


CLASSIFY_PROMPT = f"""Tu classes des YouTube Shorts d'autres chaînes pour une usine à Shorts sans visage, fabriqués par IA
sur un PC (images générées puis animées, voix de synthèse, montage automatique).

Pour chaque vidéo (titre, chaîne, chiffres et, quand elle est jointe, sa miniature dans le même ordre que la liste),
dis :
- format : un de ces formats, tel quel : {" | ".join(FORMATS)} ;
- niche : la niche en 2 à 5 mots, en français, assez précise pour regrouper les vidéos qui se ressemblent
  (« abris souterrains en accéléré », pas « construction ») ;
- recipe et series : la recette et le thème de chez nous les plus proches (listes plus bas), ou none / vide ;
- effort : l'échelle plus bas ; juge ce qu'on voit, pas le sujet seul (une histoire filmée avec de vrais acteurs
  connus = 5, la même histoire jouée par des fruits en 3D = 1 ou 2) ;
- ai_made, faceless : null si la miniature et le titre ne permettent pas de le dire ;
- angle : ce qui arrête le pouce, concret (« un bus rouillé enterré sous un jardin, le résultat fini dès la miniature »).

{EFFORT_HELP}

Réponds pour TOUTES les vidéos de la liste, avec leur référence (V1, V2…), et rien d'autre."""


def classify_message(videos: Sequence[Mapping[str, Any]], series: Sequence[Mapping[str, Any]], with_images: bool) -> str:
    """`videos` : ref, title, channel, views, age_d, duration_s, outlier, description."""
    lines = []
    for v in videos:
        lines.append(
            f"{v['ref']} · « {v['title']} » · chaîne {v.get('channel') or '?'} · {v.get('views', 0):,} vues en "
            f"{v.get('age_d', 0):.0f} j · {v.get('duration_s') or '?'} s · × {v.get('outlier') or '?'} sa chaîne"
            + (f"\n    {v['description'][:160]}" if v.get("description") else "")
        )
    head = "MINIATURES JOINTES : une par vidéo, dans l'ordre de la liste.\n\n" if with_images else ""
    return f"{head}{recipes_block()}\n\n{series_block(series)}\n\nVIDÉOS :\n" + "\n".join(lines)


def clean_label(label: VideoLabel) -> dict[str, Any]:
    """Valeurs ramenées aux listes permises (un LLM écrit parfois « Chantier » ou « timelapse video »)."""
    fmt = next((f for f in FORMATS if f.lower() == label.format.strip().lower()), None)
    if fmt is None:
        fmt = next((f for f in FORMATS if label.format.strip().lower()[:6] in f), "autre")
    recipe = label.recipe.strip().lower()
    return {
        "format": fmt,
        "niche": label.niche.strip()[:80],
        "recipe": recipe if recipe in RECIPES else "none",
        "series": label.series.strip()[:60],
        "effort": max(1, min(5, int(label.effort or 3))),
        "ai_made": label.ai_made,
        "faceless": label.faceless,
        "angle": label.angle.strip()[:240],
    }


# ---- L'analyste vidéo (Gemini regarde le Short) ----------------------------------------------------------------------


class Beat(BaseModel):
    t: str = Field(description="moment, ex. « 0-2 s »")
    what: str = Field(description="ce qu'on voit et entend")


class Remake(BaseModel):
    title: str = Field(description="titre de NOTRE vidéo, en français, histoire nouvelle")
    premise: str = Field(description="l'idée en 2 ou 3 phrases : même mécanique, sujet, lieu et personnages nouveaux")
    hook: str = Field("", description="l'image 0 et la première phrase (ou le premier texte) de notre vidéo")
    scenario: str = Field(
        "",
        description="pour recipe = drama ou none : le scénario complet de notre vidéo, actions dans l'ordre, une par "
        "phrase, pour l'équipe « Mon scénario »",
    )
    style: str = Field("auto", description="cinematic_real | pixar_human | dreamworks_animal | pixar_fruit | auto")
    speech: str = Field("auto", description="muet | repliques | dialogues | auto")
    duration_s: int = Field(45, description="20 à 90 s")
    keep: list[str] = Field(default_factory=list, description="ce qu'on garde de la mécanique")
    change: list[str] = Field(default_factory=list, description="ce qu'on change pour ne rien copier")


class VideoAnalysis(BaseModel):
    summary: str = Field(description="ce qui se passe, en deux phrases")
    hook_visual: str = Field(description="l'image à 0 s, ce qui change avant 2 s, pourquoi le pouce s'arrête")
    hook_text: str = Field("", description="première phrase dite ou premier texte écrit, mot pour mot")
    structure: list[Beat] = Field(default_factory=list, description="les temps de la vidéo, du début à la fin")
    pacing: str = Field("", description="nombre de plans, durée d'un plan, caméra, montage")
    audio: str = Field("", description="voix off, dialogues, musique, bruitages, sans paroles ; langue")
    on_screen_text: str = Field("", description="textes à l'écran (sous-titres, titre, étiquettes)")
    emotion: str = Field("", description="l'émotion visée et le moment où elle culmine")
    ending: str = Field("", description="la fin : chute, révélation, boucle, appel à commenter")
    why_it_works: list[str] = Field(default_factory=list, description="3 à 5 raisons concrètes")
    weak_points: list[str] = Field(default_factory=list, description="ce qui est raté ou améliorable")
    format: str = Field("autre", description="un des FORMATS")
    recipe: str = Field("none", description="notre recette la plus proche")
    series: str = Field("", description="notre thème le plus proche (slug) ou vide")
    effort: int = Field(3, description="1 à 5")
    remake: Remake


WATCH_PROMPT = f"""Tu regardes un YouTube Short d'une autre chaîne pour une usine à Shorts sans visage, fabriqués par IA
sur un PC. Le but : comprendre pourquoi il a marché, puis en tirer UNE idée de vidéo à nous qui reprend sa mécanique
sans rien copier.

Regarde la vidéo du début à la fin, image et son. Sois concret et précis : ce qu'on voit à 0 s, ce qui change avant 2 s,
la première phrase mot pour mot, chaque temps de l'histoire avec son moment, le rythme des plans, le son, la fin.
Pourquoi ça marche : des raisons qu'on peut refaire (une question posée par la première image, un contraste dans le
cadre, l'enjeu écrit dans l'image, une transformation visible, une injustice réparée, une boucle…), pas « c'est
captivant ».

Notre idée (remake) : même mécanique (même accroche visuelle, même structure, même durée, même émotion), mais un sujet,
un lieu et des personnages nouveaux : jamais la même histoire, jamais les mêmes personnages, jamais le même titre.
Choisis la recette et le thème de chez nous qui la feraient le mieux (listes plus bas). Pour une histoire jouée
(recipe = drama) ou si aucune recette ne convient, écris le scénario complet de notre vidéo, actions dans l'ordre, une
par phrase, comme on l'expliquerait à une équipe de tournage. Réaliste (cinematic_real) par défaut, sauf si le
modèle est clairement un film d'animation ou des fruits.

Formats : {" | ".join(FORMATS)}.

{EFFORT_HELP}

Réponds en français."""


def watch_message(video: Mapping[str, Any], series: Sequence[Mapping[str, Any]], machine_hours: Mapping[str, float]) -> str:
    return (
        f"LA VIDÉO : « {video.get('title') or ''} » · chaîne {video.get('channel_title') or '?'} "
        f"({video.get('channel_subs') or '?'} abonnés) · {int(video.get('views') or 0):,} vues · "
        f"{video.get('duration_s') or '?'} s · publiée le {str(video.get('published_at') or '')[:10]}\n"
        + (f"Description : {str(video.get('description'))[:400]}\n" if video.get("description") else "")
        + f"\n{recipes_block(machine_hours)}\n\n{series_block(series)}"
    )


# ---- L'adaptateur : la version fidèle, en français, avec nos mots (docs/64 §3) -----------------------------------------


class AdaptBeat(BaseModel):
    t: str = Field(description="moment, ex. « 0-2 s », le même que dans l'original")
    image: str = Field(description="ce qu'on voit, à fabriquer par nos recettes (pas l'image de l'original)")
    words: str = Field("", description="ce qu'on dit ou écrit à ce moment, en français, avec nos mots ; vide si muet")


class Adaptation(BaseModel):
    title: str = Field(description="titre de notre vidéo en français : même promesse que l'original, nos mots")
    source_language: str = Field("", description="langue de l'original (anglais, français, hindi…)")
    subject: str = Field(description="le sujet repris tel quel : le fait, le lieu, l'histoire ou le projet de l'original")
    hook: str = Field(description="notre image à 0 s et notre première phrase : la même question que l'original")
    beats: list[AdaptBeat] = Field(default_factory=list, description="le même déroulé que l'original, temps par temps")
    narration: str = Field(
        "", description="tout le texte dit en voix off, en français, nos mots, même longueur que l'original ; vide si muet"
    )
    scenario: str = Field(
        "",
        description="pour recipe = drama ou none : le scénario complet, la même histoire que l'original, actions dans "
        "l'ordre, une par phrase, répliques en français avec nos mots",
    )
    ending: str = Field("", description="la même fin : chute, révélation, boucle, question posée")
    recipe: str = Field("none", description="notre recette qui la ferait le mieux")
    series: str = Field("", description="notre thème le plus proche (slug) ou vide")
    style: str = Field("auto", description="cinematic_real | pixar_human | dreamworks_animal | pixar_fruit | auto")
    speech: str = Field("auto", description="muet | repliques | dialogues | auto")
    duration_s: int = Field(45, description="la durée de l'original, 15 à 90 s")
    facts_to_check: list[str] = Field(
        default_factory=list, description="les faits, chiffres et noms avancés par l'original, à vérifier avant de publier"
    )
    changed: list[str] = Field(default_factory=list, description="ce qui change forcément chez nous, et pourquoi")


ADAPT_PROMPT = f"""Tu regardes un YouTube Short d'une autre chaîne qui a fait beaucoup de vues. Le créateur de notre usine
à Shorts (sans visage, fabriqués par IA sur un PC, en français) veut le REFAIRE FIDÈLEMENT, à sa manière : on ne réinvente
pas ce qui a déjà marché, on le refait bien, en français.

Garde :
- le MÊME sujet : le même fait insolite, le même lieu, le même projet, la même histoire et les mêmes rôles ;
- le MÊME déroulé, temps par temps, au même rythme (même nombre de temps, mêmes moments) ;
- la MÊME accroche : la même image à 0 s, la même question posée dans les deux premières secondes ;
- la MÊME fin (chute, révélation, boucle, question aux spectateurs) et la même durée ;
- la même émotion, le même ton, les mêmes textes à l'écran quand ils portent la vidéo (traduits).

Change :
- les MOTS : tout est réécrit en français avec nos mots à nous. Jamais une phrase traduite mot à mot : chaque phrase
  est reformulée, plus naturelle à l'oral, aussi courte ou plus courte ;
- les IMAGES : décris ce qu'on voit pour que nos recettes le fabriquent (on ne réutilise rien de la vidéo) ;
- le titre : même promesse, autres mots ; aucun nom de chaîne, logo, filigrane ni appel à s'abonner à l'autre chaîne.

Si l'original avance des faits, des chiffres ou des noms, recopie-les dans facts_to_check : on les vérifie avant de
publier, on ne diffuse pas une erreur. Si un fait est faux ou douteux, dis-le et écris notre version avec le fait juste.
Pour une histoire jouée (recipe = drama) ou si aucune recette ne convient, écris le scénario complet. Réaliste
(cinematic_real) par défaut, sauf si l'original est clairement un film d'animation ou des fruits. Écris les nombres en
chiffres.

{EFFORT_HELP}

Réponds en français."""


def adapt_message(video: Mapping[str, Any], series: Sequence[Mapping[str, Any]], analysis: Mapping[str, Any] | None) -> str:
    """La fiche de la vidéo, nos recettes et thèmes, et ce que l'analyste en a déjà dit (déroulé, accroche)."""
    seen = ""
    if analysis:
        beats = "\n".join(f"  {b.get('t', '')} : {b.get('what', '')}" for b in analysis.get("structure") or [])
        seen = (
            f"\nCE QUE L'ANALYSTE A DÉJÀ VU (à vérifier en regardant) :\nAccroche : {analysis.get('hook_visual', '')}\n"
            f"Première phrase : {analysis.get('hook_text', '')}\nDéroulé :\n{beats}\nFin : {analysis.get('ending', '')}\n"
        )
    return f"{watch_message(video, series, {})}\n{seen}"


# ---- Le stratège répond aux questions (docs/64 §4) ----------------------------------------------------------------------


class AskAnswer(BaseModel):
    answer: str = Field(
        description="la réponse, en français simple, courte (10 lignes au plus), chiffres à l'appui, qui finit par ce "
        "qu'il faut faire maintenant"
    )
    video_refs: list[str] = Field(default_factory=list, description="les vidéos de la liste citées (V1, V2…), 4 au plus")
    niches: list[str] = Field(default_factory=list, description="les slugs des niches citées, tels quels")


ASK_PROMPT = """Tu es le stratège d'une usine à YouTube Shorts sans visage, fabriqués par IA sur un PC, en français
(3 vidéos par jour, aussi sur TikTok et Instagram). Le créateur te pose une question sur sa veille : quelle vidéo faire,
quelle niche choisir, comment lire un chiffre, est-ce qu'une niche hors de sa liste vaut le coup…

Réponds comme un associé qui connaît les chiffres : directement, simplement, sans jargon, en 10 lignes au plus. Appuie-
toi sur les chiffres fournis (calculés par le code) et cite les vidéos par leur référence (V1…). Termine toujours par ce
qu'il faut faire maintenant, concrètement. Si les données ne permettent pas de répondre, dis-le et dis quoi relever.

Comment lire les chiffres :
- vues médianes : la médiane des 50 Shorts les plus vus publiés dans le mois mesuré, pour la recherche de la niche ;
  c'est le niveau du haut du panier, pas ce que fait une vidéo moyenne ni une nouvelle chaîne ;
- tubes : parmi ces 50, ceux qui dépassent 1 M de vues ;
- porte ouverte : la part de ces tubes faits par une petite chaîne (moins de 10 000 abonnés) ou une chaîne de moins
  de 6 mois ; haute = l'algorithme pousse encore les nouveaux venus ;
- note sur 100 : 35 demande (vues médianes, 10 k → 0, 10 M → plein) + 25 élan (la phase, jugée par rapport à
  l'ensemble des niches) + 20 porte ouverte + 20 faisabilité (effort moyen pour nos recettes) ;
- × N d'une vidéo : ses vues divisées par la médiane des Shorts de sa chaîne ; un × 100 sur une petite chaîne, c'est
  le sujet qui a porté, donc reproductible.

Le créateur reprend ce qui a déjà marché : la « version fidèle » garde le même sujet, le même déroulé et la même
accroche, réécrits en français avec ses mots et fabriqués par ses recettes ; jamais les images, la voix ou le texte
mot à mot de l'autre chaîne. Les niches « découvertes » sont hors de sa liste : dis franchement si elles demandent une
nouvelle recette (effort 3) ou si l'IA ne sait pas encore les faire (effort 4-5 : jeu vidéo, visage, tournage)."""


def ask_message(context: str, report_headline: str | None, history: Sequence[Mapping[str, str]], question: str) -> str:
    past = "\n".join(f"Q : {h['question']}\nR : {h['answer']}" for h in history if h.get("answer"))
    return (
        f"{context}"
        + (f"\n\nDERNIÈRE RECOMMANDATION DU LUNDI : {report_headline}" if report_headline else "")
        + (f"\n\nÉCHANGES PRÉCÉDENTS :\n{past}" if past else "")
        + f"\n\nQUESTION DU CRÉATEUR : {question}"
    )


# ---- Le stratège -----------------------------------------------------------------------------------------------------


class NichePick(BaseModel):
    niche: str = Field(description="slug de la niche, tel quel")
    verdict: str = Field(description="à lancer | à tester | à surveiller | à éviter")
    why: str = Field(description="pourquoi, avec les chiffres fournis")
    how: str = Field("", description="comment on la ferait : recette, thème, durée, ce qu'il faut changer chez nous")
    first_videos: list[str] = Field(default_factory=list, description="2 ou 3 titres de premières vidéos")


class RemakePick(BaseModel):
    ref: str = Field(description="référence de la vidéo : V1, V2…")
    why: str = Field(description="pourquoi la reproduire maintenant")
    angle: str = Field("", description="notre angle, en une phrase")


class FastFormat(BaseModel):
    format: str
    why: str = Field(description="pourquoi il est rapide et pourquoi il peut marcher, chiffres à l'appui")
    recipe: str = Field("none", description="notre recette qui le ferait, ou none s'il en faut une nouvelle")


class NewNiche(BaseModel):
    label: str = Field(description="nom de la niche en français")
    description: str = ""
    queries: list[str] = Field(default_factory=list, description="2 recherches YouTube (mots-clés), en anglais puis en français")
    why: str = ""


class NextVideo(BaseModel):
    ref: str = Field(description="référence de LA vidéo à refaire en premier : V1, V2…")
    why: str = Field(description="pourquoi celle-là, chiffres à l'appui, en 2 phrases simples")
    how: str = Field("", description="comment on la refait : version fidèle, recette, durée, ce qu'on soigne")


class ResearchBrief(BaseModel):
    headline: str = Field(description="la recommandation principale, en une phrase")
    next_video: NextVideo | None = Field(None, description="LA vidéo à faire maintenant, s'il y en a une")
    niches: list[NichePick] = Field(default_factory=list)
    remakes: list[RemakePick] = Field(default_factory=list)
    fast_formats: list[FastFormat] = Field(default_factory=list)
    new_niches: list[NewNiche] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list, description="limites des données, pièges")


BRIEF_PROMPT = f"""Tu es le stratège d'une usine à YouTube Shorts sans visage (3 vidéos par jour, aussi publiées sur
TikTok et Instagram), fabriqués par IA sur un PC. Le créateur veut automatiser au maximum : moins de vérifications,
moins de retouches, plus de vidéos qui marchent. Tu reçois la veille de la semaine, calculée par le code :

- les niches suivies : phase (émergente, en hausse, installée, en baisse, à vide) et sa raison, note sur 100 avec ses
  parts (demande, élan, porte ouverte = part des tubes faits par de petites ou nouvelles chaînes, faisabilité), vues
  médianes du mois, tubes, âge, formats, recette et effort moyen pour nous ;
- les vidéos qui surperforment le plus (× leur chaîne), avec ce que l'analyste vidéo en a dit quand il l'a regardée ;
- le temps de fabrication mesuré de chacune de nos recettes, et les leçons tirées de nos propres vidéos.

Les niches marquées « découverte » sont hors de la liste du créateur (trouvées en balayant de grands sujets de
YouTube : jeux vidéo, montres, voitures, cuisine…) : signale celles qui valent une nouvelle recette.

Rends :
- next_video : LA vidéo de la liste à refaire en premier (forte, récente, faisable, dans une niche qui tient), avec
  pourquoi en deux phrases simples et comment la refaire ;
- niches : 3 à 6 niches, verdict « à lancer » (forte note, porte ouverte, effort 1-2), « à tester », « à surveiller »
  ou « à éviter » (en baisse, saturée, hors de portée), chacune avec les chiffres qui le justifient et comment on la
  ferait (recette, thème existant ou nouveau, durée), plus 2 ou 3 titres de premières vidéos ;
- remakes : 3 à 6 vidéos de la liste à reproduire maintenant (référence V…), les plus fortes ET les plus faciles ;
- fast_formats : 2 à 4 formats rapides à fabriquer (peu de machine, pas de vérification image par image) qui marchent
  dans les données : c'est la priorité du créateur ;
- new_niches : 0 à 3 niches à ajouter à la veille, vues dans les titres ou les formats mais pas encore suivies,
  avec 2 recherches YouTube chacune ;
- warnings : les limites (petits échantillons, recherche YouTube qui ne voit que 50 vidéos par requête…).

Le créateur reprend ce qui a déjà marché plutôt que d'explorer : une vidéo se refait en « version fidèle » (même sujet,
même déroulé, même accroche, réécrits en français avec ses mots et fabriqués par ses recettes), jamais en recopiant les
images, la voix ou le texte mot à mot. Les vidéos dans une langue lointaine du français (hindi, bengali…) se refont mal :
préfère l'anglais et le français. Pas de recette inventée : celles qui existent sont listées. Réponds en français,
chiffres à l'appui.

{EFFORT_HELP}"""


def _pct(x: Any) -> str:
    return f"{round(100 * float(x))} %" if x is not None else "?"


def brief_message(
    niches: Sequence[Mapping[str, Any]],
    videos: Sequence[Mapping[str, Any]],
    machine_hours: Mapping[str, float],
    lessons: str,
) -> str:
    """`niches` : slug, label, recipe, summary ; `videos` : ref, title, niche, views, outlier, vpd, age_d, format,
    effort, why (analyse), angle."""
    n_lines = []
    for n in niches:
        s = n.get("summary") or {}
        parts = s.get("score_parts") or {}
        views = s.get("median_views_month") or s.get("median_views_7")
        n_lines.append(
            f"- {n['slug']} · {n['label']}{' · DÉCOUVERTE (hors de notre liste)' if n.get('origin') == 'discover' else ''}"
            f" · phase {s.get('phase', '?')} ({s.get('phase_reason', '')}) · note "
            f"{parts.get('score', '?')}/100 (demande {_pct(parts.get('demand'))}, élan {_pct(parts.get('momentum'))}, "
            f"porte ouverte {_pct(parts.get('open'))}, faisabilité {_pct(parts.get('feasibility'))}) · vues médianes "
            f"{f'{int(views):,}' if views else '?'} ({s.get('last_month') or '7 derniers jours'}, "
            f"{s.get('sample_month') or '?'} Shorts) · tubes (1 M+) {s.get('hits_month', '?')} · cette semaine "
            f"{s.get('hits_7', '?')} à 100 k+ · âge {s.get('age_months') or '?'} mois · formats "
            f"{', '.join(s.get('formats') or []) or '?'} · recette {n.get('recipe') or 'aucune'} · effort moyen "
            f"{s.get('effort') or '?'}"
        )
    v_lines = []
    for v in videos:
        v_lines.append(
            f"{v['ref']} · « {v['title']} » · niche {v.get('niche') or '?'} · langue {v.get('lang') or '?'} · "
            f"{int(v.get('views') or 0):,} vues en {v.get('age_d', 0):.0f} j · × {v.get('outlier') or '?'} sa chaîne · "
            f"{v.get('format') or '?'} · effort {v.get('effort') or '?'}"
            + (f"\n    angle : {v['angle']}" if v.get("angle") else "")
            + (f"\n    pourquoi (analyste vidéo) : {v['why']}" if v.get("why") else "")
        )
    hours = ", ".join(f"{k} ≈ {h:.1f} h" for k, h in machine_hours.items()) or "pas encore mesuré"
    return (
        f"{recipes_block(machine_hours)}\n\nTEMPS DE FABRICATION MESURÉ (médiane par vidéo) : {hours}\n\n"
        f"NICHES (suivies, puis découvertes) :\n"
        + "\n".join(n_lines)
        + "\n\nVIDÉOS QUI SURPERFORMENT :\n"
        + "\n".join(v_lines)
        + (f"\n\n{lessons}" if lessons else "")
    )
