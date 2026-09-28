# 20 · Qualité vidéo : les leviers sur la RTX 3070, les nouveaux modèles, les passes et les prompts

> 2026-09-26, question de Luca : quels leviers pour de meilleures vidéos avec les modèles déjà sur le PC ? Existe-t-il
> des modèles plus performants qui tournent sur cette machine sans y passer des heures ? Plusieurs passes sur les
> images, un meilleur moteur d'image ou de meilleurs prompts entre l'image et la vidéo donneraient-ils de meilleures
> vidéos ? Machine : RTX 3070 8 Go, 32 Go de RAM, 55 Go libres sur C: le 26/09. Complète `14-modeles-de-generation-et-gratuite.md`
> (choix des moteurs) et `15-formats-timelapse-et-visites.md` §10 (cohérence des formats visuels). Règle de
> gratuité inchangée (ADR-007) : tout ce qui suit est local, sous licence Apache 2.0 ou MIT.

## En bref

**Le moteur n'est pas le problème principal : ce qui dégrade le plus les vidéos, c'est ce qu'il y a autour de Wan.**
Aucun modèle vidéo sorti en 2026 n'est à la fois meilleur que Wan 2.2 14B en image → vidéo, publiable en France et
faisable sur 8 Go. En revanche, ComfyUI 0.37 (installé) sait déjà faire l'interpolation et l'agrandissement IA, et le
prompt de mouvement est aujourd'hui écrit à l'aveugle.

Où la qualité se perd aujourd'hui (code au 26/09) :

