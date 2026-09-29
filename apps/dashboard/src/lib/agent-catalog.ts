/**
 * Catalogue de l'onglet Agents (docs/22-agents.md) : les agents du pipeline, les consignes communes glissées dans leurs
 * messages et la chaîne de production complète, de l'idée à la publication. Données statiques, partagées par le
 * serveur et les composants client.
 *
 * Les clés sont celles de prompt_templates.agent. Le worker y écrit le texte de son code à chaque démarrage
 * (services/worker/worker/prompts.py) et lit la version active à chaque appel ; son test tests/test_prompts.py
 * vérifie que toutes les clés de ce fichier existent. Les descriptions suivent le code des steps (worker/steps/*.py).
 */
import type { JobType } from "@/lib/types";

export type AgentIcon =
  | "idea"
  | "story"
  | "shots"
  | "review"
  | "timelapse"
  | "tour"
  | "seo"
  | "strategy"
  | "improve"
  | "analyst"
  | "keyframe"
  | "clip";

export interface AgentDef {
  key: string;
  name: string;
  /** Une phrase : ce que fait l'agent. */
  summary: string;
  icon: AgentIcon;
  /** Regarde des images (modèle de vision) plutôt que du texte seul. */
  vision?: boolean;
  /** Thèmes concernés quand l'agent ne sert pas partout. */
  scope?: string;
  /** Job du worker qui appelle l'agent (activité de la semaine). */
  job: JobType;
  when: string;
  /** Ce que le code envoie avec le prompt système, tâche par tâche. */
  inputs: string[];
  /** Consignes communes (clés) ajoutées au message. */
  consignes: string[];
  output: string;
  /** Ce qui se passe ensuite. */
  then: string;
}

export interface ConsigneDef {
  key: string;
  name: string;
  summary: string;
  /** Agents (clés) qui la reçoivent. */
  usedBy: string[];
  /** Ce que le code vérifie de son côté, avec ses propres valeurs. */
  note?: string;
}

