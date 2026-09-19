# 07 · Roadmap

## Phase 0 · Prérequis (à faire à la main, cette semaine)
- [ ] Créer les deux chaînes YouTube (FR, EN) + une chaîne de test non listée.
- [ ] Projets GCP `yt2-fr`, `yt2-en` : activer Data API v3 + Analytics API, écran de consentement
      **en production**, client OAuth Web, **soumettre l'audit de conformité API** (délai long, voir
      `05-youtube-api.md` §2).
- [ ] Projet Supabase (région EU) ; projet Vercel relié au dossier `apps/dashboard`.
- [ ] PC : ComfyUI + modèles, Kokoro, FFmpeg, Python/uv (`06-local-stack.md`).
- [ ] Décisions ouvertes : LLM (Claude API vs Ollama), fournisseur vidéo initial, validation
      humaine on/off, OS du PC.

## Phase 1 · Fondations (données réelles dans le dashboard)
- [ ] Appliquer `0001_init.sql`, insérer `app_users`, déployer le dashboard (mode mock → réel).
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
- [ ] Benchmark LTX-Video vs Wan 2.1 (et un fournisseur cloud en comparaison) : qualité 9:16,
      temps / clip, stabilité sur 8 Go → choix du `video_provider` par défaut.
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