| Étape | Ce qui se passe | Effet à l'écran |
|---|---|---|
| Résolution | Wan génère en 480 × 832 ; le montage agrandit ×2,3 en bicubique (`scale` de FFmpeg, `assemble.py`) | image molle sur un téléphone |
| Fluidité | Wan sort 16 i/s ; formats narrés : images dupliquées pour passer à 30 i/s ; formats visuels : `minterpolate` de FFmpeg | saccades ; halos et déchirures dès que ça bouge vite |
| Négatif | ignoré en 4 passes (CFG 1) ; le mixte le réactive au prix de ≈ 10 min par clip | passants et fantômes inventés |
| Prompt de mouvement | écrit par le LLM du script **avant** que l'image existe ; le style photo (objectif, profondeur de champ, « static wide shot ») y est collé (`styled()` dans `providers/video.py`) | la caméra va chercher ce qui n'est pas dans l'image : Wan l'invente |
| Image de départ | Z-Image Turbo, 2 candidates, contrôle vision pour les formats visuels | composition parfois fausse sur les scènes complexes (l'escalier dans la bibliothèque fermée, docs/14) |

Les leviers, du meilleur rapport gain / effort au moins bon :

| # | Levier | Gain attendu | Temps en plus | À télécharger |
|---|---|---|---|---|
| 1 | **Interpolation IA** 16 → 32 i/s (RIFE 4.26 ou FILM, nœuds natifs) | plus de saccades, ralentis du montage fluides | secondes (RIFE) à ≈ 1 min (FILM) par clip | 23 à 69 Mo |
| 2 | **Agrandissement IA SeedVR2 3B** (nœuds natifs, gabarit officiel) : 480 × 832 → 960 × 1664 | vrai détail au lieu du flou bicubique | à mesurer, quelques minutes par clip | 4 Go |
| 3 | **Prompt de mouvement écrit en regardant l'image retenue** (Gemini vision, déjà configuré pour le contrôle) | caméra et mouvement cohérents avec le cadre, moins d'inventions | un appel LLM par scène | rien |
| 4 | **Image de fin** (Qwen-Image-Edit) + première et dernière image pour chaque scène qui révèle quelque chose | Wan interpole au lieu d'inventer : le plus gros gain de cohérence | ≈ 1 min de retouche par scène concernée | rien |
| 5 | **Négatif actif en 4 passes (NAG)** | l'effet du mixte (pas de passants) pour moitié moins de temps, à vérifier | ≈ +10-30 % sur 4 passes (estimation) | nœuds KJNodes |
| 6 | **Wan 2.2 distillé 720p d'avril 2026** en GGUF Q4_K_M, à la place de base + LoRA v1 | détails et textures plus fins (annoncé), même taille, même vitesse | 0 | 19,3 Go |
| 7 | **Qwen-Image-2512** pour les images de départ, en concurrence avec Z-Image | respect de la scène : 998 contre 940 aux votes à l'aveugle | ≈ 1-2 min par image au lieu de 17 s (estimation) | 15,9 Go |
| 8 | **Deux tirages par clip**, le contrôle vision garde le meilleur (existe pour les formats visuels) | on écarte les ratés sans relecture | ×2 sur le GPU | rien |
| 9 | **Gemini Omni pour les plans clés** (accroche, révélation), Wan pour le reste | le n° 1 du classement image → vidéo sur les 2 plans qui comptent | quota Google (≈ 9 clips par fenêtre de 5 h) | rien |

Les leviers 1 et 2 ensemble coûtent ≈ 4 Go et quelques minutes par clip : Wan 4 passes + post-traitement (≈ 8 à 11 min
par clip, estimation) devrait être plus net que Wan 20 passes brut (25-35 min), qui reste plus régulier dans le
mouvement. À mesurer sur une production existante avant de toucher au pipeline (§5).

## 1. Ce qu'on laisse sur la table avec les modèles installés

### 1.1 Interpolation 16 → 32 images par seconde

ComfyUI 0.37.2 a des nœuds natifs `FrameInterpolationModelLoader` + `FrameInterpolate` (modèles RIFE et FILM, gabarit
officiel `utility_video_frame_interpolation`). Modèles à poser dans `ComfyUI/models/frame_interpolation` depuis
`Comfy-Org/frame_interpolation` : `rife_v4.26.safetensors` (23 Mo, RIFE, MIT) ou `film_net_fp16.safetensors` (69 Mo,
FILM de Google, Apache 2.0, plus lent, meilleur sur les grands mouvements).

- Wan sort 81 images à 16 i/s ; ×2 donne 161 images à 32 i/s, que le montage ramène à 30 i/s (une image sur seize
  retirée, au lieu d'images montrées tantôt une fois, tantôt deux comme aujourd'hui). Variante : ×4 puis 60 i/s.
- Remplace la duplication d'images (formats narrés) et `minterpolate` (formats visuels) ; les ralentis jusqu'à ×1,35
  (`MAX_SLOWDOWN`) deviennent fluides. Les traînées du time-lapse (`tmix`) restent au montage.
- L'interpolation lisse le mouvement ; elle ne corrige ni une géométrie qui fond ni un objet inventé.

### 1.2 Agrandissement SeedVR2 : du vrai détail en 1080p

SeedVR2 (ByteDance, Apache 2.0) est un modèle de restauration vidéo « en une passe » : il agrandit en ajoutant du détail
cohérent d'une image à l'autre. ComfyUI 0.37.2 l'intègre en natif (`SeedVR2Preprocess`, `SeedVR2Conditioning`,
`SeedVR2TemporalChunk` / `SeedVR2TemporalMerge` pour découper la vidéo selon la VRAM libre, `SeedVR2PostProcessing` pour
corriger les couleurs) avec le gabarit `utility_seedvr2_3b_int8_upscale_video` : ×2, VAE en tuiles de 512, découpage
automatique.

- Fichiers (`Comfy-Org/SeedVR2`) : `seedvr2_3b_int8_convrot.safetensors` (3,46 Go, `diffusion_models`) +
  `seedvr2_ema_vae_fp16.safetensors` (0,5 Go, `vae`). Le 7B int8 (8,3 Go) est trop lourd pour de la vidéo sur 8 Go.