export const AGENTS: AgentDef[] = [
  {
    key: "idea",
    name: "Agent idées",
    summary: "Propose des idées de Shorts notées sur 100, thème par thème.",
    icon: "idea",
    job: "ideate",
    when: "Quand tu demandes des idées dans Création, et chaque heure pour tout thème qui a moins de 6 idées en attente.",
    inputs: [
      "Le thème : nom, brief (ligne éditoriale) et catégories",
      "Thèmes documentaires : la matière du jour tirée de Wikipédia, en sources numérotées",
      "La répartition des catégories sur 30 jours, les 20 vidéos publiées qui retiennent le mieux et les idées déjà proposées, à éviter",
      "La stratégie validée et les leçons de l’agent analyste que tu as validées (Dashboard)",
      "Le nombre d’idées à produire",
    ],
    consignes: ["rules_storytelling", "guide_timelapse", "guide_tour", "guide_drama"],
    output: "Des idées qui sont des histoires : titre, accroche (le sujet et un contraste), prémisse (le héros, ce qu’il veut, ce qui l’en empêche, ce qu’il risque, le renversement), angle (le moteur : enquête, ironie dramatique…), catégorie, temps visuels, score sur 100 et, pour les thèmes documentaires, 8 à 12 faits sourcés qui couvrent le contexte, l’enjeu, le conflit, les rebondissements et la fin.",
    then: "Une idée de thème documentaire n’est gardée que si au moins deux faits citent une source fournie. Les idées arrivent dans Création, où tu choisis ✓ ou ✗.",
  },
  {
    key: "script",
    name: "Conteur · histoires",
    summary:
      "Écrit l’histoire en entier, comme un conteur : l’idée unique, l’accroche et sa promesse, le contexte, les « mais » et les « donc », la chute écrite en premier.",
    icon: "story",
    scope: "Thèmes racontés : histoires vraies, animaux étranges, maisons de rêve…",
    job: "script",
    when: "Dès que tu valides une idée (✓ dans Création).",
    inputs: [
      "Le thème : brief (ligne éditoriale)",
      "L’idée : titre, accroche, angle, prémisse, catégorie, temps visuels",
      "Les faits sourcés et leurs sources (thèmes documentaires)",
      "Le dossier : les pages Wikipédia des sources relues en entier, version anglaise comprise (thèmes documentaires)",
      "La durée visée et son budget de mots dits (75 s ≈ 218 mots), la langue de la chaîne",
      "La stratégie validée, les leçons validées de l’agent analyste et le texte de trois vidéos qui ont bien marché",
    ],
    consignes: ["rules_storytelling", "rules_hook_title"],
    output:
      "L’histoire : l’idée centrale, le moteur (enquête, ironie dramatique…), le héros et son enjeu, la dernière phrase écrite avant le reste, puis les temps du récit (accroche, promesse, contexte, conflit, renversement, réponse, chute), chacun avec ce qu’on doit y voir ; le titre d’accroche.",
    then: "Le correcteur mesure l’histoire (mots pour la durée, accroche et promesse courtes, contexte avant 12 s, phrases courtes et longues mêlées, pas de « et ensuite », chute courte) et le relecteur la juge ; s’il la refuse, elle repart au conteur (deux fois au plus, la première réécriture est relue), puis une passe corrige la forme (rythme, longueurs) sans toucher au fond. Le conteur et le relecteur n’écrivent qu’avec les modèles forts de la chaîne d’écriture : si leurs quotas sont épuisés, la tâche attend (12 h au plus). Le code découpe ensuite l’histoire en scènes, phrase par phrase, sans changer un mot, et le réalisateur fait les plans.",
  },
  {
    key: "script_review",
    name: "Relecteur · histoires",
    summary: "Relit l’histoire avant le découpage, comme un spectateur qui ne connaît rien au sujet, avec la checklist du storytelling.",
    icon: "review",
    scope: "Thèmes racontés",
    job: "script",
    when: "Juste après le conteur, une fois par histoire.",
    inputs: [
      "L’idée : titre, accroche, prémisse",
      "L’histoire temps par temps, avec l’idée centrale, le moteur, le héros, l’enjeu, la dernière phrase et le titre d’accroche",
      "Les faits de l’idée et le dossier des sources (thèmes documentaires)",
    ],
    consignes: ["rules_storytelling"],
    output:
      "Un verdict : bonne, ou jusqu’à 8 problèmes précis (temps visé et correction), par exemple des faits posés les uns après les autres sans « mais » ni « donc », un contexte qui manque, une promesse non tenue.",
    then: "Des problèmes : l’histoire repart une fois au conteur avec la liste. S’il ne répond pas (quota), l’histoire continue sans relecture.",
  },
  {
    key: "script_shots",
    name: "Réalisateur · histoires",
    summary: "Découpe l’histoire en plans : l’image de départ et le mouvement de chaque scène, la carte d’un lieu réel, la musique.",
    icon: "shots",
    scope: "Thèmes racontés",
    job: "script",
    when: "Après la relecture, une fois l’histoire découpée en scènes par le code (phrase par phrase, sans changer un mot).",
    inputs: [
      "Le thème : brief et ambiances musicales disponibles",
      "L’histoire (idée centrale, moteur, héros) et ses scènes : rôle, durée, narration mot pour mot, ce que le conteur veut y montrer",
      "L’idée, ses temps visuels, le style visuel et la langue de la chaîne",
      "Les faits et le dossier des sources, pour l’exactitude des images (époque, lieux, objets)",
    ],
    consignes: ["rules_images", "hint_continuity"],
    output:
      "Un plan par scène : l’image de départ et le mouvement (en anglais), un texte à l’écran facultatif, la continuité, la scène carte d’un lieu réel ; ce qui est commun à toutes les images (époque, lieu, lumière), la boucle, l’ambiance musicale et des métadonnées brouillon.",
    then: "Le code assemble le script (la narration du conteur, mot pour mot, et ces plans) puis le correcteur le vérifie ; une scène oubliée est redemandée une fois. Le storyboard suit.",
  },
  {
    key: "scene_rewrite",
    name: "Scénariste · scène réinventée",
    summary: "Réécrit une scène du storyboard qui ne colle pas au sujet : un autre plan, une nouvelle image, la narration raccord.",
    icon: "story",
    job: "storyboard",
    when: "Quand tu cliques « Réinventer » sur une scène du storyboard (Création → Regarder et choisir).",
    inputs: [
      "Le thème, l’idée et, pour les thèmes documentaires, les faits sourcés et le dossier des sources",
      "Les consignes de qui a fait les plans (le réalisateur des histoires, ou le scénariste du format) et, pour les histoires, les règles du récit et de l’image",
      "Le script scène par scène (image, mouvement, narration, texte à l’écran) et la scène visée, son rôle et sa durée",
      "Ce que tu en dis (facultatif) et les versions de la scène déjà écartées, pour ne pas y revenir",
    ],
    consignes: ["rules_storytelling", "rules_images"],
    output: "La scène réécrite : son nouveau plan en une phrase (en français, pour toi), l’image de départ et le mouvement (en anglais), la narration et le texte à l’écran ; rôle et durée ne changent pas.",
    then: "Le correcteur vérifie le script ; un écart nouveau renvoie la scène une fois au scénariste. Le script est enregistré, les anciennes images de la scène sont retirées, de nouvelles sont faites et le storyboard revient à valider.",
  },
  {
    key: "script_timelapse",
    name: "Scénariste · chantier en accéléré",
    summary: "Écrit les étapes d’un chantier vu d’un point fixe, sans voix off.",
    icon: "timelapse",
    scope: "Thèmes « chantier en accéléré »",
    job: "script",
    when: "Dès que tu valides une idée d’un thème chantier.",
    inputs: [
      "Le thème : brief et ambiances musicales conseillées",
      "L’idée : titre, accroche, angle, prémisse, catégorie, temps visuels",
      "La durée cible, le style visuel et la langue de la chaîne",
      "La liste des bruitages disponibles",
      "La stratégie validée, les leçons validées de l’agent analyste et deux scripts de la série qui ont bien marché",
    ],
    consignes: ["rules_hook_title"],
    output:
      "10 à 14 étapes dans l’ordre du chantier : l’image de chaque étape, la retouche qui remonte le temps, le mouvement, les bruitages, le compteur de jours et le titre d’accroche.",
    then: "Le code impose la mécanique (ordre des retouches, durées, dernier plan au crépuscule) puis vérifie le format ; une reprise en cas d’écart.",
  },
  {
    key: "script_tour",
    name: "Scénariste · visite de luxe",
    summary: "Écrit le parcours d’une maison d’exception, pièce par pièce, sans voix off.",
    icon: "tour",
    scope: "Thèmes « visite de luxe »",
    job: "script",
    when: "Dès que tu valides une idée d’un thème visite.",
    inputs: [
      "Le thème : brief et ambiances musicales conseillées",
      "L’idée : titre, accroche, angle, prémisse, catégorie, temps visuels",
      "La durée cible, le style visuel et la langue de la chaîne",
      "La liste des bruitages disponibles",
      "La stratégie validée, les leçons validées de l’agent analyste et deux scripts de la série qui ont bien marché",
    ],
    consignes: ["rules_hook_title"],
    output:
      "6 à 9 pièces dans l’ordre de la visite : l’image de chaque pièce, l’ouverture vers la suivante, le mouvement de caméra, les bruitages, le texte à l’écran, les matériaux et la vue de toute la maison.",
    then: "Le code impose les passages d’une pièce à l’autre et les durées, puis vérifie le format ; une reprise en cas d’écart.",
  },
  {
    key: "script_drama",
    name: "Scénariste · drame en dialogues",
    summary: "Écrit une histoire de karma jouée par des personnages (fruits, humains ou animaux) : une réplique par plan.",
    icon: "story",
    scope: "Thèmes « drame » : Le Karma des Fruits, Histoires de familles, Histoires d’animaux",
    job: "script",
    when: "Dès que tu valides une idée d’un thème drame.",
    inputs: [
      "Le thème : brief et ambiances musicales conseillées",
      "L’idée : titre, accroche, angle, prémisse, catégorie, temps visuels",
      "La durée cible, le style visuel et la langue de la chaîne",
      "Les voix de synthèse des personnages (patron, jeune homme humble, femme mielleuse, vieille dame…)",
      "La stratégie validée, les leçons validées de l’agent analyste et deux scripts de la série qui ont bien marché",
    ],
    consignes: ["rules_storytelling", "rules_hook_title"],
    output:
      "La distribution (nom, apparence en anglais, voix de chaque personnage) puis 14 à 20 plans : les personnages à l’image, une réplique de 12 mots au plus dite par un seul personnage, l’image de départ et le mouvement (en anglais) ; le titre d’accroche, l’ambiance musicale et des métadonnées brouillon.",
    then: "Le code relie chaque réplique à son personnage, cale la durée du plan sur la réplique, puis vérifie le format (une voix par plan, 60 % de plans dialogués, personnages décrits) ; une reprise en cas d’écart. Au storyboard, chaque personnage reçoit sa fiche, donnée en référence à chaque plan où il apparaît.",
  },
  {
    key: "seo",
    name: "Agent SEO",
    summary: "Écrit le titre, la description, les tags et les hashtags de chaque vidéo.",
    icon: "seo",
    job: "seo",
    when: "Juste après le script, une fois par vidéo, dans la langue de la chaîne.",
    inputs: [
      "La chaîne et sa langue, le thème et son brief",
      "L’idée et son accroche",
      "Ce que dit la narration, scène par scène (ou ce qu’on voit, pour les vidéos sans voix) et les textes à l’écran",
      "Le brouillon de titre et de tags du scénariste",
      "Les 10 titres de la chaîne qui marchent le mieux et les 30 derniers, à ne pas répéter",
      "La stratégie validée et les leçons validées de l’agent analyste",
    ],
    consignes: [],
    output: "3 à 5 titres au choix, la description, 10 à 15 tags, 3 hashtags et un commentaire à épingler.",
    then: "Le code applique les limites de YouTube (titre de 70 caractères, description de 5 000 octets, tags de 500 caractères) et ajoute les sources Wikipédia et la mention « images générées par IA ».",
  },
  {
    key: "keyframe_qc",
    name: "Contrôleur des images",
    summary: "Regarde chaque image clé des chantiers et des visites avant l’animation.",
    icon: "keyframe",
    vision: true,
    scope: "Thèmes chantier et visite",
    job: "storyboard",
    when: "Pendant le storyboard, image par image.",
    inputs: [
      "L’image clé, et l’image retouchée pour l’obtenir",
      "Les exigences de sa scène, écrites par le code : pièce vraiment intérieure, personne à l’image, bâtiment entier dans le cadre, ouvriers à l’échelle…",
    ],
    consignes: [],
    output: "Un verdict : bonne, ou la liste des problèmes.",
    then: "Une image refusée est refaite, deux fois au plus ; si elle l’est encore, elle t’attend dans Création avec la liste des problèmes.",
  },
  {
    key: "clip_qc",
    name: "Contrôleur des clips",
    summary: "Vérifie chaque clip animé des chantiers, des visites et des drames.",
    icon: "clip",
    vision: true,
    scope: "Thèmes chantier, visite et drame",
    job: "generate_clip",
    when: "Après chaque clip.",
    inputs: [
      "L’image de départ et trois images tirées du clip",
      "Les exigences de la scène : aucune personne, aucun appareil de tournage, rien qui apparaît ou se déforme…",
      "Drames : aucun texte écrit à l’image par le modèle vidéo (la réplique en sous-titre, une légende)",
    ],
    consignes: [],
    output: "Un verdict : bon, ou la liste des problèmes.",
    then: "Un clip refusé est refait une fois ; le verdict reste attaché au clip.",
  },
  {
    key: "strategy",
    name: "Agent stratégie",
    summary: "Lit les statistiques de la chaîne et propose des ajustements.",
    icon: "strategy",
    job: "strategy",
    when: "Chaque dimanche à 4 h 30, pour chaque chaîne, dès 6 vidéos publiées depuis au moins 3 jours.",
    inputs: [
      "Les statistiques déjà calculées : vues à 7 jours, rétention, abonnés, engagement, par catégorie, format, durée, créneau et forme de titre",
      "La stratégie validée actuelle, les catégories et les créneaux de publication",
    ],
    consignes: [],
    output: "Les poids des catégories, des consignes d’accroche, des modèles de titres, ce qu’il faut éviter, les créneaux, la durée cible et des expériences à mener.",
    then: "Rien n’est appliqué sans validation humaine ; une stratégie validée est lue par l’agent idées, les scénaristes et l’agent SEO.",
  },
  {
    key: "improve",
    name: "Agent amélioration",
    summary: "Propose de meilleures versions des prompts de l’agent idées et du scénariste.",
    icon: "improve",
    job: "improve",
    when: "Chaque dimanche à 4 h, s’il y a eu des vidéos publiées ces 14 derniers jours.",
    inputs: [
      "La performance de chaque version de prompt : rétention moyenne et vues des vidéos qu’elle a produites",
      "Les 10 meilleures et les 10 moins bonnes vidéos",
      "Les prompts actifs de l’agent idées et du scénariste",
    ],
    consignes: [],
    output: "Au plus une nouvelle version par agent, avec sa raison.",
    then: "Ses propositions arrivent dans l’historique de l’agent concerné, inactives : à toi de les utiliser ou non.",
  },
  {
    key: "analyst",
    name: "Agent analyste",
    summary: "Compare les vidéos qui marchent et les autres, explique pourquoi et propose des leçons.",
    icon: "analyst",
    job: "analyze",
    when: "Chaque dimanche à 5 h, et quand tu cliques « Analyser maintenant » dans Dashboard, dès 2 vidéos publiées depuis plus de 24 h.",
    inputs: [
      "Les chiffres de chaque vidéo, déjà calculés : vues, note par rapport à la médiane (top, moyen, flop), rétention, audience encore là à 3 s, j’aime, partages, abonnés",
      "La fiche de chaque vidéo : thème, format, titre, titre d’accroche, textes à l’écran, narration, premier plan, nombre et durée des plans, musique, modèle vidéo, hashtags, heure de publication, commentaires",
      "Une planche de 4 images par vidéo (0,5 s, 2,5 s, milieu et fin ; images YouTube pour celles mises en ligne à la main), quand le modèle réglé voit les images",
      "Les ventilations par format, thème, durée, créneau, forme du titre, accroche affichée ou non, voix off, modèle vidéo, musique",
      "Les leçons déjà en service",
    ],
    consignes: [],
    output: "Pour chaque vidéo, pourquoi elle marche ou non ; ce qui distingue les tops des flops, preuve chiffrée à l’appui ; au plus 6 leçons à l’impératif, chacune pour un agent (idées, scénaristes, SEO) ou pour toi ; au plus 3 expériences.",
    then: "Tout arrive dans Dashboard. Une leçon validée (✓) est glissée dans le message de l’agent visé à chacune de ses tâches ; celles « à régler toi-même » ne vont à aucun agent.",
  },
];

