# 21 · Les meilleurs modèles pour la RTX 3070 : vidéo et vision, modèle par modèle

> 2026-09-28, demande de Luca : parmi les modèles en tendance sur Hugging Face (texte → vidéo et image-texte → texte,
> première page de chaque), lesquels tournent sur son PC, et lesquels donnent les meilleures vidéos possibles ?
> Phase de recherche : **les licences ne comptent pas** (consigne répétée par Luca) ; seuls le matériel et la qualité
> décident. Machine vérifiée ce jour : RTX 3070 8 Go (Ampere, sm_86), i7-14700K, 31,8 Go de RAM, 41 Go libres sur C:.
> Pour la phase de test, ce document remplace le verdict « exclu (licence) » de MiniMax H3 dans `20-qualite-video.md` §4.

## En bref

- **Vidéo : MiniMax H3, version élaguée en GGUF Q4_K_M (11,6 Go).** N° 1 des modèles ouverts, il tourne sur une
  3070 avec 32 Go de RAM d'après les retours de la communauté : ≈ 480 × 832, 5 s, ≈ 9-10 min par clip, **son compris**.
  Il a 250 points d'Elo d'avance sur Wan 2.2 A14B en image → vidéo (1357 contre 1107), soit environ 4 duels gagnés sur 5.
  La session « Leviers de performance vidéo » est en train de l'installer (§3).