- 480 × 832 → 960 × 1664, puis le montage passe à 1080 × 1920 (×1,13 au lieu de ×2,3).
- Ordre : SeedVR2 sur le clip à 16 i/s (81 images), puis interpolation à la nouvelle taille (peu coûteuse).
- Risques à surveiller : sur 8 Go c'est un usage « communautaire », pas une promesse de l'éditeur ; textures inventées
  ou raccords de tuiles si le chevauchement est trop faible. Garder la correction de couleur `lab`.
- Alternative plus lourde, seulement si SeedVR2 déçoit : repasser le clip dans l'expert basse lumière de Wan en 720p
  (vidéo → vidéo, débruitage 0,3, 2-3 passes avec la LoRA).

### 1.3 Négatif actif en 4 passes : NAG

En 4 passes (CFG 1), le négatif ne sert à rien : Wan fait entrer des gens par les portes (docs/15 §10). Le mixte
(2 passes à CFG 3,5 sans LoRA, puis la LoRA) règle le problème en ≈ 10 min au lieu de 4 min 30. Le NAG (Normalized
Attention Guidance) applique le négatif dans l'attention croisée, donc même à CFG 1.

- Piège vérifié dans le code de ComfyUI 0.37.2 : le nœud natif `NAGuidance` s'accroche à `attn1_output_patch`, que le
  modèle Wan n'appelle pas (`comfy/ldm/wan/model.py`) : **sans effet sur Wan**, et il désactive l'optimisation CFG 1
  (calcul doublé). Pour Wan, il faut le nœud `WanVideoNAG` de ComfyUI-KJNodes (kijai), fait pour les modèles Wan natifs
  avec les LoRA de distillation (`nag_scale` ≈ 11 par défaut).
- Essai : les scènes de visite comparées le 25/09 (4 passes, mixte, 20 passes), en 4 passes + NAG. Si c'est aussi
  propre que le mixte, les visites vont deux fois plus vite.

### 1.4 Wan 2.2 distillé 720p (lightx2v, 12/04/2026)

La LoRA 4 passes installée (`wan2.2_i2v_lightx2v_4steps_lora_v1_*`) est la première version (août 2025). Depuis :
LoRA `…_4step_1022` (oct. 2025) puis, le 12/04/2026, des **modèles distillés complets entraînés sur des vidéos 720p de
haute qualité** (« fine-grained detail rendering and visual texture »), Apache 2.0. Versions GGUF chez jayn7 :
`wan2.2_i2v_A14b_{high,low}_noise_lightx2v_4step_720p_260412-Q4_K_M.gguf`, **9,66 Go chacun, la taille de nos Q4
actuels** : même chargeur (`UnetLoaderGGUF`), on retire les deux nœuds LoRA.

- Garder les modèles de base Q4 : le 20 passes et les 2 premières passes du mixte s'en servent.
- 19,3 Go de disque en plus ; C: avait 55 Go libres le 26/09.
- Le 720p natif devient tentant, mais 720 × 1280 représente ≈ 2,3 fois plus de jetons et ≈ 4 fois plus de calcul
  (attention) : ≈ 20 min par clip en 4 passes (estimation), avec un risque mémoire. À garder pour après SeedVR2.

### 1.5 Ce qui n'aide pas

- Plus de passes sur Z-Image Turbo : il est distillé pour 8 passes, au-delà rien à gagner.
- Wan en Q6 ou Q8 : 24 à 31 Go pour les deux experts, la RAM déborde (docs/14 §3).
- Les caches d'accélération (EasyCache, TeaCache) : ils gagnent du temps en perdant de la qualité, l'inverse de la
  règle de Luca. SageAttention accélérerait presque sans perte, mais son installation sous Windows (triton-windows, roue pour
  torch 2.13 / Python 3.13) est un risque de plantage pour un gain de vitesse seulement.

## 2. Plusieurs passes sur les images, meilleur moteur d'image

**Oui, mais pas pour la netteté.** Wan relit l'image de départ en 480 × 832 : le détail ajouté par une seconde passe
(agrandissement ×2 puis Z-Image en image → image à 0,33, gabarit `utility_z_image_turbo_2k_upscaler`) disparaît
presque entièrement dans la vidéo. Ce que l'image décide vraiment, et que Wan conserve : la composition, ce qui est dans
le cadre, la géométrie, la lumière, l'absence de personnes et de texte. Les passes qui paient :

