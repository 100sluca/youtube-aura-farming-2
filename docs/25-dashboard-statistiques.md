# 25 · Dashboard des statistiques et agent analyste

> 2026-09-28. Demande de Luca : un endroit, comme sur MJClipIt, où voir toutes les vidéos publiées avec leurs chiffres
> (vues, rétention, j'aime, commentaires…), triables et en graphiques, qu'on peut actualiser ; comprendre pourquoi la Vue
> d'ensemble affichait 0 abonné (la chaîne en a 2) et un graphique des vues vide ; puis un agent qui compare les vidéos
> qui marchent et les autres (script, format, titre d'accroche, voix, hashtags…) et dont les leçons servent aux agents
> qui écrivent les vidéos suivantes. La Vue d'ensemble reste telle quelle, ses chiffres sont corrigés.

## 1. Pourquoi « Abonnés » restait à 0 et le graphique vide

- **Abonnés** : la synchro (`sync_metrics`) n'écrivait le total d'abonnés que sur la ligne « aujourd'hui » de
  `channel_metrics_daily`. Or YouTube Analytics ne renvoie jamais le jour même : la valeur n'était jamais enregistrée,
  la Vue d'ensemble lisait donc 0. Le total vient maintenant des relevés horaires (`channel_snapshots`), comme les vues.
- **Vues par jour** : le graphique ne lisait que YouTube Analytics, qui publie ses chiffres **2 à 3 jours après** et
  n'avait encore rien pour cette chaîne neuve (vérifié le 28/09 : 0 ligne sur 28 jours, alors que la Data API donne
  bien 2 abonnés et 1 330 vues). Les jours qu'Analytics n'a pas encore publiés sont maintenant estimés d'après les
  relevés horaires (barres claires) ; tant que les relevés ne suffisent pas, le graphique le dit au lieu de rester vide.
- **Fréquence** : avant, une synchro par nuit sur 3 jours. Maintenant compteurs chaque heure, Analytics toutes les 6 h,
  et bouton **Actualiser** (§ 4).

## 2. La page Dashboard (`/dashboard`)

Menu **Dashboard**, juste sous Vue d'ensemble. La chaîne se choisit en haut, comme partout ; la **période** (7, 28,
90 jours, tout) filtre les vidéos par date de mise en ligne.

- **Six chiffres** : vues des vidéos de la période, abonnés (total relevé chaque heure, +Δ sur 7 jours), rétention
  moyenne (pondérée par les vues), audience encore là à 3 s, j'aime (et leur part des vues), commentaires · partages.
- **Vues par jour** : Analytics en plein, estimations d'après les compteurs en clair ; les vues pas encore datées sont
  comptées dans les totaux et signalées sous le graphique.
- **Chaque vidéo** : classement par vues (couleur = format : chantier, visite, récit, mise en ligne à la main) ou nuage
  vues × durée / rétention / audience à 3 s / heure de publication (vues en échelle logarithmique). Un clic ouvre la fiche.
- **Toutes les vidéos publiées** : un tableau triable par chaque colonne (clic sur le titre de la colonne), filtres
  format / tops / flops / recherche, ligne de totaux et moyennes. Le ⓘ de chaque colonne dit d'où vient le chiffre.
  Un clic sur une ligne ouvre la même fiche que la Bibliothèque (lecture, stats, fabrication), avec en plus l'avis de
  l'agent analyste et huit chiffres (vues, j'aime, commentaires, partages, rétention, à 3 s, durée regardée, abonnés).
- **Ce qui marche, et pourquoi** : le dernier rapport de l'agent analyste (§ 6), ses leçons à valider, les leçons en
  service, les expériences à mener. Bouton **Analyser maintenant**.

La page se recharge seule chaque minute, toutes les 4 s pendant une synchro ou une analyse.

| Colonne | Ce que c'est | Source |
|---|---|---|
| Vues | compteur public | Data API, chaque heure |
| Note | vues comparables ÷ médiane de la chaîne (§ 5) | calcul |
| Vues 24 h | vues 24 h après la mise en ligne | relevés horaires (vidéos publiées depuis le 28/09) |
| Rétention | part moyenne de la vidéo regardée (au-delà de 100 % : revisionnages) | Analytics, totaux de la vidéo |
| À 3 s | part de l'audience encore là à 3 s : l'accroche a-t-elle retenu ? | courbe de rétention |
| Durée vue | durée moyenne regardée | Analytics |
| J'aime, Comm. | compteurs publics (et taux de j'aime) | Data API, chaque heure |
| Partages, Abonnés | partages, abonnés gagnés moins perdus | Analytics |
| Engagées | vues engagées ÷ vues (lectures poursuivies après la première image ; ce sont elles qui comptent pour les revenus Shorts) | Analytics |