- **N° 2, LTX-2.5** : plus lourd que H3 élagué (15,7 Go de modèle + 15,4 Go d'encodeur) et moins bon. Plan B seulement.
- **Page 1 texte → vidéo** : 22 modèles sur 30 sont des modules pour H3 (LoRA, ControlNet, accélérations), utilisables
  dès que H3 tourne. Les versions complètes non compressées (100 à 575 Go) ne passent pas. Le reste (Wan 1.3B et 5B,
  CogVideoX) tourne mais fait moins bien que le Wan 14B actuel.
- **Vision et texte** : Qwen3.8-27B est le plus fort qui tourne (≈ 17 Go, réparti entre la carte et la RAM, lent) ;
  les 9B (ZDTaichu5.0, MiMo-V2.6-Distill, Qwen3.5-9B) tiennent entiers dans la carte et vont vite ; tout ce qui
  dépasse ≈ 100B est impossible.

## 1. Ce que la machine permet

| Limite | Conséquence |
|---|---|
| 8 Go de VRAM | ComfyUI charge les poids par morceaux depuis la RAM (déchargement dynamique) : un modèle plus gros que la carte passe, c'est la place pour l'image en cours de calcul qui limite la résolution |
| 31,8 Go de RAM | **le vrai goulot** : modèle vidéo + encodeur de texte + VAE doivent y tenir, avec Windows et ComfyUI. Retour H3 : même carte 12 Go, 16 Go de RAM → 20-29 min et machine figée ; 32 Go → 6-10 min |
| Ampere (sm_86) | pas de calcul FP8 ni FP4 natif. Les fichiers FP8 / NVFP4 se chargent quand même : comfy_kitchen les décompresse en bf16 (`tensor/base.py`, « Fallback to dequantization »), sans le gain de vitesse. INT8 (convrot) et GGUF : natifs, déjà utilisés (Z-Image, Qwen-Image 2.1, Wan 14B) |
| 41 Go libres sur C: | un gros modèle à la fois |
| Texte et vision (LM Studio, Ollama, installés) | ≤ 10B en Q4 (≈ 6 Go) : entier dans la carte, rapide · 27-31B dense (16-19 Go) : partagé carte / RAM, lent · MoE 35B-A3B (≈ 21 Go) : experts en RAM, rapide · ≥ 100B : impossible |
| Une seule carte | un modèle de vision local et ComfyUI ne peuvent pas être chargés en même temps : décharger l'un avant l'autre |

Premiere Pro ouvert prend ≈ 2 Go de VRAM et 4 Go de RAM : le fermer pendant les rendus.

## 2. Qualité : le classement à l'aveugle

Artificial Analysis, modèles ouverts, votes à l'aveugle, relevé le 28/09/2026.

| Modèle | Image → vidéo, sans son | Texte → vidéo, sans son | Avec son (I → V / T → V) | Sur la 3070 |
|---|---|---|---|---|
| **MiniMax H3** (juillet 2026, 33B ; ≈ 20B élagué) | **1357** | **1302** | 1181 / 1220 | **oui**, élagué en GGUF Q3 / Q4 |
| Cosmos3-Super-Image2Video 4-step (NVIDIA, 64B) | 1273 | — | — | non, trop gros |
| MAGI-2 Preview (Sand.ai, 114B) | — | — | 1094 / — | non, trop gros |
| LTX-2.5 Fast / Pro (22B) | 1214 / 1193 | 1218 / 1209 | 1036 / 1055 | oui, mais plus lourd que H3 élagué |
| LTX-2 et LTX-2.3 (19-22B) | 1149 à 1201 | 1121 à 1127 | 923 à 975 | oui, lourd |
| HunyuanVideo 1.5 (8,3B) | 1134 | 1020 | — | oui |
| **Wan 2.2 A14B (en service)** | 1107 | 1116 | — | oui |
| Wan 2.1 14B | 1000 | 1018 | — | oui |
| Wan 2.2 5B (installé) | 992 | 950 | — | oui |
| Mochi 1 / CogVideoX-5B | — | 1000 / 805 | — | oui, dépassés |

Seul H3 est à la fois nettement devant Wan 2.2 et faisable. LTX-2.5 est devant Wan de ≈ 100 points mais pèse plus
lourd que H3 élagué : aucune raison de le préférer ici, sauf si H3 plante.

## 3. MiniMax H3 sur 8 Go : la recette

ComfyUI 0.37.2 gère H3 en natif (`comfy/ldm/minimax`, nœuds `MiniMaxH3ImageToVideo`, `MiniMaxH3AddGuide`…).
La session « Leviers de performance vidéo » l'installe : workflows `minimax_h3_i2v` et `minimax_h3_flf2v`, entrée
`minimax_h3_i2v` dans `catalog.json`. État le 28/09 : VAE et LoRA présentes, modèle en cours de téléchargement.

| Pièce | Fichier conseillé | Taille | Remarque |
|---|---|---|---|
| Modèle | `MiniMax-H3-FL2VA-Pruned-Q4_K_M.gguf` (Abiray/MiniMax-H3-Pruned-GGUF) | 11,6 Go | Q3_K_M (8,9 Go) si la RAM sature. FL2VA = première (+ dernière) image → vidéo + son : sert aussi aux chantiers et visites |
| Variante à comparer | Singularity (fine-tune : netteté HDR, visages lointains, mouvements vifs), GGUF Q4_K_M chez Abiray | 11,56 Go | même taille, même workflow |
| Encodeur de texte (Qwen3-VL-32B tronqué) | au choix : ① `qwen3vl_32b_minimax_h3_nvfp4_awq` ; ② GGUF Q2_K (realrebelai/FastH3-V2_GGUFs) ; ③ **ClipProj** avec le Qwen3-VL-8B déjà installé | ① 15,7 Go ② 8,5 Go ③ 0 Go de plus | ① choisi par l'autre session : marche sur Ampere, mais porte la RAM à ≈ 31 Go sur 31,8. ③ demande le nœud ComfyUI-ClipProj et une matrice `mmh3-8b-ClipProj-v3.1` (« any ComfyUI-format Qwen3-VL-8B ») |
| VAE | `minimax_h3_video_vae_int8_convrot` + `minimax_h3_audio_vae_fp32` | 2,8 + 0,6 Go | déjà installés |
| Accélération | LoRA Turbo 8 passes (installée) ; plus récente : `fl2v_turbo_4step_v1.2_768p` (lightx2v/Minimax-h3-Turbo) | 2 Go | pour la qualité maximale : 20 passes sans LoRA |
| Réglages | 480 × 832 (0,4 Mpx), 124 images = 5,2 s à 24 i/s, `res_multistep` / `simple` | | la toile native 768 × 1344 n'est citée qu'à partir de 12 Go de VRAM, « avec la LoRA Turbo et de la patience » |
| Finition | SeedVR2 (agrandissement vers 1080 × 1920) puis RIFE (fluidité), déjà installés | | workflow `post/seedvr2_rife` en cours dans l'autre session |

Temps rapportés par la communauté (non mesurés ici) : RTX 3070 + 32 Go, ≈ 9-10 min pour un clip de 5 s à 0,4 Mpx ;
RTX 3060 12 Go, moins de 9 min en 20 passes. À vérifier au premier clip : temps, VRAM et RAM maximales.

Le son généré (ambiance, bruitages) peut servir au montage ; les workflows actuels l'ignorent.

Si le GGUF refuse de charger : mettre à jour ComfyUI-GGUF (la copie installée date du 12/01/2026, avant H3).

## 4. Page 1 « texte → vidéo », modèle par modèle

✅ tourne · ⚠️ tourne en forçant ou à essayer · ❌ ne tourne pas. « Avec H3 » : module qui s'ajoute à H3 et tourne
dès que H3 tourne.

| # | Modèle | Ce que c'est | Taille | Verdict |
|---|---|---|---|---|
| 1 | alibaba-pai/MiniMax-H3-Fun-Controlnet-Union-2.0 | ControlNet H3 : 8 contrôles (contours, profondeur, pose, croquis, mise en page…) | 13,6 Go ; 4,5 Go en int8 élagué (Comfy-Org) | ✅ avec H3, en int8 ; utile pour les visites sur plan |
| 2 | larryvrh/MiniMax-H3-Turbo-Lora | LoRA 4 passes vidéo + son | points d'étape de 10,9 Go | ✅ avec H3, mais prendre les LoRA de 2 Go de lightx2v / Comfy-Org |
| 3 | smhfacct/Minimax-H3-fl2va-ref2va-hybrid-models | fusion des deux versions de H3 | 21 Go (int8), pas de GGUF | ⚠️ RAM au bord (21 Go + encodeur) |
| 4 | Veda-Sparse/Minimax-H3-T2VA-Veda-8NFE-600Step-Preview | prédicteur d'attention creuse : accélère le texte → vidéo en 8 passes | 0,28 Go | ⚠️ préversion, vitesse seulement |
| 5 | drbaph/MiniMax-H3-Turbo-Lora-ComfyUI | LoRA rapides pour ComfyUI (HyperFlow 8 passes, DMD, TaoMate 3 passes) | 2,3 à 3,9 Go | ✅ avec H3 |
| 6 | FastVideo/FastVideo-FastH3-8-Step-V2 | H3 complet distillé en 8 passes | 148 Go | ❌ tel quel ; ⚠️ en GGUF (n° 19) |
| 7 | alibaba-pai/MiniMax-H3-Acc-LoRAs | LoRA 8 passes sans CFG | 1,4 Go | ✅ avec H3 |
| 8 | Wan-AI/Wan2.1-T2V-1.3B | petit Wan 2.1, 480p | 5,7 Go | ✅ facile, nettement moins bon |
| 9 | SexGod1979/PinkCherry_MiniMax-H3 | fine-tune H3 pour adultes | 34 à 66 Go | ❌ trop lourd sans GGUF, hors sujet |
| 10 | JOKER141/BUNNY_H3_Conditioning_Bridge | module de conditionnement sémantique pour H3 | 0,15 Go | ✅ avec H3 |
| 11 | SulphurAI/Sulphur-2-base | LTX 2.3 « non censuré » + améliorateur de prompt 9B | 29 Go en fp8 ; GGUF chez vantagewithai | ⚠️ comme LTX ; sans intérêt face à LTX-2.5 ou H3 |
| 12 | FastVideo/FastVideo-FastH3-4-step-Preview-v1-VSA-DataFree | H3 complet en 4 passes | 148 Go | ❌ |
| 13 | vpakarinen/better-human-motion-h3-lora | LoRA mouvements humains | 0,3 Go | ✅ avec H3 |
| 14 | TaoLiveAIGC/TaoMate-H3 | génération en direct (streaming) sur H3, 3 passes | 2,5 Go | ⚠️ pensé pour le direct ; version ComfyUI chez CZMartin22 |
| 15 | alibaba-pai/MiniMax-H3-Fun-Controlnet-Union | ancienne version du n° 1 | 6,8 Go | ✅ mais prendre la 2.0 |
| 16 | lilcheaty/MiniMax-H3-NVFP4 | H3 au format des RTX 50 | 12,5 Go élagué | ⚠️ marche par décompression, sans gain ; le GGUF Q4 fait la même taille |
| 17 | aptech0081/MiniMax-H3-Acc-LoRAs-ComfyUI | le n° 7 converti pour ComfyUI | 1,7 Go ; 34 Go « intégré » | ✅ les LoRA ; ❌ la version intégrée |
| 18 | OpenVDN/vdn-minimax-h3 | H3 accéléré par attention hybride (recherche) | 87 Go | ❌ |
| 19 | realrebelai/FastH3-V2_GGUFs | le n° 6 en GGUF, + encodeur de texte en GGUF | Q4_K_M 19,8 Go ; encodeur Q2_K 8,5 Go | ⚠️ modèle non élagué : RAM pleine ; **l'encodeur Q2_K est utile** (§3) |
| 20 | vpakarinen/asmr-trigger-audio-h3-lora | LoRA ASMR (chuchotements) | 0,16 Go | ✅ avec H3, hors sujet |
| 21 | vpakarinen/natural-face-speech-h3-lora | LoRA visages qui parlent (anglais) | 0,3 Go | ✅ avec H3, pour un personnage qui parle |
| 22 | Wan-AI/Wan2.2-TI2V-5B | Wan 5B, déjà installé | 10 Go | ✅ jugé pas convaincant le 21/09 |
| 23 | NicoLab28/ClipProj-MiniMax-H3 | remplace l'encodeur 32B de H3 par un Qwen3-VL 4B ou 8B | 26 Mo à 0,6 Go + l'encodeur | ✅ **la clé des 8 Go** (le 8B est déjà installé) |
| 24 | siraxe/H3_slider_experiments | LoRA curseurs (détail, vitesse, brouillard) | 0,15 Go | ✅ avec H3 |
| 25 | zai-org/CogVideoX-2b | modèle de 2024, 720 × 480 | 3,4 Go + T5 | ✅ dépassé |
| 26 | Wan-AI/Wan2.2-T2V-A14B | Wan 14B texte → vidéo | GGUF Q4 ≈ 9,7 Go × 2 | ✅ comme l'image → vidéo actuel |
| 27 | Lightricks/LTX-2.5-Diffusers | LTX-2.5 au format diffusers | 174 Go | ❌ tel quel ; ⚠️ en GGUF (Abiray, Q4_K_M 15,7 Go) = plan B |
| 28 | unsloth/Wan2.2-TI2V-5B-GGUF | Wan 5B en GGUF | 1,9 à 5,4 Go | ✅ tient entier dans la carte, faible |
| 29 | Jojocodex/minimax-h3-spatial-physics-lora | LoRA physique des objets (chocs, empilements, chutes) | 0,16 Go | ✅ avec H3, à essayer sur les chantiers |
| 30 | shamanic/minimax-h3-equi360-lora | LoRA vidéo 360° | 0,13 Go | ✅ avec H3, hors sujet |

## 5. Page 1 « image-texte → texte », modèle par modèle

Usages possibles dans le pipeline : contrôle vision des images et des clips, brief de mouvement, prompts ; relève de
Gemini quand son quota tombe. Déjà dans LM Studio : Qwen3.5-35B-A3B, Qwen3.6-27B, un Qwen3.8-27B non censuré, deux
Gemma 4 12B ; dans Ollama : qwen3-coder.

| # | Modèle | Ce que c'est | Taille | Verdict |
|---|---|---|---|---|
| 1 | XingChen-AGI/TeleOCR | lecture de documents (OCR) | 1,4B | ✅ inutile ici |
| 2 | XiaomiMiMo/MiMo-V2.6-Distill-Qwen-9B | agent et code sur Qwen3.5-9B, avec vision | Q4_K_M 5,8 Go | ✅ entier dans la carte |
| 3 | TaichuAI/ZDTaichu5.0-9B | vision générale, raisonnement spatial | ≈ 6 Go en Q4 (GGUF officiel) | ✅ entier ; **candidat pour le contrôle vision** |
| 4 | Qwen/Qwen3.8-27B | le plus fort de la page qui tourne | UD-Q4_K_M 16,5 Go ; UD-IQ3_XXS 10,9 Go | ⚠️ partagé carte / RAM, lent ; **meilleure qualité possible** |
| 5 | ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF | le n° 4 en quantification non uniforme | IQ3_XXS 10,1 Go | ⚠️ plus léger que Q4, à comparer |
| 6 | apple/LensVLM-9B | lecture de pages de texte compressées en image | 9,4B ; GGUF chez bartowski | ✅ hors sujet |
| 7 | deepseek-ai/DeepSeek-V4.1-Flash | | 763B | ❌ |
| 8 | Qwen/Qwen3.8-Flash-Next | | 180B | ❌ |
| 9 | DavidAU/Qwen3.8-27B-TURBO-Fable-…-GGUF | fusion non censurée du n° 4 | 27B | ⚠️ comme le n° 4 |
| 10 | ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF | | 177B | ❌ |
| 11 | HauhauCS/Qwen3.8-27B-Uncensored-…-GGUF | le n° 4 non censuré | 27B | ⚠️ |
| 12 | bottlecapai/ThinkingCap-Qwen3.8-27B | le n° 4 réglé pour raisonner | 55 Go en bf16 ; GGUF publié | ⚠️ en GGUF |
| 13 | bartowski/MiMo-V2.6-Distill-Qwen-9B-GGUF | le n° 2 en GGUF, vision comprise | 5,8 Go + 0,9 Go | ✅ |
| 14 | ukisai/Swift-1.5-Qwen3.8-27B-GGUF | le n° 4 qui réfléchit ≈ 2 fois moins longtemps (58 % de jetons de réflexion en moins selon l'auteur) | 27B | ⚠️ un peu moins lent que le n° 4 |
| 15 | ukisai/Swift-Qwen3.8-27B-GGUF | version 1 du n° 14 | 27B | ⚠️ |
| 16 | ukisai/Swift-Qwen3.8-27b | le n° 15 en bf16 | 55 Go | ❌ tel quel, prendre le GGUF |
| 17 | DavidAU/Qwen3.5-9B-The-Defiant-Fable-…-GGUF | 9B non censuré | 9B | ✅ |
| 18 | agentionai/Qwen3.8-27B-AP-GGUF | variante du n° 4 | 27B | ⚠️ |
| 19 | huihui-ai/Huihui-Qwen3.8-27B-abliterated-GGUF | le n° 4 sans refus | 27B | ⚠️ |
| 20 | zai-org/GLM-5.3-Flash | | 321B | ❌ |
| 21 | moonshotai/Kimi-K3 | | 2 800B | ❌ |
| 22 | ukisai/Swift-1.5-Qwen3.8-27b | le n° 14 en bf16 | 55 Go | ❌ tel quel, prendre le GGUF |
| 23 | ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-Coder-GGUF | | 117B | ❌ |
| 24 | jinaai/jina-ocr-v1 | OCR | 3,4B | ✅ inutile ici |
| 25 | orcarouter/Qwen3.8-27B-Uncensored-GGUF | le n° 4 non censuré | 27B | ⚠️ |
| 26 | unsloth/Qwen3.8-Flash-Next-GGUF | | 177B | ❌ |
| 27 | Accio-Lab/occamy-1.0 | agent de travail sur Qwen3.6-35B-A3B (MoE, 3B actifs) | Q4_K_M 21,2 Go | ✅ experts en RAM, rapide (même famille que le Qwen3.5-35B-A3B installé) |
| 28 | Jackrong/Qwopus3.8-27B-Flash-V2-GGUF | le n° 4 réentraîné par la communauté | Q4_K_M 16,8 Go | ⚠️ |
| 29 | google/gemma-4-31B-it | Gemma 4 31B | Q4_K_M 18,3 Go + 2,3 Go de vision | ⚠️ plus lourd que Qwen 27B |
| 30 | badtheorylabs/Tinfield-1 | agent terminal | 180B | ❌ |

## 6. Suite proposée

1. Laisser l'autre session finir H3, premier clip en 480 × 832 mesuré (temps, VRAM, RAM). Si la RAM sature :
   ClipProj avec le Qwen3-VL-8B déjà installé, ou encodeur Q2_K.
2. Mêmes images de storyboard : H3 élagué, H3 Singularity et Wan 2.2 actuel, puis SeedVR2 + RIFE, côte à côte.
3. Vision locale : ZDTaichu5.0-9B contre Qwen3.8-27B sur une vingtaine d'images de storyboards déjà jugées.

## 7. Comparatif chiffré des moteurs (28/09)

30 s de vidéo = 8 clips de 4 s ; semaine = 21 Shorts. Mesures tirées de l'historique de ComfyUI (`/history`) :
Wan 14B mixte = 27 clips le 26/09 (9,9 à 10,4 min pour 81 images, 7,8-7,9 min pour 65 images). Un clip de 4 s coûte
≈ 0,78 fois un clip de 5 s (rapport mesuré sur le mixte, appliqué aux autres). Wan 14B consomme ≈ 0,9 min par calcul
complet du modèle (mixte = 10 calculs, 4 passes = 4, 20 passes avec CFG = 40), d'où l'estimation des 20 passes.

| Moteur (réglage) | Qualité (Elo) | Image | Son | Clip de 4 s | 30 s de vidéo | Semaine | Origine du chiffre |
|---|---|---|---|---|---|---|---|
| **Wan 2.2 14B mixte 8 passes (actuel)** | 1107 | 480 × 832, 16 i/s | non | **7,8 min** | **≈ 1 h** | ≈ 22 h | mesuré ici (27 clips) |
| Wan 2.2 14B 4 passes | 1107 | 480 × 832, 16 i/s | non | ≈ 3,7 min | ≈ 30 min | ≈ 10 h | mesuré ici le 25/09 (6 clips de 5 s en 29 min) |
| Wan 2.2 14B 20 passes | 1107 | 480 × 832, 16 i/s | non | ≈ 29 min | ≈ 3 h 50 | ≈ 80 h | estimé d'après les mesures |
| Wan 2.2 5B | 992 | 480 × 832, 24 i/s | non | ≈ 2,9 min | ≈ 23 min | ≈ 8 h | mesuré ici le 21/09 (222 s pour 5 s) |
| LTX-Video 2B distillé | < 1031 (non classé) | 576 × 1024, 24 i/s | non | ≈ 25 s | ≈ 3,5 min | ≈ 1 h 15 | mesuré ici le 25/09 (30-32 s pour 5 s) |
| **MiniMax H3 élagué Q4, Turbo 8 passes** | 1357 | 480 × 832, 24 i/s | oui | ≈ 2,5-4 min | ≈ 20-32 min | ≈ 7-11 h | estimé |
| MiniMax H3 élagué Q4, 20 passes | 1357 | 480 × 832, 24 i/s | oui | ≈ 7-8 min | ≈ 1 h | ≈ 21 h | retours de la communauté (RTX 3070 + 32 Go) |
| LTX-2.5 distillé GGUF Q4 | 1214 | ≈ 480 × 832, 24 i/s | oui | ≈ 4-6 min | ≈ 32-48 min | ≈ 11-17 h | estimé (docs/14 §4) |
| Gemini Omni (en ligne, bouton ✦) | 1369 | 720 × 1280, 10 s | oui | 3-4 min, parfois 20 et plus | ≈ 30 min | quota : ≈ 1 Short par fenêtre de 5 h | constaté le 26/09 (docs/17) |

Elo : image → vidéo sans son, Artificial Analysis, au réglage officiel de chaque modèle ; les réglages accélérés
(4 passes, mixte, Turbo, élagage, Q4) sont sans doute un peu en dessous.

| Moteur | Mémoire | Disque | État le 28/09 | Défauts vus |
|---|---|---|---|---|
| Wan 2.2 14B | 7,7 Go de VRAM au maximum, stable | installé | en service | 4 passes : personnes et fantômes inventés ; moins en mixte |
| Wan 2.2 5B | 7,6 Go de VRAM | installé | installé | géométrie qui fond, plan figé |
| LTX-Video 2B | léger | installé | installé | image plus douce ; suit la caméra sans inventer de personnes (2 scènes) |
| MiniMax H3 élagué | RAM ≈ 31 Go sur 32 avec l'encodeur nvfp4 (≈ 15 Go avec ClipProj) | installé le 28/09 au matin (≈ 33 Go) | premier essai (480 × 832 × 124, 8 passes) arrêté à la main à 09 h 32 pendant le calcul : fichiers chargés, pas encore de clip | — |
| LTX-2.5 | RAM ≈ 31 Go | ≈ 33 Go à télécharger | impossible sans faire de la place : 17 Go libres sur C: | — |
| Gemini Omni | rien en local | — | branché | ≈ 8 clips puis ≈ 5 h d'attente |

HunyuanVideo 1.5 (8,3B, Elo 1134) n'a jamais été mesuré sur 8 Go : plus léger que H3, mais nettement moins bon.

MiniMax H3 en 20 passes (réglage officiel, sans LoRA Turbo) est proposé dans Réglages depuis le 28/09 :
`minimax_h3_i2v_20step` et `minimax_h3_flf2v_20step`. Premier essai de H3 le 28/09 : RAM saturée (le cache de
ComfyUI garde l'encodeur 32B pendant la génération) ; ComfyUI relancé en `--cache-none` par la session « Leviers ».

## 8. Comparatif des générateurs d'images (28/09)

Un Short = 6 scènes × 2 images candidates = 12 images ; semaine = 21 Shorts = 252 images. Temps en 768 × 1344,
mesurés dans l'historique de ComfyUI depuis le 25/09 (médiane) ; les autres sont des estimations.

| Modèle | Qualité (Elo) | Poids à charger | Par image | Storyboard d'un Short | Semaine | État |
|---|---|---|---|---|---|---|
| **Qwen-Image 2.1 (réglage actuel)** | **1035, n° 1 ouvert** | 7,3 Go int8 + encodeur 9,4 Go | **26 s** (13 mesurées) | ≈ 5 min | ≈ 1 h 50 | installé |
| Ideogram 4.0 | 1010 | 2 modèles int8 de 9,6 Go + encodeur 10,6 Go | ≈ 1-3 min (estimé) | ≈ 12-36 min | ≈ 4-13 h | 30 Go à télécharger (17 libres), RAM au bord |
| FLUX.2 dev (32B) | 1000 | GGUF Q4 ≈ 19 Go + encodeur Mistral 12-18 Go | ≈ 3-8 min (estimé) | ≈ 36-96 min | ≈ 13-34 h | trop lourd (RAM et disque) |
| Qwen-Image 2512 (20B) | 998 | GGUF Q4 ≈ 13 Go | ≈ 40-70 s (estimé) | ≈ 8-14 min | ≈ 3-5 h | workflow prêt, modèle absent ; moins bon et plus lourd que 2.1 |
| Ming-Image 0.1 Design (6,2B) | 996 | — | — | — | — | pas de prise en charge dans ComfyUI |
| Cosmos3-Super / HunyuanImage 3.0 | 995 / 963 | 65B / 83B | — | — | — | impossibles |
| HiDream-O1 (8,8B) | 979 | 8,1 Go fp8 + encodeur Gemma 4 E4B | ≈ 40-90 s (estimé) | ≈ 8-18 min | ≈ 3-6 h | faisable, sans intérêt face à 2.1 |
| Z-Image Turbo | 940 | 6,2 Go int8 + encodeur 5,6 Go | **9 s** (55 mesurées) | ≈ 2 min | ≈ 40 min | installé ; le plus rapide |
| FLUX.2 klein 9B | 940 | GGUF Q8 10 Go | ≈ 10-20 s (estimé) | ≈ 2-4 min | ≈ 1 h | faisable, = Z-Image |
| ERNIE Image Turbo (8B) | 923 | 16 Go (GGUF possible) | ≈ 15-30 s (estimé) | ≈ 3-6 min | ≈ 1-2 h | faisable, moins bon |
| Flux.1 schnell | 802 | GGUF Q8 12,7 Go + T5 5,2 Go | 45 s (7 mesurées) | ≈ 9 min | ≈ 3 h | installé ; le plus lent et le moins bon des installés |

Elo : Artificial Analysis, texte → image, modèles ouverts, relevé le 28/09. Retouche (même source) : **Qwen-Image 2.1
= 1071, n° 1**, devant Qwen-Image-Edit-2511 (1023, celui des formats visuels : 95 s médianes en 4 passes, 117 mesurées ;
≈ 13 min en 40 passes) et FLUX.2 klein 9B (1014). Qwen-Image 2.1 sait retoucher (gabarit ComfyUI
`image_qwen_image_2_1_image_edit`) : piste pour remplacer 2511 sans rien télécharger.

## Sources

- Listes Hugging Face (API, tri « trending », 28/09/2026) : [texte → vidéo](https://huggingface.co/models?pipeline_tag=text-to-video&sort=trending),
  [image-texte → texte](https://huggingface.co/models?pipeline_tag=image-text-to-text&sort=trending),
  [image → vidéo](https://huggingface.co/models?pipeline_tag=image-to-video&sort=trending) ; tailles lues dans l'arborescence de chaque dépôt.
- Classements : [image → vidéo, modèles ouverts](https://artificialanalysis.ai/video/leaderboard/image-to-video/open-weights),
  [texte → vidéo, modèles ouverts](https://artificialanalysis.ai/video/leaderboard/text-to-video/open-weights) (onglets « With Audio » et « No Audio »).
- H3 sur petites cartes : [MiniMax H3 dans ComfyUI (Comfy.org)](https://blog.comfy.org/p/minimax-h3-day-0-support-in-comfyui),
  [VRAM par palier (minimaxh3.app)](https://minimaxh3.app/posts/minimax-h3-vram-requirements),
  [déploiement local (HelloGen)](https://hellogen.ai/blog/minimax-h3-local-deployment/),
  [GGUF élagués](https://huggingface.co/Abiray/MiniMax-H3-Pruned-GGUF), [Singularity GGUF](https://huggingface.co/Abiray/MiniMax-H3-Singularity-GGUF),
  [ClipProj](https://huggingface.co/NicoLab28/ClipProj-MiniMax-H3), [encodeur GGUF](https://huggingface.co/realrebelai/FastH3-V2_GGUFs),
  [LoRA Turbo lightx2v](https://huggingface.co/lightx2v/Minimax-h3-Turbo), [fichiers Comfy-Org](https://huggingface.co/Comfy-Org/MiniMax-H3).
- LTX-2.5 : [fichiers officiels](https://huggingface.co/Lightricks/LTX-2.5), [GGUF distillés](https://huggingface.co/Abiray/LTX-2.5-Distilled-GGUF).
- Code local : ComfyUI 0.37.2 (`comfy/ldm/minimax`, `comfy_extras/nodes_minimax_h3.py`, `comfy/quant_ops.py`),
  comfy_kitchen 0.2.35 (`tensor/base.py`), ComfyUI-GGUF (`loader.py`, `nodes.py`).
