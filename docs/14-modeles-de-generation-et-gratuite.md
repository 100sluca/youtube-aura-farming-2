# 14 · Modèles de génération : Qwen-Image 2.1, LTX, Blender + Higgsfield, et la règle de gratuité

> 2026-09-25, à la demande de Luca : il envisage de tester Qwen-Image 2.1, LTX, ou Blender + Higgsfield, veut
> savoir lequel est le plus pertinent dans le workflow, et pose la règle : **tout doit rester gratuit**, en local
> sur le PC ou avec un service en ligne gratuit **sans limite d'usage** (ADR-007). Volume visé : 3 Shorts publiés
> par jour, beaucoup d'avance au départ, peut-être une journée de production par semaine (organisation à décider
> plus tard). Précisé ensuite : **le temps de calcul n'est pas une contrainte**, ce qui compte est la qualité et un
> pipeline qui ne plante pas. Machine : RTX 3070 8 Go, 32 Go de RAM. Complète `08-benchmark-video.md` et `12` §5.

## En bref

| Rôle dans le workflow | Choix | Pourquoi |
|---|---|---|
| Image de storyboard | **Z-Image Turbo** (inchangé) | Apache 2.0 ; meilleur photoréalisme ouvert utilisable sur 8 Go (Elo 940, devant FLUX.2 klein 4B à 864) |
| Animation | **Wan 2.2 I2V 14B** GGUF Q4 : 4 passes pour la vitesse, **20 passes** (`wan22_i2v_20step`) pour la qualité maximale | Apache 2.0 ; meilleur modèle ouvert en image → vidéo (tient le sujet, suit le prompt) |
| Retouche et cohérence (nouveau) | **Qwen-Image-Edit-2511** ; FLUX.2 klein 4B en secours léger | avant / après, même sujet d'un plan à l'autre ; meilleur modèle de retouche ouvert à usage commercial (Elo 1025, klein 4B 949) |
| Son généré avec l'image | **LTX-2.5**, en option | moins bon que Wan en image → vidéo ; seul intérêt : le son ; très serré sur 8 Go |
| Minecraft, mécanismes exacts | **Blender** + chaîne libre (plus tard) | blender-mcp + Wan 2.2 Fun Control / VACE en local à la place de Higgsfield + Seedance |
| Exclus | Qwen-Image 2.1 (même en étape intermédiaire), FLUX.2 klein 9B, Higgsfield, Open-Higgsfield-AI, Wan 2.5 à 2.7, Hunyuan3D, services en ligne gratuits | licences non commerciales ou excluant l'UE ; crédits ou API payants ; crédits du jour, filigrane |

**Le plus pertinent : ne pas changer de moteur, mais le pousser en qualité.** Z-Image Turbo + Wan 2.2 14B reste la
meilleure combinaison gratuite et publiable ; puisque le temps ne compte pas, Wan 14B passe de 4 à 20 passes quand on
veut la meilleure qualité. On ajoute une étape de **retouche d'image** (Qwen-Image-Edit-2511) pour les scènes de
transformation, et, plus tard, LTX-2.5 pour le son.

**Suite (26/09)** : les leviers de qualité sans changer de moteur (interpolation, agrandissement SeedVR2, prompts de
mouvement écrits d'après l'image, Wan distillé 720p, Qwen-Image-2512) et les modèles sortis en 2026 sont dans
`20-qualite-video.md`.

## 1. La règle de gratuité, en critères (ADR-007)

Un outil entre dans le pipeline s'il remplit l'une des deux conditions :

