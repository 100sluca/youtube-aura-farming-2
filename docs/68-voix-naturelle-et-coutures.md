# 68 · Voix : coutures sans bruit et modificateur plus naturel (05/10)

Retour de Luca (05/10 après-midi, après le Studio du modificateur, docs/67) :
- en bougeant le **timbre**, la voix devient « électrifiée », « trop IA » : elle perd son naturel ;
- un **léger bruit de fond** s'entend quand une prise commence et quand elle s'arrête : « des bruits atroces » aux
  coutures entre paragraphes ;
- quelques hésitations dans les prises : Luca les corrige lui-même (Studio voix, « Refaire certains paragraphes »).

Écoute comparative : Bibliothèque → Démos et essais, « Voix : coutures sans bruit et modificateur plus naturel »
(`C:\YouTube2\bench\2026-10-05-voix-naturelle`), voix seule, sans musique.

## 1. Pour Luca

- **Coutures** : chaque prise est maintenant coupée sur ta voix, et plus sur les mots de Whisper. Le « toc » du micro,
  l'inspiration d'avant la phrase et le clic du bouton d'arrêt restent dehors. Dans les pauses, le souffle de la pièce
  est baissé de 24 dB. Pendant que tu parles, ta voix n'est pas touchée.
- **Modificateur** : nouvelle méthode **Naturelle (vocodeur)**, choisie par défaut. Ta voix est refaite par un vocodeur
  avec une autre hauteur et un autre timbre. La texture reste, même en bougeant le timbre.
  - **Praat** reste au menu : il est juste pour la hauteur, mais un peu rêche dès qu'on touche au timbre.
  - **Rubber Band** est retiré : c'était lui, le son « électrique ». Tes réglages qui l'utilisaient passent à
    Naturelle.
  - L'intonation marche maintenant avec les deux méthodes.
- Un essai avec la méthode Naturelle prend 3 à 5 s, et 8 s la première fois (chargement du vocodeur).
- **Khéops** : onglet Voix, « Appliquer à mes prises » est allumé, avec la mention « Nouveau nettoyage ». Un clic
  refait la voix avec le nouveau nettoyage, puis le montage, sans rien réenregistrer.

## 2. D'où venaient les bruits

Mesuré sur les 43 prises de Khéops (pièce à −63 à −73 dB) :
- **Whisper place souvent le premier mot à 0,00 s** (25 prises sur 43). La coupe partait donc du début de
  l'enregistrement, et gardait :
  - 0,3 à 0,8 s de souffle de la pièce ;
  - un « toc » grave du micro qui s'allume (−39 à −44 dB) ;
  - souvent une inspiration ;
  - et, à la fin, le clic du bouton d'arrêt.
- La voix est remontée d'environ 10 dB pour atteindre −18 LUFS, puis de 4 dB au mixage. Le « toc » arrivait ainsi
  vers −25 dBFS et le souffle vers −50 dBFS.
- Entre deux paragraphes, le montage met un silence numérique : le souffle s'allumait et s'éteignait net à chaque
  prise.
- Trois prises avaient un son isolé 1 à 2 s avant la phrase : bruit de bouche ou inspiration. Whisper ne l'avait pas
  transcrit.

**Corrigé** (`voice.clean_take`, `CLEANING_VERSION = 2`) :
1. **`speech_bounds`, la coupe** :
   - la voix, c'est au moins 60 ms sur 100 ms à plus de 20 dB au-dessus du bruit, et à moins de 25 dB sous son propre
     niveau. Un clic ou une inspiration n'y suffit pas ;
   - quand Whisper situe la phrase, un son plus de 0,5 s avant le premier mot (ou 0,6 s après le dernier) reste dehors ;
   - marges : la montée douce de la voix (200 ms au plus) puis 60 ms avant ; l'extinction (600 ms au plus) puis 150 ms
     après ;
   - les 120 premières et les 80 dernières ms de l'enregistrement sont écartées, sauf si la voix y est déjà ;
   - si la coupe tombe dans un mot que Whisper a entendu, elle recule.
2. **`pause_gain`, les pauses** : un expandeur doux. Il s'ouvre 60 ms avant la voix, reste ouvert 150 ms après, puis se
   referme en 200 ms. Il baisse les pauses de 24 dB, sans aller jusqu'au silence total.
   - Les inspirations entre les phrases (−42 à −50 dB) passent : elles font partie du jeu.
   - Mesure : 0 % des cases de la voix modifiées.
3. **Pièce bruyante** (plus de −58 dB) : DeepFilterNet 3 (`deep-filter.exe` de la publication officielle,
   `C:\YouTube2\models\voix`, téléchargé au premier besoin), limité à 18 dB de baisse. Repli : `afftdn`, réglé sur le
   bruit mesuré.
   - Pourquoi pas DeepFilterNet partout : sur la prise la plus calme, il baisse de plus de 4 dB 15 à 20 % des « s » au-dessus de 8 kHz.
   - L'expandeur seul ne touche pas la voix.
4. Fondus de 20 ms à l'entrée et de 50 ms à la sortie : la coupe tombe déjà dans une pause.

