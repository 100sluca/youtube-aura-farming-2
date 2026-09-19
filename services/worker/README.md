# Worker local

Boucle : `claim_jobs` → step → `done` / `fail_job`, heartbeat toutes les 30 s, planificateur
APScheduler pour les tâches récurrentes (voir `docs/03-pipeline.md`).

```
worker/
├── main.py          boucle principale, deux voies (gpu / io)
├── config.py        Settings (pydantic-settings, .env)
├── db.py            accès Postgres (psycopg) : claim, heartbeat, complete, fail, enqueue, log
├── models.py        Job, ScriptV1, IdeaBatch, QAReport (pydantic)
├── scheduler.py     tâches récurrentes (planification des créneaux, synchro, alertes)
├── notify.py        alertes (table alerts + e-mail)
├── steps/           une classe par type de job
├── providers/       protocoles LLM / vidéo / TTS + implémentations
└── youtube/         OAuth (refresh token chiffré), Data API, Analytics API, quota
workflows/           workflows ComfyUI (JSON) paramétrés par le step generate_clip
```

## Lancer
```bash
uv sync --extra tts --extra dev
cp ../../.env.example .env   # DATABASE_URL = chaîne « Session pooler » Supabase
uv run worker                # ou : uv run worker --once (traite un job puis quitte)
DRY_RUN=1 uv run worker      # aucun appel YouTube / fournisseur, sorties factices
```

## Ajouter un step
1. Créer `worker/steps/mon_step.py` avec une classe héritant de `Step` (`type`, `lane`, `run`).
2. L'enregistrer dans `worker/steps/__init__.py` (`REGISTRY`).
3. Ajouter le type dans l'enum SQL `job_type` (migration) et dans `WORKER_JOB_TYPES`.
