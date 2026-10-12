# 67 · Studio du modificateur de voix (05/10)

Demande de Luca (05/10, après trois essais sur Khéops) :
- les voix d'arrivée de Chatterbox (narrateur grave, récit mystérieux, vieil homme) « font trop IA » ;
- pour en juger, il fallait refaire toute la vidéo (environ 15 min de voix et de montage), puis regarder ;
- il veut un endroit pour essayer sur un petit extrait, avec des réglages qu'il fait lui-même ;
- la voix doit changer un peu, pas trop, et rester celle d'un humain.

Page **Vidéos longues → Studio du modificateur** (`/long/voix`). Le lien est aussi dans l'onglet Voix de chaque vidéo et
dans les réglages de la page.

## 1. Pour Luca

1. **L'extrait** : une de tes prises (vidéo, puis passage), ou « Enregistrer un extrait » au micro (30 s au plus).
   L'essai porte sur les 25 premières secondes.
2. **Les curseurs** : chaque curseur relâché relance un essai. Le worker répond en 1 à 2 s.

   | Curseur | Ce qu'il change | Plage |
   |---|---|---|
   | Hauteur | plus grave ou plus aigu | ±4 demi-tons |
   | Timbre | la « taille » de la voix (formants) : plus ample ou plus claire | ±12 % |
   | Intonation | la mélodie des phrases : plus plate ou plus chantante (Praat seulement) | 50 à 150 % |
   | Débit | la vitesse de lecture ; les images suivent | 85 à 115 % |
   | Chaleur | les graves, vers 160 Hz | ±6 dB |
   | Présence | le médium qui rapproche la voix, vers 3 kHz | ±6 dB |
   | Brillance | les aigus et le souffle, vers 8,5 kHz | ±6 dB |
   | Densité | un compresseur : voix plus égale, plus « radio » | 0 à 100 % |
   | Pièce | un peu de résonance d'une petite pièce | 0 à 100 % |

   Cliquer sur la valeur d'un curseur le remet au neutre ; « Tout remettre à zéro » remet tout.
3. **L'écoute** : « Ta voix » / « Modifiée » passe de l'une à l'autre au même endroit, sans couper.
   - Espace pour écouter ou mettre en pause, A pour passer de l'une à l'autre.
   - Les deux sont nettoyées comme pour le montage et mises au même volume : on compare la voix, pas le niveau.
4. **Enregistrer le réglage** sous un nom. Ouvert depuis une vidéo, le Studio propose aussi « Enregistrer et appliquer
   à la vidéo ».
5. **Pour une vidéo** : onglet Voix, menu du modificateur.
   - Tes réglages viennent en premier, les voix d'IA de Chatterbox ensuite.
   - « Appliquer à mes prises » refait la voix puis le montage, sans rien réenregistrer.
   - Un réglage modifié dans le Studio après un montage rallume ce bouton.

**Méthode** (en bas des réglages) : **Praat**, la méthode par défaut, ou **Rubber Band**, à comparer à l'oreille.
- Praat (« Change gender », PSOLA) recopie la forme d'onde de ta voix période par période : la texture reste.
- Rubber Band est un vocodeur de phase. Il ne sait pas changer l'intonation.

## 2. Comment c'est fait

Aucun modèle d'IA, seulement du traitement du signal (`services/worker/worker/longform/voice_mod.py`) :
1. **Forme** (hauteur, timbre, intonation, débit).
   - Praat (`praat-parselmouth`) : la hauteur visée est la hauteur médiane de la prise × 2^(demi-tons/12).
   - Ou Rubber Band (filtre `rubberband` de FFmpeg). Le timbre seul s'y obtient en deux passes : tout décaler (voix et
     formants), puis ramener la hauteur en gardant les formants.
   - Rien n'est fait si ces quatre curseurs sont au neutre.
2. **Son** : étagère basse 160 Hz, cloche 3,2 kHz, étagère haute 8,5 kHz, compresseur (seuil −14 à −24 dB, rapport 1 à
   4), réverbération synthétique (réflexions à 7-29 ms, queue de 0,45 s adoucie dans les aigus).
3. **Niveau** : remis à −18 LUFS, comme la voix nettoyée, avec un limiteur.

**Mesuré sur la prise c0p1 de Khéops (23 s)** :
- essai fait en moins de 1 s ;
- hauteur −1,5 demi-ton demandée : −1,58 avec Praat, −1,45 avec Rubber Band ;
- débit 95 % : 24,25 s au lieu de 23,04 s.

| Où | Quoi |
|---|---|
| `worker/longform/voice_mod.py` | `PARAMS` (bornes), `normalize`, `apply` (une voix), `preview` (essai du Studio, en cache), `profile_params` |
| `worker/steps/long_take.py` | action `voice_mod` du job `long_take` (voie preview, pris dans la seconde) : pas de nouveau type de job ni de migration |
| `worker/steps/long_make.py` (`_voice`) | `modifier_voice = "reglage:<id>"` : chaque paragraphe nettoyé passe par `apply` ; débit changé = mots horodatés et durée multipliés d'autant ; `voice.made_with.params` garde le réglage utilisé |
| `app_settings.voice_mods` | `{"profiles": [{"id", "name", "params", "updated_at"}]}` |
| `<données>/voix-studio/` | `extraits/` (enregistrés au micro), `essais/` (original nettoyé et essais, nommés par l'empreinte du réglage) |
| `apps/dashboard/src/app/long/voix/page.tsx`, `components/long/voice-studio.tsx` | la page |
| `apps/dashboard/src/app/api/voice-studio/route.ts`, `file/route.ts` | essai (job), extrait (envoi), état de l'essai, fichiers d'essai (nom vérifié) |
| `apps/dashboard/src/lib/voice-mods.ts` | curseurs, libellés et bornes (les mêmes que `PARAMS`) |
| `components/long/modifier-select.tsx` | le menu du modificateur (réglages puis Chatterbox), onglet Voix et réglages de la page |
| `app/long/actions.ts` | `saveVoiceProfile`, `deleteVoiceProfile` (refusé si une vidéo en cours s'en sert), `setVoiceModifier` (`voiceNeedsRedo`) |

`praat-parselmouth` est ajouté aux dépendances du worker (`pyproject.toml`, `uv.lock`) et installé dans
`C:\YouTube2\worker-venv`.

## 3. Limites et suite

> **05/10 après-midi (docs/68)** : Rubber Band retiré (le son « électrique » du timbre) ; nouvelle méthode par défaut
> « Naturelle » (vocodeur pc-NSF-HiFiGAN), Praat en second ; l'intonation marche avec les deux. Le nettoyage des prises
> coupe maintenant sur la voix (plus de « toc » du micro ni de clic d'arrêt) et baisse le bruit des pauses.

- L'essai porte sur 25 s : assez pour juger le timbre. Pour juger le débit sur la durée, il faut appliquer à la vidéo.
- Les essais restent dans `voix-studio/essais` : environ 2,3 Mo par essai, à vider de temps en temps.
- Pistes si un réglage sonne encore faux :
  - un correcteur de hauteur plus fin (WORLD) ;
  - ou un léger chorus pour masquer la voix d'origine. Ce serait moins naturel.
