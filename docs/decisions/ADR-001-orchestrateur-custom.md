# ADR-001 · Worker Python + file Postgres plutôt que n8n

**Statut** : accepté · 2026-09-19

## Contexte
Le plan initial hésite entre n8n et du code custom pour orchestrer 3 uploads / jour / chaîne.
Le gros du travail est local et lourd (GPU, FFmpeg) ; n8n ne ferait que déclencher des scripts.

## Décision
Un **worker Python unique** (`services/worker`) exécute toutes les étapes en réclamant des jobs
dans une **table Postgres** (`jobs`, `FOR UPDATE SKIP LOCKED`). Un planificateur interne
(APScheduler) remplace les crons n8n.

## Conséquences
- (+) Un seul langage pour les étapes, les fournisseurs et l'API YouTube ; tests unitaires simples.
- (+) La progression (0-100, étape courante, journal) vit dans la base → visible en temps réel
  dans le dashboard sans intégration supplémentaire.
- (+) Pas de service n8n à héberger/maintenir, pas de secrets dupliqués.
- (−) Pas d'éditeur visuel de flux ; les enchaînements sont du code (DAG via `depends_on`).
- n8n reste possible en périphérie (notifications Notion/Slack) via un webhook sur `alerts`.
