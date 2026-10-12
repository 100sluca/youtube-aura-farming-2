# 60 · Page Recherche : niches, tendances et vidéos à reproduire (02/10)

> Suite le 04/10 dans **docs/64-que-faire.md** : comment lire les chiffres, « Que faire » (la vidéo à faire, questions
> au stratège), version fidèle en français (Refaire), Découverte des niches Shorts hors des nôtres, élan comparé au
> marché, mois sous 10 Shorts écartés.

Demande de Luca (02/10) : trouver les vidéos courtes qui marchent le plus, dans quelle niche, pourquoi elles marchent,
combien de temps une niche dure, et que l'appli recommande quoi produire, jusqu'aux vidéos à reproduire. Une page
dédiée, intégrée à l'usine. Contrainte : **tout gratuit**. Un outil sans API gratuite, on refait son analyse nous-mêmes.
Migrations **0049** (job `research`) et **0050** (tables).

## 1. Pour Luca

Menu **Recherche**. En haut, **Relever maintenant**, le compteur de recherches YouTube du jour et la dernière tâche.
Le relevé tourne aussi seul chaque jour à 10 h.

| Onglet | Ce qu'on y trouve |
|---|---|
| **Recommandations** | Ce que le stratège conseille (chaque lundi, ou « Nouvelles recommandations ») : niches à lancer, à tester, à surveiller ou à éviter, chiffres à l'appui, avec comment les faire et de premiers titres ; vidéos à reproduire maintenant ; formats rapides à fabriquer ; niches à ajouter à la veille (bouton **Suivre**). |
| **Niches** | Chaque niche suivie : phase (émergente, en hausse, installée, en baisse, à vide), note sur 100, vues médianes, tubes, porte ouverte, âge, recette de chez nous, effort, **courbe sur 12 mois**. Un clic ouvre le détail : courbe mois par mois, pic, élan des 7 derniers jours, concentration, recherches utilisées, ses Shorts les plus vus du mois. Pause ou retrait par niche ; ajout d'une niche à la main (nom + une ou deux recherches YouTube). |
| **Vidéos à reproduire** | Les Shorts qui dépassent le plus leur chaîne (× sa médiane), rapides, frais et faciles à refaire, filtrables par niche et par effort. **Analyser** : Gemini regarde la vidéo. **Pourquoi ça marche** : son analyse (accroche, déroulé, raisons, points faibles) et notre version. **Reproduire** : notre version part en fabrication. Épingler, écarter. |
| **Explorer et régler** | Un sujet tapé (« tiny house in a forest ») devient une niche proposée, relevée tout de suite (la semaine + 6 mois, 7 recherches) : **Suivre** ou oublier. Réglages : recherches par jour, vidéos regardées par Gemini après chaque relevé, vues minimum, jour des recommandations. |

« Reproduire » ne copie rien : même mécanique (accroche visuelle, structure, durée, émotion), sujet, lieu et
personnages nouveaux. Une histoire jouée va à l'équipe « Mon scénario » (docs/59) avec un scénario complet ; le reste
devient une idée du thème le plus proche (chantier, visite, récit, citation). La production part tout de suite ; le
storyboard reste à valider dans Création.

Les trois agents (classeur, analyste vidéo, stratège) sont dans l'onglet **Agents**, modifiables comme les autres.

## 2. Les outils cités : verdict

