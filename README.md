# YouTube 2.0

Fabrique automatisée de **YouTube Shorts** (construction, design d'intérieur, DIY spectaculaire)
sur deux chaînes (FR / EN), générés par IA en local, avec un dashboard de pilotage.

| Dossier | Contenu |
|---|---|
| [`docs/`](docs/) | Architecture, modèle de données, pipeline, dashboard, API YouTube, stack locale, roadmap, ADR |
| [`supabase/migrations/`](supabase/migrations/) | Schéma Postgres (Supabase) : jobs, productions, vidéos, métriques, RLS |
| [`apps/dashboard/`](apps/dashboard/) | Dashboard Next.js 16 + shadcn/ui (vue d'ensemble, vidéos publiées, production, calendrier, idées, A/B, réglages) |
| [`services/worker/`](services/worker/) | Worker Python local : agents LLM (Claude, Mistral, Gemini, Ollama en secours), ComfyUI, Kokoro, FFmpeg, upload et Analytics YouTube, benchmark vidéo |
| [`launcher/`](launcher/) | Lanceur Windows `.bat` + fiche mémo (dossier Projets_Code-start) |

![Vue d'ensemble du dashboard (mode démo)](docs/dashboard-overview.png)

## Lire en premier
1. [`docs/01-architecture.md`](docs/01-architecture.md) : les trois plans (dashboard, Supabase, PC), les principes.
2. [`docs/03-pipeline.md`](docs/03-pipeline.md) : les étapes, le planificateur, les agents.
3. [`docs/05-youtube-api.md`](docs/05-youtube-api.md) : OAuth, quotas, **audit de conformité à lancer tout de suite**.
4. [`docs/08-benchmark-video.md`](docs/08-benchmark-video.md) : génération vidéo gratuite, locale et en ligne, recommandation.
5. [`docs/07-roadmap.md`](docs/07-roadmap.md) : phases et prérequis manuels.

## Démarrage rapide (tout en local, ADR-006)

Windows : double-cliquer `launcher/youtube-2.0 - demarrer.bat` (après avoir adapté `ROOT` et créé
les deux fichiers `.env`). Il lance ComfyUI, le worker et le dashboard, puis ouvre le navigateur.

À la main :

```bash
# Dashboard (données factices, sans backend)
cd apps/dashboard
npm install
NEXT_PUBLIC_MOCK=1 npm run dev        # http://localhost:3000

# Base de données : coller supabase/migrations/0001_init.sql puis supabase/seed.sql
# dans l'éditeur SQL du projet Supabase (ou `supabase db push`)

# Worker (sur le PC avec le GPU)
cd services/worker
cp ../../.env.example .env             # remplir DATABASE_URL, clés LLM, fournisseurs
uv sync --extra tts && uv run worker
```

## Dépôt
Ce dossier vit provisoirement dans `Logements100s` (branche `claude/youtube-2-0-architecture-tud7zx`)
en attendant le dépôt dédié. Extraction avec historique, le dossier devenant la racine :

```bash
git checkout claude/youtube-2-0-architecture-tud7zx
git subtree split --prefix=youtube-2.0 -b youtube-2.0-main
git push https://github.com/100sluca/YouTube-2.0.git youtube-2.0-main:main
```
