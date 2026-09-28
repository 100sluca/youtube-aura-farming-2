# 08 · Benchmark génération vidéo (gratuit, local et en ligne)

> Mise à jour du 2026-09-25 : Qwen-Image 2.1, LTX-2.5, Blender + Higgsfield, budget d'une journée de production
> par semaine et règle de gratuité : voir `14-modeles-de-generation-et-gratuite.md` et `decisions/ADR-007-gratuite.md`.

État au 19 septembre 2026, pour un PC Windows avec GPU **8 Go de VRAM** (RTX 4060 / 4070 / 3070),
32 Go de RAM, et un besoin de **~24 clips de 4-5 s par jour** (3 productions × 8 scènes, master
partagé FR/EN, ADR-002). Les chiffres viennent de tests publiés (sources en bas) : ils donnent
l'ordre de grandeur, le script `services/worker/scripts/bench_video.py` donne les vrais chiffres
sur ta machine.

## 1. Critères

| Critère | Pourquoi | Seuil |
|---|---|---|
| Coût récurrent | objectif 0 € | gratuit sans plafond journalier bloquant |
| Automatisable | le worker doit appeler une API ou ComfyUI | API officielle ou local ; jamais d'automatisation d'UI web (CGU) |
| Sans filigrane | YouTube déclasse les contenus watermarkés, CGU | aucun filigrane visible |
| 9:16 natif | Shorts | ratio vertical supporté |
| Temps / clip de 4-5 s | 24 clips / jour dans une session de nuit | ≤ 6 min |
| Qualité intérieurs / architecture | photoréalisme, matières, lumière stable | note ≥ 3,5 / 5 au benchmark |
| Licence | usage commercial (monétisation) | Apache 2.0 / MIT ou licence permettant l'usage commercial |

## 2. Local (ComfyUI, 8 Go de VRAM)

