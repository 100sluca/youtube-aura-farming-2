# ADR-004 · Tous les appels YouTube (upload et Analytics) dans le worker

**Statut** : accepté · 2026-09-19

## Contexte
L'upload doit partir du PC (le fichier y est). Les métriques pourraient être synchronisées
depuis le cloud (Vercel Cron) ou depuis le worker.

## Décision
Le **worker** fait tous les appels YouTube (upload, `videos.list`, Analytics, commentaires) et
gère le rafraîchissement des jetons. Le dashboard ne fait que le **flux OAuth** (redirection,
callback, stockage chiffré du refresh token) et affiche « dernière synchro il y a X h ».

## Conséquences
- (+) Une seule implémentation cliente YouTube, une seule comptabilité de quota, un seul
  endroit qui manipule les jetons déchiffrés.
- (−) Si le PC est éteint plusieurs jours, les métriques ne se rafraîchissent pas (les
  publications, elles, continuent grâce à `publishAt`). Option future : route
  `api/cron/sync-metrics` sur Vercel avec le même schéma de données.
