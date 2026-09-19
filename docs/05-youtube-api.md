# 05 · YouTube : API, OAuth, quotas, audit

## 1. Projet Google Cloud et OAuth

1. Créer **un projet GCP par chaîne** (`yt2-fr`, `yt2-en`) : chaque projet a son propre
   quota Data API (10 000 unités / jour). Avec un seul projet, 6 uploads / jour = 9 600 unités,
   il ne reste rien pour les métriques.
2. Activer **YouTube Data API v3** et **YouTube Analytics API** dans chaque projet.
3. Écran de consentement OAuth : type *Externe*, statut **En production** (pas « Test » : en
   test, les refresh tokens expirent au bout de 7 jours). L'appli reste « non validée » :
   Google affiche un avertissement au moment du consentement, c'est acceptable pour un usage
   personnel.
4. Identifiant OAuth **Application Web**, URI de redirection
   `https://<dashboard>/api/youtube/callback` (et `http://localhost:3000/api/youtube/callback`).
5. Scopes demandés :
   - `https://www.googleapis.com/auth/youtube.upload` (upload)
   - `https://www.googleapis.com/auth/youtube` (update `publishAt`, lecture des vidéos privées)
   - `https://www.googleapis.com/auth/yt-analytics.readonly` (métriques et rétention)
6. Flux : `/settings` → « Connecter YouTube » → `GET /api/youtube/connect?channel=fr`
   (state signé, `access_type=offline`, `prompt=consent`) → callback → échange du code →
   `channel_credentials.refresh_token_encrypted` (AES-GCM) + `channels.youtube_channel_id`
   (via `channels.list(mine=true)`). Se connecter avec le compte Google propriétaire de la
   chaîne concernée (ou le compte de marque).

## 2. Audit de conformité : à lancer dès maintenant

> Les vidéos envoyées par `videos.insert` depuis un **projet API non audité** (créé après le
> 28 juillet 2020) sont **forcées en privé**. Pour publier via l'API, chaque projet doit passer
> l'audit de conformité YouTube (formulaire *YouTube API Services – Audit and Quota Extension*).

- Délai : plusieurs jours à plusieurs semaines → à soumettre **avant** de coder la suite.
- Préparer : description de l'usage (outil interne de publication programmée pour ses propres
  chaînes), captures du dashboard, politique de confidentialité (une page statique suffit).
- En attendant l'audit, le pipeline fonctionne en bout en bout mais les vidéos restent privées ;
  le worker le détecte au `sync_metrics` du lendemain et lève une alerte.
- Profiter du même formulaire pour demander une **extension de quota** si un seul projet est
  conservé.

## 3. Coût en unités (Data API v3, 10 000 / jour / projet)

| Appel | Unités | Usage / jour / chaîne |
|---|---|---|
| `videos.insert` | 1 600 | 3 → 4 800 |
| `videos.update` (re-programmation) | 50 | 0-2 |
| `videos.list` (statistics, 50 id / appel) | 1 | 4-8 |
| `channels.list` | 1 | 1 |
| `commentThreads.list` | 1 | 10 |
| `search.list` | 100 | **jamais** (utiliser `playlistItems.list` sur la playlist uploads, 1 unité) |

Le worker inscrit chaque appel dans `api_quota_usage` ; `/settings` affiche la jauge ; alerte à
80 %. Le compteur Google se remet à zéro à minuit heure du Pacifique (09:00 Paris en été).

## 4. Analytics API v2 (quota séparé, largement suffisant)

Endpoint `GET https://youtubeanalytics.googleapis.com/v2/reports` avec `ids=channel==MINE`.

| Besoin | Paramètres |
|---|---|
| métriques par vidéo et par jour | rapport « Top videos » : `dimensions=video` · `filters=video==id1,id2,…` (jusqu'à 500 id) · `sort=-views` · `maxResults=200` · `startDate=endDate=<jour>` (une requête par jour et par lot de 200 vidéos) · `metrics=views,engagedViews,likes,dislikes,comments,shares,subscribersGained,subscribersLost,estimatedMinutesWatched,averageViewDuration,averageViewPercentage` |
| courbe de rétention | `dimensions=elapsedVideoTimeRatio` · `filters=video==<id>` (une seule vidéo) · `metrics=audienceWatchRatio,relativeRetentionPerformance` |
| chaîne par jour | `dimensions=day` · `metrics=views,engagedViews,estimatedMinutesWatched,subscribersGained,subscribersLost,likes,comments,shares` |

Notes :
- Données consolidées avec ~48-72 h de retard : synchroniser J-2 → J et **écraser** les jours
  déjà présents (upsert sur `(video_id, day)`).
- `views` sur les Shorts compte désormais chaque lecture/relecture ; `engagedViews` correspond
  à l'ancienne définition (vue « engagée »). Le dashboard affiche les deux.
- La rétention (`averageViewPercentage`, `audienceWatchRatio`) peut dépasser 100 % sur les
  Shorts en boucle : c'est un signal positif, ne pas plafonner.
- Le total d'abonnés vient de `channels.list(part=statistics)` (Data API), pas d'Analytics.

## 5. Shorts : ce que YouTube attend

- Vidéo verticale (ou carrée) de **3 minutes max** → classée Short automatiquement.
  Aucun flag API ; `#Shorts` dans le titre est facultatif.
- Zone sûre : titre, boutons et description recouvrent le bas et la droite de l'image ; garder
  les textes dans les 80 % centraux.
- Contenu IA : cocher `status.containsSyntheticMedia=true` quand le rendu peut passer pour
  réel (obligatoire) ; éviter les watermarks de plateformes tierces (pénalisés par la
  recommandation et interdits par certaines CGU).
- Contenu « répétitif / produit en masse » : la politique YPP exige une valeur ajoutée
  (narration, montage, angle). Les formats A/B et les scripts originaux répondent à ça ;
  garder ce point en tête pour la monétisation.

## 6. Comptes de test et environnement local

- Utiliser une **chaîne de test** (non listée) pendant les phases 1-3 pour éviter de polluer
  les chaînes réelles avec des essais.
- En local, `NEXT_PUBLIC_MOCK=1` pour le dashboard et `DRY_RUN=1` pour le worker (aucun appel
  YouTube, les jobs `upload` posent un `youtube_video_id` factice).
