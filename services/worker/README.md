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
├── notify.py        mail « vidéo terminée » (boîte d'envoi = table alerts, docs/32)
├── steps/           une classe par type de job
├── providers/       protocoles LLM / vidéo / TTS + implémentations
└── youtube/         OAuth (refresh token chiffré), Data API, Analytics API, quota
workflows/           workflows ComfyUI (JSON) paramétrés par le step generate_clip
```

## Lancer
```bash
uv sync --extra tts --extra web --extra dev   # web = Playwright, pour les clips Gemini en ligne (docs/17)
cp ../../.env.example .env   # DATABASE_URL = chaîne « Session pooler » Supabase
uv run worker                # ou : uv run worker --once (traite un job puis quitte)
DRY_RUN=1 uv run worker      # aucun appel YouTube / fournisseur, sorties factices
```

## Gestes humains : commande `yt2`

En attendant les écrans du dashboard (détails : `docs/11-sous-titres-seo-strategie-storyboard.md`) :
```bash
uv run yt2 subtitles list                         # profils de sous-titres et polices
uv run yt2 subtitles preview --profile impact     # vidéo d'essai d'un profil, sans base
uv run yt2 storyboard show <production>           # images par scène + planche PNG
uv run yt2 storyboard pick <production> 2:1       # retenir l'image 1 pour la scène 2
uv run yt2 storyboard approve <production>        # lancer clips, voix, montage
uv run yt2 strategy show fr                       # dernière proposition de stratégie
uv run yt2 strategy accept fr <version>
uv run yt2 seo redo <vidéo>
uv run yt2 gemini open                            # Gemini dans le Chrome dédié (s'y connecter une fois, docs/17)
uv run yt2 gemini check                           # parcours jusqu'au bouton Envoyer, sans rien envoyer (capture)
uv run yt2 gemini send <production>               # clips fabriqués par Gemini en ligne (comme le bouton ✦ Gemini)
uv run yt2 prompts list                           # prompts des agents : version en service, origine (docs/22)
uv run yt2 prompts show seo                       # texte en service d'un prompt (--version N)
```

Prompts des agents : le texte écrit dans le code (`DEFAULT_PROMPT`, `SCRIPT_PROMPTS`, `RULES`…) est recopié dans
`prompt_templates` à chaque démarrage du worker (`worker/prompts.py`), et les steps lisent la version en service à
chaque appel : une version modifiée dans l'onglet Agents du dashboard prime sur le code (`docs/22-agents.md`).

## Tests

```bash
uv run pytest -q          # sous-titres, timeline, montage, SEO, stratégie, workflows ComfyUI
```

## Ajouter un step
1. Créer `worker/steps/mon_step.py` avec une classe héritant de `Step` (`type`, `lane`, `run`).
2. L'enregistrer dans `worker/steps/__init__.py` (`REGISTRY`).
3. Ajouter le type dans l'enum SQL `job_type` (migration) et dans `WORKER_JOB_TYPES`.
