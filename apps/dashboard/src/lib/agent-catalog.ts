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
    consignes: [
      "rules_storytelling",
      "guide_timelapse",
      "guide_timelapse_insolite",
      "guide_tour",
      "guide_drama",
      "guide_quote",
      "guide_quote_auteur",
    ],
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
    key: "script_rewrite",
    name: "Conteur · récit réécrit",
    summary: "Réécrit ce que dit la voix d’une vidéo faite, plan par plan, sur ses images telles qu’elles sont.",
    icon: "story",
    scope: "Histoires racontées",
    job: "rewrite",
    when: "Quand tu demandes « Proposer une réécriture » dans Bibliothèque → Retoucher → Récit, avec « Tout le récit ».",
    inputs: [
      "Tes remarques sur la version actuelle (ce qui ne va pas, l’angle voulu), qui priment sur tout sauf sur les faits",
      "Le sujet, la prémisse et le dossier des sources, plus la page Wikipédia que tu ajoutes",
      "L’ancien texte, puis chaque plan : ce qu’on y voit, la durée de son clip et le nombre de mots qu’il peut porter",
    ],
    consignes: ["rules_storytelling", "rules_hook_title"],
    output: "Une phrase par plan, dans l’ordre, avec son temps du récit (accroche, promesse, contexte…), le texte à l’écran, le titre d’accroche et le titre YouTube ; l’idée, l’enjeu et la chute.",
    then: "Le correcteur mesure chaque phrase contre son clip et le relecteur relit l’histoire (deux réécritures au plus, la meilleure gardée). Tu relis et corriges le texte ; « Faire la vidéo avec ce texte » en fait une nouvelle vidéo sur les mêmes clips (voix, montage, contrôle, SEO), à valider. La vidéo d’origine ne change pas.",
  },
  {
    key: "hook_rewrite",
    name: "Conteur · nouvelle accroche",
    summary: "Réécrit seulement la 1re phrase dite et la promesse d’une vidéo faite ; le reste du récit ne bouge pas.",
    icon: "story",
    scope: "Histoires racontées par le conteur",
    job: "rewrite",
    when: "Quand tu demandes « Proposer une nouvelle accroche » dans Bibliothèque → Retoucher → Récit, avec « L’accroche seulement ».",
    inputs: [
      "Tes remarques sur l’ouverture actuelle",
      "Le sujet, la prémisse et le dossier des sources, plus la page Wikipédia que tu ajoutes",
      "Le récit actuel en entier, le titre YouTube actuel et les deux premiers plans (ce qu’on y voit, les mots qu’ils peuvent porter)",
    ],
    consignes: ["rules_storytelling", "rules_hook_title"],
    output: "L’accroche, la promesse, le texte à l’écran du premier plan, le titre d’accroche, le titre YouTube et le ressort choisi (gâchis, perte ou émerveillement).",
    then: "Le correcteur compte les mots (14 pour l’accroche, 22 avec la promesse, et ce que porte chaque plan) ; une reprise s’il trouve un écart. Tu relis, puis la variante d’accroche est fabriquée sur les mêmes clips, à valider.",
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
    key: "script_timelapse_insolite",
    name: "Scénariste · lieu insolite en accéléré",
    summary: "Écrit la construction d’un lieu insolite vue de dehors puis de dedans, avec des gros plans de mains, sans voix off.",
    icon: "timelapse",
    scope: "Thème « Lieux insolites en accéléré »",
    job: "script",
    when: "Dès que tu valides une idée du thème Lieux insolites.",
    inputs: [
      "Le thème : brief et ambiances musicales conseillées",
      "L’idée : titre, accroche, angle, prémisse, catégorie, temps visuels",
      "La durée cible, le style visuel et la langue de la chaîne",
      "La liste des bruitages disponibles",
      "La stratégie validée, les leçons validées de l’agent analyste et deux scripts de la série qui ont bien marché",
    ],
    consignes: ["rules_hook_title"],
    output:
      "20 à 26 plans de 60 à 70 s : les étapes vues de dehors, puis de dedans, 4 à 6 gros plans des mains intercalés, la révélation du soir, le compteur de jours et le titre d’accroche.",
    then: "Le code construit chaque vue à rebours depuis son résultat fini, sort les gros plans de la chaîne des retouches, impose les durées puis vérifie le format ; une reprise en cas d’écart.",
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
      "La distribution (nom, apparence en anglais, voix de chaque personnage) puis 22 à 28 plans rapides : les personnages à l’image, une réplique de 4 à 9 mots dite par un seul personnage, l’image de départ et le mouvement (en anglais) ; le titre d’accroche, l’ambiance musicale et des métadonnées brouillon.",
    then: "Le code relie chaque réplique à son personnage, cale la durée du plan sur la réplique, puis vérifie le format (une voix par plan, 75 % de plans dialogués, jamais deux plans muets de suite, personnages décrits) ; une reprise en cas d’écart. Au storyboard, chaque personnage reçoit sa fiche, donnée en référence à chaque plan où il apparaît. Au montage, chaque plan commence juste avant sa réplique et s’arrête dès qu’elle est dite, les clips sont joués 12 % plus vite (docs/70).",
  },
  {
    key: "script_quote",
    name: "Scénariste · citation",
    summary: "Écrit une citation courte, son image (peinture ou photo, le haut calme pour le texte), son mouvement lent et sa musique.",
    icon: "story",
    scope: "Thèmes « Citations (pensées) » et « Citations animées »",
    job: "script",
    when: "Dès que tu valides une idée d’un thème citations.",
    inputs: [
      "Le thème : brief et ambiances musicales (triste, tendre, rêveur, espoir)",
      "L’idée : la citation (titre), son thème, sa figure (retournement, paradoxe…), l’image",
      "La langue de la chaîne",
      "La stratégie validée et les leçons validées de l’agent analyste",
    ],
    consignes: [],
    output:
      "Une seule scène : la citation affichée (8 à 35 mots, signée seulement si c’est un auteur), l’image et le mouvement en anglais, l’ambiance musicale, le titre, la description et les tags.",
    then: "Le code garde une scène, calcule la durée selon la longueur du texte (6 à 13 s), puis vérifie la citation ; une reprise en cas d’écart. Au montage, le texte est dessiné sur l’image (police, ombre, voile), avec une musique générée sans droits d’auteur ; TikTok et Instagram mettent la leur à la publication.",
  },
  {
    key: "script_quote_auteur",
    name: "Scénariste · citation d’auteur",
    summary: "Met en scène une vraie citation d’auteur tirée de Wikiquote : l’image qui rappelle son univers, son mouvement lent, sa musique et ses textes YouTube.",
    icon: "story",
    scope: "Thème « Citations d’auteurs »",
    job: "script",
    when: "Dès que tu valides une idée du thème Citations d’auteurs.",
    inputs: [
      "Le thème : brief et ambiances musicales (triste, tendre, rêveur, espoir)",
      "L’idée : la citation choisie dans Wikiquote, son auteur et l’œuvre d’où elle vient, l’image",
      "La langue de la chaîne",
      "La stratégie validée et les leçons validées de l’agent analyste",
    ],
    consignes: [],
    output:
      "Une seule scène : la citation signée « — Auteur », l’image et le mouvement en anglais (jamais le visage de l’auteur), l’ambiance musicale, le titre, la description et les tags.",
    then: "Le code remet la citation exacte de Wikiquote et le nom de l’auteur, quoi qu’ait écrit le scénariste, puis calcule la durée (6 à 13 s). La description cite l’auteur, l’œuvre et la page Wikiquote. Le montage est celui des citations.",
  },
  {
    key: "scenario_adapt",
    name: "Metteur en scène · ton scénario",
    summary: "Lit le scénario que tu écris dans Création → « Mon scénario » et le met en forme sans le trahir.",
    icon: "shots",
    scope: "Mes scénarios",
    job: "script",
    when: "Dès que tu confies un scénario à l’équipe.",
    inputs: [
      "Ton texte, mot pour mot, et tes choix s’il y en a (titre, style, paroles, durée)",
      "Les styles visuels proposés (film d’animation, prise de vue réelle, animaux qui parlent, fruits)",
      "La langue de la chaîne",
    ],
    consignes: ["rules_hook_title"],
    output:
      "La mise en scène : titre, histoire en une phrase, genre, style, paroles (muet, quelques répliques, dialogues), durée, personnages et leur apparence en anglais, les temps de l’histoire dans l’ordre avec le passage de ton texte que chacun réalise, le titre d’accroche, ce qu’il a décidé là où ton texte ne disait rien, et ce qui sera délicat à filmer.",
    then: "Tes choix l’emportent sur les siens. La mise en scène est gardée et montrée dans Création (« Ce que l’équipe a compris ») ; le scénariste écrit les plans à partir d’elle.",
  },
  {
    key: "script_scenario",
    name: "Scénariste · ton scénario",
    summary: "Écrit les plans de ton scénario mis en scène : une action par plan, personnages constants, répliques seulement si prévues.",
    icon: "story",
    scope: "Mes scénarios",
    job: "script",
    when: "Juste après le metteur en scène.",
    inputs: [
      "Ton texte d’origine et la mise en scène",
      "Les ambiances musicales de ta bibliothèque",
      "La durée, le style et la langue",
      "Les voix de synthèse, s’il y a des paroles",
    ],
    consignes: ["rules_hook_title"],
    output:
      "La distribution, puis 5 à 24 plans de 2 à 5 s : les personnages à l’image, l’image de départ et l’action en anglais (même décor décrit avec les mêmes mots), une réplique de 12 mots au plus quand les paroles le prévoient ; titre d’accroche, musique et métadonnées brouillon.",
    then: "Le code le traite comme un drame (personnages reliés, durées, aucune réplique en muet) et vérifie le format ; le relecteur de fidélité le relit. Au storyboard, chaque personnage reçoit sa fiche, donnée en référence à chaque plan où il apparaît.",
  },
  {
    key: "scenario_review",
    name: "Relecteur · fidélité à ton scénario",
    summary: "Compare les plans à ton texte : toutes tes actions, dans l’ordre, lisibles et faisables.",
    icon: "review",
    scope: "Mes scénarios",
    job: "script",
    when: "Après le scénariste, et encore après sa première réécriture.",
    inputs: ["Ton texte d’origine", "La mise en scène", "Les plans : personnages à l’image, réplique, image et mouvement"],
    consignes: [],
    output: "ok, ou 8 problèmes au plus, précis (action oubliée, deux actions dans un plan, personnage absent de sa fiche, chute peu visible).",
    then: "Ses remarques, avec les écarts du correcteur, font réécrire les plans (deux fois au plus) ; la première réécriture est relue à son tour.",
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
  {
    key: "research_classify",
    name: "Recherche · classeur",
    summary: "Range chaque Short trouvé par la veille : format, niche, recette de chez nous la plus proche, effort pour la refaire.",
    icon: "review",
    vision: true,
    job: "research",
    when: "À chaque relevé de la page Recherche (chaque jour à 10 h, ou « Relever maintenant »), pour les nouvelles vidéos à 50 000 vues et plus, par lots de 16.",
    inputs: [
      "Titre, chaîne, vues, âge, durée, surperformance (× sa chaîne) et début de la description de chaque vidéo",
      "Sa miniature, recadrée en 9:16, quand le modèle réglé voit les images",
      "Nos recettes et nos thèmes actifs",
    ],
    consignes: [],
    output: "Pour chaque vidéo : format, niche en quelques mots, recette et thème de chez nous les plus proches, effort de 1 (une recette le fait telle quelle) à 5 (impossible sans tournage), fabriquée par IA ou non, sans visage ou non, ce qui arrête le pouce.",
    then: "La page Recherche s’en sert pour la faisabilité des niches et pour choisir les vidéos à reproduire.",
  },
  {
    key: "research_watch",
    name: "Recherche · analyste vidéo",
    summary: "Gemini regarde un Short d’une autre chaîne, explique pourquoi il a marché et en tire une idée à nous.",
    icon: "clip",
    vision: true,
    job: "research",
    when: "Après chaque relevé pour les 4 meilleures vidéos à reproduire, et quand tu cliques « Pourquoi ça marche » ou « Reproduire » dans Recherche.",
    inputs: [
      "La vidéo YouTube elle-même (image et son, par son adresse, sans téléchargement)",
      "Son titre, sa chaîne, ses vues, sa durée et sa description",
      "Nos recettes avec leur temps de fabrication mesuré, et nos thèmes actifs",
    ],
    consignes: [],
    output: "Accroche (image à 0 s, première phrase), structure seconde par seconde, rythme, son, textes, émotion, fin, pourquoi ça marche, points faibles, et notre version : titre, idée, ouverture, scénario complet pour une histoire jouée, ce qu’on garde et ce qu’on change.",
    then: "« Reproduire » envoie notre version en fabrication : à l’équipe « Mon scénario » pour une histoire jouée, sinon en idée du thème le plus proche. Le storyboard reste à valider dans Création.",
  },
  {
    key: "research_brief",
    name: "Recherche · stratège",
    summary: "Lit la veille de la semaine et dit quelles niches lancer, quelles vidéos reproduire et quels formats rapides essayer.",
    icon: "strategy",
    job: "research",
    when: "Chaque lundi après le relevé de 10 h, et quand tu cliques « Nouvelles recommandations » dans Recherche.",
    inputs: [
      "Chaque niche suivie : phase et sa raison, note sur 100 (demande, élan, porte ouverte, faisabilité), vues médianes, tubes, âge, formats, effort",
      "Les 15 vidéos qui surperforment le plus, avec ce que l’analyste vidéo en a dit",
      "Le temps de fabrication mesuré de chaque recette",
      "Les leçons validées tirées de nos propres vidéos",
    ],
    consignes: [],
    output: "Une recommandation principale ; 3 à 6 niches (à lancer, à tester, à surveiller, à éviter) avec comment les faire et de premiers titres ; 3 à 6 vidéos à reproduire ; 2 à 4 formats rapides ; jusqu’à 3 niches à ajouter à la veille.",
    then: "Tout s’affiche en haut de Recherche. Les niches proposées attendent « Suivre » ; les vidéos retenues passent en tête de « Vidéos à reproduire ».",
  },
  {
    key: "research_adapt",
    name: "Recherche · version fidèle",
    summary: "Gemini regarde un Short qui a marché et le réécrit en français : même sujet, même déroulé, même accroche, avec nos mots et nos images.",
    icon: "clip",
    vision: true,
    job: "research",
    when: "Quand tu cliques « Refaire fidèlement » ou « Écrire la version fidèle » dans Recherche.",
    inputs: [
      "La vidéo YouTube elle-même (image et son, par son adresse)",
      "Son titre, sa chaîne, ses vues, sa durée, sa description et ce que l’analyste vidéo en a déjà vu",
      "Nos recettes et nos thèmes actifs",
    ],
    consignes: [],
    output: "Titre en français, sujet repris, ouverture, déroulé temps par temps (image + paroles), texte de la voix off, scénario complet pour une histoire jouée, fin, recette, durée, faits à vérifier.",
    then: "La version part en fabrication : idée du thème le plus proche (le conteur garde le sujet et le déroulé), ou équipe « Mon scénario » pour une histoire jouée. Le storyboard reste à valider dans Création.",
  },
  {
    key: "research_ask",
    name: "Recherche · questions au stratège",
    summary: "Répond à tes questions sur la veille : quelle vidéo faire, quelle niche choisir, comment lire un chiffre.",
    icon: "strategy",
    job: "research",
    when: "Quand tu poses une question dans Recherche → Que faire.",
    inputs: [
      "Les niches suivies et découvertes avec leurs chiffres",
      "Les 20 meilleures vidéos à reproduire, avec l’analyse de Gemini",
      "Le temps de fabrication de nos recettes, nos leçons, la dernière recommandation et les 3 derniers échanges",
    ],
    consignes: [],
    output: "Une réponse courte, chiffres à l’appui, qui finit par ce qu’il faut faire maintenant, avec les vidéos et les niches citées.",
    then: "La réponse s’affiche sous ta question, avec les vidéos citées (Analyser, Refaire).",
  },
  {
    key: "research_discover",
    name: "Recherche · découverte des niches",
    summary: "Range les chaînes qui percent, trouvées hors de nos niches : la niche, la catégorie qui fixe le RPM, sans visage ou non, faite par IA ou non, l’effort pour la refaire.",
    icon: "review",
    job: "research",
    when: "À chaque découverte (chaque jour à 9 h 30, ou « Découvrir maintenant » dans Recherche → Découverte), par lots de 15 chaînes.",
    inputs: ["Nom, langue, âge, abonnés et nombre de vidéos de chaque chaîne", "Les titres, vues et durées de ses vidéos récentes qui marchent"],
    consignes: [],
    output: "Pour chaque chaîne : niche (le même nom pour les chaînes qui font la même chose), catégorie, sans visage, IA, effort de 1 à 5, format, pourquoi elle marche.",
    then: "Le code estime son revenu (vues par mois × RPM de la catégorie et de la langue) ; la Découverte regroupe les chaînes par niche, de la plus rentable à la moins rentable.",
  },
  // Vidéos longues « histoire et mystères » narrées par Luca (docs/63)
  {
    key: "long_idea",
    name: "Vidéos longues · sujets et emballage",
    summary: "Propose des sujets de vidéos longues avec leur titre, leur miniature et leur promesse : l’emballage avant tout.",
    icon: "idea",
    scope: "Vidéos longues",
    job: "long_write",
    when: "Quand tu cliques « Proposer des sujets » dans Vidéos longues, ou pour un sujet tapé dans « Mon sujet ».",
    inputs: [
      "Les formats de la chaîne (mystère, ta vie à l’époque) et leur proportion",
      "Les sujets déjà traités",
      "Les vidéos longues qui marchent ailleurs (Recherche)",
      "Les leçons validées et ta demande",
    ],
    consignes: ["guide_long_mystere", "guide_long_epoque", "rules_storytelling", "rules_long", "rules_thumbnail"],
    output: "Pour chaque sujet : titre (70 caractères au plus) et 2 autres, ouverture, promesse, angle, pourquoi on clique et on reste, concept de miniature (image + 0 à 4 mots), pages Wikipédia, note sur 100.",
    then: "Le code garde les sujets dont la page Wikipédia existe ; ils attendent « Écrire » dans Vidéos longues.",
  },
  {
    key: "long_outline",
    name: "Vidéos longues · plan en chapitres",
    summary: "Construit le plan d’une vidéo de 20 à 25 min : idée centrale, promesse, dernière phrase, 6 à 8 chapitres avec leurs faits et leurs relances.",
    icon: "story",
    scope: "Vidéos longues",
    job: "long_write",
    when: "Au début de l’écriture d’une vidéo longue.",
    inputs: [
      "L’idée et son emballage (titre, miniature, promesse) et tes remarques",
      "Le dossier : pages Wikipédia entières, françaises et anglaises",
      "La durée visée et son nombre de mots (150 mots par minute)",
      "Les leçons validées",
    ],
    consignes: ["guide_long_mystere", "guide_long_epoque", "rules_storytelling", "rules_long"],
    output: "Idée centrale, moteur, héros et enjeu, promesse, dernière phrase, ouverture, puis chaque chapitre : titre, but, faits sourcés, question ouverte, durée.",
    then: "Le conteur écrit les chapitres d’après ce plan.",
  },
  {
    key: "long_writer",
    name: "Vidéos longues · conteur",
    summary: "Écrit le texte que tu lis au micro, chapitre par chapitre, en paragraphes d’un souffle, avec ce qu’on voit à l’image.",
    icon: "story",
    scope: "Vidéos longues",
    job: "long_write",
    when: "Après le plan (3 chapitres par appel), puis pour chaque correction du relecteur et chaque « Réécrire ce chapitre ».",
    inputs: ["Le plan complet", "Les chapitres déjà écrits (continuité)", "Le dossier", "Les corrections demandées, s’il y en a"],
    consignes: ["guide_long_mystere", "guide_long_epoque", "rules_storytelling", "rules_long"],
    output: "Des paragraphes de 40 à 110 mots : le texte lu (nombres en chiffres) et ce qu’on voit.",
    then: "Le correcteur mesure (longueurs, phrases, formules interdites), le relecteur juge ; deux tours de corrections, puis une relecture finale.",
  },
  {
    key: "long_review",
    name: "Vidéos longues · relecteur",
    summary: "Relit le script complet à la place d’un spectateur qui a cliqué : promesse tenue, ouverture, fil, relances, exactitude, langue, fin.",
    icon: "review",
    scope: "Vidéos longues",
    job: "long_write",
    when: "Après l’écriture des chapitres, à chaque tour de corrections, et une dernière fois à la fin.",
    inputs: ["Le script numéroté (chapitre, paragraphe)", "L’idée et son emballage", "Le dossier"],
    consignes: ["rules_storytelling", "rules_long"],
    output: "ok ou non, jusqu’à 10 problèmes (chapitre, paragraphe, correction attendue) et ce qui marche déjà.",
    then: "Les problèmes repartent au conteur ; ceux de la relecture finale s’affichent au-dessus du script.",
  },
  {
    key: "long_director",
    name: "Vidéos longues · réalisateur",
    summary: "Découpe chaque paragraphe en plans de 5 à 8 s : image animée, clip ou carte, et le mot où l’image change.",
    icon: "shots",
    scope: "Vidéos longues",
    job: "long_write",
    when: "Quand tu valides le script (environ 900 mots par appel).",
    inputs: ["Les paragraphes, mots numérotés toutes les 5", "Ce que le conteur veut montrer", "La bible visuelle"],
    consignes: ["rules_long_images"],
    output: "Pour chaque plan : paragraphe, mot de départ, image / clip / carte, prompt de l’image en anglais, mouvement ; la bible visuelle commune.",
    then: "Les images partent chapitre par chapitre sur la carte graphique, puis les clips depuis leur image.",
  },
  {
    key: "long_packaging",
    name: "Vidéos longues · titres et miniatures",
    summary: "Prépare la publication : 3 à 5 titres, la description, les tags, le commentaire épinglé, 3 concepts de miniature et la musique.",
    icon: "seo",
    scope: "Vidéos longues",
    job: "long_write",
    when: "À la fin de l’écriture du script.",
    inputs: [
      "L’idée (titre et miniature de départ)",
      "Le script complet",
      "Les ambiances de musique des vidéos longues",
      "Les leçons validées pour le SEO",
    ],
    consignes: ["rules_thumbnail"],
    output: "Titres avec leur levier et le meilleur, description (sans chapitres ni sources), 12 à 20 tags, 3 hashtags, commentaire épinglé, 3 miniatures (image + texte), ambiance musicale.",
    then: "Tu choisis dans « Titre et miniature » ; à l’envoi, le code ajoute les chapitres horodatés, les sources et la mention de l’IA.",
  },
  {
    key: "long_image_check",
    name: "Vidéos longues · contrôle des images",
    summary: "Regarde les images d’un chapitre (6 à la fois) et signale un vrai défaut : lettres, mains déformées, sujet absent, anachronisme.",
    icon: "keyframe",
    vision: true,
    scope: "Vidéos longues",
    job: "long_make",
    when: "Après les images de chaque chapitre.",
    inputs: ["Les images et ce que chacune devait montrer"],
    consignes: [],
    output: "Pour chaque image : bonne ou non, et le défaut.",
    then: "Une image ratée est refaite une fois ; elle porte « refaite » dans l’onglet Images.",
  },
  {
    key: "long_factcheck",
    name: "Vidéos longues · vérificateur des faits",
    summary: "Confronte chaque fait du script (dates, nombres, noms, causes, superlatifs) aux sources du dossier : pas de désinformation.",
    icon: "review",
    scope: "Vidéos longues",
    job: "long_write",
    when: "Après la relecture finale du script, puis une seconde fois après les corrections.",
    inputs: ["Le script numéroté", "Le dossier : Wikipédia et les sources sérieuses qu’elle cite (CNRS, INRAP, musées, revues, grands journaux)"],
    consignes: [],
    output: "Chaque fait : confirmé (avec ses sources), hypothèse dite comme telle, pas dans les sources, ou contredit, avec la correction.",
    then: "Les faits non confirmés repartent au conteur ; le bilan et la liste des sources s’affichent dans l’onglet Script.",
  },
  {
    key: "long_thumbs",
    name: "Vidéos longues · nouvelles miniatures",
    summary: "Propose de nouveaux concepts de miniature, différents de ceux qui existent, dans le style des miniatures qui marchent dans la niche.",
    icon: "seo",
    scope: "Vidéos longues",
    job: "long_make",
    when: "Quand tu cliques « Proposer 3 autres miniatures » (les miniatures gardées restent).",
    inputs: ["Le titre, l’idée centrale, la promesse, les chapitres", "Les miniatures déjà faites, leur note et celles que tu gardes", "Le style de la niche"],
    consignes: ["rules_thumbnail", "guide_thumb_niche"],
    output: "Des concepts : ce qu’ils montrent, le prompt de l’image, 0 à 4 mots de texte, le côté du texte.",
    then: "Les images sont faites, le texte posé par le code, chaque miniature notée ; elles s’ajoutent aux autres.",
  },
  {
    key: "long_thumb_style",
    name: "Vidéos longues · style des miniatures de la niche",
    summary: "Regarde les miniatures des vidéos qui marchent le mieux dans la niche et en tire un style et des règles concrètes.",
    icon: "keyframe",
    vision: true,
    scope: "Vidéos longues",
    job: "long_write",
    when: "Quand tu cliques « Étudier les miniatures de la niche » (onglet Titre et miniature).",
    inputs: ["Les miniatures des vidéos les plus vues de la Découverte (histoire, mystères…), avec leur titre et leurs vues"],
    consignes: [],
    output: "Le style commun en quelques phrases et 6 à 10 règles à suivre.",
    then: "Il remplace la consigne par défaut pour les titres, l’emballage et les nouvelles miniatures.",
  },
  {
    key: "long_thumb_check",
    name: "Vidéos longues · notes des miniatures",
    summary: "Note chaque miniature comme vue en petit sur un téléphone : lisible, tentante avec le titre, sans défaut.",
    icon: "keyframe",
    vision: true,
    scope: "Vidéos longues",
    job: "long_make",
    when: "Après la fabrication des miniatures.",
    inputs: ["Le titre", "Les miniatures réduites à la taille d’un téléphone"],
    consignes: [],
    output: "Une note sur 10 et une phrase par miniature.",
    then: "La mieux notée est choisie par défaut ; tu peux en choisir une autre.",
  },
];