export const CONSIGNES: ConsigneDef[] = [
  {
    key: "rules_storytelling",
    name: "Règles du récit",
    summary:
      "L’art de raconter, pour toute histoire : une seule idée, les 3 C, l’enjeu, « mais » et « donc », montrer plutôt que dire, l’accroche sans délai et sa promesse, les boucles ouvertes, l’ironie dramatique, des mots simples et un rythme varié, la fin écrite en premier, la checklist.",
    usedBy: ["idea", "script", "script_review", "scene_rewrite", "script_drama"],
    note: "Le correcteur vérifie aussi, avec ses propres valeurs. L’histoire : environ 2,9 mots dits par seconde de vidéo (75 s ≈ 218 mots, de 185 à 244), accroche de 14 mots au plus, accroche et promesse de 22 mots à elles deux, contexte avant 12 s, phrases de 18 mots au plus, au moins 15 % de phrases courtes (5 mots ou moins) et 15 % de longues (12 ou plus), ni « et ensuite » ni « puis », chute de 12 mots au plus, un nombre par tranche de 10 s. Le script découpé : 16 mots par scène au plus, une narration qui couvre au moins 70 % de la durée, révélation avant 12 s, une seule scène carte, pas d’appel à l’action ni de superlatif vide. Si tu changes ces chiffres ici, le correcteur garde les siens. Les nombres s’écrivent en chiffres (« 852 morts », « en 1994 ») : la voix les lit en toutes lettres, le correcteur compte les mots qu’elle dit (« 1994 » = 4 mots) et un nombre resté en lettres passe en chiffres.",
  },
  {
    key: "rules_images",
    name: "Règles de l’image · histoires",
    summary:
      "La première image montre l’accroche, chaque image montre ce que dit la narration, les mêmes mots pour ce qui revient, un seul mouvement lent, un changement de plan à chaque scène, l’époque qui se voit, la carte d’un lieu réel, aucun visage reconnaissable.",
    usedBy: ["script_shots", "scene_rewrite"],
  },
  {
    key: "guide_timelapse",
    name: "Guide · chantier en accéléré",
    summary: "Ce qu’est une bonne idée de chantier en accéléré : lieu de départ, résultat final, étapes visibles, accroche.",
    usedBy: ["idea"],
  },
  {
    key: "guide_tour",
    name: "Guide · visite de luxe",
    summary: "Ce qu’est une bonne idée de visite : propriété d’exception, parcours de pièce en pièce, détail qui fait parler, accroche.",
    usedBy: ["idea"],
  },
  {
    key: "guide_drama",
    name: "Guide · drame en dialogues",
    summary: "Ce qu’est une bonne histoire de karma : prémisse d’argent et de paradoxe, ressort, victime et son besoin, méchant proche, preuve, fin juste.",
    usedBy: ["idea"],
  },
  {
    key: "rules_hook_title",
    name: "Règles du titre d’accroche",
    summary: "Le titre gravé à l’écran (où et sur quels formats : onglet Montage) : 3 à 8 mots, parlé, qui donne envie de voir la suite.",
    usedBy: ["script", "script_timelapse", "script_tour", "script_drama"],
    note: "Le correcteur vérifie aussi, avec ses propres valeurs : 3 à 8 mots et 70 caractères au plus. Un nombre écrit en lettres passe en chiffres au montage (« Huit cent cinquante-deux morts » → « 852 morts »).",
  },
  {
    key: "hint_continuity",
    name: "Continuité entre clips",
    summary: "Quand un clip prolonge le précédent (il part de sa dernière image) et quand il coupe.",
    usedBy: ["script_shots"],
  },
];

