# 07 · Roadmap

## Phase 0 · Prérequis (à faire à la main, cette semaine)
- [ ] Créer les deux chaînes YouTube (FR, EN) + une chaîne de test non listée.
- [ ] Projets GCP `yt2-fr`, `yt2-en` : activer Data API v3 + Analytics API, écran de consentement
      **en production**, client OAuth Web, **soumettre l'audit de conformité API** (délai long, voir
      `05-youtube-api.md` §2).
- [ ] Projet Supabase (région EU, offre gratuite) : appliquer `0001_init.sql` puis `seed.sql`.
- [ ] Clés API LLM : Anthropic (principal), Mistral et Gemini (secours) ; Ollama en local.
- [ ] PC Windows : outils, ComfyUI portable + modèles, Kokoro (`06-local-stack.md`) ; copier
      `launcher/` dans `C:\Users\Luca\Desktop\Projets_Code-start\youtube-shorts-daily-2026_09_19\`.
- [ ] Lancer le benchmark vidéo (`08-benchmark-video.md` §6) et choisir `VIDEO_PROVIDER`.
- [x] Décisions prises : 100 % automatique par défaut (validation humaine + e-mail en option),
      tout en local (ADR-006), LLM multi-fournisseurs avec secours.

## Phase 1 · Fondations (données réelles dans le dashboard)
- [ ] Brancher le dashboard sur Supabase (`src/lib/data/supabase.ts`, mode mock → réel).
- [ ] Flux OAuth (`/api/youtube/connect|callback`), stockage chiffré des refresh tokens.
- [ ] Worker : boucle `claim_jobs`, heartbeat, `sync_metrics` / `sync_retention` / `sync_comments`
      → premières métriques réelles (même sur 0 vidéo : abonnés, vues chaîne).
- [ ] Alertes e-mail (échec de job).

## Phase 2 · Un Short de bout en bout (sans génération vidéo IA)
- [ ] Agent script (`ScriptV1`) + prompts v1 ; TTS Kokoro FR/EN ; assemblage FFmpeg avec des
      clips de remplacement (banque libre) ; QA ; aperçu dans `/production` ; validation humaine.
- [ ] Upload en `private + publishAt` sur la chaîne de test ; vérifier classement Short,
      métadonnées, `containsSyntheticMedia`.

## Phase 3 · Génération vidéo
- [ ] Fournisseurs `comfy_wan5b`, `comfy_wan14b_i2v` (+ step image Z-Image Turbo) d'après le
      benchmark ; `kaggle` si la capacité du PC ne suffit pas.
- [ ] Presets de style, 2 candidats / scène, sélection automatique, upscale.

## Phase 4 · Cadence 3 / jour / chaîne
- [ ] Planificateur (créneaux, tampon 2 jours, priorités), jauge de quota, alertes créneau vide.
- [ ] Agent idée automatique, auto-approbation optionnelle, calendrier complet.

## Phase 5 · Optimisation
- [ ] Classement top 20, few-shot dans les prompts, agent d'amélioration (propositions de prompts
      à valider), tableau A/B, clone d'une vidéo performante en nouvelle idée.
- [ ] Commentaires : synchro + brouillons de réponses (validation humaine).

## Phase 6 · Durcissement
- [ ] Purge des fichiers, sauvegardes Supabase, tests d'intégration du worker (jobs factices),
      surveillance du PC (dernier heartbeat visible dans `/settings`).