export const CONSIGNES: ConsigneDef[] = [
  {
    key: "rules_storytelling",
    name: "Règles du récit",
    summary:
      "L’art de raconter, pour toute histoire : une seule idée, les 3 C, l’enjeu, « mais » et « donc », montrer plutôt que dire, l’accroche sans délai et sa promesse, les boucles ouvertes, l’ironie dramatique, des mots simples et un rythme varié, la fin écrite en premier, la checklist.",
    usedBy: ["idea", "script", "script_review", "scene_rewrite", "script_drama", "script_rewrite", "hook_rewrite"],
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
    key: "guide_timelapse_insolite",
    name: "Guide · lieu insolite en accéléré",
    summary: "Ce qu’est une bonne idée de lieu insolite : un endroit improbable qui devient un cocon tout confort, dehors puis dedans, une accroche qui pose l’énigme.",
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
    key: "guide_quote",
    name: "Guide · citation",
    summary: "Ce qu’est une bonne citation : une vérité que chacun a vécue, dite simplement, un rythme et une chute, inédite et sans signature ; et l’image qui porte la même émotion.",
    usedBy: ["idea"],
  },
  {
    key: "guide_quote_auteur",
    name: "Guide · citation d’auteur",
    summary: "Comment choisir, parmi les citations sourcées de Wikiquote, celles qui touchent : la vie de chacun, comprise seule à la première lecture, un nom connu ; recopiées mot pour mot.",
    usedBy: ["idea"],
  },
  {
    key: "rules_hook_title",
    name: "Règles du titre d’accroche",
    summary: "Le titre gravé à l’écran (où et sur quels formats : onglet Montage) : 3 à 8 mots, parlé, qui donne envie de voir la suite.",
    usedBy: ["script", "script_timelapse", "script_timelapse_insolite", "script_tour", "script_drama", "scenario_adapt", "script_scenario", "script_rewrite", "hook_rewrite"],
    note: "Le correcteur vérifie aussi, avec ses propres valeurs : 3 à 8 mots et 70 caractères au plus. Un nombre écrit en lettres passe en chiffres au montage (« Huit cent cinquante-deux morts » → « 852 morts »).",
  },
  {
    key: "hint_continuity",
    name: "Continuité entre clips",
    summary: "Quand un clip prolonge le précédent (il part de sa dernière image) et quand il coupe.",
    usedBy: ["script_shots"],
  },
  {
    key: "rules_long",
    name: "Règles du récit long",
    summary:
      "Ce qu’ajoute une vidéo de 20 à 25 min : la première minute qui confirme le clic, une question centrale tenue jusqu’au bout, des chapitres liés par « mais » et « donc », des relances vers 3, 6 et 10-12 min, le vrai et seulement le vrai, un narrateur qui raconte à un ami, la fin sans appel à s’abonner.",
    usedBy: ["long_idea", "long_outline", "long_writer", "long_review"],
    note: "Le correcteur vérifie aussi : 150 mots par minute (de 90 à 112 % du total visé), chapitres à ±25-30 %, paragraphes de 20 à 140 mots, phrases de 26 mots au plus, 1re phrase de 24 mots au plus, ni formule d’introduction, ni « et ensuite », ni appel au public, ni superlatif vide.",
  },
  {
    key: "rules_long_images",
    name: "Règles de l’image (vidéos longues)",
    summary: "Image 16:9 de cinéma qui montre ce que dit la voix, l’époque visible, jamais un visage réel reconnaissable, aucune lettre, une carte pour situer un lieu réel.",
    usedBy: ["long_director"],
  },
  {
    key: "rules_thumbnail",
    name: "Règles de la miniature",
    summary:
      "Titre et miniature se complètent sans se répéter ; 3 éléments au plus ; l’anomalie, jamais la réponse ; lumière forte et couleurs opposées ; image sans texte, 0 à 4 mots posés par le code ; honnête ; 3 concepts vraiment différents.",
    usedBy: ["long_idea", "long_packaging"],
  },
  {
    key: "guide_long_mystere",
    name: "Format « Mystère » (vidéos longues)",
    summary: "Une énigme réelle de l’histoire menée comme une enquête : l’énigme, ce qu’on croyait, les indices, les fausses pistes, la révélation, ce qui reste inexpliqué.",
    usedBy: ["long_idea", "long_outline", "long_writer"],
  },
  {
    key: "guide_long_epoque",
    name: "Format « Ta vie à l’époque » (vidéos longues)",
    summary: "Une condition dure du passé vécue en deuxième personne et au présent, avec une colonne vertébrale (les heures d’une journée, les rangs d’une hiérarchie).",
    usedBy: ["long_idea", "long_outline", "long_writer"],
  },
  {
    key: "guide_thumb_niche",
    name: "Style des miniatures « histoire et mystères »",
    summary: "Le monument ou l’objet énorme et net avec des humains minuscules, une anomalie qui se voit, un contraste froid / chaud, le « toi » de dos pour « ta vie à l’époque », 2 à 4 mots jaunes qui posent le conflit.",
    usedBy: ["long_packaging", "long_thumbs"],
    note: "Remplacé par le style relevé sur les miniatures qui marchent dès que tu cliques « Étudier les miniatures de la niche ».",
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
        agents: [
          "script",
          "script_timelapse",
          "script_timelapse_insolite",
          "script_tour",
          "script_drama",
          "script_quote",
          "script_quote_auteur",
        ],
        jobs: ["script"],
        model: "llm",
      },
      {
        id: "scenario_team",
        kind: "agent",
        title: "Équipe de ton scénario",
        detail:
          "Un scénario écrit dans Création → « Mon scénario » : le metteur en scène le met en forme, le scénariste écrit les plans, le relecteur vérifie qu’ils réalisent bien ton texte.",
        agents: ["scenario_adapt", "script_scenario", "scenario_review"],
        jobs: ["script"],
        model: "llm",
        only: "Mes scénarios",
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
        id: "story_rewrite",
        kind: "agent",
        title: "Récit réécrit",
        detail:
          "Sur ta demande (Retoucher → Récit), avant ou après la sortie : le conteur réécrit tout le texte dit, ou l’accroche seule, sur les mêmes plans ; tu relis, puis une nouvelle vidéo est faite avec les mêmes clips.",
        agents: ["script_rewrite", "hook_rewrite"],
        jobs: ["rewrite"],
        model: "llm",
        only: "à ta demande",
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