1. **Un moteur qui respecte mieux la scène.** Classement Artificial Analysis des modèles d'image ouverts (votes à
   l'aveugle, 26/09/2026) :

   | Modèle | Elo | Licence | Sur la 3070 |
   |---|---|---|---|
   | Qwen-Image 2.1 | 1035 | recherche seulement | exclu en production (docs/14) |
   | Ideogram 4.0 (juin 2026, 9,3B) | 1003-1010 | **non commerciale** | exclu |
   | FLUX.2 [dev] | 1000 | non commerciale | exclu |
   | **Qwen-Image-2512** (déc. 2025, 20B) | **998** | **Apache 2.0** | GGUF Q5_K_M 15 Go + LoRA Lightning 8 passes 0,85 Go ; encodeur `qwen_2.5_vl_7b_fp8_scaled` et VAE `qwen_image_vae` **déjà installés** pour Qwen-Image-Edit-2511 |
   | Ming-Image-0.1-Design (sept. 2026, 6B) | 996 | MIT | fait pour le graphisme et le texte, pas la photo |
   | HiDream-O1-Image (mai 2026, 9B) | 979 | MIT | ≈ 10 Go en FP8 : déchargement, lent ; second choix |
   | Z-Image Turbo (actuel) | 940 | Apache 2.0 | 17 s par image |

   Qwen-Image-2512 est le dernier Qwen-Image publiable (le 2.1, qui a respecté le passage secret là où Z-Image s'est
   trompé, docs/14 §3, est un autre modèle) : à comparer sur nos prompts par Réglages → Modèles de génération, puis
   « Refaire avec les réglages actuels ». Si le rendu « photo » de Z-Image reste meilleur, on garde les deux : Qwen-Image-2512 pour
   la composition, puis une passe Z-Image en image → image à 0,25-0,35 (`zimage_img2img.json` existe déjà) pour les
   matières.
2. **Une passe de correction plutôt qu'un nouveau tirage.** Quand le contrôle vision trouve un défaut précis (une
   personne, un texte sur un panneau, une ligne cassée), Qwen-Image-Edit-2511 corrige l'image retenue (« remove the
   person ») au lieu de tout régénérer.
3. **L'image de fin, la passe qui change le plus la vidéo.** Qwen-Image-Edit fabrique l'état de la fin de scène (porte
   ouverte, « même pièce vue un pas plus près »), Wan anime de la première à la dernière image. C'est déjà le principe
   du chantier et des passages de visite (docs/15 §10) ; à étendre aux scènes de révélation des formats narrés
   (`reveal`, `escalation`).
4. **Plus de candidates là où ça compte** : 4 images au lieu de 2 pour l'accroche et la révélation (17 s de plus par
   image avec Z-Image).

## 3. Des prompts meilleurs entre l'image et la vidéo

Aujourd'hui le LLM du script écrit `visual_prompt` et `motion_prompt` en même temps, avant l'image ; au moment du clip,
le style photo est ajouté au mouvement. Or, pour l'image → vidéo, le guide officiel de Wan (Alibaba) dit que l'image
porte déjà le sujet, le décor et le style : le prompt doit décrire **le mouvement et la caméra**, avec vitesse et
direction explicites.

Proposition : un « brief de mouvement » écrit par le modèle de vision (Gemini, déjà branché pour `keyframe_qc.py`) qui
regarde l'image retenue et l'intention de la scène (son `motion_prompt`, son rôle), et répond selon une structure fixe :

1. une phrase d'ancrage sur ce qui est visible (sujet, lieu, lumière) ;
2. **un seul** mouvement de caméra, pris dans une liste fermée (slow push-in, slow pull-back, pan left / right, tilt up
   / down, orbit left / right, static camera), avec la vitesse (« slowly », « steady ») ;
3. ce qui bouge dans la scène (eau, rideau, lumière) et **ce qui reste immobile** (« the walls and furniture stay
   perfectly still ») ;
