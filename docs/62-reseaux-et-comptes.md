# 62 · Réseaux et comptes : Instagram dans les stats, un compte par carte

Demande de Luca (04/10) : les comptes Instagram manquaient. Il y en a deux : celui où partent les mêmes vidéos que sur
YouTube et TikTok (@arzakparker), et celui de « Paf, j'achète » (la vidéo du vendredi, docs/50). Voir dans la Vue
d'ensemble et le Dashboard les vues par réseau et par compte, et passer d'un compte à l'autre plus simplement.

## 1. En bref

- **Vue d'ensemble → « Par réseau et par compte »** : une carte par chaîne YouTube, par compte TikTok, par compte
  Instagram des Shorts et pour « Paf, j'achète ». Sur chaque carte : vues des 7 derniers jours et leur évolution par
  rapport aux 7 jours d'avant, mini-courbe des vues par jour sur 28 jours, abonnés (+ sur 7 jours), vidéos sorties en
  7 jours, vues sur 28 jours. À droite du titre : le total tous réseaux. Un clic ouvre le Dashboard sur ce compte. Les
  deux premiers chiffres du haut s'appellent maintenant « Abonnés YouTube » et « Vues YouTube 7 j ».
- **Dashboard → rangée des comptes** (à la place des onglets YouTube | TikTok) : chaque compte de chaque réseau avec ses
  vues sur 7 jours ; un clic change d'onglet et de compte d'un coup. Le compte affiché est en relief.
- **Dashboard → onglet Instagram** (`/dashboard?plateforme=instagram`, `&compte=<id Instagram>` ou `&compte=paf`) : les
  comptes et leur rôle, les Reels déjà programmés (dont le prochain vendredi), six chiffres de la période, vues par jour,
  chaque Reel en graphique, tableau triable avec la note top / moyen / flop (mêmes règles que YouTube) et les vues de la
  même vidéo sur YouTube et sur TikTok.
- **Onglet YouTube** : `?chaine=<slug>` montre une chaîne sans changer celle de l'en-tête (c'est ce que fait la carte).
- **Relevé** : job `sync_instagram`, chaque heure à h14 et par « Actualiser », pour les deux comptes Zernio.
- **« Paf, j'achète » n'a pas encore son compte** : voir § 5, il y a une action à faire avant vendredi.

## 2. Ce qu'Instagram donne, comparé à YouTube et TikTok

