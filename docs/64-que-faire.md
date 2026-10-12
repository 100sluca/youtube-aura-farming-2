# 64 · Recherche : que faire, lire les chiffres, refaire ce qui a marché, niches hors des nôtres (04/10)

Demande de Luca (04/10, page Recherche) : les vues médianes lui parlent, mais pas la note ; avec toutes ces données il
ne sait pas quelle vidéo faire. Il veut :
- qu'on lui explique les chiffres, et qu'on lui dise directement quelle vidéo est la plus intéressante à faire ;
- **reprendre ce qui a déjà marché** : même fait, même structure, même scénario, mais avec ses mots, en français (une
  vidéo anglaise qui a fait le buzz se refait en français) ; pas de phase d'exploration ;
- voir les niches qui marchent **hors de celles prévues** (Minecraft, jeux vidéo, montres…), quitte à en ajouter ;
- une page plus claire (la Découverte, « Explorer un sujet »).

Migration **0056**. Suite de docs/60 (veille) et docs/63 §9 (Découverte des vidéos longues).

## 1. Lire les chiffres

Encadré **Comment lire ces chiffres** en haut de l'onglet Niches ; le même texte sert au stratège.

| Chiffre | Ce qu'il veut dire | Piège |
|---|---|---|
| **Vues médianes** | Pour la recherche de la niche, les 50 Shorts les plus vus publiés pendant le dernier mois jugé (un mois se juge 3 semaines après sa fin) : la moitié de ces 50 a fait plus. | C'est le **haut du panier**, pas « la moitié des vidéos de la niche » : une vidéo moyenne, ou une chaîne qui démarre, fait beaucoup moins. Ça sert à comparer les niches. |
| **Tubes** | Parmi ces 50, ceux à 1 M de vues et plus. | Oui, c'est bien « plus d'un million ». |
| **Porte ouverte** | Part de ces tubes faits par une chaîne de moins de 10 000 abonnés ou de moins de 6 mois. | Haute = YouTube pousse encore les nouveaux : c'est là qu'on a notre chance. |
| **Phase** | Les 2 derniers mois jugés ÷ les 3 d'avant, **comparé à l'ensemble des niches** (§5). | |
| **Note /100** | 35 demande (10 k → 0, 10 M → 35, échelle log) + 25 élan (phase) + 20 porte ouverte + 20 faisabilité (effort moyen pour nos recettes). | Le détail en points s'affiche dans la fiche de la niche (« Demande 27 / 35 »…). |
| **× N** d'une vidéo | Ses vues ÷ la médiane des Shorts de sa chaîne. | Un × 100 sur une petite chaîne : c'est le sujet qui a porté, donc ça se refait. |

Exemple, Cabanes et mini-maisons (83) : 2,2 M de vues médianes → demande 0,78 × 35 = 27 ; en hausse → 0,9 × 25 = 23 ;
83 % de porte ouverte → 17 ; effort 1,9 → 0,82 × 20 = 16.

## 2. Découverte → Shorts : les niches hors des nôtres

Onglet **Découverte**, volet **Shorts** (le volet **Vidéos longues** reste celui de docs/63 §9, pour Arzak Parker).

- `worker/discovery_shorts.py` : 73 grands sujets qui ne sont pas dans nos 22 niches (Minecraft en anglais et en
  français, Roblox, Fortnite, GTA, montres, bijoux, sneakers, supercars, motos, avions, trains, engins de chantier,
  recettes, street food, football, NBA, MMA, F1, musculation, animaux filmés, dinosaures, pêche, bois, forge, Lego,
  dessin, animation 3D, expériences, géographie, mythologie, gadgets, outils d'IA, argent, immobilier, crypto, histoires
  Reddit, horreur, faits divers, films, anime, magie, musique, voyages, hôtels…).
- Chaque sujet devient une niche « découverte » (`research_niches.origin = 'discover'`, `status = 'proposed'`) mesurée
  **exactement comme nos niches** : une recherche YouTube sur le dernier mois jugé (50 Shorts), vues médianes, tubes,
  porte ouverte ; ses 6 Shorts les plus vus sont classés (format, recette proche, effort) pour la faisabilité.
- Coût : une recherche par sujet et par mois (un mois jugé ne change plus). Chaque jour à 9 h 45, 15 recherches au plus
  (`app_settings.research.discover_shorts_searches`) ; « Découvrir maintenant » en prend 40. Balayage complet du 04/10 :
  73 recherches.
