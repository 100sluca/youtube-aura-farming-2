# ADR-003 · File de jobs dans Postgres (pas de Redis / pgmq)

**Statut** : accepté · 2026-09-19

## Contexte
Un seul worker (parfois deux : GPU + réseau), quelques centaines de jobs / jour, besoin de
progression détaillée, de dépendances et d'une vue temps réel dans le dashboard.

## Décision
Table `jobs` + fonctions SQL `claim_jobs` (SKIP LOCKED), `fail_job` (backoff, alerte),
`requeue_stale_jobs` (heartbeat 15 min). Dépendances par `depends_on uuid[]`.
Supabase Realtime diffuse les changements au dashboard.

## Conséquences
- (+) Zéro infrastructure supplémentaire ; transactions et requêtes ad hoc sur la file.
- (+) Les jobs sont des données : historique, statistiques de durée, relance depuis l'UI.
- (−) Polling (5 s) plutôt que push ; acceptable pour des jobs de plusieurs minutes.
- Migration vers `pgmq` (Supabase Queues) possible si le volume dépasse quelques milliers / jour.