4. les interdits déjà appris : aucun nom d'appareil de tournage (crane, gimbal, dolly deviennent des objets à l'écran,
   `_no_rig`), aucune personne (« the room stays empty »).

Et un contrôle de faisabilité : si le mouvement demandé va montrer ce qui n'est pas dans le cadre (panoramique vers une
mezzanine absente de l'image), le modèle choisit un autre mouvement ou demande une image de fin (§2.3). Écrit au moment
du storyboard, le brief peut s'afficher sous chaque image dans Création et se corriger avant le ✓.

À côté : séparer le style d'image du style de mouvement (retirer objectif, profondeur de champ, « static wide shot » du
prompt vidéo, mettre « smooth steady camera motion, realistic physics, consistent lighting ») et viser 80 à 120 mots.
Coût : 6 à 13 appels de vision par Short, dans le quota gratuit de Flash-Lite (≈ 500 par jour).

## 4. D'autres modèles sur cette machine ?

> Mise à jour du 2026-09-28 : en phase de test, Luca ignore les licences. MiniMax H3 élagué (GGUF Q4, 11,6 Go) tourne
> sur 8 Go + 32 Go de RAM et devient le moteur à essayer : voir `21-modeles-hugging-face-8go.md`.

**Vidéo : non, rien de mieux que Wan 2.2 14B qui soit publiable en France et faisable sur 8 Go.** Classement
Artificial Analysis image → vidéo (votes à l'aveugle, 26/09/2026) : sans son, Gemini Omni Flash 1369 (celui de l'appli
Gemini, docs/17), Wan 3.0 1363 (API payante), MiniMax H3 1357, Cosmos3-Super-Image2Video-4Step 1274 ; avec son, parmi
les modèles ouverts, MiniMax H3 1180, MAGI-2 Preview 1094, LTX-2.5 Fast 1036.

| Modèle (2026) | Licence | Sur la 3070 | Verdict |
|---|---|---|---|
| MiniMax H3 (juillet, 33B, n° 1 des modèles ouverts) | H3 Community : **exclut l'UE**, les États-Unis, le Royaume-Uni, la Corée du Sud | 12 Go minimum avec déchargement | exclu (licence) |
| Cosmos 3 Super Image2Video (NVIDIA, mai, 64B) | OpenMDW 1.1, commercial permis | plusieurs H100 | impossible |
| Cosmos3-Nano (16B) | idem | BF16 seulement, cartes pro | impossible |
| MAGI-2 Preview (Sand.ai, août, 114B MoE) | Apache 2.0 | 8 GPU Hopper, 307 Go | impossible |
| LTX-2.5 (août, 22B, son) | LTX communautaire | Q2-Q3 + déchargement | option son seulement (docs/14 §2.2) |
| Kandinsky 5.0 I2V Lite (2B) / Pro (19B) | MIT | Lite tient dans la carte, nœuds natifs | curiosité : meilleure image et plus de mouvement que Wan selon ses auteurs (comparaisons en texte → vidéo), moins fidèle au prompt |
| HunyuanVideo 1.5 | exclut l'UE | — | exclu (docs/14) |
| **Wan 2.2 distillé 720p (lightx2v, avril)** | Apache 2.0 | même taille que l'actuel | **à essayer** (§1.4) |

La seule vraie montée en gamme sans payer est donc en ligne : Gemini Omni Flash, déjà branché (docs/17), en tête du
classement. Réservé aux 1 ou 2 plans clés d'un Short (accroche, révélation), il resterait dans le quota (≈ 9 clips par
fenêtre de 5 h, plafond hebdomadaire inconnu) ; il faut pour cela un choix du fournisseur **par scène** (aujourd'hui un
seul par production).

**Image : Qwen-Image-2512** (§2.1), puis HiDream-O1-Image si on veut un second avis.

## 5. Plan d'essai proposé