**Pas de colonne « clics »** : dans le fil Shorts la vidéo démarre seule, il n'y a ni clic ni miniature ; le taux
« regardé plutôt que balayé » de YouTube Studio n'existe pas dans l'API. Ce qui s'en approche : « À 3 s ».

## 3. D'où viennent les chiffres

| Donnée | Table | Source, fréquence |
|---|---|---|
| Abonnés, vues, vidéos de la chaîne | `channel_snapshots` | `channels.list`, chaque heure (1 unité) |
| Vues, j'aime, commentaires de chaque vidéo | `video_stats` + `video_snapshots` | `videos.list`, chaque heure (1 unité pour 50 vidéos) |
| Vues 24 h et 7 j | `video_stats.views_24h / views_7d` | relevés horaires (écart ≤ 6 h / 30 h autour du cap), sinon (7 j) somme des jours Analytics |
| Chaîne jour par jour | `channel_metrics_daily` | Analytics `dimensions=day`, 7 derniers jours à chaque synchro |
| Vidéo jour par jour | `video_metrics_daily` | Analytics « Top videos », un appel par jour |
| Totaux de toute la vie de la vidéo | `video_stats` (engaged_views, shares, subscribers_*, average_view_*, analytics_views/through) | Analytics « Top videos » de la mise en ligne à aujourd'hui |
| Courbe de rétention, audience à 3 s et à la fin | `video_retention` (la plus récente), `video_stats.hook/end_retention_pct` | Analytics `elapsedVideoTimeRatio`, une par vidéo et par jour, vidéos de moins de 45 jours |
| Commentaires | `video_comments` | chaque nuit, 10 dernières vidéos |

Les relevés horaires sont gardés 10 jours, puis seulement le dernier de chaque jour. Les compteurs publics redescendent
parfois (vues retirées par YouTube) : une baisse compte zéro dans les estimations.