| Outil | Ce qu'il fait | API | Verdict |
|---|---|---|---|
| **Virlo** (virlo.ai) | Tendances TikTok/Shorts/Reels, sons, « outliers », base d'accroches | oui, à l'appel (10 $ de dépôt, 0,05 à 1 $ l'appel) ; appli 49 $/mois | le seul branchable, mais payant : pas retenu |
| **Pentos** | Tendances TikTok | non | fermé (domaine éteint au 02/10) |
| **Exolyt** | Statistiques TikTok, écoute sociale | non (CSV) ; 250 €/mois | à écarter |
| **Analisa.io** | Profils et hashtags TikTok | non (« plus tard ») ; 69 $/mois | à écarter |
| « Octupi » = **Octupie** | Agent qui trouve les posts à × 10 et les réécrit en scripts | non, liste d'attente ; Reels seulement | l'idée est reprise ici (vidéos à reproduire) |
| « Reten6 » = **Retensis** | Notes accroche/rythme/son, rétention prédite | non ; 19,99 € les 40 analyses | refait gratuitement par Gemini (§5) |
| **Exploding Topics** | Sujets de recherche en croissance | ≈ 1 249 $/mois avec l'API | hors budget |

Sources : pages de prix de chaque outil, consultées le 02/10/2026.

## 3. Ce qu'on refait nous-mêmes, gratuitement

| Source | Ce qu'elle donne | Limite |
|---|---|---|
| API YouTube `search.list` (jeton d'une de nos chaînes) | les 50 Shorts les plus vus d'une recherche, sur une période (`publishedAfter` / `publishedBefore`) | **100 recherches par jour**, compteur à part (docs/05 §3) ; la veille en prend 90 (réglable) |
| `videos.list` (50 par appel), avec `player` | vues, likes, commentaires, durée, **taille du lecteur** : un Short est vertical (720 × 1280) | 1 unité / 50 vidéos sur 10 000 |
| `channels.list` | abonnés, **date de création** de la chaîne | 1 unité / 50 chaînes |
| Playlist **`UUSH` + identifiant de chaîne** | les seuls Shorts d'une chaîne (astuce connue, non documentée, vérifiée le 02/10) → médiane de la chaîne | 2 unités par chaîne, 30 chaînes par relevé |
| **Gemini** avec l'adresse YouTube (`file_data.file_uri`) | regarde la vidéo, image et son, sans téléchargement | gratuit jusqu'à 8 h de vidéo par jour ; résolution basse (≈ 6 000 jetons par Short) ; les quotas du jour des modèles Flash sont souvent pris par les autres agents l'après-midi : Flash-Lite prend le relais |

Vérifié en direct le 02/10 : `chart=mostPopular` ne renvoie **aucun** Short (0 vertical sur 50 en France) : les
tendances viennent donc des recherches par niche. TikTok Creative Center demande une connexion et son adresse JSON
interne répond « no permission » ; la Research API de TikTok est réservée aux universitaires.

Règle développeur YouTube : une donnée de l'API non rafraîchie depuis 30 jours est effacée. Le relevé rafraîchit
chaque jour les vidéos de moins de 45 jours et celles gardées (analysées, retenues, reproduites) ; les autres
disparaissent au bout de 30 jours. Les courbes de niche ne gardent que nos propres calculs.

## 4. Les calculs (worker/research.py, testés)

- **Surperformance** (« outlier » de vidIQ, 1of10, Nexlev) : vues ÷ médiane des Shorts de la chaîne (ceux de plus de
  2 jours, 5 au moins) ; à défaut vues ÷ abonnés (1 000 au moins). Un × 10 sur une petite chaîne, c'est le sujet qui a
  porté la vidéo, pas l'audience : c'est ce qu'on veut reproduire.
- **Vitesse** : vues ÷ jours depuis la mise en ligne ; relevé chaque jour pour suivre la vie d'une vidéo.
- **Porte ouverte** : part des tubes faits par une petite chaîne (< 10 k abonnés) ou une chaîne de moins de 6 mois.
  Haute = l'algorithme pousse encore les nouveaux venus ; basse = niche tenue par quelques grosses chaînes.
- **Concentration** : part des tubes des 3 chaînes qui en ont le plus.
- **Courbe d'une niche, mois par mois** : pour chaque mois de mise en ligne, les Shorts les plus vus publiés ce
  mois-là (la recherche principale de la niche, `publishedAfter` / `publishedBefore`). Un mois n'est jugé que **3
  semaines après sa fin**, quand les vues de ses Shorts se sont tassées ; ensuite il ne change plus : il se mesure
  une fois. Pourquoi : la recherche « les plus vus de l'année » favorise les vieilles vidéos, qui ont eu le temps
  d'accumuler des vues ; le premier essai du 02/10 classait ainsi à tort « en baisse » une niche en pleine forme.
  Niveau d'un mois : la médiane des vues de ses meilleurs Shorts ; tube = 1 M de vues.
- **Phase** : dès 4 mois jugés, rapport des deux derniers mois aux trois d'avant (× 1,3 : en hausse ; × 0,7 : en
  baisse ; ou retombée de moitié depuis un pic vieux de 4 mois et plus) ; premier tube il y a 4 mois au plus :
  émergente ; aucun tube et médiane < 100 k : à vide. Tant que la courbe est courte, l'élan des relevés « 7 derniers
  jours » d'une semaine à l'autre décide. **Âge** : mois depuis le premier mois à tube (« 1 an et + » si la courbe
  commence déjà par un tube).
- **Note d'une niche** (sur 100) : 35 % demande (vues médianes du dernier mois jugé, 10 k → 0, 10 M → 1, échelle
  log), 25 % élan (phase), 20 % porte ouverte, 20 % faisabilité (effort moyen de ses vidéos pour nos recettes).
