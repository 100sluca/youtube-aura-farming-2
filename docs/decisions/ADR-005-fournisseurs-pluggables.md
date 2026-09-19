# ADR-005 · Fournisseurs LLM / vidéo / TTS derrière des interfaces

**Statut** : accepté · 2026-09-19

## Contexte
Le choix des modèles n'est pas arrêté (benchmark prévu en phase 3) : LTX-Video vs Wan 2.1 en
local, fournisseurs cloud en comparaison ; Claude API vs Ollama ; Kokoro vs Chatterbox.

## Décision
Trois protocoles Python (`providers/llm.py`, `providers/video.py`, `providers/tts.py`) avec une
implémentation par fournisseur, sélectionnée par configuration (`LLM_PROVIDER`,
`VIDEO_PROVIDER`, `TTS_PROVIDER`) et surchargeable par production (`productions.video_provider`).

## Conséquences
- (+) A/B entre fournisseurs mesurable dans le dashboard (le fournisseur est stocké par vidéo).
- (+) Repli automatique (cloud → local) sans changer le pipeline.
- (−) Les prompts visuels doivent rester portables (préfixes de style par fournisseur).
