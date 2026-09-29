# 39 · TikTok partout : Dashboard, Calendrier, rattrapage des anciennes vidéos

Demande de Luca (2026-09-29, 2 h) : maintenant que les Shorts partent aussi sur TikTok (docs/36), avoir dans le Dashboard
un onglet YouTube et un onglet TikTok avec à peu près les mêmes chiffres, pour chaque compte connecté ; voir dans le
Calendrier les vidéos programmées sur TikTok ; pouvoir envoyer automatiquement sur TikTok les vidéos déjà produites ; et
savoir où TikTok est vraiment branché dans l'appli.

## 1. En bref

- **Dashboard → onglet TikTok** (`/dashboard?plateforme=tiktok`) : le compte TikTok relié à la chaîne choisie en haut
  (tous les comptes sinon, avec un choix par compte), ses abonnés, les publications déjà programmées, puis les mêmes
  blocs que l'onglet YouTube : six chiffres de la période, vues par jour, chaque vidéo (classement ou nuage), tableau
  triable avec note top / moyen / flop (mêmes règles que YouTube). Un clic ouvre la fiche de la vidéo dans la
  Bibliothèque.
- **Chiffres relevés chaque heure** par le worker (job `sync_tiktok`, à h10) auprès de Zernio, qui les lit chez TikTok.
  Les statistiques sont comprises dans le plan gratuit de Zernio (`hasAnalyticsAccess: true`, vérifié le 29/09).
- **Calendrier** : chaque créneau montre YouTube ▶ et TikTok ♪ (programmée, publiée, échec, brouillon, rattrapage) ;
  une ligne « TikTok · autres heures » pour ce qui est sorti hors créneau. La Vue d'ensemble fait de même dans
  « Prochaines publications ».
- **Rattrapage** (Réglages → TikTok, par chaîne, **coupé par défaut**) : les vidéos de l'appli déjà sorties sur YouTube et
  jamais envoyées sur TikTok partent une par une, la plus ancienne d'abord, dans les créneaux restés vides.
- **Bibliothèque** : chaque vignette dit où en est la vidéo sur TikTok (vues, « prog. », « échec »…) ; le tableau de
  l'onglet YouTube a une colonne « TikTok » pour comparer.
- **Agent analyste** : la fiche de chaque vidéo qu'il lit contient maintenant ses chiffres TikTok.
- **Tâches** : « Publication TikTok » et « Synchro stats TikTok » ont enfin un libellé (le panneau affichait
  `tiktok_publish`).

## 2. Ce que TikTok donne, comparé à YouTube

| YouTube (onglet YouTube) | TikTok (onglet TikTok) | D'où vient le chiffre TikTok |
|---|---|---|
| Vues, j'aime, commentaires | Vues, j'aime, commentaires, partages | `GET /analytics` de Zernio ; j'aime et commentaires aussi en direct (`GET /accounts/{id}/posts`) |
| Abonnés de la chaîne (+7 j) | Abonnés du compte (+7 j), j'aime reçus, nombre de vidéos | `GET /analytics/tiktok/account-insights` (en direct chez TikTok), relevés dans `tiktok_account_snapshots` |
| Rétention moyenne | **Regardée** : durée moyenne regardée ÷ durée de la vidéo | `igReelsAvgWatchTime` (ms), 24 à 48 h après la sortie |
| Encore là à 3 s | **Jusqu'au bout** : part des spectateurs allés à la fin | `completionRate`, 24 à 48 h après |
| Durée moyenne regardée | Durée vue | idem |
| Abonnés gagnés par vidéo | Abonnés gagnés par vidéo | `follows`, 24 à 48 h après |
| Partages | Partages, **enregistrements** | `shares`, `saves` |
| Vues engagées | **Pour toi** : part des vues venues du fil « Pour toi » | `impressionSources.forYou`, 24 à 48 h après |
| Vues à 24 h, note | Vues à 24 h, note (vues à 7 j ÷ médiane du compte) | relevés horaires `tiktok_post_snapshots` |
| Vues par jour (YouTube Analytics + relevés) | Vues par jour (relevés seulement) | différence entre deux fins de journée |

Les chiffres « 24 à 48 h après » viennent de l'appli TikTok for Business (notre compte y est relié : badge **Business**),
seulement pour les vidéos vues dans les 7 derniers jours. Avant, Zernio renvoie des zéros : on les garde comme « pas encore
connu » (« — »), pas comme 0. La courbe de rétention seconde par seconde n'existe dans aucune API TikTok.