**Vues par jour** (dashboard, `lib/views-series.ts`) : jusqu'au dernier jour publié par Analytics (`through`), ses
chiffres ; après, la différence entre les derniers relevés de deux jours consécutifs (vue `v_video_daily_snapshots`) ;
un jour sans relevé la veille reste inconnu. **Vues 7 j** (Vue d'ensemble) = jours Analytics de la semaine + tout ce
que les compteurs ont vu depuis (`views − analytics_views` de chaque vidéo).

## 4. Horaires et bouton « Actualiser »

| Quand | Quoi |
|---|---|
| Chaque heure, à h 05 | compteurs publics de chaque chaîne connectée (`sync_metrics`, `{"scope": "counters"}`) |
| 3 h 20, 9 h 20, 15 h 20, 21 h 20 | synchro complète : compteurs + Analytics (7 derniers jours, totaux, courbes de rétention) |
| 3 h 20 | commentaires des 10 dernières vidéos |
| Dimanche 5 h | agent analyste (`analyze`) |
| Bouton « Actualiser » | synchro complète tout de suite, devant les autres tâches (une minute environ) |

Quota Data API : environ 50 unités par jour et par chaîne sur 10 000. Analytics a son propre quota. La boucle
principale du worker ne prend rien de nouveau pendant un job GPU (un clip dure jusqu'à 10 min) : les synchros et
l'analyse ont donc leur propre fil (`worker/main.py`, `STATS_TYPES`, comme les aperçus du Montage) et partent dans la
seconde, même pendant une fabrication. Si « Actualiser » attend plus de 3 minutes, le worker est sans doute arrêté :
la page le signale.

## 5. La note : top, moyen, flop

Vues comparables = vues à 7 jours pour une vidéo de plus de 7 jours (si on les connaît), sinon ses vues du moment.
Note = vues comparables ÷ médiane des vidéos jugeables (publiées depuis plus de 24 h, sur 90 jours). **Top** : dans le
premier tiers et ×1,25 au moins ; **flop** : dans le dernier tiers et ×0,8 au plus ; sinon **moyen** ; moins de 24 h :
**trop récente**. Mêmes règles dans le dashboard (`lib/stats.ts`) et chez l'agent (`worker/performance.py`).

## 6. L'agent analyste

Clé `analyst` (prompt modifiable dans l'onglet Agents), job `analyze`, chaque dimanche à 5 h et à la demande.

1. Le code prépare la **fiche de chaque vidéo publiée** (90 jours) : chiffres, note, verdict, et ce qu'elle contient :
   thème, format, titre, titre d'accroche affiché, textes à l'écran, narration, premier plan, nombre et durée moyenne
   des plans, musique (piste posée au montage, migration 0018, sinon ambiance du script), modèle vidéo et image,
   description, hashtags, tags, heure de publication (Paris), commentaires. Plus des **ventilations** par format, thème,
   durée, créneau, forme du titre, accroche affichée, voix off, modèle vidéo, musique, origine, avec une confiance
   (faible sous 3 vidéos, bonne à partir de 8).
2. Il passe par le **modèle d'écriture** de Réglages → IA (le plus fort, avec repli sur le modèle principal) : une
   analyse par semaine, c'est elle qui guide les autres agents.
   **Il regarde les vidéos** quand un modèle qui voit est réglé (Gemini, Claude) : une planche de 4 images par vidéo
   (`worker/analysis_frames.py`, gardée dans `DATA_DIR/analysis/`) : 0,5 s, 2,5 s, milieu et 90 % du fichier final pour
   les vidéos de l'appli ; 25, 50 et 75 % publiées par YouTube pour celles mises en ligne à la main. Au plus 8 vidéos
   (les 4 meilleures et les 4 moins bonnes). Sans modèle qui voit, ou si l'appel échoue, il travaille sur le texte.
3. Il rend : pour chaque vidéo pourquoi elle a ce verdict, ce qui a marché, ce qui a manqué ; au plus 5 différences
   entre tops et flops avec leur preuve chiffrée ; **au plus 6 leçons** à l'impératif, chacune pour une cible ; au plus
   3 expériences ; un résumé. Le code vérifie : vidéos inconnues retirées, verdicts et notes repris du calcul, confiance
   plafonnée (faible sous 4 vidéos jugées, moyenne sous 10), leçons en double écartées.
4. Rien ne s'applique seul. Dans le Dashboard : **✓ Valider** (texte modifiable avant), **✗ Écarter**, **Retirer** une
   leçon en service. Une nouvelle analyse remplace les leçons encore en attente (`superseded`).

| Cible d'une leçon | Qui la reçoit |
|---|---|
| `idea` | agent idées (message de chaque tâche) |
| `script` | scénaristes (histoires, chantier, visite), filtrée par format si la leçon en vise un |
| `seo` | agent SEO |
| `production` | personne : réglage à faire soi-même (modèle vidéo, durée, musique, montage), affiché « À régler toi-même » |

Les leçons validées sont ajoutées au message des agents à **chaque appel** (`worker/lessons.py`, `lessons_text`), comme
la stratégie validée : une leçon validée sert dès la tâche suivante. Moins de 2 vidéos jugées : rapport chiffré sans
appel au LLM.

Premier essai (28/09, 4 vidéos, texte seul) : le refuge mis en ligne à la main ×17 la médiane, les visites moyennes ou
en dessous ; une leçon « à régler toi-même » (durées de moins de 25 s). Confiance faible : trop peu de vidéos.

## 7. Fichiers

- Migrations : `0015_analyze_job.sql` (valeur d'enum seule), `0016_stats_dashboard.sql` (`channel_snapshots`,
  `video_snapshots`, vue `v_video_daily_snapshots`, colonnes de `video_stats`, `v_video_overview` étendue,
  `performance_reports`, `performance_lessons`). La 0018 (session musique) ajoute `music_track`, `music_title`,
  `audio_mix` en fin de `v_video_overview`.
- Worker : `steps/sync.py` (réécrit : compteurs, Analytics, rétention, vues 24 h / 7 j), `metrics.py` (interpolation,
  audience à 3 s), `scheduler.py` (horaires), `youtube/client.py` (`channel_statistics`, `analytics_retention`, totaux sur
  une période), `performance.py` (fiches, notes, ventilations, message, garde-fous), `analysis_frames.py` (planches),
  `steps/analyze.py` (agent, prompt `ANALYST_PROMPT`), `lessons.py` (leçons servies aux agents ; appelée par
  `steps/ideate.py`, `script.py`, `seo.py`) ; tests `tests/test_stats_analyst.py`.
- Dashboard : `app/dashboard/` (page, actions : actualiser, analyser, décider une leçon), `components/stats/`
  (barre d'outils, chiffres, graphiques, tableau, panneau de l'analyste, couleurs des formats), `lib/stats.ts`,
  `lib/stats-types.ts`, `lib/insights.ts`, `lib/views-series.ts` ; Vue d'ensemble : `lib/data/supabase.ts`
  (abonnés, vues 7 j, vues par jour), `components/overview/daily-views-chart.tsx` ; fiche vidéo :
  `components/library/video-stats.tsx` ; onglet Agents : `lib/agent-catalog.ts` (agent analyste, boucle d'apprentissage).

## 8. Pistes

- Sources de trafic par vidéo (fil Shorts, recherche, page de chaîne) : dit si l'algorithme l'a poussée.
- Courbe de démarrage dans la fiche (vues heure par heure des 48 premières heures, déjà dans `video_snapshots`).
- Renseigner à la main le format d'une vidéo importée (le refuge est un chantier en accéléré, la fiche l'ignore).
- Mesurer l'effet d'une leçon : notes des vidéos produites avant et après sa validation.
- L'agent stratégie (docs/11) fait en partie doublon : le fusionner avec l'analyste ou le retirer, à décider.