- Carte d'une niche : note et ses 4 parts, effort et ce qu'il veut dire (« nos recettes la font déjà » … « hors de portée :
  tournage, visage ou jeu vidéo »), ses 4 Shorts les plus vus (Analyser, Refaire). **Suivre chaque jour** la fait entrer
  dans la veille (courbe sur 12 mois en quelques jours) ; **Écarter** l'archive (plus remesurée). Filtre « Faisables chez
  nous (effort 1 à 3) ».
- Le stratège voit les 15 meilleures niches découvertes, marquées « DÉCOUVERTE », et dit lesquelles valent une recette.
- Les vidéos d'effort 5 (jeu vidéo, tournage, visage) ne sont jamais proposées à reproduire.

« Tester un sujet » (ancien « Explorer un sujet ») reste pour une idée précise ; la liste de ses niches proposées ne
montre plus les découvertes.

## 3. Refaire fidèlement (version fidèle en français)

Le choix de Luca : on ne réinvente pas la roue, on refait ce qui a marché, à notre manière.

- Agent **`research_adapt`** (onglet Agents ; Gemini regarde la vidéo par son adresse) : titre en français (même
  promesse), sujet repris tel quel, ouverture (même image à 0 s, même question), déroulé temps par temps (image à
  fabriquer + paroles), texte de la voix off, scénario complet pour une histoire jouée, même fin, même durée, recette et
  thème, **faits à vérifier**. Règles : chaque phrase reformulée (jamais traduite mot à mot), nos images, aucun nom de
  chaîne ni filigrane ; un fait douteux est signalé et corrigé.
- Rangé dans `research_videos.adaptation` ; affiché dans « Pourquoi ça marche » (encadré violet).
- **Refaire** (bouton des cartes, mode `fidele` par défaut) : Gemini regarde la vidéo si besoin, écrit la version fidèle,
  puis la production part : idée du thème le plus proche (source `clone`, la version fidèle en prémisse : le conteur
  garde le sujet et le déroulé) ou équipe « Mon scénario » pour une histoire jouée (son relecteur de fidélité tient le
  scénario). Le storyboard reste à valider dans Création.
- L'ancienne voie reste dans le dialogue : **Faire une histoire nouvelle** (même mécanique, autre sujet, docs/60).
- « Écrire la version fidèle d'abord » : la lire avant de lancer.
- Filtre de langue des vidéos à reproduire : « Anglais, français et proches » par défaut (titre surtout en alphabet
  latin) ; les vidéos en hindi ou en bengali passent aussi après dans le choix du stratège (× 0,7).

## 4. Que faire : la vidéo à faire maintenant, et les questions au stratège

Premier onglet, renommé **Que faire** :
- **La vidéo à faire maintenant** : le stratège la choisit à chaque rapport (`next_video` : la plus forte, récente,
  faisable, dans une niche qui tient), avec pourquoi et comment ; à défaut, la première de ses vidéos à reproduire.
  Bouton Refaire.
- **Pose ta question au stratège** (agent `research_ask`, chaîne « writer ») : il reçoit toute la veille (niches suivies
  et découvertes, 20 vidéos à reproduire avec l'analyse de Gemini, temps de fabrication, leçons, dernier rapport, 3
  derniers échanges) et répond en 10 lignes au plus, en finissant par ce qu'il faut faire ; les vidéos et niches citées
  s'affichent sous la réponse. Tâche `research` action `ask`, réponse dans `jobs.result` (pas de table).

## 5. Corrections

- **Mois mesuré sur trop peu de Shorts** : le 02/10, la recherche d'août des faits insolites n'a rendu que 3 Shorts d'une
  seule chaîne (9,5 M de vues médianes, 0 % de porte ouverte) : un mois sous 10 Shorts n'est plus « jugé », sort de la
  courbe et se remesure une fois par semaine. Faits insolites : 70 → 62 (juillet, 3,6 M, 24 % de porte ouverte).
- **Élan comparé au marché** : en juillet 2026 presque toutes les niches ont bondi d'un coup ; 17 sur 22 étaient « en
  hausse », l'élan ne départageait plus rien. La phase se juge désormais sur le rapport de la niche ÷ celui de toutes les
  niches suivies (`market_ratio`, médiane, 5 niches au moins ; × 1,6 au 04/10). Motivation passe « en baisse », citations
  et « et si » « installées ».
- **Message du stratège** : il lisait des champs qui n'existaient plus (`median_views_30`, `hits_30`) et recevait « ? » pour
  les vues et les tubes de chaque niche ; il reçoit maintenant vues médianes, mois, nombre de Shorts, tubes, tubes de la
  semaine.

## 6. Rattrapage des tâches quotidiennes

