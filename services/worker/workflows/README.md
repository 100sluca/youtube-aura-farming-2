# Workflows ComfyUI

Un fichier par fournisseur, au **format API** de ComfyUI (`Save (API format)`), nommé
`<nom>.json`. Le choix se fait dans le dashboard, **Réglages → Modèles de génération** (ou
`yt2 settings generation --image <nom> --video <nom>`), parmi les modèles listés dans `catalog.json` (libellé, détail,
licence, publiable) ; `VIDEO_PROVIDER=comfy_<nom>` et `COMFY_IMAGE_WORKFLOW=<nom>` du `.env` ne servent plus que de
repli. Chaque production garde les modèles avec lesquels elle a été faite (docs/14 §6).

## Ce qui tourne aujourd'hui (modèle installé le 2026-09-21 : Wan 2.2 TI2V-5B fp16)

| Fichier | Rôle | Mesuré sur la RTX 3070 (8 Go) |
|---|---|---|
| `wan22_5b_t2i.json` | **image de storyboard** : le 5B en une seule image (`length = 1`), 768×1344, 20 passes | 30 s, image nette et cohérente |
| `wan22_5b_i2v.json` | **défaut** : anime l'image de storyboard, 24 i/s, 121 images (5 s), 20 passes, CFG 5, uni_pc | 480×832 : 3 min 42 s, 7,6 Go de VRAM ; 704×1280 : arrêté après 55 min, la carte déborde (docs/12 §5) |
| `wan22_5b_t2v.json` | texte → vidéo, même modèle ; repli pour une scène sans image retenue | idem |

Le 5B est entraîné en 720p (`VIDEO_SIZE=704x1280`, multiples de 32) mais le fp16 ne tient pas sur 8 Go à
cette taille : laisser `VIDEO_SIZE` vide sur la RTX 3070. Le négatif officiel Wan (en chinois,
`WAN_NEGATIVE` dans `providers/video.py`) est appliqué à tout workflow dont le nom contient « wan ».

## La voie « meilleure qualité sur 8 Go » (à télécharger, `scripts/download_models.ps1`)

| Fichier | Rôle | Mémoire graphique |
|---|---|---|
| `zimage_turbo.json` | images du storyboard, **Z-Image Turbo** (6B, Apache 2.0), 8 passes, CFG 1, 768×1344 ; version int8 + encodeur fp8 (ComfyUI 0.37+) | 6,2 Go : tient dans la carte ; ≈ 15-30 s par image |
| `wan22_i2v_4step.json` | anime l'image, **Wan 2.2 I2V 14B** en GGUF Q4_K_M + LoRA lightx2v **4 passes sans CFG**, 480×832, 81 images (5 s à 16 i/s) | 8 Go avec déchargement (32 Go de RAM utiles) ; ≈ 2-4 min par clip |
| `wan22_i2v_20step.json` | **qualité maximale** : mêmes modèles sans la LoRA, 20 passes avec CFG 3,5, shift 8 (réglages du gabarit officiel ComfyUI de juillet 2025) ; mouvement plus ample et plus fidèle au prompt | 8 Go ; ≈ 10 × plus long que 4 passes (≈ 15-25 min par clip, estimation) |
| `wan22_t2v_4step.json` | texte → vidéo, même recette ; repli | 8 Go |
| `wan22_i2v_4step_fp8.json` | variante fp8 d'OpenMontage | 16 Go et plus (Kaggle) |
| `ltxv_2b_i2v.json` | anime l'image avec **LTX-Video 2B 0.9.8 distillé** en fp8 (licence LTX Open Weights : gratuite sous 10 M$ de chiffre d'affaires) : 8 passes, CFG 1, pas de débruitage du réglage officiel (`ManualSigmas`), 576 × 1024 à 24 i/s ; nœuds natifs de ComfyUI, encodeur T5 de Flux ; à l'essai face à Wan (`download_models.ps1 -Ltx`) | 4,5 Go : tient entier dans la carte |
| `flux1_schnell_gguf.json` | images **Flux.1 schnell** (Apache 2.0) en GGUF Q8_0, 4 passes, CFG 1, encodeur T5 fp8 « scaled » + CLIP-L, VAE `ae.safetensors` (celui de Z-Image) ; alternative à Z-Image, installée le 25/09 (`download_models.ps1 -Flux`) | 12,7 Go + 5,2 Go, déchargés en RAM ; 45 s pour la première image, chargement compris (mesuré le 25/09) |
| `qwen_image_21.json` | images **Qwen-Image 2.1** en int8 (gabarit officiel ComfyUI : 25 passes, CFG 1), `COMFY_IMAGE_WORKFLOW=qwen_image_21` ; **tests et évaluation seulement** : licence de recherche (docs/14 §2.1) ; ComfyUI 0.37 ou plus | 7,3 Go + encodeur 9,4 Go, déchargés en RAM |