**Délais constatés le 29/09** : Zernio repasse chez TikTok toutes les 90 minutes au mieux. Une vidéo publiée à la main
dans l'appli TikTok à 2 h 07 n'était toujours pas dans ses statistiques à 2 h 36. Le relevé fait donc trois appels par
compte : `POST /posts/sync-external` (relecture immédiate des vidéos publiées à la main), `GET /analytics` (vues et le
reste), puis `GET /accounts/{id}/posts` (les 25 dernières vidéos, en direct). Une vidéo que Zernio n'a pas encore relevée
apparaît quand même, avec ses j'aime, commentaires et partages ; ses vues affichent « — » jusqu'au passage suivant
(`sync_status = 'live'`, pas notée, pas de relevé horaire pour ne pas fausser les vues par jour).

## 3. Relevé des statistiques (worker)

| Pièce | Où | Rôle |
|---|---|---|
| Client Zernio | `worker/tiktok/zernio.py` | `post_analytics` (pages de 100, 365 jours), `account_insights`, `account_posts`, `sync_external` |
| Lecture des réponses | `worker/tiktok/stats.py` | `parse_post` (clé stable `latePostId` ou `postId`, chiffres Business à zéro → inconnus, brouillons ignorés), `merge_posts` (une ligne par vidéo), `parse_live_post` / `add_live_posts`, `match_by_title` |
| Step | `worker/steps/sync_tiktok.py` | job `sync_tiktok` (voie « stats » : pris dans la seconde, même pendant un clip) : comptes, vidéos, relevés, vues 24 h / 7 j, ménage des relevés (horaires 10 jours, puis un par jour), lien TikTok d'une vidéo de l'appli s'il manquait |
| Planificateur | `scheduler.tiktok_counters` (chaque heure à h10) | un relevé si une clé Zernio est enregistrée et qu'aucun n'attend |
| Base | migrations 0025 (type de job) et 0026 | `tiktok_accounts`, `tiktok_account_snapshots`, `tiktok_posts`, `tiktok_post_snapshots`, vue `v_tiktok_post_daily_snapshots` |
| CLI | `yt2 tiktok stats [--here]`, `yt2 tiktok status` | relevé à la demande ; résumé des comptes et des vidéos |

Rattachement d'une vidéo TikTok à la vidéo de l'appli : id de la publication Zernio (`videos.tiktok->>'post_id'`), sinon
id TikTok tiré du lien. **Vidéo publiée à la main dans TikTok** (brouillon terminé dans l'appli TikTok, ou envoi fait à la
main) : reconnue si la première ligne de sa légende est le titre d'une vidéo de l'appli fabriquée avant. Elle est alors
notée dans `videos.tiktok` (source « manuel ») : la Bibliothèque la dit publiée et ni la publication automatique ni le
rattrapage ne la republient. Un brouillon envoyé par l'appli puis publié dans TikTok perd son état de brouillon.

## 4. Dashboard, Calendrier, Vue d'ensemble, Bibliothèque

- **Onglets** : `components/stats/platform-tabs.tsx` (la période suit d'un onglet à l'autre). Onglet TikTok :
  `lib/tiktok-stats.ts` (données, note avec `rankVideos` de `lib/stats.ts`), `components/stats/tiktok-accounts.tsx`,
  `tiktok-kpis.tsx`, `tiktok-explorer.tsx`, `tiktok-table.tsx`. La barre période + « Actualiser » (`stats-toolbar.tsx`),
  le graphique des vues par jour (`daily-views.tsx`) et celui de chaque vidéo (`videos-chart.tsx`, axes au choix) servent
  aux deux onglets. « Actualiser » met en file un `sync_tiktok` (action `refreshTikTokStats`).
- **Calendrier** (`app/calendar/page.tsx`, `components/calendar/slot-cell.tsx`) : `getTikTokCalendar` (`lib/tiktok.ts`)
  lit `videos.tiktok` ; une publication à ±10 min d'un créneau de sa chaîne va dans ce créneau, les autres dans « TikTok ·
  autres heures ». Le rattrapage prévu est calculé depuis maintenant avec la même règle que le worker, en pointillés :
  c'est ce qui partira si aucune nouvelle vidéo ne prend ces créneaux d'ici là.
- **Vue d'ensemble** : « Prochaines publications » montre le badge TikTok de chaque créneau ; lien « TikTok » à côté de
  « Toutes les stats ».
- **Bibliothèque** : `LibraryItem.tiktok` (`getTikTokBriefs`) : vues TikTok ou état sur chaque vignette ; colonne « TikTok »
  dans le tableau de l'onglet YouTube.

## 5. Rattrapage des vidéos déjà sorties sur YouTube