Le 04/10, ni la découverte de 9 h 30 ni le relevé de 10 h n'étaient partis (worker arrêté à l'heure dite : le
planificateur ne rattrape pas une heure manquée). `scheduler.catch_up_research`, toutes les 15 min : chaque tâche du jour
(9 h 30 découverte longue, 9 h 45 découverte Shorts, 10 h relevé) dont l'heure est passée et qui n'a pas été mise en file
depuis 9 h part, dans l'ordre.

## 7. Premiers résultats (04/10 au soir, vrais appels)

- Balayage complet : 73 recherches, 3 382 Shorts, 416 classés, 8 min (lancé hors du worker, qui attendait la fin d'une
  vidéo longue pour recharger son code).
- Meilleures niches découvertes (août 2026) :

| Niche | Note | Vues médianes | Tubes | Porte ouverte | Effort | Lecture |
|---|---|---|---|---|---|---|
| Corps humain et santé | 68 | 2,1 M | 46 / 49 | 63 % | 2 | organes animés en 3D, récit narré : à essayer |
| Travail du bois | 67 | 8,9 M | 50 / 50 | 52 % | 3,3 | énorme demande, nouvelle recette (gestes précis) |
| Restauration de voitures | 65 | 844 k | 19 / 44 | 68 % | 1,8 | notre recette chantier telle quelle |
| Roblox | 64 | 25 M | 47 / 47 | 15 % | 2,5 | gros, mais tenu par de grosses chaînes |
| Comment c'est fabriqué | 64 | 4,4 M | 48 / 48 | 71 % | 4 | très ouvert, difficile pour l'IA |
| Minecraft | 57 | 17 M | 47 / 47 | **4 %** | 3,5 | porte fermée : à éviter |
| Montres | 43 | 846 k | 21 / 50 | 10 % | 3,9 | faible, face caméra |

- Stratège (nouveau rapport) : **la vidéo à faire** = « Desert Shelter, I Built a Hidden Semi-Underground Survival
  Home » (9 M de vues, × 267 sa chaîne de 17 k abonnés, effort 1, timelapse) ; niches à lancer : cabanes, abris
  souterrains, survie ; à éviter : motivation (en baisse par rapport au marché) ; à ajouter : restauration de voitures,
  comment c'est fabriqué.
- Version fidèle de la Desert Shelter (Gemini 3.8 Flash, 1 min) : muette, 9 temps (cercle blanc tracé au sol à 0 s →
  fosse → rondins → toit → sable et panneau solaire → pierres → intérieur bois → poêle → plan de nuit étoilé), thème
  `lieux_insolites`. Aucune production lancée (c'est à Luca de cliquer « Refaire »).
- Question test « Minecraft ou les montres ? » : « oublie les deux (porte à 4 % ; montres 43/100, face caméra) ;
  ajoute Restauration de voitures (65, porte 68 %, effort 1,8, timelapse), ou Corps humain en récit ».

## 8. Comment c'est fait

| Où | Quoi |
|---|---|
| `supabase/migrations/0056_recherche_que_faire.sql` | `origin` 'discover', `research_videos.adaptation(_at)`, mois sous 10 Shorts plus jugés |
| `worker/research.py` | `month_ok`, `curve_ratio`, `market_ratio`, `niche_phase(…, market)`, `mostly_latin` |
| `worker/research_agents.py` | `Adaptation` + `ADAPT_PROMPT`, `AskAnswer` + `ASK_PROMPT`, `next_video` du rapport, message du stratège corrigé |
| `worker/discovery_shorts.py` | `SEEDS`, `ensure_seeds`, `discover_shorts` |
| `worker/steps/research.py` | `scan(weekly=, classify_top=)`, `market_of`, `adapt`, `reproduce(mode=)`, `strategist_inputs`, `ask` ; actions `adapt`, `ask`, `discover_shorts` |
| `worker/scheduler.py` | `daily_discover_shorts` (9 h 45), `catch_up_research` |
| `apps/dashboard/src/components/research/` | `research-view.tsx` (Que faire, questions, Découverte en deux volets), `research-niches.tsx` (`HowToRead`, `ScoreParts`), `research-videos.tsx` (version fidèle, Refaire, langue), `research-discover-shorts.tsx` |
| `apps/dashboard/src/lib/research*.ts`, `app/research/actions.ts` | types, lecture (questions, vidéos citées, Shorts des niches découvertes sur 75 jours), actions `reproduceVideo(mode)`, `adaptVideo`, `askStrategist`, `discoverShortsNow` |
| `apps/dashboard/src/lib/agent-catalog.ts` | agents `research_adapt`, `research_ask` |
| `tests/test_research.py` | mois trop petit, élan du marché, alphabet latin, sujets de la découverte |