| # | Essai | Téléchargement | Où |
|---|---|---|---|
| 1 | Interpolation + SeedVR2 sur les clips d'une production existante (chalet v2 ou Villa Ocre) : avant / après, temps mesuré | ≈ 4 Go | bac à sable, puis step GPU `enhance_clip` entre `generate_clip` et le montage ; le clip 480p d'origine reste pour le contrôle et la continuité |
| 2 | Brief de mouvement par la vision + style vidéo séparé | rien | `generate_clip` / `storyboard`, `providers/video.py` |
| 3 | 4 passes + NAG face au mixte, scènes de visite du 25/09 | ComfyUI-KJNodes | nouveau workflow `wan22_i2v_4step_nag` |
| 4 | Wan distillé 720p face à base + LoRA v1, mêmes scènes, même graine | 19,3 Go | nouveau workflow + entrée `catalog.json` |
| 5 | Qwen-Image-2512 face à Z-Image, sur 10 prompts de storyboards récents | 15,9 Go | `qwen_image_2512.json` + `catalog.json`, Réglages → Modèles |
| 6 | Plans clés par Gemini, le reste en local | rien | fournisseur par scène (script ou storyboard) |

Chaque essai passe par une vraie production visible dans le dashboard (règle « tout passe par l'app ») dès qu'il sort
du simple réglage technique ; les téléchargements attendent l'accord de Luca.

## 6. Mise en place du 28/09 : MiniMax H3, Qwen-Image 2512, agrandissement + interpolation

Luca (28/09) : essayer MiniMax H3, utiliser Qwen-Image 2512, ne pas se soucier des licences pendant les essais.

**Installé** (dossiers de modèles du ComfyUI de `Downloads`, `download_models.ps1 -H3 -Post`) : MiniMax H3 élagué en GGUF
Q4_K_M (11,6 Go, Abiray) + encodeur Qwen3-VL 32B NVFP4 (15,7 Go ; il lit aussi l'image de départ, d'où ce modèle et pas
un GGUF sans partie vision) + VAE vidéo int8 et audio + LoRA 8 passes (≈ 32,6 Go) ; SeedVR2 3B int8 + VAE, RIFE 4.26,
FILM (≈ 4 Go). **Pas encore** : Qwen-Image 2512 (14,1 Go), faute de place sur C: (18 Go libres après H3) ; Luca fait
de la place, le workflow `qwen_image_2512.json` et son entrée de catalogue sont prêts (`download_models.ps1 -Qwen2512`).

**Dans l'app** : Réglages → Modèles de génération propose « MiniMax H3 · 8 passes (essai) » (et « 20 passes », ajouté par
la session « Modèles vidéo compatibles », docs/21) ; la variante première + dernière image (`minimax_h3_flf2v`) sert aux
chantiers et aux passages de visite comme pour Wan. H3 sort 124 images à 24 i/s (5,2 s), en **480 × 832** sur la 3070 :
les retours d'utilisateurs donnent ≈ 10 min par clip à cette taille, le 768 × 1344 natif à partir de 12 Go.

**Piège mémoire rencontré, et correction.** Premier essai H3 : ComfyUI à 26 Go de RAM privée, 315 Mo disponibles,
30 000 à 120 000 pages/s, GPU à 3 %, aucune passe en 2 min → arrêté. Deux causes, lues dans le code de ComfyUI 0.37 :
1. le cache « pression RAM » (défaut) n'évince jamais les modèles utilisés par le prompt en cours
   (`comfy_execution/caching.py`) : l'encodeur de 15,7 Go reste en RAM pendant toute la génération ;
2. pour un modèle GGUF, ComfyUI ne sait pas que les poids viennent d'un fichier (`Model storage policy: fast_disk=False`)
   et recopie chaque poids déchargé en **RAM verrouillée** (`comfy/ops.py`, `pin_memory`) : ces pages ne peuvent pas
   partir dans le fichier d'échange, la RAM se remplit en double.