- **Quoi** : la vue `v_tiktok_backlog` (0026) = vidéos de l'appli publiées sur YouTube, montage encore sur le disque,
  jamais envoyées sur TikTok (`videos.tiktok` nul : les brouillons comptent comme envoyés), sans job en file ni échec de
  moins de 6 h (mêmes gardes que `plan_tiktok` et `request_tiktok_publish`). Au 29/09 : la villa de Santorin et le chalet
  face au pic (26/09), le home cinéma (28/09). Les vidéos importées de YouTube n'ont pas de fichier : elles restent hors
  rattrapage.
- **Quand** : `scheduler.plan_tiktok_backlog` (toutes les 5 min) prend un créneau de la chaîne situé entre 29 et 5 min
  d'ici, sans vidéo YouTube (quand la publication automatique est active, la vidéo YouTube du créneau part déjà sur
  TikTok) et sans publication TikTok à ±10 min. 29 min : `next_free_slot` garde 30 min de marge, donc aucune nouvelle
  vidéo YouTube ne peut plus prendre ce créneau. La plus ancienne vidéo d'abord (les séries en plusieurs parties restent
  dans l'ordre), une par créneau : jamais de rafale (Zernio accepte 15 vidéos par 24 h et par compte).
- **Comment** : un job `tiktok_publish` avec `payload.at` = l'heure du créneau et `source: "rattrapage"` ; le step
  programme la publication à cette heure au lieu du créneau YouTube, passé depuis longtemps. `videos.tiktok.source` garde
  l'origine (auto, rattrapage, bibliothèque, cli, manuel) pour le Calendrier.
- **Où** : Réglages → TikTok, interrupteur « Rattrapage » sous chaque chaîne reliée, avec la liste des vidéos dans l'ordre
  où elles partiront ; `yt2 tiktok backlog <chaîne> [--on|--off]` fait de même dans le terminal. **Coupé par défaut** :
  c'est une publication publique, Luca l'active lui-même.
- **Limite** : le PC doit être allumé une demi-heure avant le créneau (le choix se fait au dernier moment, pour ne jamais
  voler un créneau à une nouvelle vidéo).

## 6. Où TikTok est branché (état au 29/09)

| Endroit | TikTok ? |
|---|---|
| Publication (créneau YouTube → même heure sur TikTok) | oui, docs/36 |
| Anciennes vidéos | oui, rattrapage (§ 5) ou « Publier sur TikTok » dans la fiche |
| Dashboard | oui, onglet TikTok ; colonne TikTok dans l'onglet YouTube |
| Calendrier, Vue d'ensemble | oui |
| Bibliothèque | oui, vignettes et fiche |
| Agent analyste | chiffres TikTok dans la fiche de chaque vidéo ; la note et les leçons restent calculées sur YouTube |
| Tâches | libellés |
| Création, scripts, SEO | non : la légende TikTok reprend le titre et la description YouTube sans #shorts (docs/36). Piste : un agent « légende TikTok » (hashtags propres à TikTok) |
| Mail « vidéo terminée » | non concerné |

Pistes : note et leçons de l'analyste propres à TikTok, légende TikTok écrite par un agent, déplacer la publication TikTok
quand on change le créneau YouTube d'une vidéo (limite connue de docs/36).

## 7. Essais du 29/09

1. Sonde de l'API : `hasAnalyticsAccess: true` ; `GET /analytics`, `/analytics/tiktok/account-insights`,
   `/accounts/follower-stats` et `/accounts/{id}/posts` répondent 200. Une publication programmée n'apparaît pas dans
   `GET /analytics` (seulement en lecture unitaire, code 202) ; Zernio renvoie pour elle l'adresse du MP4 en guise de
   vignette (écartée : l'appli prend son affiche). Le brouillon d'essai a pour id TikTok `v_inbox_url~…` (ignoré).
2. `yt2 tiktok stats --here` : compte @arzakparker enregistré (Business, 0 abonné) ; la vidéo publiée à la main à 2 h 07
   apparaît grâce à la lecture en direct (1 j'aime, vues « — »).
3. Dashboard vérifié dans le navigateur : onglets, compte, 6 publications programmées, tableau ; Calendrier (badges
   YouTube et TikTok, ligne « autres heures » avec le brouillon), Réglages (3 vidéos à rattraper, rattrapage coupé),
   Bibliothèque (« prog. », « brouillon ») ; aucune erreur dans la console.
4. Worker : 407 tests (dont 17 dans `tests/test_tiktok_stats.py`), ruff propre ; dashboard : `tsc` et eslint propres.