- **Vidéos à reproduire** : 35 % surperformance (log, × 100 = plein), 25 % vitesse, 15 % fraîcheur (0 à 120 jours),
  25 % faisabilité ; publiées depuis moins de 60 jours, 50 k vues au moins, effort ≤ 3 pour Gemini (≤ 4 affichées).

Même formules dans `apps/dashboard/src/lib/research-types.ts` (outlier, note de reproduction) : à changer ensemble.

Coût en recherches : chaque niche 1 ou 2 par jour (ses recherches sur 7 jours), plus 1 par mois de sa courbe la
première fois (12), puis 1 par mois. Avec 22 niches et 90 recherches par jour, toutes les courbes sont complètes en
4 à 5 jours (au 02/10, 227 mois restaient après le premier relevé complet) ; les derniers mois arrivent d'abord,
pour toutes les niches à tour de rôle.

## 5. Les agents

| Agent (clé) | Chaîne | Reçoit | Rend |
|---|---|---|---|
| Classeur (`research_classify`) | « default », images | par lots de 16 : titre, chaîne, chiffres, surperformance, début de description, **miniature recadrée en 9:16** ; nos recettes et thèmes | format (liste fixe), niche en quelques mots, recette et thème les plus proches, effort 1 à 5, IA ou non, sans visage ou non, ce qui arrête le pouce |
| Analyste vidéo (`research_watch`) | Gemini seulement, chaîne d'écriture puis par défaut | **la vidéo elle-même** par son adresse, sa fiche, nos recettes avec leur temps de fabrication mesuré, nos thèmes | résumé, accroche (image à 0 s, ce qui change avant 2 s, première phrase), déroulé seconde par seconde, rythme, son, textes, émotion, fin, pourquoi ça marche, points faibles, format, recette, thème, effort, **notre version** (titre, idée, ouverture, scénario complet si histoire jouée, style, paroles, durée, ce qu'on garde, ce qu'on change) |
| Stratège (`research_brief`) | « writer » | niches (phase, raison, note et ses parts, vues, tubes, âge, formats, effort), 15 meilleures vidéos à reproduire avec l'analyse de Gemini, temps de fabrication mesuré par recette (`job_runs`, docs/45), leçons validées de nos vidéos | recommandation principale, niches avec verdict, vidéos à reproduire, formats rapides, niches à ajouter, limites |

Effort : 1 = une recette le fait telle quelle ; 2 = avec un réglage ; 3 = nouvelle recette ; 4 = difficile pour l'IA ;
5 = impossible sans tournage, visage ou jeu vidéo.