Avec l'accord de Luca, ComfyUI tourne désormais avec **`--cache-none --fast-disk`** (`C:\YouTube2\comfyui.bat` et le
lanceur du projet, copie du Bureau comprise) : les sorties sont jetées dès qu'elles ont servi (l'encodeur est libéré
avant l'échantillonnage) et les poids GGUF sont relus sur le SSD au lieu d'être recopiés (Wan et Qwen-Edit en profitent
aussi). Effet de bord : chaque tâche recharge ses modèles depuis le disque. La machine reste chargée : ≈ 45 Go de
mémoire engagée hors ComfyUI (24 processus Claude, 29 node dont le serveur du dashboard à 7 Go, 24 Brave, WSL) ; H3
laisse 200 à 800 Mo disponibles pendant l'échantillonnage, sans emballement.

**Mesures H3 sur la 3070** (villa Ocre 9a747c8c, mêmes images et prompts que les clips Wan, 480 × 832, 124 images à 24 i/s,
LoRA 8 passes) :

| Clip | Temps total | Échantillonnage | Wan « mixte » sur le même plan |
|---|---|---|---|
| scène 0, image → vidéo | **5 min 02 s** | 8 passes en 3 min 58 s (≈ 30 s par passe) | 4 s à 16 i/s, ≈ 10 min |
| scène 1, première + dernière image | **5 min 58 s** | 8 passes en 4 min 56 s | 5 s à 16 i/s, ≈ 10 min |