export const AGENT_BY_KEY: Record<string, AgentDef> = Object.fromEntries(AGENTS.map((a) => [a.key, a]));
export const CONSIGNE_BY_KEY: Record<string, ConsigneDef> = Object.fromEntries(CONSIGNES.map((c) => [c.key, c]));
export const PROMPT_KEYS: string[] = [...AGENTS.map((a) => a.key), ...CONSIGNES.map((c) => c.key)];

/** Nom lisible d'une clé de prompt (agent ou consigne). */
export function promptName(key: string): string {
  return AGENT_BY_KEY[key]?.name ?? CONSIGNE_BY_KEY[key]?.name ?? key;
}

// ---------------------------------------------------------------------------------------------------------------
// Chaîne de production (worker/dag.py, steps/*.py, scheduler.py)
// ---------------------------------------------------------------------------------------------------------------

/** agent : appel à un LLM (prompt éditable) ; model : modèle local sur la carte graphique ; code : étape
 * programmée ; human : c'est toi qui décides. */
export type StepKind = "agent" | "model" | "code" | "human";

/** Ce qui attend à une étape, compté en direct. */
export type WaitingKey = "concepts" | "storyboards" | "videos_review" | "scheduled" | "published";

/** Modèle réglé dans Réglages, affiché en direct sur l'étape. */
export type ModelSlot = "llm" | "vision" | "image" | "video" | "voice";

