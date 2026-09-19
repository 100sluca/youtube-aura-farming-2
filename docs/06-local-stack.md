# 06 · Fabrique locale (PC, GPU 8 Go)

Cible : CPU haut de gamme, 32 Go RAM, GPU 8 Go (RTX 4060 / 4070 / 3070).

## 1. Composants

| Rôle | Outil | Remarques 8 Go VRAM |
|---|---|---|
| Orchestration | worker Python (`services/worker`), service au démarrage (Task Scheduler / NSSM sous Windows, systemd sous Linux) | concurrence GPU = 1 |
| Vidéo | ComfyUI + **LTX-Video 2B** (rapide, 576×1024 OK) ou **Wan 2.1 1.3B** (480p, plus lent, meilleure cohérence) ; variantes GGUF/NF4 + offload CPU | 1-8 min / clip de 4-5 s ; benchmark en phase 3 |
| Upscale | Real-ESRGAN (x2) ou lanczos FFmpeg | 10-20 s / clip |
| TTS | **Kokoro-82M** (voix FR `ff_siwis`, EN `af_heart`…) ; alternative **Chatterbox multilingue** | CPU suffisant, ~temps réel |
| LLM | Claude API (défaut) ; **Ollama** Qwen 2.5 7B Q4 en secours/hors-ligne | Ollama et ComfyUI ne cohabitent pas en VRAM : le worker décharge Ollama (`keep_alive=0`) avant un job GPU vidéo |
| Montage | FFmpeg 7 (`drawtext`, `loudnorm`, `minterpolate`) | CPU |
| SFX / ambiances | bibliothèque locale libre de droits (Freesound CC0, Pixabay) indexée par tags | format B |

## 2. Budget temps GPU par jour (3 productions, 8 scènes de 4 s)

| Modèle | / clip | 24 clips | + 2 candidats / scène |
|---|---|---|---|
| LTX-Video 2B (576×1024, 97 frames) | ~1-2 min | 25-50 min | 50-100 min |
| Wan 2.1 1.3B (480×832, 81 frames) | ~5-8 min | 2-3 h | 4-6 h |

→ Commencer avec LTX pour le volume, tester Wan sur les scènes « héro » (révélation).
Le partage du master visuel entre FR et EN (ADR-002) est ce qui rend 6 Shorts / jour tenable.

## 3. Fenêtre de fonctionnement

Le PC n'a pas besoin de tourner 24 h/24 :
- les uploads sont programmés à l'avance (`publishAt`), tampon de 2 jours ;
- le planificateur rattrape les jobs manqués au réveil (`requeue_stale_jobs`, créneaux vides) ;
- alerte si le tampon descend sous 6 vidéos programmées par chaîne.

Recommandation : session de génération nocturne (ex. 23:00-06:00) planifiée par le worker,
uploads à 07:00, synchro métriques à 03:00.

## 4. Arborescence des fichiers (DATA_DIR)

```
data/
├── productions/<production_id>/
│   ├── clips/scene_00.mp4 …        (natifs 576×1024)
│   ├── clips_up/scene_00.mp4 …     (upscalés 1080×1920)
│   └── master.mp4                  (visuel silencieux)
├── videos/<video_id>/
│   ├── narration.wav
│   ├── final.mp4                   (→ YouTube)
│   ├── preview.mp4                 (480p → Storage)
│   └── poster.jpg                  (→ Storage)
└── sfx/                            (bibliothèque)
```

Rétention : masters et finals conservés 90 jours après publication puis purgés (les vidéos
sont sur YouTube) ; previews purgées de Storage 30 jours après publication.

## 5. Installation (résumé, détaillé dans `services/worker/README.md`)

1. Python 3.11+, `uv`, FFmpeg dans le PATH, pilotes NVIDIA + CUDA récents.
2. ComfyUI (portable Windows ou git) + modèles LTX-Video / Wan (+ encodeurs texte) dans
   `ComfyUI/models/…` ; lancer avec `--listen 127.0.0.1 --port 8188`.
3. `uv sync` dans `services/worker`, copier `.env.example` → `.env`.
4. Kokoro : `pip install kokoro-onnx` (ou `kokoro` PyTorch) + fichiers de voix.
5. `uv run worker` : le worker se déclare (`WORKER_ID`), réclame les jobs, envoie un heartbeat.
6. Installer en service (NSSM / Task Scheduler « au démarrage », redémarrage automatique).
