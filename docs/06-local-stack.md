# 06 · Fabrique locale (PC, GPU 8 Go)

Cible : CPU haut de gamme, 32 Go RAM, GPU 8 Go (RTX 4060 / 4070 / 3070).

## 1. Composants

| Rôle | Outil | Remarques 8 Go VRAM |
|---|---|---|
| Orchestration | worker Python (`services/worker`) lancé dans une fenêtre par `launcher/youtube-shorts-daily - demarrer.bat` (service Windows plus tard si besoin) | concurrence GPU = 1 |
| Vidéo | ComfyUI + **Wan 2.2 TI2V-5B** (FP8/GGUF, principal), **Wan 2.2 I2V 14B Rapid GGUF** (plans héros, image → vidéo), **LTX-Video 2B** (brouillons) ; voir `08-benchmark-video.md` | 1-6 min / clip de 4-5 s |
| Upscale | Real-ESRGAN (x2) ou lanczos FFmpeg | 10-20 s / clip |
| TTS | **Kokoro-82M** (voix FR `ff_siwis`, EN `af_heart`…) ; alternative **Chatterbox multilingue** | CPU suffisant, ~temps réel |
| LLM | Claude API (défaut), secours Mistral API, Gemini API, puis **Ollama** Qwen 2.5 7B Q4 hors-ligne | Ollama et ComfyUI ne cohabitent pas en VRAM : le worker décharge Ollama (`keep_alive=0`) après chaque appel |
| Montage | FFmpeg 7 (`drawtext`, `loudnorm`, `minterpolate`) | CPU |
| SFX / ambiances | bibliothèque locale libre de droits (Freesound CC0, Pixabay) indexée par tags | format B |

## 2. Budget temps GPU par jour (3 productions, 8 scènes de 4 s)

| Modèle | / clip | 24 clips | + 2 candidats / scène |
|---|---|---|---|
| LTX-Video 2B (576×1024, 97 frames) | quelques s à 1 min | 10-25 min | 20-50 min |
| Wan 2.2 TI2V-5B FP8 (480p, 81 frames) | ~4-6 min | 1,5-2,5 h | 3-5 h |
| Wan 2.2 I2V 14B Rapid GGUF (image → vidéo) | ~2 min | 50 min | 1,5 h |

→ Wan 2.2 5B pour le volume, la route image → vidéo pour les scènes « héro », LTX 2B pour les
brouillons (`08-benchmark-video.md`). Le partage du master visuel entre FR et EN (ADR-002) est ce
qui rend 6 Shorts / jour tenable.

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

## 5. Installation sur Windows (résumé, détaillé dans `services/worker/README.md`)

1. Outils : `winget install Python.Python.3.12 astral-sh.uv Gyan.FFmpeg OpenJS.NodeJS.LTS Git.Git`,
   pilote NVIDIA récent (CUDA 12.x inclus).
2. ComfyUI **portable Windows** (dossier `C:\ComfyUI_windows_portable`, `run_nvidia_gpu.bat`) +
   ComfyUI Manager ; modèles Wan 2.2 (5B FP8, 14B I2V Rapid GGUF, encodeur T5, VAE) et LTX-Video
   dans `ComfyUI\models\…` ; exporter les workflows en format API dans `services/worker/workflows/`.
3. Kokoro : `uv sync --extra tts` installe `kokoro-onnx` ; déposer `kokoro-v1.0.onnx` et
   `voices-v1.0.bin` dans `services/worker/models/`.
4. Ollama (optionnel, secours hors-ligne) : `winget install Ollama.Ollama` puis `ollama pull qwen2.5:7b`.
5. Copier `.env.example` → `apps/dashboard/.env.local` et `services/worker/.env`, renseigner
   `DATABASE_URL` (pooler Supabase), clés LLM, `ALERT_EMAIL_TO`.
6. Double-cliquer `launcher/youtube-shorts-daily - demarrer.bat` : il vérifie tout (env, dépendances, port
   3000), lance ComfyUI, le worker et le dashboard, puis ouvre le navigateur.

## 6. Benchmark

`uv run python scripts/bench_video.py --providers comfy_ltx,comfy_wan --duration 4 --runs 2`
mesure temps, VRAM et résolution par clip et produit un tableau à noter (voir `08-benchmark-video.md` §6).