1. **local**, poids ouverts, **et** licence qui autorise la publication sur une chaîne qui sera monétisée
   (Apache 2.0, MIT, licence communautaire LTX sous 10 M$ de chiffre d'affaires) ; « poids ouverts » ne suffit
   pas, la licence se lit à chaque nouveauté ;
2. **en ligne, gratuit, sans plafond, avec une API, sans filigrane** : aucun service ne remplit ces conditions
   aujourd'hui (docs/08 §3).

Les quotas gratuits récurrents (Kaggle 30 h de GPU par semaine, offre gratuite de l'API Gemini) sont acceptés en
appoint, avec un repli local. Les crédits payants (Higgsfield, fal.ai, Replicate, Runway, API Claude) n'entrent pas
en production.

## 2. Les trois pistes de Luca

### 2.1 Qwen-Image 2.1 : excellent, mais interdit même comme image de départ

- Sorti le **20 septembre 2026** (Alibaba) : générateur de 7 milliards de paramètres, encodeur de texte Qwen3-VL 8B,
  2K natif (9:16 = 1536 × 2752), retouche avec **jusqu'à 10 images de référence**, retouches locales guidées par
  des marques, PNG transparents. Pris en charge par ComfyUI dès la sortie, versions GGUF communautaires.
- **Licence : Qwen Research License.** La licence porte sur l'**usage du modèle**, pas sur la destination des
  images : elle interdit d'utiliser le modèle « for any commercial purpose » sans licence commerciale, et réserve
  l'usage gratuit à la recherche et à l'évaluation. Produire les images d'une chaîne destinée à être monétisée est
  un usage commercial, que l'image soit publiée telle quelle ou animée ; en image → vidéo, elle est d'ailleurs la
  première image du clip publié. Voie légale : demander une licence commerciale à
  `model-business@notice.qwencloud.com` (conditions et prix inconnus).
- Qualité, d'après les comparaisons disponibles : pour le **photoréalisme**, Qwen-Image 2.1 ne bat pas Z-Image Turbo
  (comparatif CRITICA : 1. Z-Image Turbo, 2. Krea 2 Turbo, 3. FLUX.2 klein 4B, 4. Qwen-Image 2.1, fort surtout en
  texte dans l'image et en retouche multi-images). Son vrai atout pour nous est la **retouche**.
- Sur la 3070 : 40 passes par défaut, pas de version distillée ; Unsloth annonce ≈ 11 Go de VRAM en GGUF avec
  l'encodeur de texte en RAM. Estimation : 2 à 5 min par image.

**FLUX.2 klein 4B est-il aussi bon ?** Non, surtout en retouche. Classements Artificial Analysis (votes à l'aveugle,
septembre 2026), modèles ouverts :

| Modèle | Licence | Génération (Elo) | Retouche (Elo) | Sur 8 Go |
|---|---|---|---|---|
| **Z-Image Turbo** | Apache 2.0 | **940** | — (pas de retouche) | 15-30 s par image, 8 passes |
| **Qwen-Image-Edit-2511** | Apache 2.0 | — | **1025** | 20B ; Nunchaku INT4 + LoRA 4 passes (3-4 Go de VRAM avec déchargement, d'après Nunchaku) ; ≈ 20 Go de disque |
| FLUX.2 klein 4B | Apache 2.0 | 864 | 949 | 4 passes, GGUF Q4 ≈ 2,6 Go, quelques secondes |
| FLUX.2 klein 9B | **non commerciale** | 940 | 1014 | ≈ 29 Go en natif |
| Qwen-Image 2.1 | **recherche seulement** | pas encore classé | pas encore classé | 2-5 min par image (estimation) |

Donc : **Z-Image Turbo pour créer l'image, Qwen-Image-Edit-2511 pour la transformer.** FLUX.2 klein 4B ne sert que si
Qwen-Image-Edit est trop lourd sur la machine.

Usage prévu de la retouche : les scènes de **transformation** (avant / après d'une rénovation, passage secret fermé
puis ouvert) et le **sujet récurrent** (le même animal ou la même pièce dans deux plans coupés). On génère l'image
« avant » avec Z-Image, la retouche produit l'image « après » dans la même pièce, puis Wan 2.2 14B anime **de la
première à la dernière image** (`WanFirstLastFrameToVideo`, docs/12 §4). Le modèle interpole au lieu d'inventer :
c'est la réponse directe au défaut du premier rendu (la porte qui fond en étagères).

### 2.2 LTX-2.5 : pas meilleur que Wan pour notre usage, même sans contrainte de temps

- Sorti le **11 août 2026** (Lightricks) : 22B, vidéo **et son synchronisés** en une passe, plans multiples, image →
  vidéo, première et dernière image, 4K ; encodeur de texte Gemma 4 12B. Licence communautaire gratuite sous 10 M$ de
  chiffre d'affaires : conforme.
- **Qualité en image → vidéo** : les comparatifs indépendants (menés sur LTX-2.3 face à Wan 2.2) donnent Wan
  gagnant : il suit mieux les consignes de caméra et d'action, et garde le sujet de l'image de départ, là où LTX a
  tendance à le transformer. LTX gagne sur la vitesse, la résolution et le son. LTX-2.5 est trop récent pour des comparatifs indépendants ; le seul qui le place devant Wan est celui de
  Lightricks.
- **Sur la 3070** : Lightricks recommande 32 Go de VRAM ; les GGUF distillés communautaires vont de 8 à 22 Go. Sur
  8 Go, il faut les plus petites quantifications (Q2-Q3), qui dégradent l'image, plus l'encodeur de 12B et le
  déchargement dans les 32 Go de RAM : c'est la configuration la plus exposée aux plantages. Repère : LTX-2 (19B)
  prenait 300 à 400 s par clip court sur une 3070 Ti 8 Go. ≈ 22 Go de disque.

Verdict : pas de remplacement de Wan. LTX-2.5 reste une option pour le **son** (format B visuel pur, bruitages), à
tester une fois le moteur principal validé, avec 22 Go de disque en plus.

**Mise à jour du 25/09 au soir : les modèles des tableaux soumis par Luca** (comparatifs d'une autre IA pour une
RTX 3070 8 Go + 32 Go) :

| Modèle | Verdict | Pourquoi |
|---|---|---|
| Wan 2.2 14B GGUF | **déjà en service** | 4 passes ≈ 4 min 30 par clip (mesuré) ; 20 passes ≈ 25-35 min d'après ces mesures (40 passages du modèle au lieu de 4), soit ≈ 55-75 h pour 126 clips par semaine ; mixte 8 passes ≈ 10 min (`wan22_i2v_hybrid`). Q3_K_M ou Q4_K_S ne vont pas plus vite (le temps vient des passes) et perdent en finesse : garder Q4_K_M |
| LTX-Video 2B 0.9.8 distillé fp8 | **installé à l'essai** (`ltxv_2b_i2v`) | seule version qui tient entière dans la carte (4,5 Go), d'où les « 30-50 s » ; le 13B fp8 fait 15,7 Go et la 3070 ne calcule pas en fp8. **Mesuré le 25/09** sur les scènes 1 et 3 de la production 0e306bad (même image, même prompt que Wan) : 32 s et 30,5 s par clip de 5 s en 576 × 1024, chargement compris (Wan 4 passes ≈ 4 min 30, mixte ≈ 11 min) ; LTX suit le mouvement de caméra (poussée, panoramique vers le haut) sans inventer de personnes, là où Wan 4 passes a ajouté une passante puis des nageurs ; image un peu plus douce, décor inventé au-delà du cadre lors d'un panoramique. À juger par Luca sur une production entière |
| Mochi 1 | non installé | ComfyUI ne l'utilise qu'en texte → vidéo (aucun nœud image → vidéo) : il ne peut pas animer le storyboard validé ; 848 × 480 en paysage |
| CogVideoX-2B | non | texte → vidéo seulement, 720 × 480 en paysage, 8 i/s, 2024 |
| Stable Video Diffusion | non | 2023, pas de prompt : on ne peut pas lui dire quel mouvement faire |
| HunyuanVideo (1.0, I2V, 1.5) | **exclu** | licence Tencent : « ne s'applique pas dans l'Union européenne » ([texte](https://huggingface.co/tencent/HunyuanVideo-1.5/blob/main/LICENSE)) |

### 2.3 Blender + Higgsfield : Higgsfield payant, la chaîne libre existe

- Le module Higgsfield pour Blender (août 2026) construit une maquette 3D à partir d'un prompt (Claude via un pont
  MCP), puis **Seedance 2.5** rend la vidéo finale en suivant la caméra de la maquette. **Chaque génération consomme
  des crédits** ; en septembre 2026 le plan gratuit n'en donne aucun et marque les rendus d'un filigrane. Exclu.
- **Équivalents libres, pièce par pièce :**

| Étape | Higgsfield | Libre et gratuit | Remarque |
|---|---|---|---|
| Maquette 3D depuis un prompt | Scene Builder (Claude via MCP) | **blender-mcp** (MIT, le premier pont Claude ↔ Blender), ou un script Python lancé par le worker (`blender -b --python`) | même principe : c'est Claude qui construit la scène |
| Objets 3D | génération 3D Higgsfield | **TRELLIS.2** (Microsoft, MIT) : image → modèle 3D | 8 Go : basse résolution (256³) seulement ; 512³ demande 12-16 Go |
| Personnages Minecraft | — | **MCprep** (libre) | rigs et textures Minecraft (docs/12 §3) |
| Rendu final | Seedance 2.5 (cloud) | **Wan 2.2 Fun Control** ou **VACE** 14B en GGUF (Apache 2.0) : Blender fournit profondeur ou contours, Wan redessine | le 5B Fun Control est déjà installé |
| Montage dans Blender | — | **Pallaidium** (libre, dans l'éditeur vidéo de Blender, Wan / LTX / FLUX en local) | orienté montage, pas maquette |

- Pièges relevés : **Open-Higgsfield-AI** (MIT) n'est qu'une interface pour l'API payante Muapi ; **Hunyuan3D** et
  **HY-Motion** (Tencent) ont une licence qui exclut l'Union européenne ; ComfyUI-BlenderAI-node (GPL) gère mal les
  nœuds vidéo.
- **Aussi bien ?** Pour la maquette, oui : c'est le même mécanisme. Pour le rendu final, non : Wan sur 8 Go reste en
  dessous de Seedance 2.5, et il faut assembler les pièces soi-même. Pour Minecraft (vrais blocs) et les mécanismes
  (la 3D fixe la forme), c'est suffisant. Blender n'est pas installé sur le PC.

Verdict : projet à part, après la mise en route de Wan 14B.

## 3. Le workflow retenu, scène par scène

1. Image de storyboard : Z-Image Turbo (2 candidates par scène, `STORYBOARD_CANDIDATES`, on garde la meilleure).
2. **Nouveau, seulement pour les scènes de transformation et le sujet récurrent** : retouche Qwen-Image-Edit-2511
   (image « après », ou même sujet sous un autre angle).
3. Animation : Wan 2.2 I2V 14B GGUF Q4, `wan22_i2v_4step` (rapide) ou `wan22_i2v_20step` (qualité maximale, sans
   LoRA, 20 passes, CFG 3,5, réglages du gabarit officiel ComfyUI) ; première + dernière image quand l'étape 2 a servi.
4. Son : voix Kokoro + musique ; LTX-2.5 plus tard pour les bruitages et le format B.

**Test d'un Short complet**, dans l'ordre :

| # | Qui | Geste | Volume |
|---|---|---|---|
| 1 | Luca | libérer de la place sur C: : **≈ 65 Go libres** visés (35 Go le 25/09), jamais sur D: | — |
| 2 | Claude, avec accord | nœud ComfyUI-GGUF, puis `download_models.ps1` vers le ComfyUI de `Downloads` : Wan 14B Q4 (19,3 Go), LoRA 4 passes (2,5 Go), VAE (0,25 Go), Z-Image Turbo + encodeur (20,7 Go), Kokoro (0,36 Go) | ≈ 43 Go |
| 3 | Luca | clé Gemini gratuite dans Réglages → Intelligence artificielle (aucune clé LLM aujourd'hui dans `.env`) | — |
| 4 | Claude | lanceur (Docker, Supabase, ComfyUI, worker), un concept maisons de rêve → script → storyboard → clips en 4 passes → voix → montage | ≈ 30 min de calcul |
| 5 | Claude | même production en 20 passes, pour comparer | ≈ 1,5-2,5 h |

Ensuite : Qwen-Image-Edit-2511 sur trois avant / après (≈ 20 Go), puis LTX-2.5 si le son intéresse (≈ 22 Go).
Qwen-Image 2.1 peut être comparé à Z-Image en évaluation, jamais dans une production.

**Mise en place et premières mesures (2026-09-25).** Luca branche Qwen-Image 2.1 pour les tests (`qwen_image_21.json`,
évaluation). ComfyUI passe de 0.36.0 à **0.37.2** (prise en charge de Qwen-Image 2.1, pic de mémoire de Wan réduit,
cache adapté à la pression sur la RAM ; branche de secours `backup_branch_2026-09-25_11_05_14`), ComfyUI-GGUF installé.
Modèles installés dans le ComfyUI de `Downloads` : Wan 2.2 I2V 14B Q4_K_M + LoRA 4 passes + VAE 2.1, Z-Image Turbo en
**int8** + encodeur fp8 (6,2 + 5,6 Go au lieu de 12,3 + 8 Go : le modèle tient dans la carte), Qwen-Image 2.1 int8
(7,3 + 9,4 Go), Kokoro. ComfyUI se lance par `C:\YouTube2\comfyui.bat` (le `run_nvidia_gpu.bat` d'origine exige d'être
lancé depuis son dossier).

| Étape | Réglage | Temps | VRAM max |
|---|---|---|---|
| image Qwen-Image 2.1 | int8, 768 × 1344, 25 passes | 44 s (chargement compris) | — |
| image Z-Image Turbo | int8, 768 × 1344, 8 passes | 17 s | — |
| clip Wan 2.2 14B | Q4_K_M, 4 passes, 480 × 832, 81 images à 16 i/s | 329 s (premier clip, chargement compris) | 7,7 Go sur 8 |

Sur le prompt du passage secret, Qwen-Image 2.1 respecte la scène (panneau entrouvert, escalier éclairé), là où Z-Image
place l'escalier à l'intérieur d'une bibliothèque fermée. Wan 14B garde la géométrie : le panneau pivote, l'escalier
reste un escalier (le 5B faisait fondre la porte). Un seul prompt : à confirmer sur la vidéo complète.

**Pourquoi c'est le réglage le plus adapté à cette machine** (8 Go de VRAM, 32 Go de RAM) : Wan 14B en Q4_K_M est la
plus haute qualité qui tienne dans la RAM (deux experts de 9,65 Go ; en Q6 ou Q8, 24 à 31 Go feraient déborder la
mémoire et planter) ; 480 × 832 est la résolution qui tient dans les 8 Go (le 720p du 14B demande plus du double de
calcul que le 5B en 720p, qui saturait déjà la carte) ; les modèles d'image en int8 tiennent entiers dans la carte ;
4 passes pour les brouillons, 20 passes pour la qualité finale. Deux améliorations restent à faire après le test
complet : l'**interpolation** 16 → 32 images par seconde (le montage duplique aujourd'hui les images pour passer à 30 i/s,
ce qui saccade) et un **agrandissement IA** (aujourd'hui FFmpeg bicubique de 480 × 832 à 1080 × 1920).

## 4. Trois Shorts par jour, une journée de production par semaine

Une semaine = 21 Shorts × 6 scènes = **126 clips** et environ 200 images de storyboard (2 candidates par scène
qui coupe).

| Pile | Par scène (images + clip) | 126 scènes | Tient dans |
|---|---|---|---|
| Z-Image + Wan 14B en 4 passes | ≈ 2,5-5 min | ≈ 5-10 h | une nuit |
| **Z-Image + Wan 14B en 20 passes** | ≈ 16-26 min | ≈ 35-55 h | 2 à 3 jours, ou 5-8 h chaque nuit en production au fil de l'eau |
| Wan 5B à 480p (installé aujourd'hui) | ≈ 4-4,5 min mesurées | ≈ 9 h | une nuit, mais qualité refusée |
| Z-Image + LTX-2.5 GGUF | ≈ 5,5-9 min | ≈ 12-18 h | une journée et une nuit |

Le temps n'étant pas une contrainte, la qualité maximale reste tenable : la « journée de production » devient deux à
trois jours de calcul par semaine, ou une nuit de calcul par jour. Ce qui existe déjà : « Autoriser la publication »
place la vidéo au prochain créneau libre, ou à une date choisie (docs/13). Ce qu'il faudra : un mode « journée de
production » (`PRODUCTIONS_PER_DAY` à 21 ce jour-là ; la file GPU est déjà traitée une tâche à la fois). Les durées
de 20 passes sont des estimations (≈ 10 fois 4 passes ; un guide annonce plus de 20 min par clip pour le 14B sur 8 Go) :
le test du §3 donnera les vraies.

**Point d'attention, le LLM.** L'offre gratuite de l'API Gemini plafonne par modèle et par jour : d'après des guides
de septembre 2026, 20 requêtes par jour pour les Flash récents (3.5 à 3.8 Flash, dont `gemini-3.8-flash`, défaut du
dashboard) et 500 pour les Flash-Lite (3.5 et 3.1) ; les vrais chiffres de la clé sont sur
[aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit). Une journée de 21 Shorts fait environ 60 à
90 appels (script, reprise après relecture, SEO FR et EN, idées) : un Flash à 20 par jour s'arrête vers le cinquième
Short. Solutions : un Flash-Lite ce jour-là, les scripts étalés sur la semaine, ou Ollama en local (sans limite,
moins bon, et il dispute les 8 Go à ComfyUI : à faire tourner avant les clips). L'API Claude, défaut de `config.py`,
est payante : hors règle.

## 5. Ce qui reste exclu (rappel de docs/08)

- Services en ligne gratuits (Kling, Hailuo, PixVerse, Veo / Flow, Seedance via Dreamina) : crédits du jour,
  filigrane, pas d'API gratuite, automatisation interdite par leurs conditions. Comparaisons à la main seulement.
- Wan 2.5, 2.6, 2.7 : API payante. Les poids ouverts de Wan s'arrêtent à la famille 2.2 (dernier dépôt :
  Wan2.2-Animate-2-14B, août 2026). Les articles annonçant un « Wan 3.0 open source » ne correspondent à rien sur
  le compte Wan-AI de Hugging Face : à ignorer.
- Kaggle (30 h de GPU gratuites par semaine, 2 × T4 16 Go) : capacité d'appoint si le PC ne suffit pas, pas une
  solution sans limite.

## 6. Choisir ses modèles depuis Réglages, la voix, les bruitages (2026-09-25)

**Choisir les modèles.** Réglages → **Modèles de génération** : modèle des images du storyboard, modèle d'animation,
nombre d'images par scène, voix française et anglaise, puis « Enregistrer les modèles ». Chaque modèle affiche sa
licence (« publiable » ou « tests seulement ») et s'il est installé : le dashboard compare les fichiers cités par le
workflow à ceux que ComfyUI voit (`/object_info`). Le réglage vit dans `app_settings.generation` (migration 0005) et
prime sur le `.env` ; en ligne de commande : `yt2 settings generation --image zimage_turbo --video wan22_i2v_20step`.

**Comparer.** Les modèles sont figés dans la production au moment du script (`productions.image_workflow`,
`productions.video_provider`, badges « images » et « vidéo » dans la fiche) : changer les réglages ne touche pas une
production en cours. Pour comparer, ouvrir une production → **Refaire avec les réglages actuels** (ou
`yt2 remake <production>`) : nouvelle production, même script, sans appel au LLM pour le script, nouveau storyboard
et nouveaux clips avec les modèles du moment ; l'originale reste intacte.

**Ajouter un modèle.** Son workflow ComfyUI au format API dans `services/worker/workflows/<nom>.json` (nœuds titrés,
voir le README du dossier), une entrée dans `workflows/catalog.json` (libellé, détail, licence, publiable) : il
apparaît dans Réglages.

**La voix.** Elle est déjà dans le montage : le job `tts` fait lire chaque scène par Kokoro (local, Apache 2.0), pose
les voix sur la timeline (`narration.wav`), et le montage y cale les sous-titres mot à mot et passe la musique sous la
voix (compression déclenchée par la narration). Kokoro n'a qu'une voix française (`ff_siwis`). Pour une voix plus
naturelle, ou la voix de Luca clonée à partir d'un échantillon de 10 s : **Chatterbox multilingue** (Resemble AI,
licence MIT, français inclus), à ajouter comme second moteur TTS ; XTTS-v2 et Fish Speech sont exclus (licences non
commerciales). **Mise à jour du 25/09 au soir** : trois moteurs ajoutés, choisis et écoutés depuis Réglages
(Qwen3-TTS avec 6 voix françaises « dessinées », Kyutai Pocket TTS, Supertonic 3) ; Chatterbox finalement écarté
(français plus faible, filigrane) : voir `18-voix.md`.

**Les bruitages et la musique** sont traités dans `15-formats-timelapse-et-visites.md` §4-5 : génération locale avec
**Stable Audio 3 « small-sfx »**, plutôt que Stable Audio Open 1.0 (même licence communautaire Stability : gratuite
sous 1 M$ de chiffre d'affaires, inscription gratuite obligatoire ; 2,3 Go au lieu de 4,9 Go, meilleure sur les
bruitages), et musique ACE-Step. Exclu des deux côtés : **MMAudio**, qui génère le son à partir de la vidéo, car il
dépend du CLIP d'Apple (DFN), non commercial. Alternatives : le son natif de LTX-2.5 (§2.2), ou une banque de sons
libres (Pixabay, Freesound CC0) posée à la main.

## Sources

- Qwen-Image 2.1 : [fiche Hugging Face](https://huggingface.co/Qwen/Qwen-Image-2.1), [licence](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE),
  [dépôt GitHub](https://github.com/QwenLM/Qwen-Image-2.1), [article sur la licence (Mixed)](https://mixed-news.com/en/qwen-image-2-1-transparent-rgba-7b-open-weights-research-licence/),
  [ComfyUI](https://comfy.org/qwen-image-2.1/), [GGUF](https://huggingface.co/abenzerps/Qwen-Image-2.1-GGUF),
  [Unsloth, exécution locale](https://unsloth.ai/docs/models/qwen-image-2.1).
- Comparaisons d'images : [Artificial Analysis, génération, modèles ouverts](https://artificialanalysis.ai/image/leaderboard/text-to-image/open-weights),
  [Artificial Analysis, retouche](https://artificialanalysis.ai/image/leaderboard/editing),
  [CRITICA : Z-Image, Flux Klein, Qwen-Image 2.1, Krea 2](https://www.criticatv.com/z-image-vs-flux-klein-vs-qwen-image-krea-2-comfyui/).
- Qwen-Image-Edit-2511 : [fiche](https://huggingface.co/Qwen/Qwen-Image-Edit-2511), [Nunchaku INT4](https://huggingface.co/QuantFunc/Nunchaku-Qwen-Image-EDIT-2511),
  [doc Nunchaku (3-4 Go)](https://nunchaku.tech/docs/nunchaku/usage/qwen-image.html), [ComfyUI](https://docs.comfy.org/tutorials/image/qwen/qwen-image-edit-2511).
- FLUX.2 klein : [4B (Apache 2.0)](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B), [9B (non commerciale)](https://huggingface.co/black-forest-labs/FLUX.2-klein-9B),
  [ComfyUI](https://docs.comfy.org/tutorials/flux/flux-2-klein), [GGUF](https://huggingface.co/unsloth/FLUX.2-klein-4B-GGUF).
- LTX-2.5 : [annonce](https://comfyui-wiki.com/en/news/2026-08-11-ltx-2-5-open-weights-release), [ComfyUI](https://docs.comfy.org/tutorials/video/ltx/ltx-2-5),
  [licence LTX-2](https://github.com/Lightricks/LTX-2/blob/main/LICENSE), [seuil de 10 M$](https://www.therundown.ai/tools/ltx-2-5),
  [variantes et tailles](https://ltxworkflow.com/models), [GGUF distillés](https://huggingface.co/Abiray/LTX-2.5-Distilled-GGUF),
  [LTX-2 sur 8 Go](https://github.com/nalexand/LTX-2-OPTIMIZED).
- LTX face à Wan : [WaveSpeed](https://wavespeed.ai/blog/posts/ltx-2-3-vs-wan-2-2-comparison-2026/), [CrePal](https://crepal.ai/blog/aivideo/ltx-2-3-vs-wan-2-2/),
  [Magic Hour](https://magichour.ai/blog/ltx-2-3-vs-wan-2-2), [comparatif de Lightricks](https://ltx.io/alternatives/wan-2-2).
- Wan 2.2 en 20 passes : [gabarit officiel ComfyUI de juillet 2025](https://github.com/Comfy-Org/workflow_templates/blob/40fc612cdf058af9440a9262ef293002832cf9ea/templates/video_wan2_2_14B_i2v.json),
  [temps sur 8 Go](https://willitrunai.com/blog/wan-2-2-vram-requirements) ; Fun Control depuis une profondeur Blender :
  [ComfyUI Wiki](https://comfyui-wiki.com/en/tutorial/advanced/video/wan2.2/wan2-2-fun-control), [gabarit 14B](https://comfy.org/workflows/video_wan2_2_14B_fun_control-67a816af8a73/).
- Higgsfield : [module Blender](https://higgsfield.ai/blog/higgsfield-blender-plugin), [filigrane](https://higgsfield.ai/creator-hub/help-center/credits-and-usage/watermark-and-how-to-remove),
  [plan gratuit 2026 (Krea)](https://www.krea.ai/blog/what-is-higgsfield-ai-pricing-free-plan-and-alternatives-in-2026),
  [plan gratuit 2026 (Segmind)](https://blog.segmind.com/higgsfield-ai-free-use/).
- Chaîne libre Blender : [blender-mcp](https://github.com/ahujasid/blender-mcp), [TRELLIS.2](https://github.com/microsoft/TRELLIS.2),
  [Pallaidium](https://github.com/tin2tin/Pallaidium), [ComfyUI-BlenderAI-node](https://github.com/AIGODLIKE/ComfyUI-BlenderAI-node),
  [Open-Higgsfield-AI](https://github.com/Autom8AI/Open-Higgsfield-AI), [licence Hunyuan3D (hors UE)](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE).
- Wan : [compte Wan-AI](https://huggingface.co/Wan-AI), [Wan 2.7 non ouvert](https://localaimaster.com/blog/wan-2-7-open-source).
- Voix et bruitages : [Stable Audio Open, licence](https://huggingface.co/stabilityai/stable-audio-open-1.0/blob/main/LICENSE.md),
  [licence communautaire Stability](https://stability.ai/license), [MMAudio et le CLIP d'Apple non commercial](https://note.com/luta_ai/n/n016f31c8f838?hl=en),
  [TTS libres pour un usage commercial (Kokoro, Chatterbox)](https://localclaw.io/blog/local-tts-guide-2026).
- Gemini : [limites officielles (renvoi à AI Studio)](https://ai.google.dev/gemini-api/docs/rate-limits),
  [quotas gratuits par modèle, septembre 2026](https://www.scriptbyai.com/gemini-api-free-tier-limits/).