export interface PipelineStep {
  id: string;
  kind: StepKind;
  title: string;
  detail: string;
  /** Agents liés (clés de prompt) : un clic ouvre leur prompt. */
  agents?: string[];
  /** Jobs du worker qui font ce travail (tâches en cours). */
  jobs?: JobType[];
  model?: ModelSlot;
  /** L'étape ne sert qu'à certaines vidéos. */
  only?: string;
  waiting?: WaitingKey;
  /** Écran du dashboard où l'étape se pilote. */
  href?: string;
}

export interface PipelineStage {
  id: string;
  title: string;
  summary: string;
  steps: PipelineStep[];
}

export const PIPELINE: PipelineStage[] = [
  {
    id: "idees",
    title: "Idées",
    summary: "Des idées notées, thème par thème.",
    steps: [
      {
        id: "ideate",
        kind: "agent",
        title: "Agent idées",
        detail: "Brief du thème, matière Wikipédia pour les thèmes documentaires, vidéos qui marchent : des idées notées sur 100.",
        agents: ["idea"],
        jobs: ["ideate"],
        model: "llm",
      },
      {
        id: "pick",
        kind: "human",
        title: "Tu choisis",
        detail: "Création : ✓ lance la production, ✗ écarte l’idée.",
        waiting: "concepts",
        href: "/create",
      },
    ],
  },
  {
    id: "ecriture",
    title: "Écriture",
    summary: "Le script scène par scène, puis les textes YouTube.",
    steps: [
      {
        id: "script",
        kind: "agent",
        title: "Scénariste",
        detail:
          "Selon le format du thème : le conteur écrit l’histoire racontée en entier, ou le scénariste du chantier en accéléré, de la visite de luxe ou du drame en dialogues écrit ses plans.",
        agents: ["script", "script_timelapse", "script_tour", "script_drama"],
        jobs: ["script"],
        model: "llm",
      },
      {
        id: "lint",
        kind: "code",
        title: "Correcteur",
        detail: "Vérifie les règles mesurables ; en cas d’écart, l’histoire ou le script repart au scénariste.",
      },
      {
        id: "script_review",
        kind: "agent",
        title: "Relecteur",
        detail:
          "La checklist du récit : sujet dit tout de suite, promesse tenue, contexte compris, « mais » et « donc » plutôt que des faits alignés, une seule idée, faits du dossier ; ses remarques font réécrire l’histoire une fois.",
        agents: ["script_review"],
        jobs: ["script"],
        model: "llm",
        only: "histoires racontées",
      },
      {
        id: "script_shots",
        kind: "agent",
        title: "Réalisateur",
        detail: "Le code découpe l’histoire en scènes, phrase par phrase ; le réalisateur décide l’image et le mouvement de chaque plan.",
        agents: ["script_shots"],
        jobs: ["script"],
        model: "llm",
        only: "histoires racontées",
      },
      {
        id: "seo",
        kind: "agent",
        title: "Agent SEO",
        detail: "Titre, description, tags et hashtags de chaque vidéo, pendant que la suite avance.",
        agents: ["seo"],
        jobs: ["seo"],
        model: "llm",
      },
    ],
  },
  {
    id: "storyboard",
    title: "Storyboard",
    summary: "Une image par scène, avant toute animation.",
    steps: [
      {
        id: "images",
        kind: "model",
        title: "Images",
        detail: "La première image de chaque scène ; les étapes d’un chantier sont obtenues en retouchant l’image finale.",
        jobs: ["storyboard"],
        model: "image",
        href: "/settings",
      },
      {
        id: "keyframe_qc",
        kind: "agent",
        title: "Contrôleur des images",
        detail: "Regarde chaque image clé et fait refaire celles qui ne vont pas.",
        agents: ["keyframe_qc"],
        model: "vision",
        only: "chantiers et visites",
      },
      {
        id: "scene_rewrite",
        kind: "agent",
        title: "Scène réinventée",
        detail: "Sur ta demande (« Réinventer ») : le scénariste réécrit une scène qui ne colle pas au sujet, raccord avec les autres, puis ses images sont refaites.",
        agents: ["scene_rewrite"],
        model: "llm",
        only: "à ta demande",
        href: "/create",
      },
      {
        id: "validate",
        kind: "human",
        title: "Tu valides",
        detail: "Création : ✓ Valider et fabriquer, ou ✦ Gemini pour faire les clips en ligne.",
        waiting: "storyboards",
        href: "/create",
      },
    ],
  },
  {
    id: "fabrication",
    title: "Fabrication",
    summary: "Les clips, la voix, puis le montage.",
    steps: [
      {
        id: "clips",
        kind: "model",
        title: "Clips",
        detail: "Chaque image est animée en un clip de quelques secondes (ou par Gemini en ligne).",
        jobs: ["generate_clip"],
        model: "video",
        href: "/settings",
      },
      {
        id: "clip_qc",
        kind: "agent",
        title: "Contrôleur des clips",
        detail: "Vérifie chaque clip et fait refaire ceux qui inventent une personne ou un objet, ou qui écrivent du texte à l’image.",
        agents: ["clip_qc"],
        model: "vision",
        only: "chantiers, visites et drames",
      },
      {
        id: "tts",
        kind: "model",
        title: "Voix off",
        detail: "Une phrase par scène, avec les mots horodatés pour les sous-titres.",
        jobs: ["tts"],
        model: "voice",
        only: "histoires racontées",
        href: "/settings",
      },
      {
        id: "assemble",
        kind: "code",
        title: "Montage",
        detail: "Clips, voix, sous-titres, musique, bruitages et titre d’accroche, en 1080×1920.",
        jobs: ["assemble"],
      },
      { id: "qa", kind: "code", title: "Contrôle qualité", detail: "Durée, résolution, volume sonore, images noires.", jobs: ["qa"] },
    ],
  },
  {
    id: "publication",
    title: "Publication",
    summary: "Sur YouTube, au prochain créneau libre.",
    steps: [
      {
        id: "approve",
        kind: "human",
        title: "Tu autorises",
        detail: "Bibliothèque : autoriser la publication (ou publication automatique, réglable par chaîne).",
        waiting: "videos_review",
        href: "/library",
      },
      {
        id: "upload",
        kind: "code",
        title: "Envoi YouTube",
        detail: "En privé avec sa date de publication, au plus tôt 72 h avant le créneau.",
        jobs: ["upload"],
        waiting: "scheduled",
        href: "/calendar",
      },
      {
        id: "sync",
        kind: "code",
        title: "Suivi",
        detail: "Abonnés, vues, j’aime et commentaires chaque heure ; rétention, partages et abonnés par vidéo (YouTube Analytics) toutes les 6 h.",
        jobs: ["sync_metrics", "sync_retention", "sync_comments"],
        waiting: "published",
        href: "/dashboard",
      },
    ],
  },
];

