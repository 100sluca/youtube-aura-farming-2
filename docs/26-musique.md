# 26 · Musiques de fond : la bibliothèque de Luca et le son du montage

> 2026-09-28. Demande de Luca : 10 musiques à lui, dans le dossier `music` du dépôt, à poser sur les vidéos au lieu de
> générer une musique à chaque fois, chacune décrite (à quoi elle sert) ; d'autres suivront. Dans l'onglet Montage,
> régler le volume de base de chaque musique et de la voix IA (toutes les musiques n'ont pas le même niveau sonore),
> avec des niveaux de départ choisis par Claude. Garder quelle musique est sur quelle vidéo, pour voir si la musique
> joue sur le succès.

## 1. Ce qu'on trouve

**Montage → onglet Son** (à côté de Titre d'accroche, Sous-titres, Textes à l'écran). Revu le 28/09 après l'essai de
Luca (« un écran super chargé » avec les dix musiques listées, et aucun moyen de juger le mixage) :

- **À gauche, la vidéo de test** remplace l'aperçu 9:16 : un menu « Vidéo de test » (les dernières vidéos montées,
  récits d'abord) et la vraie vidéo. ▶ la joue avec **sa voix et la musique choisie, mixées aux réglages en cours** :
  bouger un curseur pendant la lecture s'entend aussitôt. « Son d'origine » (ou le haut-parleur de la vidéo) rend le son
  de son dernier montage, pour comparer. **Rendu exact avec le son** : le worker refait le son de la vraie vidéo avec le
  code du montage (bruitages compris, ≈ 2 s) ; c'est la preuve de ce que donnera la vidéo.
- **À droite, un menu « Musique »** : une musique à la fois, marquée « choix auto pour cette vidéo » quand c'est celle
  que le montage lui donnerait (sinon un lien « L'écouter » vers celle-ci). Dessous, sa durée, sa sonie mesurée, ses
  formats, ambiances et préférence, **Volume de cette musique**, **Début dans le fichier** (passer une intro trop
  calme), et la **fiche** dépliable : nom, description, formats, ambiances, préférence, « Utiliser cette musique », mise
  en garde. Ces réglages s'enregistrent aussitôt et valent pour tous les modèles.
- **Les niveaux du modèle** (enregistrés avec le modèle, bouton « Enregistrer ») : pour les récits narrés, *Voix IA*,
  *Musique sous la voix*, *Baisse pendant que la voix parle* ; pour les chantiers et les visites (sans voix), *Musique*
  et *Bruitages* ; et les formats où passe une musique.

L'écoute directe fait dans le navigateur le calcul du montage (§4) sur la voix et la musique ; elle n'a pas les
bruitages des chantiers et des visites (pas de piste séparée) : le rendu exact les ajoute. Le « Rendu exact » des
autres onglets reste muet : il montre l'habillage.

## 2. La bibliothèque

Dossier : `<dépôt>/music` (réglable : `MUSIC_LIBRARY_DIR` pour le worker et le dashboard). Une ligne par fichier dans
la table `music_tracks` (migration 0018), identifiant = nom du fichier sans extension. Le worker (à chaque montage,
`yt2 music list`) et le dashboard (à l'ouverture de l'onglet) tiennent la table à jour : un fichier ajouté apparaît
**« À décrire »** et ne sert qu'une fois un format coché ; un fichier retiré est marqué absent (la ligne reste pour
les statistiques) ; un fichier nouveau ou remplacé est mesuré (sonie intégrée EBU R128, FFmpeg, ≈ 1 s par piste).

Les 10 pistes du 28/09, décrites par Luca :

| Piste | Nom | Formats | Ambiances | Préférence | Sonie | Durée |
|---|---|---|---|---|---|---|
| music_0 | Majestueuse et sentimentale : histoires sentimentales, amours qui finissent mal, monuments, un peu médiévale | récit, visite | sentimental, tragique, majestueux | normale | −15,8 LUFS | 4:09 |
| music_1 | Narration douce : récits narrés, visites de lieux et d'appartements | récit, visite | posé, découverte | normale | −15,1 | 1:17 |
| music_2 | Narration douce (bis) : comme la 1, un peu moins | récit, visite | posé, découverte | moins souvent | −16,5 | 1:47 |
| music_3 | Badass, punchy : tour de force, spectaculaire, « aura » ; visites, monuments, construction impressionnante | récit, chantier, visite | épique, majestueux | normale | −7,2 | 1:44 |
| music_4 | Tranquille et joyeuse : construction de bâtiments. **Droits d'auteur à surveiller** | chantier | joyeux | normale | −12,2 | 4:29 |
| music_5 | Triste : histoires tristes ou sentimentales | récit | triste, sentimental | normale | −18,1 | 1:42 |
| music_6 | Narration d'histoires | récit | posé | normale | −6,9 | 1:30 |
| music_7 | Intrigante, enquête : histoires à comprendre, mystère ; aussi chantiers et visites. **À privilégier** | récit, chantier, visite | mystère, posé, découverte | souvent (×2) | −10,0 | 3:47 |
| music_8 | Voyage, nostalgie, un peu de solitude : histoires de voyage, construction, visites | récit, chantier, visite | voyage, sentimental, découverte | normale | −16,1 | 2:17 |
| music_9 | Tragique, découverte : comme la 0 (amours tragiques), aussi découverte de lieux, visites, récits | récit, visite | tragique, sentimental, découverte | normale | −6,7 | 2:35 |

11 dB séparent la plus faible (music_5) de la plus forte (music_9) : sans égalisation, la même consigne donnait une
musique inaudible sur l'une et envahissante sur l'autre.

Ajouter une musique : déposer le fichier (mp3, wav, ogg, m4a, flac, aac) dans le dossier, ouvrir l'onglet Son, cocher
ses formats et ses ambiances (ou donner sa description à Claude). Les fichiers audio sont dans le dépôt public (≈ 31 Mo
pour les dix) : ce sont les compositions de Luca, qu'il choisit de partager (29/09).

## 3. Quelle musique sur quelle vidéo

1. Le scénariste reçoit la liste des ambiances qui ont au moins une piste pour son format (consigne « MUSIQUE DE
   FOND », `music.mood_brief`) et écrit l'identifiant de l'ambiance dans `music_mood` : mystere, epique, majestueux,
   sentimental, tragique, triste, voyage, decouverte, joyeux, pose. Les anciennes ambiances anglaises (scripts déjà
   écrits, `series.music_moods`) sont traduites : mysterious et suspense → mystère, epic → épique, inspiring → épique
   ou joyeux, emotional → sentimental, luxury et elegant → découverte, calm → posé…
2. Au montage (`music.choose_track`), parmi les pistes actives du format de la vidéo : celles qui portent l'ambiance,
   sinon ses voisines (tragique → triste → sentimental, joyeux → découverte → posé…), sinon les ambiances conseillées
   par la série, sinon toutes. Tirage selon la préférence (« Souvent » : deux fois plus de chances), **le même pour
   une même production** : refaire le montage ne change pas la musique.
3. La piste retenue est gardée dans `videos.music_track` avec les niveaux (`videos.audio_mix`) ; un nouveau montage
   la reprend tant qu'elle est dans le dossier et active.

Sans bibliothèque (dossier ou migration absents), le montage prend l'ancienne bibliothèque générée
(`DATA_DIR/music/<ambiance>`, ACE-Step) ; une bibliothèque sans piste pour le format donne une vidéo sans musique,
signalée dans le journal (`assemble.sans_musique`). Décocher un format dans « Musique de fond sur » coupe la musique
de ce format.

## 4. Les niveaux : égalisation, puis réglages

Chaque voix et chaque piste sont d'abord ramenées au même niveau (sonie mesurée), puis on applique :

| Réglage | Départ | Ce que ça veut dire |
|---|---|---|
| Voix IA | 0 dB | voix égalisée à −18 LUFS (les moteurs sortent vers −18,8) |
| Musique sous la voix | −10 dB | la musique à 10 dB sous la voix (−28 LUFS) entre les phrases : bien audible, sans gêner |
| Baisse pendant que la voix parle | 4 dB | pendant chaque passage parlé, la musique descend encore de 4 dB (≈ 14 dB sous la voix) et remonte entre les phrases |
| Musique sans voix (chantiers, visites) | 0 dB | −20 LUFS, sous les bruitages : l'équilibre des chantiers et visites déjà publiés |
| Bruitages | 0 dB | volumes d'origine de worker/sfx.py |
| Volume d'une piste | 0 dB | s'ajoute au reste ; à baisser pour une piste qui couvre la voix |

Le mixage final est toujours ramené à −14 LUFS (loudnorm, le niveau auquel YouTube ramène les vidéos) : ces réglages
font l'équilibre entre voix, musique et bruitages, pas le volume du téléphone ; monter la voix revient à baisser la
musique. La baisse suit les mots horodatés de la narration (deux mots à moins de 0,7 s : même passage ; la musique
descend en 0,12 s avant la voix et remonte en 0,45 s après) : une rampe calculée, pas un compresseur, donc la même à
l'écoute et au montage. La musique commence au « Début » réglé, avancé si la vidéo dépasserait la fin du fichier ;
fondus de 0,6 s au début et 1,2 s à la fin.

**Musique très basse (30/09, demande de Luca : « parfois c'est vraiment trop fort pour mes oreilles »)** : les curseurs
*Musique sous la voix* et *Musique* descendent à −40 dB ; plus bas, on tape la valeur dans la case, jusqu'à −120 dB
(muette), dans l'onglet Montage → Son comme dans Retoucher. Le garde-fou de ±30 dB ne borne plus que l'égalisation d'une
piste (mesure aberrante), plus le réglage : avant, un réglage bas pouvait être rogné par lui (`mix_levels`, worker/music.py
et lib/audio-mix.ts).

Essai du 28/09 (hors appli, dans le dossier de travail de Claude) : « Miroir secret » remonté avec le nouveau code →
ambiance « mysterious » → music_7 ; final à −14,9 LUFS, musique seule entre les phrases à ≈ 10 dB sous les passages
parlés.

## 5. Statistiques

`videos.music_track` (piste), `videos.audio_mix` (piste, sonies mesurées, gains, baisse, ambiance, modèle) et, dans
`v_video_overview`, `music_track`, `music_title`, `audio_mix`. L'analyste des performances ventile par musique et le
tableau du Dashboard affiche la piste de chaque vidéo (docs/25). Les vidéos montées avant le 28/09 n'ont pas de piste
enregistrée (l'analyste reprend alors l'ambiance du script).

## 6. Droits

Une musique protégée peut valoir une réclamation Content ID (revenus reversés à l'ayant droit, parfois vidéo bloquée
dans certains pays) : music_4 porte la mise en garde de Luca, visible dans l'onglet. La musique de chaque vidéo étant
enregistrée, une réclamation se relie tout de suite à sa piste ; « Utiliser cette musique » la retire des tirages
suivants.

## 7. Fichiers

| Où | Quoi |
|---|---|
| `music/` | les pistes de Luca |
| supabase/migrations/0018_music_library.sql | `music_tracks` (et les 10 descriptions), `videos.music_track`, `videos.audio_mix`, `v_video_overview` |
| services/worker/worker/music.py | ambiances, bibliothèque (`sync_library`, `load_library`), choix, niveaux, baisse sous la voix |
| services/worker/worker/media.py | `measure_loudness` (EBU R128) ; ancienne bibliothèque (`pick_music`) |
| services/worker/worker/montage.py | `AudioLayer` : les niveaux du modèle |
| services/worker/worker/steps/assemble.py | `prepare_video` et `choose_music` (partagés par le montage et l'essai du son), `apply_audio`, `music_chain`, `audio_filters`, `sound_command` |
| services/worker/worker/steps/montage_preview.py | rendu exact avec le son (mode « sound » : image copiée, son refait) |
| services/worker/worker/steps/script.py, recipes.py | consigne « MUSIQUE DE FOND » du scénariste |
| services/worker/assets/montage/defaults.json | niveaux de départ, constantes du mixage, ambiances, voisines et traductions, lus par le dashboard (`tests/test_music.py` vérifie qu'ils suivent le code) |
| apps/dashboard/src/components/montage/audio-panel.tsx | onglet Son : menu « Musique », réglages et fiche de la piste, niveaux du modèle |
| apps/dashboard/src/components/montage/sound-test.tsx, use-mix-player.ts | vidéo de test, écoute du mixage calée sur l'image (Web Audio), rendu exact avec le son |
| apps/dashboard/src/lib/music-library.ts, audio-mix.ts | bibliothèque, vidéos d'essai et choix automatique d'une piste côté serveur ; calculs du mixage recopiés du worker |
| apps/dashboard/src/app/api/music/[id] | lecture d'une piste (requêtes partielles) |

`yt2 music list` : les pistes avec leur sonie, leurs formats et leurs ambiances (et mesure les nouvelles).

## 8. Idées pour la suite

Changer la musique d'une vidéo depuis sa fiche avant de refaire son montage ; un niveau de musique sans voix propre
aux chantiers et aux visites si les engins demandent une musique plus basse ; des bruitages dans l'écoute directe
(une piste de bruitages séparée par vidéo).