Résultat sur les 43 prises : la coupe tombe après le « toc » et l'inspiration, et la voix commence 60 ms après. Aucune
coupe ne mord dans un mot : entre le mot donné par Whisper et la coupe, il n'y a que le bruit de la pièce.

## 3. Le timbre « électrique »

Banc sur le paragraphe 2 de Khéops (23 s). Note de naturel : UTMOS (prédicteur de note d'écoute, 1 à 5), sur des
fenêtres de 8 s. Ta voix nettoyée : **3,15**.

| Réglage | Rubber Band (FFmpeg) | Praat | Rubber Band R3 | WORLD | **Vocodeur** |
|---|---|---|---|---|---|
| Timbre −6 % | 2,12 | 2,90 | 3,05 | 2,69 | **3,01** |
| Timbre +6 % | 2,15 | 2,72 | 2,99 | 2,59 | **3,01** |
| Hauteur −2 demi-tons | 1,84 | 2,85 | 1,82 | 2,69 | **3,06** |
| Grave (−1,5 demi-ton, timbre −8 %) | 2,16 | 2,92 | 2,42 | 2,73 | **3,01** |
| Débit 90 % / 110 % | — | 3,04 / 3,06 | — | — | 2,94 / 3,09 |

- **Rubber Band de FFmpeg** : l'ancien moteur R2, un vocodeur de phase, avec deux passes pour le timbre. C'est le son
  « phasé, électrique », et le réglage « gdf » de Luca l'utilisait. Il est retiré.
- Rubber Band R3 (pedalboard) : bon pour le timbre seul (rééchantillonnage puis R3), mauvais dès qu'il change la
  hauteur.
- **Vocodeur pc-NSF-HiFiGAN** (OpenVPI, celui d'OpenUTAU et de DiffSinger) : la note reste vers 3,0 quelle que soit la
  modification.
  - Refaire la voix sans rien changer coûte 0,14 point (3,01).
  - L'équilibre spectral reste à ±1 dB par bande jusqu'à 18 kHz.
- Ce n'est pas une conversion vers une autre voix : le vocodeur reçoit le spectre de ta voix (128 bandes mel) et ta
  courbe de hauteur. Pour modifier la voix, on ne touche qu'à ces deux entrées :
  - hauteur : la courbe multipliée ;
  - intonation : la courbe resserrée ou élargie autour de sa médiane ;
  - timbre : le spectre étiré sur l'axe des fréquences ;
  - débit : les trames interpolées.
- Calcul : processeur (onnxruntime), environ 0,15 s par seconde de voix, soit 3 à 4 s pour 23 s.

## 4. Où c'est

| Où | Quoi |
|---|---|
| `worker/longform/voice.py` | `read_voice`, `floor_of`, `speech_bounds`, `take_bounds`, `pause_gain`, `denoiser` / `deep_filter`, `clean_take(…, settings)`, `CLEANING_VERSION` |
| `worker/longform/vocoder.py` | modèle (`ensure_model`, téléchargé depuis la publication d'OpenVPI), spectre mel au format DiffSinger (identique à librosa), `resynthesize`, `shape_file` |
| `worker/longform/voice_mod.py` | `ENGINES = ("naturel", "praat")`, « rubberband » → naturel, `apply(…, settings)`, `VERSION = 2` (cache des essais) |
| `worker/steps/long_make.py` | `made_with.cleaning` ; `apply` reçoit les réglages du worker |
| `apps/dashboard/src/lib/voice-mods.ts` | méthodes et leurs explications, plus de curseur « Praat seulement » |
| `apps/dashboard/src/lib/long-types.ts` | `VOICE_CLEANING_VERSION`, `voiceCleaningOutdated`, `voiceNeedsRedo` |
| `apps/dashboard/src/components/long/long-detail.tsx` | mention « Nouveau nettoyage » à côté de « Appliquer à mes prises » |
| `C:\YouTube2\models\voix` | `deep-filter.exe` (27 Mo), `pc-nsf-hifigan\` (57 Mo, licence CC BY-NC-SA 4.0 des poids) |
| `C:\YouTube2\labo\2026-10-05-voix-naturelle` | le banc : scripts, environnement, UTMOS (1,3 Go, supprimable) |

Dépendance ajoutée au worker : `onnxruntime` (déjà installée par kokoro-onnx, maintenant déclarée).

## 5. Limites et suite

- **Licence** du vocodeur : CC BY-NC-SA 4.0, usage non commercial. Pendant la phase de test, on ne l'écarte pas. Pour une
  chaîne monétisée, il faudra le remplacer : un vocodeur NSF-HiFiGAN réentraîné sur des voix libres, ou BigVGAN v2
  (MIT, mais il ne règle pas la hauteur seul).
- La note UTMOS est un indicateur : elle a été entraînée sur l'anglais et ne regarde que jusqu'à 8 kHz. C'est ton
  oreille qui tranche (démos 3 à 9).
- Hésitations : pas de coupe automatique des « euh » (Whisper ne les écrit pas toujours). Si besoin : les repérer par
  l'énergie voisée entre deux mots, puis proposer la coupe dans le Studio voix.
