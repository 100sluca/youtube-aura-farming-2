# 34 · Retoucher une vidéo montée : titre, sous-titres, musique, mixage, voix

> 2026-09-28. Demande de Luca devant « Canal Rhin-Main-Danube » (5571fed9), parfaite sauf ses nombres écrits en lettres
> (montée avant la règle des chiffres, docs/33) : depuis la Bibliothèque, corriger à la main le titre d'accroche et les
> sous-titres puis refaire la vidéo ; de même changer la musique (un menu), le mixage, et refaire la voix avec une autre
> voix (un menu). « Globalement ce sera automatisé » : c'est un geste exceptionnel pour avoir le dernier mot sur une
> vidéo, qui ne modifie pas la chaîne de production.

## 1. Ce qu'on trouve

**Bibliothèque → fiche d'une vidéo → « Retoucher : titre, sous-titres, musique, voix »** (sous le lecteur), qui ouvre
`/library/<vidéo>/retouche`. Le bouton n'apparaît que pour une vidéo de l'appli, montée, dont les fichiers sont sur le
PC et **pas encore envoyée sur YouTube** (YouTube ne permet pas de remplacer le fichier d'une vidéo) : à valider,
autorisée mais pas encore partie, refusée ou en échec après son montage.

- **À gauche, la vidéo** telle qu'elle est, et sous elle **Son actuel / Nouveau mixage** : « Nouveau mixage » la joue
  avec sa voix et la musique choisie, aux niveaux réglés (même écoute que l'onglet Montage → Son, docs/26) ; bouger
  un curseur pendant la lecture s'entend aussitôt. Puis **« Refaire la vidéo »** avec la liste de ce qui changera, et
  « Revenir au montage automatique » (efface toutes les retouches au prochain « Refaire »). Pendant qu'elle est refaite :
  Voix → Montage → Contrôle, avec l'avancement ; ensuite la nouvelle vidéo s'affiche et « Publier cette vidéo ? »
  (autoriser, programmer, refuser).
- **Onglet Textes** : le titre d'accroche et **sa durée** (case **« Éphémère »**, 29/09 : décochée, il reste toute la
  vidéo ; cochée, il s'affiche le temps réglé au curseur « Affiché pendant », de 5 s à toute la vidéo, puis s'efface
  en fondu de 0,4 s ; départ : la durée du modèle de montage), puis les sous-titres **scène par scène** (▶ joue la scène dans la vidéo ;
  « La voix dit : … » quand l'affichage diffère de la narration ; « Rétablir » par champ). **« Nombres en chiffres »**
  remplit les champs avec la règle du montage automatique (worker/numbers.py, `to_digits`) : « treize cent cinquante
  tonnes » → « 1 350 tonnes », « en dix-neuf cent quatre-vingt-douze » → « en 1992 » ; Luca relit et corrige avant de
  refaire.
- **Onglet Musique et son** : un **menu « Musique »** (garder la musique actuelle, sans musique, ou une des pistes de la
  bibliothèque ; celle que le montage choisirait pour l'histoire est signalée), la fiche de la piste choisie et son
  **début dans le fichier** ; puis le **mixage de cette vidéo** : voix IA, musique sous la voix, baisse pendant que la voix
  parle (récits) ; musique et bruitages (chantiers, visites). Départ : les niveaux du modèle de montage.
- **Onglet Voix** (récits) : la voix actuelle, un **menu « Voix de cette vidéo »** et « Écouter » sur une phrase de la
  vidéo (job `voice_preview`, docs/18). Une autre voix = la narration est refaite avant le montage.

## 2. Ce qui est enregistré, ce qui est refait

La retouche vit dans **`videos.retouch`** (migration 0020), pour cette vidéo seulement : modèle de montage, prompts,
réglages des voix et bibliothèque de musiques ne bougent pas. On n'y garde que ce qui diffère du montage automatique :

| Clé | Contenu | Absent |
|---|---|---|
| `hook_title` | titre d'accroche affiché | celui du script (en chiffres, docs/33) |
| `hook_display` | `{"duration_s": 6}` : titre éphémère, 6 s fondu compris ; `{"duration_s": null}` : toute la vidéo | la durée du modèle de montage (onglet Montage → Titre d'accroche → Durée à l'écran) |
| `subtitles` | `{index de scène : texte affiché}` ; texte vide = pas de sous-titre sur la scène | les mots de la voix |
| `music` | `{"track": "music_7", "start_s": 12}` ; `track` null = sans musique | la musique du montage précédent (sinon tirée) |
| `audio` | niveaux `voice_db`, `music_db`, `duck_db`, `solo_db`, `sfx_db` | ceux du modèle de montage |
| `voice` | dernière voix choisie à la main (« moteur:voix ») | — |

« Refaire la vidéo » appelle le SQL **`retouch_video`** : il enregistre la retouche, annule un envoi en file, passe la
vidéo en « rendu » (une vidéo autorisée perd son créneau et revient à valider), puis met en file, priorité 20 :
- `tts` avec `{"voice": "pocket:estelle", "retouch": true}` **si la voix change** (voie GPU : après la tâche en cours) ;
- `assemble` `{"remount": true, "retouch": true}` (après la voix), puis `qa`.

Refusé si la vidéo est déjà sur YouTube, n'a pas de montage, ou si une voix, un montage ou un envoi tourne déjà pour
elle. Durée : ≈ 1 min de montage et de contrôle pour un récit de 30 s, plus quelques dizaines de secondes à 2-3 min de
voix selon le moteur (docs/29) ; **plus l'attente** si le worker finit un clip (il ne prend la tâche suivante qu'entre
deux clips GPU, jusqu'à 10 min). La vidéo actuelle est remplacée (même dossier `final.mp4`).

Le step `assemble` relit `videos.retouch` **à chaque montage** : un « Refaire le montage » ordinaire garde donc les
retouches. Il garde aussi dans son résultat les textes du montage automatique (`texts.hook`, `texts.subtitles`), d'où
l'écran part pour les champs non retouchés ; pour une vidéo montée avant le 28/09, l'écran part des mots de la voix.

## 3. Comment le worker applique la retouche (worker/retouch.py)

- **Sous-titres** : le texte retouché est **final**, il ne repasse pas par la conversion en chiffres. Ses mots sont
  recalés sur les mots horodatés de la voix (`retime`, difflib) : un mot inchangé (casse, accents, ponctuation ignorés)
  garde son moment ; un passage réécrit (« treize cent cinquante » → « 1 350 ») prend le temps des mots qu'il remplace ;
  un mot ajouté partage le temps de son voisin. « 1 350 » tapé avec une espace normale reste un seul mot (espace
  insécable) ; « 30 % », « 2 milliards », « 170 km » restent collés à leur nombre, dans la même légende.
- **Titre d'accroche** : celui de la retouche remplace `hook_text` (même dessin, même position : modèle de montage).
  Sa durée (`hook_display`) remplace celle du modèle ; un titre éphémère est lu en boucle le temps de son affichage,
  s'efface en fondu (`hooktitle.fade_filter`), puis la vidéo passe seule (`overlay … eof_action=pass`). Une durée au
  moins égale à celle de la vidéo vaut « toute la vidéo ». Le fondu vaut aussi pour la durée réglée dans le modèle.
- **Musique** (`choose_music(..., forced=)`) : la piste choisie est prise **même coupée ou hors de ses formats**, même
  sur un format où le modèle ne met pas de musique ; son départ peut être propre à la vidéo. Piste retirée du dossier :
  le montage reprend son propre choix (journal `retouche.musique_absente`).
- **Niveaux** : ceux de la retouche remplacent ceux du modèle (`AudioLayer`), avec les mêmes bornes ; toujours après
  l'égalisation de la voix et de la piste, et le son final ramené à −14 LUFS (docs/26).
- **Voix** : le step `tts` refait la narration avec la voix du payload même si elle existe déjà (sinon il ne refait
  jamais une voix faite) ; `videos.tts_provider` / `tts_voice` suivent. La durée des scènes suit la nouvelle voix ; les
  sous-titres retouchés sont recalés sur ses mots.

`videos.audio_mix` et le résultat du job notent ce qui a été retouché (`retouch`) ; une retouche illisible ou une base
sans la migration 0020 n'empêchent jamais un montage (journal, puis montage automatique).

## 4. Essai du 28/09

Sur « Piscine : le sol monte… » (4abd01d6, vidéo d'essai refusée le 25/09), pour ne pas toucher au canal que Luca veut
corriger lui-même : « Nombres en chiffres » (« en 90 secondes », « 20 personnes »), titre « Le sol monte en 90
secondes », une scène réécrite à la main (« tout doucement »), musique « Intrigante » (music_7) à −14 dB sous la voix,
voix Kokoro Siwis → Pocket TTS Estelle. Pour ne pas envoyer de mail « vidéo terminée » sur une vieille vidéo refusée,
une alerte `video_ready` déjà close a été posée pour elle avant l'essai (docs/32 : un seul mail par vidéo).

- Voix refaite en 25 s, montage juste après : titre et sous-titres corrects, calés sur la nouvelle voix (« EN 90
  SECONDES », « DOUCEMENT SOUS LA », « 20 PERSONNES »), music_7, niveaux notés dans `videos.audio_mix`.
- Le contrôle attend la fin du clip GPU en cours : le worker ne prend ses tâches qu'entre deux clips (jusqu'à 10 min).
- **Contrôle qualité refusé : −16,1 LUFS** (il faut −15 à −13). La voix Pocket est très dynamique (LRA 12,5 LU) et le
  `loudnorm` en une passe du mixage reste 2 LU sous la cible (même mixage sans retouche : −16,1 aussi ; la voix Qwen du
  canal donne −14,7).
- Après la correction du §5, « Refaire la vidéo » sans rien changer : +1,8 dB, −14,28 LUFS, contrôle passé ; la vidéo a
  été remise « Refusée » ensuite (SQL `reject_video`), sans mail.
- Le même après-midi, Luca a retouché le canal lui-même (titre « Le projet colossal : 70 ans pour relier deux fleuves »,
  six scènes en chiffres ; « 1 350 tonnes » est venu du montage automatique, docs/33) : montage en 13 s, +0,6 dB,
  −14,15 LUFS, à valider.

## 5. Correction du niveau final (tous les montages)

Mesuré sur les deux vrais mixages : une passe seule −16,07 (Pocket) et −14,68 (Qwen) ; loudnorm en deux passes −14,18
et −14,27. Le montage garde sa passe (elle égalise la voix) puis **mesure le final** : hors de −14 ± 0,5 LUFS, il le
corrige d'un gain avec un limiteur (crête −1 dB), image copiée (`fix_level`, ≈ 2 s ; `audio_mix.level_fix_db`, journal
`assemble.niveau_corrige`). Sur le final refusé : −13,7 LUFS, crête −1,0 dB. Vaut pour tous les montages, pas seulement
les retouches : une voix Pocket choisie dans Réglages aurait eu le même refus.

Après un échec, « Refaire la vidéo » reste possible sans rien changer (il relance le montage avec la retouche enregistrée).

## 6. Fichiers

| Où | Quoi |
|---|---|
| supabase/migrations/0020_retouche_video.sql | `videos.retouch`, SQL `retouch_video` |
| services/worker/worker/retouch.py | `Retouch`, `load_retouch`, `retime`, `display_tokens`, `forced_music` |
| services/worker/worker/steps/assemble.py | `prepare_video` (sous-titres retouchés, textes automatiques), `choose_music(forced=)`, niveaux et titre dans `AssembleStep`, `fix_level` (niveau du final, §5) |
| services/worker/worker/steps/tts.py | voix imposée par le payload (`voice`) |
| services/worker/tests/test_retouch.py | recalage des mots, nombres collés, musique et niveaux imposés, montage, voix |
| services/worker/tests/test_hook_ephemeral.py | durée du titre retouchée (prime sur le modèle), boucle et fondu, vrai rendu FFmpeg |
| apps/dashboard/src/app/library/[id]/retouche/page.tsx | la page |
| apps/dashboard/src/components/library/retouch-editor.tsx | l'écran (onglets, écoute, avancement) |
| apps/dashboard/src/lib/retouch.ts, retouch-types.ts | données de l'écran et état de la vidéo pendant qu'elle est refaite |
| apps/dashboard/src/app/library/retouch-actions.ts | `retouchVideo`, `fetchRetouchState`, `suggestDigits` (Python du worker : `worker.numbers.to_digits`) |
| apps/dashboard/src/components/library/library-sheet.tsx | bouton « Retoucher » |

## 7. Idées pour la suite

Retoucher aussi les textes à l'écran (chantiers, visites) ; garder la version d'avant pour revenir en arrière d'un clic
(≈ 50 Mo par vidéo) ; aperçu du titre et des sous-titres sur l'image avant de refaire (éditeur de l'onglet Montage).
