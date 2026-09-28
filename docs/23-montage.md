# 23 · Onglet Montage : le modèle de montage de toutes les vidéos

> 2026-09-28. Demande de Luca : un onglet « édition » avec une vidéo 9:16 sur laquelle régler soi-même où et comment
> s'affichent le titre d'accroche, les sous-titres et les textes à l'écran (police, taille, couleurs, fond, position),
> pour y mettre sa patte au lieu du rendu figé dans le code, puis déclarer ce réglage comme le modèle réutilisé pour
> tous les clips.

## 1. Ce qu'on trouve

Menu **Montage** (`/montage`), entre Agents et Réglages.

- **À gauche, l'aperçu 9:16** : un clip d'une production récente tourne en fond (vignettes « Fond de l'aperçu » : un
  clip par production, quelques images de storyboard, ou un dégradé neutre), avec par-dessus les trois couches du
  modèle. On **clique** un élément pour ouvrir ses réglages et on le **fait glisser** pour le placer (aimanté au centre ;
  flèches du clavier : 1 px, Maj + flèche : 10 px). En haut, le format montré : Récits narrés, Chantiers, Visites.
  « Zones YouTube » hachure ce que l'interface des Shorts recouvre souvent (barre du haut, colonne de boutons, titre et
  chaîne en bas). « Pause / Lecture » arrête ou relance le défilement des sous-titres.
- **Rendu exact** : le worker monte 5 s avec le vrai code du montage (même fichier ASS, même PNG du titre, même FFmpeg)
  sur le fond choisi, avec les réglages en cours (enregistrés ou non). Prêt en 2 à 4 s, même pendant qu'un clip se
  fabrique (voir §5). C'est la preuve de ce que donnera la vidéo.