Pourquoi c'est mieux que le 5B : le 14B tient la géométrie (une porte qui s'ouvre reste une porte) et
suit mieux le prompt de mouvement ; la LoRA 4 passes rend le 14B **plus rapide** que le 5B en 20 passes.
Nœud personnalisé requis : **ComfyUI-GGUF** (city96), via ComfyUI Manager. Le 14B utilise le VAE Wan 2.1
(`wan_2.1_vae.safetensors`), pas `wan2.2_vae`.

Inspirés des workflows d'OpenMontage (`tools/_comfyui/workflows`, AGPL-3.0), réécrits : modèles GGUF
pour 8 Go, format vertical, et latent vidéo `EmptyHunyuanLatentVideo` pour le texte → vidéo (le
workflow d'origine utilise `EmptyLatentImage` × 81, qui produit 81 images indépendantes).

## Formats visuels : chantiers en accéléré, visites de luxe (docs/15)

Choisis par la recette de la série (`series.recipe`), pas par le catalogue : ils complètent le modèle vidéo et
le modèle d'image des réglages.

| Fichier | Rôle | Modèles |
|---|---|---|
| `wan22_flf2v_4step.json`, `wan22_flf2v_20step.json` | clip **première + dernière image** (`WanFirstLastFrameToVideo`, nœud natif) : l'étape d'un chantier se construit entre deux images clés ; variante prise d'après le modèle vidéo de la production (`i2v` → `flf2v`, même nombre de passes) | ceux de Wan 2.2 I2V 14B, déjà installés |
| `wan22_i2v_hybrid.json`, `wan22_flf2v_hybrid.json` | **mixte 8 passes** : 2 passes haut bruit sans LoRA avec CFG 3,5 (le négatif agit : pas de passants inventés), puis 2 passes haut bruit et 4 bas bruit avec la LoRA, shift 8 ; imposé aux visites (`RecipeSpec.video_variant`, docs/15 §10), proposé dans le catalogue | ≈ 10 min par clip de 5 s (2 fois les 4 passes) |
| `qwen_image_edit_2511_4step.json` | **retouche** d'une image clé (étape suivante, même cadre) : Qwen-Image-Edit-2511 GGUF Q5_K_M + LoRA Lightning, 4 passes, CFG 1 ; image recadrée en 768 × 1344 exactement ; **défaut**, ≈ 1 min 30 par image | installés le 25/09 |
| `qwen_image_edit_2511.json` | même retouche en 40 passes, CFG 4 (gabarit officiel) : 13 min par image sur la RTX 3070, RAM saturée (le modèle et son encodeur font ≈ 24 Go) | idem |
| `zimage_img2img.json` | repli de la retouche : Z-Image en image → image (force 0,62) ; garde la composition, mais le décor bouge d'une étape à l'autre | installés |
| `audio/ace_step_15_music.json` | **musique** instrumentale ACE-Step 1.5 (`yt2 music generate`) : 75 s de musique en ≈ 40 s | installé le 25/09 |
| `audio/stable_audio_3_sfx.json` | **bruitages** Stable Audio 3 small-sfx, 8 passes (`yt2 sfx generate`) : ≈ 6 s par son | installé le 25/09 |

## Essais du 28/09 : MiniMax H3, Qwen-Image 2512, agrandissement + interpolation (docs/20)

| Fichier | Rôle | Modèles (`download_models.ps1`) |
|---|---|---|
| `minimax_h3_i2v.json`, `minimax_h3_flf2v.json` | anime l'image avec **MiniMax H3** élagué (n° 1 des modèles vidéo ouverts, licence de test) : GGUF Q4_K_M + LoRA 8 passes, `res_multistep`, sans CFG (le nœud `NEGATIVE` est là pour la convention, il ne sert pas) ; 24 i/s, toujours 124 images (5,2 s : H3 a appris de 124 à 362) ; le prompt passe par un `PrimitiveStringMultiline` relié à `MiniMaxH3ImageToVideo`, qui porte aussi `SIZE` ; variante première + dernière image choisie comme pour Wan (`i2v` → `flf2v`) ; son généré, ignoré au montage | `-H3`, ≈ 32,6 Go |
| `qwen_image_2512.json` | images **Qwen-Image 2512** (Apache 2.0) : GGUF Q4_K_M + LoRA Lightning 8 passes, CFG 1, shift 3,1 (gabarit officiel) ; encodeur et VAE de Qwen-Image-Edit-2511 | `-Qwen2512`, ≈ 14,1 Go (pas encore téléchargé le 28/09 : place disque) |
| `post/seedvr2_rife.json` | **post-traitement** d'un clip : SeedVR2 3B int8 ×2 (une passe, correction de couleur `lab`, VAE en tuiles de 16 images pour tenir en 8 Go) puis RIFE 4.26 ×2 ; titres `VIDEO` (LoadVideo), `SEED`, `FPS` (CreateVideo : i/s de la source × 2), `OUTPUT` ; hors convention image/vidéo, comme `audio/` | `-Post`, ≈ 4 Go |

Titres supplémentaires : `IMAGE_END` (LoadImage de la dernière image), et pour l'audio `PROMPT` sur l'encodeur
ACE-Step (entrées `tags`, `duration`, `bpm`, `keyscale`, `seed`) ou un CLIPTextEncode, `SIZE` sur le latent audio
(`seconds`). Les workflows audio sont dans `audio/` : ils ne suivent pas la convention image/vidéo.

## Titres de nœuds (obligatoires)

Le worker remplace les entrées des nœuds dont le titre (`_meta.title`) vaut :

| Titre | Entrées remplacées |
|---|---|
| `PROMPT` | `text` (prompt positif, style ajouté) |
| `NEGATIVE` | `text` |
| `SEED` | `noise_seed` (KSamplerAdvanced) ou `seed` (KSampler) |
| `SIZE` | `width`, `height`, `length` (nombre d'images : 4k + 1 pour le 5B, 8k + 1 pour le 14B) |
| `IMAGE` | `image` (LoadImage) — sa présence fait du workflow un **image → vidéo** |
| `OUTPUT` | `filename_prefix` ; c'est le nœud dont la sortie est téléchargée |

Pour ajouter un workflow : le construire dans ComfyUI, renommer ces nœuds (clic droit → *Title*),
exporter en format API dans ce dossier. `tests/test_workflows.py` vérifie les titres et les liens.
Résolution : `providers/video.py` choisit la valeur native d'après le nom (`ltx`, `minimax_h3`, `5b`, sinon 14B) ;
`VIDEO_SIZE` la force.

## Modèles à télécharger

`scripts/download_models.ps1` télécharge tout ce qui suit (≈ 35 Go) ; à lancer une fois de la place faite
sur C: et ComfyUI installé dans `C:\ComfyUI_windows_portable` (chemin attendu par le lanceur).

| Fichier | Dossier ComfyUI | Source |
|---|---|---|
| `Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf`, `Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf` | `models/unet/` | huggingface.co/QuantStack/Wan2.2-I2V-A14B-GGUF |
| `Wan2.2-T2V-A14B-HighNoise-Q4_K_M.gguf`, `Wan2.2-T2V-A14B-LowNoise-Q4_K_M.gguf` (facultatif, repli texte → vidéo) | `models/unet/` | huggingface.co/QuantStack/Wan2.2-T2V-A14B-GGUF |
| `wan2.2_i2v_lightx2v_4steps_lora_v1_{high,low}_noise.safetensors` | `models/loras/` | huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged (split_files/loras) |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` (déjà présent) | `models/text_encoders/` | huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged |
| `wan_2.1_vae.safetensors` | `models/vae/` | huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged (split_files/vae) |
| `z_image_turbo_int8_convrot.safetensors`, `qwen_3_4b_fp8_mixed.safetensors`, `ae.safetensors` | `models/diffusion_models/`, `models/text_encoders/`, `models/vae/` | huggingface.co/Comfy-Org/z_image_turbo |
| `flux1-schnell-Q8_0.gguf`, `t5xxl_fp8_e4m3fn_scaled.safetensors`, `clip_l.safetensors` (alternative, option `-Flux`) | `models/unet/`, `models/text_encoders/` | city96/FLUX.1-schnell-gguf, comfyanonymous/flux_text_encoders |
| `qwen_image_2.1_int8_convrot.safetensors`, `qwen3vl_8b_int8_convrot.safetensors`, `qwen_image_2.1_vae_bf16.safetensors` (test, hors script) | `models/diffusion_models/`, `models/text_encoders/`, `models/vae/` | huggingface.co/Comfy-Org/Qwen-Image-2.1 (fichiers à la racine du dépôt, pas dans `split_files/`) |

Les noms exacts des fichiers GGUF varient selon le dépôt et la quantification : si le vôtre diffère,
modifiez `unet_name` dans le JSON. Sur 8 Go, si Q4_K_M sature la mémoire, prendre Q3_K_M.