| Dans l'onglet Instagram | Équivalent | D'où vient le chiffre |
|---|---|---|
| Vues, j'aime, commentaires, partages, enregistrements | idem | `GET /analytics?platform=instagram` (Zernio) ; j'aime et commentaires aussi en direct (`GET /accounts/{id}/posts`) |
| Portée | — | comptes différents touchés par le Reel |
| **À 3 s** : 100 − part des spectateurs partis dans les 3 premières secondes | Encore là à 3 s (YouTube) | `reelsSkipRate`, estimation de Meta, peut bouger d'un relevé à l'autre |
| **Regardé** : durée moyenne regardée ÷ durée de la vidéo | Rétention moyenne (YouTube) | `igReelsAvgWatchTime` (ms) et `videoDurationSeconds` |
| Abonnés du compte (+7 j) | idem | `GET /accounts` (`followersCount`, mis à jour une fois par jour par Zernio) |
| Vues, portée, interactions du compte sur 28 jours | — | `GET /analytics/instagram/account-insights` (tout le compte : Reels, stories, profil ; jusqu'à 48 h de retard) |
| Vues 24 h, vues par jour, note | idem | relevés horaires `instagram_post_snapshots` |

Instagram ne donne pas, pour un Reel, les abonnés gagnés (`follows` nul), la part vue jusqu'au bout ni la provenance
des vues.

## 3. Relevé des statistiques (worker)

| Pièce | Où | Rôle |
|---|---|---|
| Client Zernio | `worker/tiktok/zernio.py` | `post_analytics(..., platform="instagram")`, `post_analytics_one` (lecture unitaire, code 202 si pas prête), `instagram_insights` |
| Lecture des réponses | `worker/instagram/stats.py` | `parse_post` (clé = id Instagram du Reel), `parse_live_post` (vidéos seulement), `missing_live`, `refresh_live_counters`, `account_info` (id Instagram + id Zernio), `parse_insights` |
| Step | `worker/steps/sync_instagram.py` | les deux clés (`zernio_api_key`, `zernio_paf_api_key`) ; un compte Instagram relevé une fois même si les deux comptes Zernio le voient ; rattachement à la vidéo de l'appli (`videos.instagram`) ou au vendredi (`paf_posts`) ; lien du Reel rattrapé dans `videos.instagram.url` |
| Planificateur | `scheduler.instagram_counters` (h14) | un relevé si une des deux clés existe et qu'aucun n'attend |
| Base | migrations 0051 (type de job) et 0052 | `instagram_accounts` (clé = id Instagram, `zernio_ids` {"main", "paf"}), `instagram_account_snapshots`, `instagram_posts`, `instagram_post_snapshots`, vue `v_instagram_post_daily_snapshots` |
| CLI | `yt2 instagram stats [--here]` | relevé à la demande et résumé |

Vues 24 h / 7 jours et ménage des relevés (horaires 10 jours, puis un par jour) : mêmes fonctions que TikTok
(`record_launch_marks` et `prune_snapshots` de `steps/sync_tiktok.py`, qui prennent maintenant la plateforme).

**Constaté le 04/10** :
- `GET /analytics?platform=instagram` renvoyait une liste vide alors que deux Reels de l'appli étaient sortis. Une
  lecture unitaire (`GET /analytics?postId=<id Instagram>`) les a fait apparaître, avec leurs chiffres, puis la liste
  les a donnés. Le step relit donc un par un (12 au plus par compte) les Reels vus en direct mais absents de la liste,
  et les publications de l'appli sorties mais pas encore relevées.
- Les statistiques de compte sont sous `/v1/analytics/instagram/…` (`account-insights`, `follower-history`), pas sous
  `/v1/accounts/{id}/instagram/…` comme le dit la page Instagram de la doc Zernio (404).
- Les deux clés Zernio voient le même compte @arzakparker (même `platformUserId`) : une seule ligne, deux ids Zernio.

## 4. Dashboard et Vue d'ensemble

- Données : `lib/instagram-stats.ts` (+ `-types.ts`) pour l'onglet, `lib/networks.ts` (+ `network-types.ts`) pour les
  cartes, `lib/post-daily-views.ts` (vues par jour TikTok et Instagram, partagé avec `lib/tiktok-stats.ts`).
- Composants : `components/networks/network-cards.tsx` (`NetworkCards` pour la Vue d'ensemble, `NetworkSwitcher` pour le
  Dashboard), `components/stats/instagram-accounts.tsx`, `instagram-kpis.tsx`, `instagram-explorer.tsx`,
  `instagram-table.tsx`, `InstagramMark` dans `platform-marks.tsx`. « Actualiser » : action `refreshInstagramStats`.
- Rôle d'un compte Instagram : « Shorts · <chaîne> » s'il est relié à une chaîne dans Réglages → Instagram, « Paf,
  j'achète » s'il est choisi dans l'onglet Paf, j'achète. Chaîne choisie dans l'en-tête : ses comptes reliés, plus « Paf,
  j'achète » qui ne dépend d'aucune chaîne.
- **Vues sur 7 jours (TikTok, Instagram)** = vues d'aujourd'hui − vues au dernier relevé de la fin du jour J−7 (0 pour
  une vidéo sortie après) : juste dès le premier relevé pour les vidéos récentes. Sans relevé assez ancien, on part du
  premier relevé et l'évolution reste inconnue. Les mini-courbes et « Vues par jour » viennent des fins de journée :
  Instagram n'a de barres qu'à partir du 05/10 (relevés commencés le 04/10).
- Piège PostgREST : `.neq("sync_status", "live")` écarte aussi les lignes où le statut est vide (toutes celles de
  TikTok) ; on écrit `.or("sync_status.is.null,sync_status.neq.live")`.

## 5. « Paf, j'achète » : état au 04/10, à régler par Luca

- Le second compte Zernio (clé de l'onglet Paf, j'achète) ne voit **que @arzakparker** : @paf.jachete n'est connecté à
  aucun compte Zernio.
- L'onglet Paf, j'achète vise toujours @arzakparker, et son **interrupteur est allumé depuis le 02/10**. Sans changement,
  le job du vendredi 09/10 est créé le mercredi 07/10 à 7 h et la vidéo du vendredi sort sur @arzakparker.
- À faire : sur zernio.com, avec le second compte, Accounts → Instagram → connecter @paf.jachete (compte professionnel,
  Instagram Login), puis dans l'onglet Paf, j'achète choisir @paf.jachete. Ses chiffres arrivent seuls dans l'heure.
  D'ici là, la carte « Paf, j'achète » et l'onglet Instagram affichent l'avertissement.

## 6. Mise en service (04/10)

- Migrations 0051 et 0052 appliquées à la main en local et inscrites dans `supabase_migrations.schema_migrations` :
  `migration up` refuse de tourner à cause de `0038_prises_de_voix_par_lot.sql` (numéro en double, jamais inscrit).
- `sync_instagram` ajouté à `WORKER_JOB_TYPES` (`services/worker/.env`, `.env.example`, défaut de `config.py`) et aux
  types rapides du fil « stats ».
- Essai : `yt2 instagram stats --here` → @arzakparker 1 abonné, 316 vues et 260 comptes touchés sur 28 jours, deux
  Reels (156 et 160 vues, 39 % et 49 % partis avant 3 s) rattachés à leurs vidéos. Le worker en service a pris le
  relevé lancé par « Actualiser » dans la seconde. Vue d'ensemble : YouTube 4,8 k, TikTok 2,1 k, Instagram 316 vues sur
  7 jours.
- Tests : `tests/test_instagram_stats.py` (9 tests), 573 au total ; ruff propre ; dashboard : `tsc` et eslint propres.

## 7. Pistes

- Reels dans le Calendrier et dans « Prochaines publications » de la Vue d'ensemble (docs/48 § 4).
- Chiffres Instagram dans la fiche de la Bibliothèque et pour l'agent analyste (comme TikTok, docs/39).
- Rattrapage Instagram des vidéos déjà sorties sur YouTube.
