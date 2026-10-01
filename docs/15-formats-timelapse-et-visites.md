# 15 · Deux formats visuels : chantiers en accéléré et visites de maisons de luxe

> 2026-09-25, demande de Luca : reproduire les vidéos du dossier `examples/` (vidéos d'autres créateurs, gardées sur le
> PC et hors du dépôt public depuis le 29/09) — des **time-lapses de construction**
> et des **visites de maisons de luxe** (la vidéo dont parle `visite_appart_ai.mp4`, pas l'explication elle-même),
> avec **bruitages**, **musique libre de droits ou générée par IA** et un **titre d'accroche** (« hook title »)
> comme dans MJClipIt. Tout gratuit et local (ADR-007). Machine : RTX 3070 8 Go, 32 Go de RAM.

## En bref

> **Refonte du 25/09 au soir (§10)** après les retours de Luca sur les deux premières démos : chantier construit
> **à rebours** depuis le résultat fini et vraiment **accéléré**, visite qui suit le **plan** de la maison, **contrôle
> automatique** de chaque image clé par un modèle de vision, et toutes les vidéos fabriquées **par l'app**.

| | Chantier en accéléré (`chantiers_timelapse`) | Visite de luxe (`visites_luxe`) |
|---|---|---|
| Ce qu'on voit | un lieu, point de vue **fixe**, qui passe d'un état saisissant à un résultat spectaculaire en 8 à 12 étapes rapides | une maison parcourue selon son **plan** : arrivée, entrée, rez-de-chaussée, étage, clou |
| Images clés | le **résultat fini** est généré (Z-Image) ; chaque étape antérieure = **retouche de la suivante** (Qwen-Image-Edit, à rebours) : même bâtiment, même échelle, même cadre | une image par pièce : **mêmes matériaux** et **même vue** par les fenêtres, **ouverture** visible vers la pièce suivante, intérieur ou extérieur dit en premier |
| Contrôle | chaque image clé vérifiée par un modèle de vision (bâtiment entier, ouvriers à l'échelle, étape moins avancée que la suivante), refaite au besoin | idem (pièce vraiment intérieure, personne, texte) |
| Clips | **première + dernière image** (Wan 2.2 14B), **accélérés ×3 à ×4** au montage, **traînées** des silhouettes | image → vidéo, mouvement lent **vers l'ouverture** de la pièce suivante |
| Liaisons | coupe invisible (le clip finit sur l'image où commence le suivant) ; fin : le jour tombe, les lumières s'allument | passage **poussé** (zoom avant flou + whoosh) d'une pièce à la suivante |
| Son | engins et outils des étapes (un fond continu tant que l'outil ne change pas) + musique | musique élégante + ambiances (eau, feu, pas) + whooshs |
| Texte | titre d'accroche en haut ; **compteur de jours qui défile** | titre d'accroche ; nom des pièces ; prix fictif en fin (optionnel) |
| Durée | 20 à 30 s | 25 à 35 s (6 à 9 pièces) |

Ce qui est livré : deux **recettes** (`series.recipe`, migration 0006), l'agent script qui les écrit, les images
clés retouchées en chaîne, les clips première + dernière image, le titre d'accroche repris de MJClipIt, les
transitions, les bruitages et la musique au montage, deux séries prêtes, un script de démonstration sans base
ni LLM, 28 tests (82 au total). Modèles téléchargés le 25/09 avec l'accord de Luca (≈ 39 Go : musique, bruitages,
retouche), bibliothèques remplies (92 bruitages, 10 musiques), deux vidéos de démonstration produites en entier
(§8). Reste à faire par Luca : **l'inscription gratuite** à la licence de Stability (bruitages) avant de publier, et
relancer le lanceur (migration 0006, worker sur le nouveau code).

## 1. Ce que montrent les exemples

Analyse image par image (1 à 2 images par seconde) et spectrogrammes du son. Toutes les vidéos sont en 576×1024
(téléchargées depuis un réseau social), 30 i/s. `build_timelapse_4.mp4` est une copie exacte de `_3` (même
empreinte MD5).

### 1.1 Les time-lapses de construction

| Vidéo | Durée | Lieu, déroulé | Caméra | Son |
|---|---|---|---|---|
| `build_timelapse.mp4` | 34 s | stade de foot abandonné envahi → bulldozers → terre nivelée → tribune rénovée (toit bleu) → gazon déroulé en bandes → lignes et buts | drone **fixe**, même cadre de bout en bout | bruitages seuls : moteurs d'engins (grave continu), impacts, déroulé du gazon ; pas de musique |
| `build_timelapse_2.mp4` | 40 s | maison moderniste abandonnée (lierre, voiture rouillée) → débroussaillage → échafaudage, démolition → structure béton → vitrages → bardage bois → allée en dalles → jardin, lumière dorée | trépied **fixe**, ciel et nuages qui défilent | débroussailleuse, marteaux, perceuses, gravats par étapes ; pas de musique |
| `build_timelapse_3.mp4` | 115 s | un ouvrier (toujours le même) aménage une chambre dans une falaise puis une salle de bain dans la roche : ossature, fenêtres, tranchées, tuyaux, isolant, placo, peinture, parquet, meubles, lampe | plusieurs angles, gros plans, l'ouvrier passe d'une pièce à l'autre | outils en continu (façon ASMR), une nappe à la fin |

Ce qui fait le style, et que la recette reproduit :

- **Un seul cadre** tenu d'une étape à l'autre : seules la matière et la lumière changent. On le voit aux
  secondes figées sur chaque étape (image clé), puis au passage flou à l'étape suivante.
- **Les ouvriers et les engins sont des silhouettes floues**, qui laissent des traînées : c'est la signature d'un
  modèle vidéo IA à qui l'on demande un time-lapse (et c'est exactement ce que Wan fait quand on ne lui interdit pas
  les personnes, défaut constaté le 25/09 sur les récits, qualité ici).
- **Les étapes vont du plus visible au détail** : nettoyage, terrassement, structure, enveloppe, finitions, puis
  la révélation dans la plus belle lumière.
- **Le son raconte le chantier** : chaque segment a son bruit d'engin ou d'outil, et le son change à chaque
  étape (les coupures du spectrogramme tombent sur les changements d'étape : chaque clip a son son).

Méthode de ces vidéos (déduite de l'image) : une suite d'images clés du même lieu (retouches successives), puis
un modèle vidéo qui anime le passage d'une image clé à la suivante. C'est ce que fait la recette `timelapse`.

### 1.2 La visite de maison de luxe

`visite_appart_ai.mp4` (31 s) est un vidéaste face caméra qui explique la méthode ; transcription (sous-titres
lus image par image) : « Les vidéastes immobiliers vont détester cette vidéo. Je t'explique. Cette visite, elle a
l'air parfaitement filmée par un pro, mais en vrai, c'est de l'IA. Générée depuis de simples photos. D'abord, tu
balances toutes tes photos dans Google Flow et tu lui demandes de générer une map avec un ordre de visite
logique. C'est elle qui va guider la caméra. Dans Seedance 2.0, la map et tes images. Et avec le bon prompt, la
caméra suit le parcours de point en point, toute seule. Le résultat ? Une visite super fluide et indiscernable
d'un vrai tournage. Tu veux le prompt exact ? Abonne-toi et commente IMMO… »

La vidéo montrée (de 3 à 8 s puis de 20 à 26 s) : villa méditerranéenne (enduit à la chaux, travertin, arches,
chêne, oliviers) : allée d'entrée → séjour à grandes arches → salle à manger → cuisine en travertin → escalier,
environ 1 s par pièce, **caméra gimbal fluide** et **passages flous rapides** (coups de fouet) entre les pièces.
La « map » est une vue 3D en coupe de la maison avec un tracé lumineux et des étiquettes numérotées.

Google Flow et Seedance 2.0 sont payants (crédits) : exclus par ADR-007. Équivalent local retenu :

| Outil de la vidéo | Rôle | Équivalent local |
|---|---|---|
| Photos de la maison | les pièces | Z-Image Turbo, une image par pièce, même « bible » de style (`design_bible`) ajoutée à chaque prompt |
| Google Flow, « map » | ordre de visite logique | l'agent script : les scènes sont les pièces dans l'ordre de la visite (arrivée → séjour → … → clou) |
| Seedance 2.0 multi-images | un seul plan qui suit le parcours | un clip Wan 2.2 14B par pièce (mouvement gimbal lent) + transitions « coup de fouet » (xfade `hblur`) + whoosh : c'est aussi ce que montre la vidéo |
| Montage fluide | 30 i/s sans saccade | interpolation d'images (`minterpolate`, 16 → 30 i/s) avant l'agrandissement |

### 1.3 Les autres exemples (hors sujet de cette demande)

`animaux_cartoon_rigolo*.mp4` (8 et 10 s, 24 i/s) et `paysage_exceptionnel.mp4` (9 s) : non traités ici.

## 2. Le titre d'accroche, comme dans MJClipIt

Repris de MJClipIt (`Projet2FOU/backend/app/services/hook_overlay.py`) : `worker/hooktitle.py`.

- **Rendu** : PNG transparent dessiné par Pillow, une **plaque arrondie sombre par ligne** (#111111, rayon 16),
  texte blanc **Arial Black 64 px** sur 1080 de large, 90 % de la largeur, interligne 1,1 ; incrusté par FFmpeg
  (`overlay`) à **150 px du haut**, pendant toute la vidéo (réglages par défaut de MJClipIt). Les émojis sont
  retirés du rendu (la police ne les a pas), gardés dans le titre YouTube.
- **Écriture** (règles de MJClipIt, dans le prompt et vérifiées en code) : 3 à 8 mots, parlé, tutoiement,
  curiosité ou choc, sans point final, guillemets, hashtag ni majuscules criardes ; varier les formes (question,
  affirmation choc, « POV : » une fois sur trois au plus). Exemples : « Personne ne voulait de cette ferme »,
  « Tu paierais combien pour cette villa ? », « Regarde ce qu'ils ont fait de ce stade ».
- **Aperçu** : `yt2 hook preview "Tu paierais combien pour cette villa ?" --image photo.png`.

Le titre YouTube (agent SEO) reste distinct du titre gravé.

## 3. Les recettes, étape par étape

`worker/recipes.py` décrit chaque recette (nombre de scènes, durées, interpolation, volume de musique, position
des textes) et **impose la mécanique en code** (`normalize_script`) : le LLM écrit les images, les retouches, les
mouvements, les bruitages et les textes ; le code fixe le reste (qui est retouché, quel clip va d'une image à
l'autre, quelles transitions), puis `lint_recipe_script` vérifie ce qui se mesure (titre d'accroche par langue,
bible du lieu, bruitages connus, mouvements présents, durée) et renvoie une fois au LLM en cas de défaut.

```
concept (agent idée, guide du format)
  └─ script (SCRIPT_PROMPTS[recette] + titre d'accroche + vocabulaire des bruitages) → normalize_script → lint
       └─ storyboard : image clé par scène
       │     timelapse : scène 1 = Z-Image ; scènes suivantes = retouche de l'image retenue précédente
       │                 (Qwen-Image-Edit-2511 ; repli Z-Image image → image si le modèle manque)
       │     tour      : Z-Image + bible de la maison (variante d'une pièce par retouche si le script le demande)
       │     → validation humaine (planche), refaire une étape refait les retouches qui en dépendent
       └─ clips : timelapse = première + dernière image (wan22_flf2v_4step / 20step, variante du modèle vidéo choisi)
       │          tour      = image → vidéo (mouvement gimbal, scène figée où seule la caméra bouge)
       └─ montage : clips accélérés pour finir sur leur image (timelapse), interpolés à 30 i/s (visite),
                    transitions xfade, titre d'accroche, textes des scènes à 1330 px, bruitages, musique,
                    -14 LUFS ; pas de voix ni de sous-titres
```

Détails qui comptent :

- **Cadre verrouillé** : chaque retouche reçoit « Keep exactly the same camera position, angle, lens and framing…
  only change what is described » ; les workflows de retouche recadrent l'image en 768 × 1344 exactement (pas de
  redimensionnement « Kontext » qui décalerait le cadre d'une étape à l'autre).
- **Première + dernière image** : 81 images (5 s) toujours générées en entier, puis accélérées au montage (×2 au
  plus) si la scène est plus courte : couper le clip ferait sauter l'image d'arrivée.
- **Visite, maison vide** : « empty, nobody, no people » dans les images (Z-Image les respecte), mais **aucune mention
  de personnes dans les mouvements** : Wan en 4 passes ignore le négatif, et nommer les personnes pour les exclure
  les fait apparaître (§8) ; le mouvement décrit une scène figée où seule la caméra bouge. Au chantier, les ouvriers
  flous sont voulus.
- **Jamais « camera », « tripod » ni « time-lapse » dans un prompt d'image** : au premier essai, « fixed camera on a
  tripod » a fait dessiner un trépied planté dans la falaise. Ces mots sont retirés en code des prompts d'image
  (ils restent dans les prompts de mouvement, où Wan les comprend comme une consigne de caméra).
- **La bible d'un chantier ne décrit que ce qui ne change pas** (paysage, point de vue) : au premier essai elle
  décrivait la cabane finie, qui serait apparue dès l'état initial.
- **Textes des scènes** (`on_screen_text`) : style « Title » du profil de sous-titres, recentré à 1330 px (sous
  l'image, au-dessus des boutons Shorts), le titre d'accroche occupant le haut.
- **Prix** (visite) : seulement comme une estimation fictive ; jamais d'adresse, d'agence ni de « à vendre » (§6).

## 4. Son : musique et bruitages

**Bruitages** (`worker/sfx.py`) : 46 étiquettes, en anglais pour l'agent script, chacune avec son prompt de
génération : engins et outils (excavator, bulldozer, chainsaw, hammer, drill, saw, jackhammer, concrete_mixer,
scaffolding, tiles…), ambiances (birds, wind, night, ocean, pool_water, fireplace, room_tone…) et coups (whoosh,
impact, riser, shimmer, door_open…). Au montage : un **fond** couvre sa scène (bouclé, fondus), un **coup** part
au début de la scène, chaque transition « whip » reçoit un **whoosh** centré. Bibliothèque :
`DATA_DIR/sfx/<étiquette>/` (wav, flac, mp3, ogg), choix stable par vidéo. Étiquettes absentes : montage sans elles,
signalé dans le journal (`assemble.recette_incomplete`).

**Musique** : `DATA_DIR/music/<ambiance>/` comme avant ; nouvelles ambiances `luxury`, `chill`, `elegant`
(visites), `inspiring`, `upbeat` (chantiers) ; volume 0,45 (visite) et 0,3 (chantier) sous des bruitages plus
présents, normalisation -14 LUFS.

Remplir les bibliothèques, une fois (quelques minutes de GPU), puis le montage y pioche :

```
yt2 music generate --mood luxury --count 5      ACE-Step 1.5, pistes instrumentales de 90 s
yt2 music generate --mood inspiring --count 5
yt2 sfx generate                                 Stable Audio 3 small-sfx, 2 fichiers par étiquette manquante
yt2 sfx list / yt2 music list                    ce que contiennent les bibliothèques
```

Autres sources gratuites, à déposer à la main dans les mêmes dossiers : **YouTube Audio Library** (filtre
« Attribution non requise », monétisable, jamais revendiqué sur YouTube, téléchargement piste par piste),
**Sonniss #GameAudioGDC** (enregistrements réels, usage commercial sans attribution, 7,5 Go en 2026, idéal pour les
bruits de chantier), **Freesound filtre CC0**. À éviter : la musique de **Pixabay** (des contributeurs l'enregistrent
dans Content ID).

## 5. Modèles : ce qui est installé

| Rôle | Modèle | Licence | Taille | État (25/09) et mesure sur la RTX 3070 |
|---|---|---|---|---|
| Images clés | Z-Image Turbo int8 | Apache 2.0 | — | installé ; 11 à 22 s par image |
| Clips, première + dernière image | Wan 2.2 I2V 14B Q4_K_M + LoRA 4 passes (`WanFirstLastFrameToVideo`, nœud natif) | Apache 2.0 | — | installé, rien à télécharger |
| **Retouche** | Qwen-Image-Edit-2511 GGUF **Q5_K_M** + Qwen2.5-VL 7B fp8 + VAE + LoRA Lightning 4 passes | Apache 2.0 | 25,5 Go | **installé** ; 4 passes : 86 à 97 s par image, décor identique au pixel près |
| Retouche (repli) | Z-Image image → image (`zimage_img2img`, force 0,62) | Apache 2.0 | — | installé ; 17 s, mais le décor bouge d'une étape à l'autre |
| **Musique** | ACE-Step 1.5 turbo, tout-en-un (DiT 2B + encodeurs + VAE) | **MIT**, usage commercial des sorties autorisé ; entraîné sur musique sous licence, libre de droits et synthétique | 10,0 Go | **installé** ; 60 s de musique en 34 s, 75 s en ≈ 40 s |
| **Bruitages** | Stable Audio 3 small-sfx + T5Gemma | **Stability Community License** : gratuit sous 1 M$ de chiffre d'affaires, **inscription gratuite obligatoire** (https://stability.ai/community-license), UE non exclue ; conditions Gemma pour l'encodeur | 3,5 Go | **installé** ; ≈ 6 s par son (92 sons en 9 min) |
| (option) Interpolation IA | RIFE v4.26 (nœud natif `FrameInterpolate`) | MIT | 0,02 Go | plus tard, à la place de `minterpolate` |
| (option) Caméra pilotée | Wan 2.2 Fun Camera 14B GGUF Q4_K_M | Apache 2.0 | 21,3 Go | plus tard : trajectoires de caméra imposées pour les visites |

Pourquoi ces choix :

- **Retouche en Q5 plutôt qu'en int8** : l'int8 (20,5 Go) + son encodeur (9,4 Go) ≈ 30 Go dans 32 Go de RAM,
  pagination et plantages probables ; en Q5_K_M, ≈ 24 Go. Le Q4 est jugé « à peine utilisable » par un comparatif.
  Alternative légère si la place manque : FLUX.2 klein 4B fp8 (Apache 2.0, 4,1 Go, retouche moins bonne : Elo 949
  contre 1025).
- **4 passes par défaut** (`qwen_image_edit_2511_4step`) : mesuré le 25/09, la version 40 passes prend **13 min par
  image** avec la RAM saturée (0,7 Go libre : Windows, navigateur et Docker occupent ≈ 15 Go, le modèle et son encodeur
  ≈ 24 Go, le reste part sur le disque) ; la version 4 passes prend 1 min 30 et garde exactement le même décor. La
  version 40 passes (`COMFY_EDIT_WORKFLOW=qwen_image_edit_2511`) reste possible sur un PC déchargé. Le worker vide
  la mémoire de ComfyUI avant la première retouche et à la fin du storyboard (`ComfyClient.free`), pour que la
  retouche ne cohabite ni avec Z-Image ni avec Wan.
- **Bruitages Stable Audio 3 small-sfx plutôt que Stable Audio Open 1.0** : 2,3 Go au lieu de 4,9 Go et meilleur
  en bruitages (FAD 0,395 contre 0,501 sur la base BBC SFX, notes d'écoute 3,35 contre 2,95).
- **Aucun modèle vidéo → son (foley) n'est utilisable** : MMAudio (poids non commerciaux), ThinkSound (recherche
  seulement), HunyuanVideo-Foley (licence hors UE). D'où la bibliothèque d'étiquettes.

Téléchargés le 25/09 (≈ 39 Go, 15 min, tailles vérifiées octet par octet) par :

```
powershell -ExecutionPolicy Bypass -File services\worker\scripts\download_models.ps1 -Formats `
    -ComfyModels "C:\Users\Luca\Downloads\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\ComfyUI\models"
```

ComfyUI 0.37.2 les voit sans redémarrage. À refaire seulement pour une nouvelle installation de ComfyUI.

## 6. YouTube : rester publiable et monétisable

- **Contenu synthétique** : une visite ou un chantier photoréalistes qui n'ont pas eu lieu doivent être déclarés
  (« realistic scene that didn't actually occur ») ; la musique générée par IA aussi. `containsSyntheticMedia` est
  déjà à `true` à l'envoi (`youtube/client.py`) ; la déclaration ne réduit ni la portée ni la monétisation. L'agent
  SEO termine la description par « Made by Arzak Parker » (`steps/seo.py`, `AI_NOTE`).
  En UE, l'article 50 de l'AI Act s'applique depuis le 2 août 2026.
- **Contenu « inauthentique »** (ex-« répétitif », précisé en juillet 2026) : sont visés le contenu IA fait à partir de
  **gabarits génériques donnant une impression de production de masse** et « la même situation encore et encore avec
  le même dénouement ». Parades intégrées : l'agent idée varie les lieux, styles et étapes et évite les idées déjà
  proposées ; chaque vidéo a sa maison, son chantier, son titre d'accroche. À surveiller : ne pas publier trois
  fermes provençales dans la semaine, varier les révélations, et envisager une voix off courte qui explique (le
  format A sait le faire) si la chaîne est signalée.
- **Jamais une vraie annonce** : pas d'adresse, d'agence, de « à vendre » ; un prix seulement comme estimation
  fictive ; pas de personnage « expert immobilier » qui donnerait des conseils d'investissement.

## 7. Faire tourner

Les deux séries sont créées par la migration **0006** (`chantiers_timelapse`, `visites_luxe`, format B, actives).
Avec le lanceur (qui applique les migrations) ou `npx supabase --workdir C:\YouTube2\supabase-workdir migration up` :

```
yt2 series list                              colonne « recette »
yt2 ideate chantiers_timelapse               idées de chantiers (guide du format)
yt2 concepts list --series visites_luxe
yt2 concepts approve <id> ; yt2 produce <id>
yt2 storyboard show <production>             planche des images clés ; pick / redo / approve comme avant
```

Pour juger le rendu sur un script écrit à la main (`scripts/demo/*.json`), **en passant par l'app** (depuis le
25/09 au soir, plus aucune vidéo n'est fabriquée hors de la base) : le script devient une production de la série,
le worker la fabrique, elle apparaît dans le dashboard (Production : storyboard à valider, puis vidéo à autoriser).

```
cd services\worker
uv run python scripts/demo_formats.py scripts/demo/timelapse_refuge.json
uv run python scripts/demo_formats.py scripts/demo/visite_chalet.json
```

Réglages (`.env`) : `COMFY_EDIT_WORKFLOW` (défaut `qwen_image_edit_2511_4step`, ou `qwen_image_edit_2511` en
40 passes), `COMFY_EDIT_FALLBACK` (défaut `zimage_img2img`), `SFX_DIR`, `HOOK_FONT`. La qualité des clips suit le
modèle vidéo des réglages (4 passes → `wan22_flf2v_4step`, 20 passes → `wan22_flf2v_20step`).

Budget GPU d'une vidéo après la refonte du soir (mesures du 25/09, §10) : chantier ≈ 15 à 20 min d'images (1 génération +
9 à 11 retouches de 1 min 30, plus les essais refaits par le contrôle) + 10 à 12 clips × 4 min 30 ≈ **1 h 15** ; visite ≈
3 min d'images + 7 à 9 pièces et 6 à 8 passages en modèle mixte × ≈ 10 min ≈ **2 h 30**. Deux vidéos en même temps se
partagent la carte et se ralentissent (rechargements de modèles) : mieux vaut les enchaîner. En 20 passes, environ 10 fois
plus pour les clips. Montage : ≈ 1 min (l'interpolation de la visite est la partie la plus lente,
sur le processeur). Musique et bruitages : pris dans les bibliothèques, rien à calculer par vidéo.

## 8. Démonstration du 25/09

Deux vidéos produites de bout en bout hors worker (`scripts/demo_formats.py`), à partir de scripts **écrits par
l'agent script réel** (Gemini 3.5 Flash-Lite, prompts de `worker/recipes.py`, idée choisie par l'agent idée) :

| | Chantier : « Cabane sur la falaise » | Visite : « Le chalet alpin suspendu » |
|---|---|---|
| Dossier | `C:\YouTube2\demo\cabane_qwen\final.mp4` | `C:\YouTube2\demo\chalet\final.mp4` |
| Titre d'accroche | « Bâtir un refuge suspendu au vide » | « Regarde cette vue depuis les sommets enneigés » |
| Images | 1 Z-Image + 6 retouches Qwen-Image-Edit (2 en 40 passes, 4 en 4 passes) | 7 Z-Image avec la bible du chalet |
| Clips | 6 première + dernière image + 1 révélation | 7 image → vidéo, coups de fouet, fondu avant le jacuzzi |
| Son | musique `epic` + engins et outils par étape | musique `luxury` + ambiances + whooshs |

Ce que la démo a appris, corrigé dans le code :

- **Trépied dessiné** : « fixed camera on a tripod » dans le prompt d'image → un trépied planté dans la falaise.
  Les mots caméra, trépied et time-lapse sont retirés des prompts d'image.
- **Bible du chantier** : l'agent décrivait la cabane finie, qui serait apparue dès l'état initial → la bible ne
  décrit que ce qui ne change pas.
- **Titre d'accroche en texte seul** (au lieu d'un objet par langue) : Gemini l'a fait une fois, le script était
  rejeté → texte seul accepté et rangé sous « fr ».
- **Coupe puis coup de fouet** : bases de temps différentes (concat puis xfade), le montage de la visite échouait →
  corrigé, test FFmpeg réel ajouté.
- **Des passants dans la bibliothèque** : Wan en 4 passes ignore le négatif et a fait traverser un homme ; une
  consigne renforcée « no person, nobody walks » a fait pire (un homme et un enfant) : nommer les personnes, même
  pour les exclure, les suggère. Le prompt de mouvement ne parle donc plus jamais de personnes (retirées en code) et
  décrit une scène figée où seule la caméra bouge : troisième essai sans personne. Pour une garantie, le modèle vidéo
  en 20 passes (CFG 3,5) applique vraiment le négatif, dix fois plus lentement.
- **Repli Z-Image** : le décor bouge d'une étape à l'autre (falaise redessinée) ; avec Qwen-Image-Edit, il reste
  identique au pixel près. Le repli ne sert qu'en secours.

## 9. Suite possible

- **Mini-plan à l'écran** pour la visite (le parcours dessiné, la pièce en cours allumée) : le plan existe déjà dans
  le script (pièces, niveaux, ouvertures, §10).
- **RIFE** (22 Mo, nœud natif) à la place de `minterpolate` pour la visite : moins d'artefacts sur les bords.
- **Wan 2.2 Fun Camera** : trajectoire de caméra imposée (avancer, tourner) pour une visite encore plus « gimbal ».
- **Agrandissement IA** (aujourd'hui FFmpeg bicubique de 480 × 832 à 1080 × 1920) : c'est la limite de netteté
  la plus visible sur les deux formats.
- **Import d'une banque de sons** (Sonniss) triée par mots-clés dans les dossiers d'étiquettes.
- Le troisième exemple (un ouvrier récurrent sur 2 minutes) demande un personnage cohérent d'un plan à l'autre :
  retouche multi-images de Qwen-Image-Edit (même ouvrier) ; à étudier après les deux formats.

## 10. Refonte du 25/09 au soir : cohérence, accéléré, autonomie

### 10.1 Les retours de Luca sur les deux démos

- **Refuge** : « la construction manque beaucoup de cohérence », « ce n'est pas un time-lapse accéléré »,
  « certains plans on a des petits hommes, d'autres plans un grand homme », « c'est long », « pas abouti ».
- **Chalet** : la bibliothèque « semble être une pièce extérieure » ; il veut « un chemin tout tracé, une sorte de
  plan de la maison », comprendre « qu'on est vraiment dans le même chalet », entrer par l'entrée puis aller de
  pièce en pièce, « tout en continu », avec des plans qui bougent très légèrement pour montrer chaque pièce.
- Plus largement : un système qui marche **seul** et donne des vidéos réalistes et cohérentes, sans risque pour la
  chaîne ; toutes les vidéos, démos comprises, **dans l'app** ; il valide lui-même le storyboard.

### 10.2 Ce qui n'allait pas (analyse image par image)

| Défaut vu | Cause |
|---|---|
| Refuge pas « accéléré » | clips de 5 s joués à vitesse réelle (accélération ×2 au plus, en pratique ×1) : ouvriers à vitesse normale, aucun nuage ni ombre qui file ; 7 étapes de 5 s = 36 s |
| Ouvrier géant | la structure n'avait aucun repère d'échelle (plancher sans porte ni fenêtre, cabane coupée par le bord de l'image) : Wan a inventé un ouvrier à la taille d'une table ; les images clés n'avaient aucun ouvrier |
| Chantier incohérent | chaque retouche **inventait** l'étape suivante (retouches en avant) : poutres, puis « palette » de bois, puis caisse, puis cabane vitrée, sans rapport de forme ni d'échelle ; foreuse démesurée |
| « Morphing » | deux images clés très différentes : Wan fond l'une dans l'autre au lieu de construire |
| Bibliothèque dehors | prompt « pièce secrète derrière une bibliothèque » + bible « chalet dans la neige » sans le mot intérieur : Z-Image a dessiné une façade avec une niche |
| Pièces sans lien | chaque pièce générée seule : bois et poutres différents, montagne différente, rien ne montre la pièce suivante ; le jacuzzi devant un autre chalet |

### 10.3 Ce qui a changé

**Chantier : à rebours depuis le résultat fini.** Le résultat fini (avant-dernière scène) est la seule image générée,
en plein jour, **entière dans le cadre** avec portes, fenêtres et escaliers (l'échelle humaine) ; chaque étape
antérieure est une retouche de l'étape **suivante** qui enlève ce qui n'est pas encore construit et ajoute échafaudages,
matériaux et ouvriers (« petits, à l'échelle du bâtiment ») ; la dernière scène retouche le fini en crépuscule, lumières
allumées. Le bâtiment, son échelle et le cadre sont donc identiques du début à la fin : l'essai du refuge donne 11 images
cohérentes (falaise nue → cordistes → poutres → plancher → ossature → charpente → pare-pluie → bardage → vitrages → fini →
crépuscule). Mécanique en code (`recipes.normalize_script`, `edit_from`, `keyframe_order`) ; l'agent script écrit
toujours dans l'ordre chronologique (un exemple dans son prompt) ; le linter refuse une scène 1 qui décrit le résultat
(Gemini l'a fait deux fois avant la correction du prompt).

**Chantier : vraiment accéléré.** 8 à 12 étapes de 1,5 s au lieu de 6 de 5 s ; chaque clip première + dernière image
(81 images, 5 s) est accéléré ×3 à ×4,5 ; les images consécutives sont fondues par quatre (`tmix`) : ce qui est
immobile reste net, ouvriers et engins laissent une traînée, comme dans les exemples ; un **compteur de jours défile**
(« Jour 1 » → « Jour 72 », au plus 10 changements par seconde) ; le prompt de mouvement ajoute « tiny workers bustle
quickly, clouds race across the sky, shadows sweep quickly » ; fin = time-lapse du coucher du soleil (le fini → le
crépuscule), puis lent travelling avant. Un fond sonore continu tant que l'outil ne change pas (sinon le son hacherait
toutes les 1,5 s). Durée : 20 à 30 s (série : 24 s, migration 0009).

**Visite : le plan d'abord.** L'agent script imagine la maison puis la fait parcourir sans retour en arrière (arrivée,
entrée, rez-de-chaussée, escalier, étage, clou) ; pour chaque pièce : `interior` (dit en premier dans le prompt :
« Interior photograph taken inside the house, walls and ceiling visible »), `floor` (le linter refuse une visite qui
redescend), `leads_to` (l'ouverture visible vers la pièce suivante, dans l'image) ; pour toute la maison :
`design_bible` = les matériaux en liste, répétés mot pour mot, et `view` = le paysage vu par toutes les fenêtres.
L'essai du chalet donne 8 pièces du même chalet (mêmes mélèze, chêne, cadres noirs, quartzite, même pic dans toutes
les fenêtres ; bibliothèque en mezzanine intérieure ; l'entrée montre le séjour, la cuisine montre l'escalier, la
chambre montre la salle de bain). Mouvement de chaque pièce : lent, **vers l'ouverture** de la pièce suivante.

**Visite : continue, de pièce en pièce.** Entre deux pièces, le code insère un **passage** (`ScriptScene.passage`) :
un clip première + dernière image qui part de l'image où le montage coupe la pièce (3,5 s sur 5 s) et finit sur l'image
clé de la pièce suivante, accéléré ×4 (1,2 s) ; la pièce suivante commence exactement là : coupe invisible, la caméra
traverse l'ouverture. Essai du 25/09 : entrée → séjour (on franchit l'ouverture, la cheminée apparaît), séjour →
cuisine (la caméra tourne et arrive devant l'îlot). Chaque pièce garde son plan lent de 2,5 à 4 s. Sans passages
(`RecipeSpec.passages=False`), repli sur le passage « poussé » (zoom avant flou + whoosh, `push`).

**Visite : sans passants (modèle « mixte »).** En 4 passes (CFG 1), Wan ignore le négatif et fait entrer des gens par
les portes et les fenêtres : même salle de bain, une femme entre par la porte vitrée ; bibliothèque, une silhouette sur
le balcon. Les visites prennent donc automatiquement la variante **mixte** du modèle (`wan22_i2v_hybrid` et
`wan22_flf2v_hybrid` : 2 passes du modèle haut bruit sans LoRA avec CFG 3,5, où le négatif agit, puis 2 passes haut bruit
et 4 passes bas bruit avec la LoRA), avec « person, people, human, silhouette, camera, tripod, crane… » ajoutés au
négatif (`RecipeSpec.video_variant`, `video_negative`, `providers/video.quality_variant`). Même salle de bain, même
graine de départ : pièce vide, la caméra tourne autour de la baignoire. Coût : ≈ 10 min par clip au lieu de 4 min 30
(≈ 2 h 15 pour une visite de 8 pièces et 7 passages). Proposé aussi dans Réglages → Modèles de génération (« Wan 2.2 14B ·
mixte 8 passes »). Une production réglée en 20 passes garde ses 20 passes (le négatif y agit déjà).

**Mots de tournage que Wan dessine.** « slow crane up » a fait descendre une grue de chantier au-dessus du jacuzzi,
« gimbal move » a planté un pied de stabilisateur à roulettes dans la salle de bain : ces mots (crane, gimbal, dolly,
tripod, drone…) sont remplacés en code dans les mouvements (`recipes._no_rig` : « rising view », « steady »,
« tracking ») et interdits dans le prompt de l'agent ; pas sur un chantier, où la grue est voulue. Les titres de deux
pièces ne se superposent plus pendant une transition.

**Contrôle automatique des images clés** (`worker/keyframe_qc.py`). Chaque image clé est regardée par un modèle de vision
(Gemini gratuit, `providers/llm.get_vision_llm` : seuls les fournisseurs qui voient les images) avec les exigences de sa
scène : pièce vraiment intérieure, aucune personne, pas de texte, bâtiment entier dans le cadre, ouvriers à l'échelle,
étape moins avancée que la suivante et même cadre (l'image retouchée est jointe). Refusée → refaite (2 essais de plus),
puis revue humaine avec la liste des problèmes. Mesuré le 25/09 : 2 à 13 s par image ; l'ancienne bibliothèque est
refusée (« prise depuis l'extérieur de la maison »), l'ancienne cabane aussi (« construction coupée par le cadre »), les
nouvelles images passent. Résultat par image dans `assets.meta.qc` (affiché sur la carte du storyboard), par
production dans le résultat du job storyboard ; la revue humaine reste la règle (`STORYBOARD_AUTOPASS=false` : Luca
valide lui-même) ; `KEYFRAME_QC=false` désactive le contrôle, `KEYFRAME_QC_RETRIES` règle les essais.

**Contrôle automatique des clips** (`keyframe_qc.check_clip`, appelé par `steps/generate_clip.py`). Trois images tirées
de chaque clip (à 30, 65 et 97 %) sont comparées à son image de départ : personne apparue, appareil de tournage ou
machine étrangère, objet inventé, architecture qui fond (pour un chantier : ouvriers à l'échelle, cadre fixe ; pour un
passage : seulement personnes et appareils). Refusé → refait une fois (`CLIP_QC_RETRIES`, ≈ 4 min 30), verdict dans
`assets.meta.qc`. Mesuré le 25/09 (3 à 4 s par clip) : il a repéré la grue au-dessus du jacuzzi, l'appareil sur
roulettes de la salle de bain et un sac apparu sur le sol de la bibliothèque, et laissé passer le bon plan de l'entrée.
Pour un fournisseur à durée imposée (Gemini en ligne), le verdict est noté sans refaire le clip (quota).

**Tout passe par l'app.** `scripts/demo_formats.py` ne fabrique plus rien hors de la base : il enregistre le script
comme une production de la série (concept + production + job script) que le worker fabrique ; scripts d'essai
`scripts/demo/timelapse_refuge.json` et `visite_chalet.json` (les anciens, en retouches « en avant », sont retirés).

### 10.4 Essais du 25/09 au soir

| | Refuge v2 (chantier) | Chalet v2 (visite) | Ruine → villa (autonome) | Villa Ocre de Santorin (autonome) |
|---|---|---|---|---|
| Script | écrit à la main (`scripts/demo/timelapse_refuge.json`) | écrit à la main (`visite_chalet.json`) | Gemini 3.5 Flash-Lite, conforme au 1er essai | Gemini, conforme au 1er essai |
| Images clés | 1 Z-Image + 10 retouches à rebours | 8 Z-Image d'après le plan | 1 + 9 retouches, 5 refus du contrôle refaits, 1 étape encore signalée | 7 pièces, toutes acceptées |
| Clips | 10 flf + 1 révélation, 4 passes (4 min 30 chacun) | 8 pièces (5 en 4 passes, 3 refaites en mixte) + 7 passages mixtes (10 à 12 min chacun) | à faire après validation | à faire après validation |
| Vidéo | 19,5 s | 37,9 s | — | — |
| Dans l'app | abandonnée (✗) à 18 h 27, sans doute un clic de trop | Création, à valider (production ef5e155e) | validée par Luca avec « Gemini (essai) » | Création, à valider (9a747c8c) |

**4, 8 (mixte) ou 20 passes ?** Même étape du refuge (ossature → charpente), même images de départ et d'arrivée :

| Modèle | Temps (RTX 3070) | Ce qu'on voit |
|---|---|---|
| 4 passes (LoRA, CFG 1) | 4 min 30 | la charpente apparaît d'un coup au début (fondu), puis plus rien ne bouge ; négatif ignoré |
| mixte 8 passes (2 avec CFG 3,5) | ≈ 10 min | construction progressive, plus d'ouvriers au travail, panneaux posés un à un ; négatif actif |
| 20 passes (CFG 3,5) | 37 min | la plus régulière : la charpente monte peu à peu, géométrie stable ; négatif actif |

Accélérées ×3 à ×4 au montage, les versions mixte et 20 passes se ressemblent beaucoup. Choix retenu : le mixte pour
les visites (imposé, à cause des passants), les 4 passes pour les chantiers (le contrôle attrape les ouvriers géants ;
le mixte se choisit dans Réglages → Modèles de génération pour tout passer en 8 passes), les 20 passes réservées aux
vidéos d'exception (un chantier de 11 clips ≈ 7 h, une visite de 15 clips ≈ 9 h : intenable à 3 vidéos par jour).

Leçons : (1) la plupart des refus du contrôle sont justes (gravats sur la pelouse d'une villa « finie », étape plus
avancée que la suivante, passant, grue, sac apparu) ; les faux refus repérés (un meuble qui sort du cadre, des ruines
« en plus » dans l'état initial) ont été corrigés dans les exigences. (2) Gemini gratuit répond souvent 503 le soir :
4 contrôles sur 7 perdus avant l'ajout de la patience (30, 90, 180 s). (3) Deux productions en même temps sur la carte
se ralentissent l'une l'autre (rechargement des modèles à chaque alternance, ×3) : le worker les enchaîne ; éviter les
essais manuels pendant une fabrication.

### 10.5 Réglages et fichiers

| Élément | Où |
|---|---|
| Recettes, ordre des retouches, compteur, linter | `worker/recipes.py` (`edit_source`, `keyframe_order`, `edit_dependents`, `day_counter`) |
| Nouveaux champs du script | `ScriptScene.edit_from`, `interior`, `floor`, `leads_to`, `passage` ; `ScriptV1.view` ; `duration_s` ≥ 1 s ; 24 scènes au plus (passages compris) |
| Storyboard dans l'ordre des retouches + contrôle | `worker/steps/storyboard.py`, `worker/keyframe_qc.py` |
| Contrôle des clips, passages (départ à l'image de coupe) | `worker/steps/generate_clip.py`, `keyframe_qc.check_clip` |
| Modèle mixte des visites (négatif actif) | `workflows/wan22_i2v_hybrid.json`, `wan22_flf2v_hybrid.json`, `providers/video.quality_variant` |
| Accéléré, traînées, compteur, passage poussé | `worker/steps/assemble.py` (`TRAILS`, `max_speedup`, `ticks`), `worker/subtitles.py` (`ticks`) |
| Images envoyées au LLM | `worker/providers/llm.py` (`images=`, `sees_images`, `get_vision_llm`) |
| Séries mises à jour | migration `0009_recipes_coherence.sql` (brief, 24 s pour les chantiers) |
| Réglages | `KEYFRAME_QC` (oui), `KEYFRAME_QC_RETRIES` (2), `STORYBOARD_AUTOPASS` (non), `CLIP_QC` (oui), `CLIP_QC_RETRIES` (1) |

## 11. 30/09 : des pièces rénovées plutôt que des bâtiments

Retour de Luca : plutôt qu'une maison vue du dehors, **une pièce d'une maison de luxe** qu'on voit évoluer de
l'intérieur, d'un état désolant (délabrée, sale, abîmée) à un intérieur **sobre, épuré, propre**, qui plaît à presque
tout le monde. Le plaisir est la satisfaction du sale qui devient impeccable ; le résultat doit être assez **réaliste**
pour qu'on se dise « ça pourrait être chez moi » (pas pour tromper : pour se projeter).

Même mécanique (à rebours depuis la pièce finie, retouches Qwen-Image-Edit, clips première + dernière image,
accéléré, compteur de jours, révélation le soir). Ce qui change :

| | Avant (bâtiment) | Maintenant (pièce) |
|---|---|---|
| Idées (`guide_timelapse`) | maisons, granges, falaises, piscines | salon, cuisine, salle de bain, suite, dressing, cave… de maisons variées ; lieu insolite une fois sur cinq au plus |
| Scénariste (`script_timelapse`) | paysage et bâtiment entier | toutes les scènes `interior: true` ; résultat réaliste (chêne clair, pierre, chaux, lin, teintes douces, lumière naturelle, proportions d'une vraie maison) ; étapes débarras → démolition → réseaux → murs → sol → peinture → agencement → luminaires → meubles |
| Image de la pièce finie | « construction entière dans le cadre » | vue large depuis un angle à hauteur d'œil, sol, murs, plafond et fenêtres, porte et meubles à l'échelle, « photo de décoration réaliste, pas un rendu 3D » |
| Ouvriers | petits, à l'échelle du bâtiment | taille humaine, au milieu de la pièce, jamais au premier plan |
| Mouvement | nuages qui filent | taches de soleil qui balaient le sol et les murs ; le soir, lampes qui s'allument une à une |
| Contrôle des images | bâtiment entier, pas d'engin | pièce terminée et propre, vue en grand, proportions crédibles ; étapes : mêmes murs, fenêtres et cadre |
| Bible (`design_bible`) | paysage et point de vue | la pièce, ses fenêtres, la vue dehors, le point de vue ; **jamais l'état de départ** (premier essai : « floor damage » dans la bible → fissure dans le parquet de la pièce finie, attrapée par le contrôle) |

Le choix bâtiment / pièce se fait par script (`recipes.indoor` : une scène marquée `interior`) : les anciennes
productions de chantiers restent des bâtiments. Série renommée « Rénovations de pièces en accéléré » (migration
**0030**, brief réécrit). Premier essai : « Suite parentale sous les décombres » (production 05e6f608), storyboard à
valider dans Création.

## Sources

- Méthode décrite dans `examples/visite_appart_ai.mp4` (Google Flow + Seedance 2.0) : transcription ci-dessus.
- MJClipIt : `Projet2FOU/backend/app/services/hook_overlay.py`, `highlights.py` (règles des titres), `models/schemas.py`
  (`HookTitle`).
- ComfyUI 0.37.2, gabarits officiels installés (`comfyui_workflow_templates_json`) : `video_wan2_2_14B_flf2v`,
  `image_qwen_image_edit_2511_int8`, `audio_ace_step_1_5_checkpoint`, `audio_stable_audio_3_medium`,
  `utility_video_frame_interpolation`, `video_wan2_2_14B_fun_camera`.
- ACE-Step 1.5 : [modèle (MIT)](https://huggingface.co/ACE-Step/Ace-Step1.5), [code](https://github.com/ace-step/ACE-Step-1.5),
  [fichiers ComfyUI](https://huggingface.co/Comfy-Org/ace_step_1.5_ComfyUI_files).
- Stable Audio 3 : [fichiers ComfyUI](https://huggingface.co/Comfy-Org/stable-audio-3), [licence communautaire](https://stability.ai/license),
  [inscription](https://stability.ai/community-license), [guide des prompts](https://github.com/Stability-AI/stable-audio-3/blob/main/docs/guides/prompting.md),
  [article SA3 (mesures SFX)](https://arxiv.org/abs/2605.17991).
- Qwen-Image-Edit-2511 : [modèle (Apache 2.0)](https://huggingface.co/Qwen/Qwen-Image-Edit-2511), [GGUF unsloth](https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF),
  [LoRA Lightning](https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning), [avis sur les quantifications (MyAIForce)](https://myaiforce.com/qie-2511/).
- Interpolation : [FILM et RIFE pour ComfyUI](https://huggingface.co/Comfy-Org/frame_interpolation). Fun Camera GGUF :
  [QuantStack](https://huggingface.co/QuantStack/Wan2.2-Fun-A14B-Control-Camera-GGUF).
- Foley exclus : [MMAudio](https://github.com/hkchengrex/MMAudio), [ThinkSound](https://github.com/QwenAudio/ThinkSound),
  [HunyuanVideo-Foley](https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley/blob/main/LICENSE).
- Bibliothèques : [Freesound](https://freesound.org/help/faq/), [Sonniss](https://sonniss.com/gdc-bundle-license/),
  [Pixabay (Content ID)](https://pixabay.com/service/faq/), [YouTube Audio Library](https://support.google.com/youtube/answer/3376882).
- YouTube : [contenu altéré ou synthétique](https://support.google.com/youtube/answer/14328491), [`containsSyntheticMedia`](https://developers.google.com/youtube/v3/docs/videos),
  [contenu inauthentique](https://support.google.com/youtube/answer/1311392), [précisions de juillet 2026 (TechCrunch)](https://techcrunch.com/2026/07/20/youtube-clarifies-policies-around-ai-slop-and-upsetting-videos/),
  [AI Act, article 50](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act).