H3 finit exactement sur l'image visée en première + dernière image ; en image fixe, détail comparable à Wan à même
résolution, la différence se juge en mouvement (24 i/s natifs contre 16). Comparaisons côte à côte :
`C:\YouTube2\bench\2026-09-28-h3\9a747c8c\`. Première production H3 par l'app : 1f5d87f0 (chantier Rhin-Danube, 6 clips).

**Agrandissement + interpolation** (clip 0 de la Villa Ocre, 480 × 832 à 16 i/s → 960 × 1664 à 32 i/s, script
`post_test.py` : mêmes clips, même montage refait avec le code du jour pour l'avant et l'après, sans rien écrire en base) :

| Essai | Tuiles du VAE | Résultat |
|---|---|---|
| 1 | 512 px × 64 images | décodage hors de la carte, arrêté après 23 min |
| 2 | 512 px × 16 images | 6,6 Go de VRAM + 4,2 Go de mémoire « partagée » (en RAM, très lente) : arrêté ; le bureau de Windows (dwm) occupe à lui seul 2,5 Go de la carte |
| 3 | **384 px × 8 images** | **14 min 40 pour 4 s** : encodage 40 s, SeedVR2 ≈ 20 s, décodage ≈ 13 min, RIFE et écriture ≈ 20 s |

Résultat à 100 % : bois, arêtes et enduit nettement plus précis, mouvement plus fluide (32 i/s ramenés à 30 au lieu
d'images dupliquées). Coût trop élevé pour tous les clips (≈ 15 min par clip, ≈ 30 h pour 126 clips par semaine) : à
réserver aux plans clés, ou à alléger (×1,5 au lieu de ×2, carte libérée des applications qui l'occupent). Pistes
suivantes : un step `enhance_clip` optionnel si Luca le valide. Comparaisons : `C:\YouTube2\bench\2026-09-28-agrandissement\9a747c8c\`.

**Première vidéo H3 par l'app** : production 1f5d87f0 (chantier Rhin-Danube, 6 clips en ≈ 5 min 30 chacun, 30 s au
total, en revue le 28/09 à 11 h 16). Défaut vu : un texte gravé illisible (« FURMBUIE EUROPEAN… ») vient de l'image
du storyboard (Flux schnell), pas d'H3 ; c'est le genre de défaut que Qwen-Image 2512 corrige (meilleur rendu du texte).

## Sources

- ComfyUI 0.37.2 local : `comfy_extras/nodes_frame_interpolation.py`, `nodes_seedvr.py`, `nodes_nag.py`,
  `comfy/ldm/wan/model.py` ; gabarits `utility_video_frame_interpolation`, `utility_seedvr2_3b_int8_upscale_video`,
  `utility_z_image_turbo_2k_upscaler` (paquet `comfyui_workflow_templates_json`).
- SeedVR2 : [guide ComfyUI](https://docs.comfy.org/tutorials/utility/seedvr2), [poids ComfyUI (Apache 2.0)](https://huggingface.co/Comfy-Org/SeedVR2),
  [SeedVR2-3B](https://huggingface.co/ByteDance-Seed/SeedVR2-3B), [8 Go : usage communautaire](https://seedvr2.net/blog/tutorials/seedvr2-comfyui-low-vram-guide-2026).
- Interpolation : [modèles RIFE et FILM pour ComfyUI](https://huggingface.co/Comfy-Org/frame_interpolation) ;
  exemple de chaîne Wan 2.2 GGUF + agrandissement + RIFE sur 8 Go : [Civitai](https://civitai.com/models/2470813/wan-22-i2v-gguf-my-8gb-daily-workflow-or-upscale-rife).
- NAG pour Wan : [WanVideoNAG (KJNodes)](https://comfy.icu/node/WanVideoNAG), [discussion WanVideoWrapper](https://github.com/kijai/ComfyUI-WanVideoWrapper/issues/1834).
- Wan 2.2 distillé : [lightx2v, modèles distillés (720p du 12/04/2026)](https://huggingface.co/lightx2v/Wan2.2-Distill-Models),
  [LoRA 1022](https://huggingface.co/lightx2v/Wan2.2-Distill-Loras), [GGUF jayn7](https://huggingface.co/jayn7/WAN2.2-I2V_A14B-DISTILL-LIGHTX2V-4STEP-GGUF),
  [MoE Distill](https://huggingface.co/lightx2v/Wan2.2-I2V-A14B-Moe-Distill-Lightx2v).
- Prompts Wan : [guide officiel Alibaba, texte et image → vidéo](https://www.alibabacloud.com/help/en/model-studio/text-to-video-prompt),
  [guide Wan 2.2](https://wan27.org/blog/wan-2-2-prompt-guide).
- Classements : [image → vidéo, modèles ouverts](https://artificialanalysis.ai/video/leaderboard/image-to-video/open-weights),
  [image → vidéo, tous](https://artificialanalysis.ai/video/leaderboard/image-to-video), [texte → image, modèles ouverts](https://artificialanalysis.ai/image/leaderboard/text-to-image/open-weights),
  [retouche](https://artificialanalysis.ai/image/leaderboard/editing).
- Modèles vidéo 2026 : [MiniMax H3, licence hors UE](https://www.atlascloud.ai/blog/tips/minimax-h3-open-source-weights),
  [MiniMax H3 dans ComfyUI](https://blog.comfy.org/p/minimax-h3-day-0-support-in-comfyui), [Cosmos3-Super-Image2Video-4Step](https://huggingface.co/nvidia/Cosmos3-Super-Image2Video-4Step),
  [Cosmos3-Nano](https://huggingface.co/nvidia/Cosmos3-Nano), [MAGI-2 Preview](https://huggingface.co/sand-ai/MAGI-2-preview),
  [Kandinsky 5.0 I2V Lite (MIT)](https://huggingface.co/kandinskylab/Kandinsky-5.0-I2V-Lite-5s), [Kandinsky 5.0 face à Wan](https://github.com/kandinskylab/kandinsky-5/).
- Modèles d'image : [Qwen-Image-2512 (Apache 2.0)](https://huggingface.co/Qwen/Qwen-Image-2512), [GGUF Unsloth](https://huggingface.co/unsloth/Qwen-Image-2512-GGUF),
  [LoRA Lightning 2512](https://huggingface.co/lightx2v/Qwen-Image-2512-Lightning), [HiDream-O1-Image (MIT)](https://huggingface.co/HiDream-ai/HiDream-O1-Image),
  [Ideogram 4.0, licence non commerciale](https://www.buildfastwithai.com/blogs/ideogram-4-open-weight-image-model),
  [Ming-Image-0.1-Design (MIT)](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design).