Temps de fabrication mesuré au 02/10 (médiane d'une vidéo prête, toutes tâches) : citation ≈ 0,05 h, histoire jouée
≈ 0,25 h, chantier ≈ 1,5 h, récit ≈ 1,9 h. Le stratège s'en sert pour les **formats rapides** : c'est la réponse à
« produire plus vite avec moins de retouches » : viser les niches où la note est haute ET la recette courte.

## 6. Premiers essais (02/10, vrais appels)

- Relevé de 2 niches, 12 mois : 28 recherches, 1 246 Shorts, 96 classés, 2 min 10 ; puis les 20 autres (7 jours + 13
  mois) : 50 recherches, 2 197 Shorts, 2 min 36.
  - **Abris et maisons souterraines en accéléré** : **en hausse** (× 5,5 sur les deux derniers mois jugés), pic en
    juillet 2026, 45 % des tubes du mois par de petites ou nouvelles chaînes, effort 2, note 64/100.
  - **Histoires de fruits IA** : **en baisse** (× 0,4), pic en mars-avril 2026, note 34/100.
  - C'est ce que Luca avait constaté à la main (docs/51 : chantiers 5 fois plus vus que les histoires de fruits).
- Gemini (Flash-Lite, 15 s) sur la meilleure vidéo à reproduire (36 M de vues) : il a relevé tout seul le **cercle
  blanc tracé au sol à 0 s** (même constat que docs/57, fait à la main), le déroulé, les raisons, et proposé notre
  version dans le thème « Lieux insolites » (effort 2). Sur une histoire animée (Flash 3, 41 s) : un scénario complet
  pour l'équipe « Mon scénario ».
- « Reproduire » testé dans une transaction annulée (rien de créé) : idée `clone` du thème + production + script en
  file ; scénario pour une histoire jouée.

## 7. Comment c'est fait

| Où | Quoi |
|---|---|
| `supabase/migrations/0049_recherche_job.sql` | `job_type` « research » (seul dans son fichier) |
| `supabase/migrations/0050_recherche.sql` | `research_niches` (22 niches de départ), `research_videos`, `research_video_niches`, `research_video_snapshots`, `research_niche_snapshots` (7 jours), `research_niche_months` (courbe), `research_reports`, `concepts.research_video_id`, `app_settings.research` |
| `worker/research.py` | calculs purs : surperformance, vitesse, `window_stats`, mois de la courbe, `niche_phase`, `niche_score`, `remake_score` |
| `worker/research_agents.py` | sorties, prompts et messages des trois agents |
| `worker/youtube/public.py` | `search_shorts`, `video_details`, `channel_details`, `channel_shorts` (UUSH), quota inscrit dans `api_quota_usage` |
| `worker/providers/gemini_video.py` | Gemini qui regarde une adresse YouTube, avec les clés et modèles de Réglages → IA |
| `worker/steps/research.py` | job `research` : `scan`, `explore`, `watch`, `reproduce`, `brief` |
| `worker/scheduler.py` | `daily_research` à 10 h (le compteur de recherches repart à 9 h, minuit heure du Pacifique) |
| `worker/main.py` | « research » dans `STATS_TYPES` : les boutons partent dans la seconde |
| `apps/dashboard/src/app/research/` | page et actions |
| `apps/dashboard/src/components/research/` | `research-view.tsx` (onglets, recommandations, explorer), `research-niches.tsx`, `research-videos.tsx` |
| `apps/dashboard/src/lib/research.ts`, `research-types.ts` | lecture serveur, types, calculs partagés |
| `tests/test_research.py` | calculs et cycle de vie |

`WORKER_JOB_TYPES` du `.env` du worker doit contenir `research` (ajouté le 02/10 sur le PC et dans `.env.example`).

## 8. Limites et suite

- **TikTok et Instagram** ne sont pas encore relevés automatiquement (aucune source gratuite et stable). Pistes : la
  lecture des pages TikTok déjà rodée à la main (docs/31) faite par le Chrome du worker (port 9333) sur les hashtags
  des niches ; pour Instagram, `business_discovery` de l'API Graph sur une liste de comptes à suivre ; les 5 $
  gratuits par mois d'Apify (limités, donc hors règle de gratuité « sans limite »).
- **Google Trends** (tendance de fond d'un sujet) : l'API officielle est en alpha sur candidature, pytrends est
  archivé ; à brancher si utile.
- La recherche YouTube ne voit que 50 vidéos par requête : une niche se juge sur ses meilleurs Shorts, pas sur tout
  ce qui se publie. Le nombre de vidéos publiées (saturation de l'offre) n'est pas mesurable gratuitement.
- Les vues publiques se comptent depuis le 27/08/2026 dès le début de la lecture (tous formats) : ne comparer que des
  mois comptés pareil (la courbe commence en octobre 2025 ; les Shorts comptaient déjà ainsi depuis mars 2025).
- Quotas Gemini : 4 vidéos regardées par relevé par défaut ; « Reproduire » regarde la vidéo d'abord si besoin.