| Modèle | Poids / licence | Sur 8 Go | Temps / clip 4-5 s (4060) | Qualité | Verdict |
|---|---|---|---|---|---|
| **Wan 2.2 TI2V-5B** | 5B, Apache 2.0, T2V + I2V | FP8 ≈ 5-8 Go, offload ComfyUI natif ; 480p natif, 720p possible mais lent | ≈ 4-6 min à 480p | bonne cohérence, meilleur rapport qualité/poids ouvert | **Candidat principal T2V** |
| **Wan 2.2 14B I2V « Rapid » distillé (GGUF Q4)** | 14B distillé, Apache 2.0 | GGUF Q4 + offload T5 sur CPU, RAM 32 Go utile | ≈ 2 min (111 s mesurés sur 4060) | supérieure au 5B en I2V | **Candidat plans « héro » via image → vidéo** |
| Wan 2.1 1.3B T2V | 1.3B, Apache 2.0 | large | ≈ 1-2 min à 480p | correcte, moins de détails | secours rapide |
| **LTX-Video 2B distillé (0.9.x)** | 2B, licence LTX (usage commercial autorisé sous conditions) | large, 576×1024 OK | quelques secondes à ~1 min | mouvement fluide, détails moyens | brouillons, prévisualisation de script |
| LTX-2 / 2.3 / 2.5 (audio + vidéo) | 19B+, GGUF Q4 | 540p24, 4 s, 20 étapes ; Lightricks documente 32 Go, la communauté tourne en Q4 sur 8 Go | ≈ 5-7 min (300-400 s sur 3070 Ti 8 Go) | très bonne, **audio synchronisé** généré | à tester pour le format B (foley) |
| FramePack (I2V) | Hunyuan-based, 6 Go | oui, VRAM constante quelle que soit la durée | lent : ~1,5 s/frame sur 4090, 4-8× plus sur 8 Go → 8-20 min pour 4 s | stable, longues durées | clips longs uniquement |
| HunyuanVideo 1.5 | 8,3B | **non** : 14 Go min avec offload (FP8 10-12 Go) | — | excellente | hors budget VRAM |
| CogVideoX-2B | 2B | oui | ≈ 2-4 min | datée (2024) | non |
| Wan 2.5 / 2.6 / 2.7 | API uniquement, pas de poids ouverts (au 07/2026, les poids ouverts s'arrêtent à Wan 2.2) | — | — | — | non (payant) |

**Route image → vidéo** (recommandée pour les plans de révélation) : générer d'abord une image
9:16 photoréaliste, puis l'animer.
- Image : **Z-Image Turbo** (6B, Alibaba, FP8 sur 8 Go, ≈ 15-20 s par image 1024² sur 4060, 8
  étapes) ou Flux.1 schnell GGUF Q4 (plus lourd, ≈ 30-60 s).
- Animation : Wan 2.2 I2V (5B ou 14B Rapid GGUF) ou FramePack.
- Avantages : on choisit la meilleure image parmi 4 en quelques secondes (netteté, matières),
  la vidéo n'a plus qu'à animer ; les scènes « avant / après » se contrôlent bien ; la première
  et la dernière image d'un Short en boucle peuvent être la même image animée.

## 3. En ligne, offres gratuites (septembre 2026)

| Service | Gratuit | Filigrane | API gratuite | Commercial | Verdict pour un pipeline automatique |
|---|---|---|---|---|---|
| Kling | 66 crédits / jour (≈ 2-6 clips 5 s, 720p) | oui | non | non | non (à la main : tests de prompts) |
| PixVerse | 60 crédits / jour (≈ 1 clip 540p) + 90 à l'inscription | oui | non | non | non |
| Hailuo / MiniMax | crédits quotidiens (≈ 2-3 clips 768p) + 200 à l'inscription | oui | non | non | non |
| Google Flow (Veo 3.1) | 50 crédits / jour sans abonnement (07/2026) ; appli Gemini ≈ 3-5 vidéos / jour | SynthID + filigrane selon la surface | non (Veo API payante) | non sur le gratuit | non (mais qualité de référence pour comparer) |
| Dreamina / CapCut (Seedance 2.x) | crédits quotidiens variables selon région | oui | non | non | non |
| Grok Imagine | gratuit **supprimé** en mars 2026 | — | — | — | non |
| Higgsfield | plan gratuit = 0 crédit + filigrane ; Starter 19 $ / 270 crédits | oui (gratuit) | payant | payant | non en gratuit ; ton connecteur MCP est expiré, à réautoriser si tu veux que je regarde tes crédits |
| Runway / Luma / Pika | crédits d'essai uniques ou faibles, filigrane | oui | non | non | non |
| fal.ai / Replicate (API) | 10 $ de crédits uniques / petits crédits d'essai | non | oui mais crédits uniques | oui | test ponctuel (50-100 clips), pas un flux quotidien |

Conclusion : **aucune offre gratuite en ligne ne tient les critères** (filigrane, pas d'API, CGU
interdisant l'automatisation). Elles servent à comparer la qualité à la main, pas au pipeline.

## 4. GPU gratuits dans le cloud (extension du PC)

| Plateforme | Quota | Carte | Contraintes | Verdict |
|---|---|---|---|---|
| **Kaggle** | 30 h GPU / semaine | T4 ×2 (2 × 16 Go) ou P100 16 Go | sessions ≤ 9-12 h, notebooks, pilotable par l'API Kaggle | **viable** : ≈ 4 h / jour, 16 Go → Wan 2.2 5B en 720p sans offload ; fournisseur `kaggle` à écrire si le PC ne suffit pas |
| Google Colab gratuit | 15-30 h / semaine, variable | T4 16 Go | déconnexions, pas d'exécution en arrière-plan fiable | dépannage manuel seulement |

## 5. Recommandation

1. **Pipeline principal** : Wan 2.2 TI2V-5B (FP8 ou GGUF) en text-to-video, 480p natif → upscale
   ×2 dans `assemble`. Budget : 24 clips × 4-6 min ≈ **1,5 à 2,5 h de GPU par nuit**.
2. **Plans héros** (révélation, avant/après, 2-3 scènes par Short) : route image → vidéo avec
   Z-Image Turbo + Wan 2.2 I2V 14B Rapid GGUF (≈ 2 min / clip).
3. **Brouillons** : LTX-Video 2B distillé pour prévisualiser un script en 1 minute avant de
   lancer la vraie génération.
4. **Format B (visuel pur)** : tester LTX-2.x GGUF pour son audio synchronisé ; sinon bibliothèque
   de foley locale (déjà prévu dans `assemble`).
5. **Capacité en plus, gratuite** : Kaggle (30 h / semaine) avec les mêmes workflows ComfyUI.
6. **Pas de service gratuit en ligne dans le pipeline.**

Fournisseurs à implémenter dans `worker/providers/video.py` : `comfy_wan5b` (T2V), `comfy_wan14b_i2v`
(image → vidéo, avec un step `generate_still` Z-Image en amont), `comfy_ltx` (existant, brouillons),
plus tard `kaggle`.

## 6. Protocole de mesure sur ta machine

1. ComfyUI portable + modèles (voir `06-local-stack.md`), workflows exportés en format API dans
   `services/worker/workflows/` (`ltx_t2v.json`, `wan_t2v.json`, …).
2. `cd services/worker && uv run python scripts/bench_video.py --providers comfy_ltx,comfy_wan --duration 4 --runs 2`
3. Ouvrir `bench/<horodatage>/README.md` : temps, VRAM max, résolution par clip ; noter chaque clip
   de 1 à 5 dans `results.csv` (netteté, cohérence temporelle, respect du prompt, matières).
4. Règle de décision : retenir le fournisseur le moins cher en temps parmi ceux dont la note
   moyenne ≥ 3,5 ; le second devient `VIDEO_PROVIDER` de secours.
5. Refaire le benchmark à chaque nouveau modèle (le paysage change tous les 2-3 mois).

## Sources
- [Thunder Compute · Best open-source video models 2026](https://www.thundercompute.com/blog/best-open-source-ai-video-generation-models)
- [Will It Run AI · Wan 2.1 / 2.2 VRAM guide](https://willitrunai.com/blog/wan-2-2-vram-requirements) · [Wan2.2 TI2V 5B](https://willitrunai.com/video-models/wan-video-2-2-ti2v-5b)
- [ComfyUI docs · Wan 2.2 workflows](https://docs.comfy.org/tutorials/video/wan/wan2_2) · [Hugging Face · Wan2.2-TI2V-5B](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B)
- [lilting.ch · Wan 2.2 I2V sur RTX 4060 8 Go : 111 s par clip (14B Rapid)](https://lilting.ch/en/articles/wan22-comfyui-rtx4060-i2v)
- [wan27.org · Wan 2.6 / 2.7 : pas de poids ouverts](https://wan27.org/blog/wan-2-6-open-source-guide) · [localaimaster · Wan 2.7 open source ?](https://localaimaster.com/blog/wan-2-7-open-source)
- [DEV · LTX-2 GGUF dans ComfyUI (8 Go)](https://dev.to/gary_yan_86eb77d35e0070f5/how-to-install-and-configure-ltx-2-gguf-models-in-comfyui-complete-2026-guide-1d3m) · [MindStudio · LTX-2.5 VRAM](https://www.mindstudio.ai/blog/ltx-2-5-comfyui-install-guide) · [NVIDIA · LTX-2 quick start](https://www.nvidia.com/en-sg/geforce/news/rtx-ai-video-generation-guide/) · [GitHub · LTX-2-OPTIMIZED 8 Go](https://github.com/nalexand/LTX-2-OPTIMIZED)
- [Will It Run AI · HunyuanVideo 1.5 VRAM](https://willitrunai.com/blog/hunyuanvideo-1-5-vram-requirements)
- [Tom's Hardware · FramePack 6 Go](https://www.tomshardware.com/tech-industry/artificial-intelligence/framepack-can-generate-ai-videos-locally-with-just-6gb-of-vram) · [Stable Diffusion Art · FramePack](https://stable-diffusion-art.com/framepack/)
- [Thunder Compute · Z-Image Turbo ComfyUI (09/2026)](https://www.thundercompute.com/blog/z-image-turbo-comfyui) · [zimage.run · 6-8 Go](https://zimage.run/blog/z-image-turbo-quantized-low-vram-guide)
- [Kling free tier 2026 (66 crédits / jour)](https://aireiter.com/blog/kling-ai-free-tier-2026) · [PixVerse free](https://www.atlascloud.ai/blog/guides/pixverse-ai-free) · [Hailuo free](https://aivideosensei.com/guides/hailuo-minimax-guide) · [Veo 3.1 / Flow gratuit](https://moelueker.com/blog/google-veo-2-free-access-beat-rate-limits-with-3-platforms) · [Seedance 2.0 free](https://reapi.ai/blog/how-to-use-seedance-2-0-for-free) · [Grok Imagine fin du gratuit](https://goongen.ai/blog/is-grok-imagine-free) · [Higgsfield pricing](https://www.krea.ai/blog/what-is-higgsfield-ai-pricing-free-plan-and-alternatives-in-2026)
- [apiframe · Free video APIs 2026](https://apiframe.ai/blog/free-ai-video-generation-api-2026) · [fal.ai free credits](https://aicredits.dev/submissions/92-fal-ai-free-credits-for-image-video-generation)
- [Kaggle · GPU 30 h / semaine](https://aicreditmart.com/ai-credits-providers/kaggle-free-gpu-tpu-30-hours-week-access-guide-2026/) · [Colab FAQ](https://research.google.com/colaboratory/faq.html)