- **À droite, les réglages** : le modèle (choisir, enregistrer, « Utiliser pour toutes les vidéos », enregistrer sous
  un autre nom, renommer, repartir des réglages d'origine, supprimer), un onglet par couche, l'onglet **Son** (niveaux
  de la voix, de la musique et des bruitages, musiques de la bibliothèque avec écoute : docs/26-musique.md), les
  textes d'essai (pris dans les dernières productions, jamais enregistrés) et les polices.

## 2. Les trois couches

| Couche | Où elle vit au montage | Réglages |
|---|---|---|
| Titre d'accroche | PNG dessiné par Pillow puis incrusté (worker/hooktitle.py) | formats où il s'affiche, durée (toute la vidéo ou N s), police, taille (px), majuscules, couleur ; fond : une plaque par ligne (style TikTok de MJClipIt), un seul bloc, ou texte contouré ; couleur, opacité, arrondi, marges ; largeur maximale, interligne, alignement des lignes ; position (centre horizontal, haut du titre) |
| Sous-titres | fichier ASS gravé par libass (worker/subtitles.py) | activés ou non (vidéos narrées seulement), style de départ (Impact, Karaoké, Sobre, Affiche, BD : la position ne bouge pas), police, taille, casse, espacement, couleur, mot prononcé (aucun, mot coloré, karaoké) et sa couleur, contour, ombre (couleur, opacité, distance, angle, flou), boîte (couleur, opacité, marge), mots par légende, caractères par ligne, apparition (pop, rebond, fondu, glisse), position (centre) |
| Textes à l'écran | même fichier ASS, couche du dessus | une case à cocher par type de contenu, police, taille, majuscules, couleur ; boîte (couleur, opacité, marge), texte contouré ou seul ; position (centre). Ce sont des repères posés sur l'image : les jours qui défilent (chantiers), le nom de chaque pièce (visites), une courte légende par scène (récits, « 1 an plus tard »). Un texte trop large rapetisse (jusqu'à 55 % de sa taille) pour tenir dans l'image. |

Positions et tailles en pixels du final 1080 × 1920, comme dans l'éditeur. Taille du titre d'accroche : taille de la
police en px (Pillow). Taille des sous-titres et des textes à l'écran : taille ASS, c'est-à-dire la hauteur d'une ligne
(libass fait tenir usWinAscent + usWinDescent de la police dans cette taille : Montserrat 88 donne des capitales
d'environ 39 px). L'aperçu du navigateur reprend ces deux conventions (métriques de chaque police forcées par
`ascent-override` / `descent-override`, découpage en lignes et en légendes recopié du worker) : vérifié le 28/09 contre
le rendu exact, écart de quelques pixels.

Les couches se montrent **selon le type de contenu** (cases à cocher Récits narrés, Chantiers, Visites). Réglage
d'origine, décidé par Luca le 28/09 : le **titre d'accroche** et les **sous-titres** sont toujours là (les sous-titres
n'existent que sur les récits narrés, seuls à avoir une voix) ; les **textes à l'écran** seulement sur les chantiers et
les visites, pour ne pas encombrer l'image d'un récit où les sous-titres suffisent. Le scénariste des récits écrit
désormais aussi un titre d'accroche (consigne `rules_hook_title`, onglet Agents) ; un ancien récit sans titre
d'accroche prend le titre de la vidéo.

## 3. Modèles : enregistrer, utiliser, refaire un montage

Table `montage_templates` (migration 0013) : un nom, le contenu (`template`, JSON de `MontageTemplate`,
worker/montage.py) et **un seul modèle par défaut** (`is_default`, SQL `set_default_montage_template`). Le step
`assemble` lit le modèle par défaut **à chaque montage** : l'enregistrer change les montages suivants, pas les vidéos
déjà montées. Sans modèle par défaut (aucun enregistré, ou celui-ci supprimé), le worker garde le **modèle d'origine**
du code. Un modèle illisible ne bloque jamais un montage : le worker le signale dans son journal et prend l'origine.

- « Enregistrer comme mon modèle » (premier enregistrement) propose de l'utiliser aussitôt pour toutes les vidéos.
- « Utiliser pour toutes les vidéos » : le modèle affiché devient celui du montage (enregistré au passage s'il a changé).
- Plusieurs modèles peuvent coexister (essais, variantes saisonnières) ; un seul sert.
- **Refaire le montage** (fiche d'une vidéo à valider, dans Création ou la Bibliothèque) : remonte la vidéo avec le
  modèle actuel, mêmes clips et même voix (SQL `remount_video` : jobs `assemble` puis `qa`). Seulement avant l'envoi
  sur YouTube ; une vidéo déjà autorisée perd son créneau et revient à valider. Une vidéo programmée est déjà sur
  YouTube : on ne la remonte pas.

Le modèle d'origine garde le style d'avant l'onglet (titre de MJClipIt : Arial Black 64 sur plaques #111111 à 150 px
du haut ; sous-titres du profil « impact » au centre ; textes à l'écran en capitales Montserrat sur boîte noire à
60 %, centrés à 1 330 px). Changements pour les **récits** : titre d'accroche affiché, plus de texte à l'écran (il
était à 330 px) ; un modèle a une seule position par couche, pour un rendu identique sur tous les formats. Le
modèle de Luca (« Mon modèle #1 ») a reçu les mêmes cases le 28/09. Les réglages `title_y`, `title_size`,
`hook_title`, `hook_duration_s` des recettes
(worker/recipes.py) et le profil de sous-titres des chaînes (`channels.subtitle_profile`, `SUBTITLE_PROFILE`) ne
servent plus au montage (le profil sert encore aux aperçus `yt2 subtitles preview`).

## 4. Polices

Même liste pour l'éditeur et le worker (lib/font-files.ts ↔ `font_registry`, worker/montage.py), dans cet ordre :

1. livrées avec l'appli : services/worker/assets/fonts (Anton, Bebas Neue, Luckiest Guy, Montserrat SemiBold, Poppins
   SemiBold) ;
2. **ajoutées depuis l'onglet** (« Ajouter une police », .ttf ou .otf, 15 Mo au plus) : `DATA_DIR/fonts`
   (C:\YouTube2\data\fonts, hors de Documents que Windows protège) ; « Retirer » les efface ;
3. une sélection de polices de Windows (Arial Black, Impact, Segoe UI Black, Verdana, Georgia…), liste
   `windows_fonts` de services/worker/assets/montage/defaults.json.

Une entrée de la liste = un fichier (une graisse). Le modèle retient la famille (nameID 1) et le gras ; le worker
retrouve le même fichier (`FontRegistry.pick` : nom exact avant famille typographique, graisse la plus proche). Le
fichier choisi est copié à côté du fichier ASS : le FFmpeg utilisé ne voit pas toujours les polices du système. Une
police absente (retirée entre-temps) : Arial Black pour le titre d'accroche, police système pour le reste, et l'éditeur
l'indique. Polices gratuites conseillées : Google Fonts (licence OFL, utilisable sur YouTube).

## 5. Rendu exact et voie « preview » du worker

Le bouton met en file un job `montage_preview` (migration 0014, priorité 5, une seule tentative) avec le modèle en cours,
le format, le fond et les textes d'essai ; le step (worker/steps/montage_preview.py) prépare un plan de 5 s (sous-titres
répartis sur la phrase d'essai pour un récit, compteur « Jour 1 → 91 » pour un chantier, texte à l'écran sinon), applique
le modèle (`apply_template`, le même que le montage) et rend avec `render`. Fichiers : `DATA_DIR/previews/montage/<job>.mp4`
et `.jpg` (20 gardés), servis par `/api/montage-preview/<job>`.

Ce job a sa propre voie, **preview** (worker/main.py : `preview_lane`, un fil qui regarde la file chaque seconde) : la
boucle principale ne reprend la main qu'entre deux jobs GPU, et un clip dure jusqu'à 10 min. L'encodage se fait sur le
processeur (libx264) pour ne pas disputer la mémoire de la carte à ComfyUI ; l'habillage est identique.

Piège corrigé le 28/09 : un type de job absent de `models.JobType` fait échouer `claim_jobs` **après** avoir pris le job
(resté « running », sans rien faire). Un test vérifie maintenant que chaque step est un type connu.

## 6. Fichiers

| Où | Quoi |
|---|---|
| worker/montage.py | `MontageTemplate` (HookLayer, SubtitleLayer, TitleLayer), `load_template`, `font_registry`, `hook_text`, `subtitle_presets` |
| worker/steps/assemble.py | `apply_template` (après `apply_recipe`), lecture du modèle dans `AssembleStep` |
| worker/subtitles.py | position libre (`x`, `y`), marge de la boîte (`background_padding` : libass prend Shadow comme marge en BorderStyle 4, mesuré), `TitleStyle` (police, fond, position, rapetissement), polices multiples |
| worker/hooktitle.py | `HookStyle` : position x, alignement, plaque par ligne ou bloc, opacité, marges, contour, majuscules |
| worker/steps/montage_preview.py | rendu exact (voie preview) |
| services/worker/assets/montage/defaults.json | modèle d'origine, styles de départ des sous-titres, polices Windows (lu par le dashboard ; `tests/test_montage.py` vérifie qu'il suit le code) |
| supabase/migrations/0013, 0014 | `montage_templates`, `set_default_montage_template`, `remount_video` ; type de job `montage_preview` |
| apps/dashboard/src/app/montage, components/montage | page, éditeur, aperçu, réglages |
| apps/dashboard/src/lib/montage*.ts, font-files.ts | données, types, validation (zod, mêmes bornes que le worker), calculs de l'aperçu, lecture des polices |
| apps/dashboard/src/app/api/fonts, api/montage-preview | polices pour l'aperçu et ajout d'une police ; rendu exact |

## 7. Réutilisation dans MJClipIt

Luca veut le même éditeur dans MJClipIt (dépôt Projet2FOU). Fiche de portage, adaptée à son architecture (FastAPI,
React + Vite, fichiers JSON) : `C:\Users\Luca\Documents\GitHub\Projet2FOU\docs\PLAN-modele-de-montage.md`.

## 8. Idées pour la suite

Logo ou filigrane de la chaîne, style des transitions, un modèle par chaîne quand il y en aura plusieurs. Le son
(volume de la voix, de chaque musique et des bruitages, musiques de Luca) est fait depuis le 28/09 : onglet **Son**,
[docs/26-musique.md](26-musique.md).