/** La boucle d'apprentissage : ce que les vidéos publiées apprennent aux agents. */
export const LEARNING_LOOP: PipelineStep[] = [
  {
    id: "analyst",
    kind: "agent",
    title: "Agent analyste",
    detail: "Chaque dimanche et à la demande : compare les vidéos qui marchent et les autres (accroche, titre, rythme, format, voix, hashtags…), explique pourquoi et propose des leçons.",
    agents: ["analyst"],
    jobs: ["analyze"],
    model: "llm",
    href: "/dashboard#analyse",
  },
  {
    id: "lessons",
    kind: "human",
    title: "Tu valides les leçons",
    detail: "Dashboard : ✓ donne la leçon à l’agent idées, aux scénaristes ou à l’agent SEO, dès leur tâche suivante ; ✗ l’écarte.",
    href: "/dashboard#analyse",
  },
  {
    id: "strategy",
    kind: "agent",
    title: "Agent stratégie",
    detail: "Chaque dimanche : lit les statistiques et propose des ajustements (catégories, accroches, titres, créneaux) qui, une fois validés, guident l’agent idées, les scénaristes et l’agent SEO.",
    agents: ["strategy"],
    jobs: ["strategy"],
    model: "llm",
  },
  {
    id: "improve",
    kind: "agent",
    title: "Agent amélioration",
    detail: "Chaque dimanche : compare les versions de prompts à la rétention des vidéos et propose de meilleures versions, à choisir dans cet onglet.",
    agents: ["improve"],
    jobs: ["improve"],
    model: "llm",
  },
];
