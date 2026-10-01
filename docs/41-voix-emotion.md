# 41 · Des voix qui jouent : l'émotion dans les voix

> 2026-09-29, demande de Luca : « au niveau des voix, c'est notre point noir : les voix IA manquent d'émotion, elles
> sont un peu plates. Regarde comment améliorer le système de voix, quelles voix et quels générateurs on peut utiliser
> en local, avec un banc : combien de temps pour les voix d'une vidéo complète, en comparaison de ce qu'on a déjà »
> (docs/29). Machine : RTX 3070 8 Go, 32 Go de RAM ; 6,4 Go libres sur C: ce jour, une production en cours.
>
> **30/09 : Luca retient Gemini** (« la comparaison 5, Gemini en ligne, c'est vraiment la meilleure ») pour toutes les
> vidéos, avec des clés réservées à la voix, le calage sur les lèvres à soigner, et la possibilité de refaire les voix
> d'une vidéo déjà faite depuis la Bibliothèque : §8.

## En bref

- **Pourquoi c'était plat** : le modèle qui dit nos voix Qwen (Base 0.6B, un clone) n'accepte aucune consigne, et le
  ton que le scénariste écrit pour chaque réplique d'un drame (« chuchoté, avide », « en larmes ») n'allait qu'au modèle
  vidéo. Mesuré : avec la voix actuelle, « C'est lui ! Le voleur ! » (crié) sort **plus bas** que les répliques
  chuchotées (−2,4 dB).
- **Fait le 29/09** : le ton de chaque réplique va jusqu'au moteur de voix ; trois façons de le jouer, sans rien
  télécharger (références émues, consigne VoiceDesign, Gemini en ligne) ; un menu **Réglages → Modèles de génération →
  Jeu des voix (drames)**, laissé sur « Voix neutres » tant que Luca n'a pas écouté ; un banc (§4) et 5 vidéos de
  comparaison dans **Bibliothèque → Démos et essais → « Voix avec émotion »**.
- **Mesures** (Madame Figue, 16 répliques, 4 personnages, RTX 3070) :

| Façon de dire | Où | Un drame complet | Récit de 75 s (estimé) | Crié − chuchoté | Variation de hauteur | Timbre constant (moy. / pire) |
|---|---|---|---|---|---|---|
| Voix actuelle (Qwen3 Base, sans ton) | carte graphique | 4 min 51 | ≈ 7 min | **−2,4 dB** | 1,8 | 0,90 / 0,85 |
| **Références émues** (Qwen3 Base + banque par voix) | carte graphique | 5 min 28 (20 min la toute 1re fois) | ≈ 8 min | **+5,4 dB** | 2,1 | 0,84 / 0,76 |
| Référence émue clonée telle quelle | carte graphique | 4 min 43 | ≈ 7 min | +3,6 dB | 2,1 | 0,85 / 0,71 |
| VoiceDesign 1.7B + ton | carte graphique | 4 min 28 | ≈ 6 min 20 | +2,6 dB | 2,1 | 0,87 / 0,82 |
| **Gemini 3.8 Flash TTS** + ton | en ligne | **2 min 22** | ≈ 4 min | **+7,8 dB** | **3,0** | 0,90 / 0,78 |

  Tous comprennent chaque mot (Whisper ne trouve que ses 3 homophones habituels, sauf VoiceDesign : une réplique
  ratée). Rappel docs/29, sans émotion : Kokoro 6 s, Pocket 20 s, Supertonic ≈ 30 s pour une narration de 40 s.
- **Recommandation** : écouter d'abord « comparaison 2 » (références émues) et « comparaison 5 » (Gemini).
  - En local, **Références émues** joue vraiment (cri et chuchotement enfin distincts) pour 13 % de temps en plus ; le
    timbre bouge un peu plus qu'aujourd'hui (0,84 contre 0,90).
  - La meilleure qualité est **Gemini** : le plus expressif, deux fois plus rapide. Il est gratuit, mais son quota
    n'est pas publié ; le 29/09, les modèles Gemini texte étaient saturés (erreurs 429 et 503). Le repli local est
    automatique, ce qui respecte ADR-007 (quota gratuit en appoint, avec repli local).

## 1. Pourquoi nos voix sont plates

Deux raisons, trouvées dans le code :

1. **Le modèle qui dit nos voix ne sait pas jouer.** Les 15 voix Qwen (narrateur, conteuse, `perso_mamie`…) sont
   « dessinées » une fois par le modèle VoiceDesign 1.7B, puis dites en production par le modèle **Base 0.6B**, qui
   clone la référence. Le modèle Base n'accepte **aucune consigne** (`generate_voice_clone` n'a pas d'argument
   `instruct`, confirmé par Qwen) : il reprend l'élan de sa référence, une phrase posée, sur toutes les répliques.
2. **Le ton écrit par le scénariste n'allait pas jusqu'à la voix.** Chaque réplique d'un drame porte un `tone`
   (« whispering, greedy », « weak, crying softly », « shouting, pointing »). Il servait au prompt du modèle vidéo
   (H3), jamais à l'étape voix : Kiwi disait « Je l'ai rendue ! À vous ! Hier soir ! » sur le même ton que « Bonsoir ».

## 2. Ce que disent les classements, en français

| Classement | Ce qu'il mesure | Résultat utile |
|---|---|---|
| Artificial Analysis, français (voix contrôlée, relevé du 29/09) | préférence à l'aveugle de francophones, voix clonées | en ligne : ElevenLabs v4 1370, Cartesia Sonic 3.6 1336, **Gemini 3.8 Flash TTS 1213** (7e), Flash-Lite TTS 1193 ; **aucun modèle ouvert dans les 19 premiers** : Voxtral 1063, Higgs V3 1057, Fish S2 Pro 1055, OpenAudio S1 Mini 1054 (à égalité, marge ± 21-31) ; Qwen3-TTS absent |
| MINT-Bench (04/2026, 10 langues) | expressivité et qualité en français | Gemini 2.5 Flash 3,70, Gemini 2.5 Pro 3,64, ElevenLabs v3 3,28, **Qwen3-TTS 1.7B VoiceDesign 3,17**, MiniMax 2.7 2,73 |
| chvalois/benchmark-tts (13/09, RTX 4090) | clonage d'une référence **émue** (colère, joie, peur, tristesse), duel à l'aveugle | FireRedTTS3 77 % (17 Go de VRAM), **OmniVoice 72 %**, VoxCPM2 52 %, XTTS-v2 50 %, Chatterbox V3 42 %, CosyVoice3 33 % ; Qwen3 non testé ; panel petit (± 0,3-0,7) |
| Hume RW-Voice-EQ (09/2026, surtout anglais) | intelligence émotionnelle de la voix | Gemini 3.8 Flash TTS 1er (0,920) |

Deux leçons : l'émotion en français se joue surtout **par la référence** (l'élan d'une phrase émue qu'on clone) ou
**par une consigne** en langage naturel ; et les notes automatiques (UTMOS, NISQA) ne collent pas à l'oreille de
francophones (corrélation ≈ 0) : seule l'écoute tranche.

## 3. Les façons de faire jouer une voix

| Façon | Exemple | Modèles | Limite |
|---|---|---|---|
| Consigne en langage naturel | « whispering, greedy » | Qwen3 VoiceDesign, Gemini TTS (`style`), VoxCPM2 (préfixe `(furieux)…`), CosyVoice3 | VoiceDesign retire le timbre à chaque appel : la voix bouge d'une réplique à l'autre |
| Balises dans le texte | `[whispers]`, `<\|emotion:anger\|>`, `(sobbing)`, `<sigh>` | Fish S2 Pro / S1 Mini, Higgs TTS 3, Gemini | fiables surtout en anglais (Fish : français « tier 2 ») |
| Curseur d'intensité | `exaggeration` 0,25-2 | Chatterbox V3 | dit « combien », pas « quelle » émotion |
| **Référence émue** | cloner une phrase dite en larmes | Qwen3 Base, OmniVoice, XTTS, dots.tts, Voxtral | une référence par émotion et par voix, dans le même timbre |
| Conversion de voix après coup | jeu expressif, puis timbre imposé | Chatterbox VC, Seed-VC, RVC | pertes sur les chuchotements et les cris |

## 4. Le banc « émotion » du 29/09

**Texte** : les 16 répliques de « Madame Figue » (production 38e4e7aa, 4 personnages), chacune avec le ton écrit par
le scénariste : « mischievous, slow », « exhausted, whispering », « weak, crying softly », « whispering, greedy »,
« shouting, pointing », « desperate, crying », « icy, quiet »… Chaque personnage garde sa voix (Madame Figue =
`perso_mamie`, Prune = `mystere`, Kiwi = `perso_humble`, Groseille = `perso_fillette` ; voix Gemini choisies d'après
leur description : Gacrux, Algieba, Achird, Leda). Vitesse 1,05, celle de la chaîne.

**Comme en production** : un appel au moteur par personnage (le modèle se charge une fois par voix), par la file du
worker (tâches « Essai de voix », priorité 5, entre deux clips, ComfyUI vidé avant) ; Gemini est appelé par le banc.
Le temps d'un drame additionne les 4 appels, chargements compris.

**Ce qu'on mesure** :

| Mesure | Comment |
|---|---|
| Temps d'un drame | somme des 4 appels (16 répliques), chargement compris ; « première fois » = avec la création de la banque de références émues |
| Récit de 75 s | estimé : chargement + 1 100 caractères au débit de calcul mesuré (une seule voix) |
| Mots mal compris | Whisper large-v3-turbo réécrit chaque réplique ; part des mots entendus autrement |
| Timbre constant | empreinte de voix (sherpa-onnx, wespeaker ResNet34) de chaque réplique comparée à la moyenne des répliques du même personnage (1 = identique) |
| Même voix qu'aujourd'hui | la même empreinte comparée à la référence de la voix Qwen du personnage |
| Crié − chuchoté | intensité moyenne des répliques criées moins celle des chuchotées (dB, avant l'égalisation du montage) : un moteur qui joue doit creuser l'écart |
| Juge à l'aveugle | Gemini 3.8 Flash écoute les 5 prises de chaque réplique dans un ordre tiré au hasard, sous des lettres, et note de 1 à 5 : émotion jouée, naturel, français natif, voix qui colle au personnage. Un repère, pas un verdict (Gemini peut préférer sa propre voix ; les notes automatiques collent mal à l'oreille de francophones) |

**Écouter** : Bibliothèque → Démos et essais → « Voix avec émotion » (la vidéo de Madame Figue redite par chaque
moteur, sur sa musique), et `C:\YouTube2\bench\2026-09-29-voix-emotion\index.html` (réplique par réplique, notes du
juge, scène entière par moteur). Refaire : `scripts/bench_emotion.py run | eval | judge | report | video` (en-tête du
script).

**Résultats** (29/09, pendant une production : clips entre les essais, RAM souvent saturée) :

| Variante | Un drame | Chargement moyen | × temps réel | VRAM | Mots mal compris | Timbre constant (moy. / pire) | Même voix qu'aujourd'hui | Crié − chuchoté | Hauteur |
|---|---|---|---|---|---|---|---|---|---|
| Qwen3 Base 0.6B, sans ton (aujourd'hui) | 291 s | 11 s | 0,18 | 3,4 Go | 2,4 % | 0,90 / 0,85 | 0,82 | −2,4 dB | 1,8 |
| Qwen3 Base + référence émue, timbre de la voix | 328 s (1re fois 1 209 s) | 12 s | 0,15 | 3,3 Go (4,7 Go en créant la banque) | 2,4 % | 0,84 / 0,76 | 0,72 | +5,4 dB | 2,1 |
| Qwen3 Base + référence émue telle quelle | 283 s | 11 s | 0,18 | 3,0 Go | 2,4 % | 0,85 / 0,71 | 0,72 | +3,6 dB | 2,1 |
| Qwen3 VoiceDesign 1.7B + ton | 268 s | 11 s | 0,23 | 4,5 Go | 5,7 % | 0,87 / 0,82 | 0,76 | +2,6 dB | 2,1 |
| Gemini 3.8 Flash TTS + ton (en ligne) | 142 s | 0,5 s | 0,38 | — | 2,4 % | 0,90 / 0,78 | autres voix | +7,8 dB | 3,0 |

Lecture :
- **Temps** : tous tiennent sous 6 min par drame, pour 16 répliques. La 1re fois qu'une voix a besoin d'une émotion,
  VoiceDesign crée sa référence (3 essais) : ≈ 1 min 15 par émotion, 20 min pour les 12 émotions des 4 personnages de
  Madame Figue. Elles restent ensuite dans `C:\YouTube2\tts\qwen3\voices\emotions`. Un seul chargement par vidéo
  (au lieu d'un par personnage) ferait gagner ≈ 40 s.
- **Jeu** :
  - Aujourd'hui, le cri de Prune sort à −25,8 dB, plus bas que ses chuchotements.
  - Avec les références émues, il monte à −16,3 dB ; avec Gemini, à −12 dB.
  - Le chuchotement de Kiwi (« Encore une nuit… ») : −24,7 dB avec les références émues, −29,1 dB avec Gemini. VoiceDesign le dit presque à voix normale (−17,9 dB).
- **Timbre** : banque choisie par l'encodeur de Qwen, qui voit 0,94 à 0,99 de ressemblance à la voix neutre.
  L'empreinte indépendante (wespeaker) voit plus d'écart : 0,72 à la référence, contre 0,82 pour la voix actuelle. Une
  partie de cet écart vient de l'émotion elle-même : une empreinte bouge quand on crie. Gemini garde 0,90 en jouant
  fort.
- **Garde** : une prise au débit impossible (mots ajoutés, phrase de la référence répétée) est refaite, 3 fois au
  plus. Au 1er passage, « Gardez la monnaie, jeune homme » durait 5,9 s au lieu de 1,2 s ; refaite, 1,2 s.
- **Juge à l'aveugle, partiel** : 5 répliques sur 16 notées avant l'épuisement du quota gratuit des modèles Gemini
  texte (429 et 503 sur 3.5 à 3.8 Flash le 29/09 après-midi). Il préfère Gemini sur Madame Figue (« l'âge est
  parfaitement crédible, le sous-entendu espiègle sur “exprès” est délicieux ») mais le trouve « caricatural » sur
  Prune et « trop grave et masculin » sur une réplique ; VoiceDesign capte « parfaitement le mélange de stupeur, de
  fragilité et de retenue » du chuchotement de Kiwi ; la voix actuelle est « plate » et « trop jeune » pour une
  septuagénaire. Trop peu de répliques pour classer : l'oreille de Luca tranche. À finir quand le quota revient :
  `bench_emotion.py judge <banc>` reprend là où il s'est arrêté.

## 5. Passer en production

- **Réglages → Modèles de génération → Jeu des voix (drames)** : « Voix neutres » (défaut, comme avant), « Références
  émues (local) », « Consigne d'émotion VoiceDesign (local) », « Gemini 3.8 Flash TTS (en ligne, repli local) ». Le
  choix vaut pour les prochaines voix de drame et pour « Nouvelle prise de voix » (Retoucher → Plans).
- Le jeu ne touche que les voix Qwen dessinées (`from: qwen3` dans catalog.json → acting) ; Kokoro, Pocket et
  Supertonic ne jouent pas.
- Gemini reçoit la description du personnage écrite par le scénariste avec le ton (« a warm elderly female voice in
  her seventies; icy, quiet ») et la voix Gemini de la voix Qwen (`params.gemini` des 15 voix dans catalog.json). En
  cas de quota épuisé : deux tours des 3 clés (≈ 1 min), puis « Références émues » prend le relais, noté
  `tts.jeu_repli` dans le journal du job.
- Les récits n'ont pas encore de ton par scène : leur voix ne change pas.

## 6. Suite proposée

1. **Écouter** : Bibliothèque → Démos et essais → « Voix avec émotion » (même image, 5 voix), ou
   `C:\YouTube2\bench\2026-09-29-voix-emotion\index.html` (réplique par réplique), puis choisir dans Réglages.
2. **Récits** : faire écrire au réalisateur un ton par scène (suspense, gravité, surprise), comme pour les répliques,
   pour que le narrateur joue aussi.
3. **OmniVoice** (3,3 Go) avec la même banque de références émues, puis **VoxCPM2** (5 Go), détails au §7 : il faut
   ≈ 10 Go libres sur C: → vider la Corbeille (≈ 9 Go).
4. **faster-qwen3-tts** pour la vitesse (rien à télécharger), une fois le jeu choisi.

## 7. Modèles à télécharger ensuite

Aucun n'a été installé ce jour : il restait 6,4 Go sur C: pendant une production (un modèle de plus aurait pu faire
échouer un rendu). Chiffres publiés, **non mesurés ici** ([É] éditeur, [C] communauté) :

| Modèle | Ce qu'il apporte | Français | À télécharger | Mémoire | Vitesse publiée | Windows | Verdict |
|---|---|---|---|---|---|---|---|
| **OmniVoice** 0,6B (k2-fsa) | le meilleur au duel « émotion » français parmi ce qui tient en 8 Go (72 %) ; WER 1,9 % ; pas de consigne : il clonerait **nos références émues** | banc chvalois | 3,3 Go | 5-7 Go [C] | RTF 0,23-0,29 sur 4090 | pip | **1er à essayer** : même banque, autre cloneur |
| **VoxCPM2** 2B (OpenBMB) | clonage + consigne libre en tête de réplique `(sobbing, broken voice)Pourquoi ?` | officiel (30 langues), émotion non prouvée en français | 5,0 Go (GGUF Q8 3,3) | ≈ 8 Go [É], 8,3-9,3 mesurés [C] : **trop juste** | RTF 0,30 sur 4090 [É] | `pip install voxcpm` | 2e, si le disque le permet ; seul modèle Apache qui clone et suit une consigne |
| Chatterbox Multilingual V3 (Resemble) | clonage + curseur d'intensité (`exaggeration`) | « accent naturel » [C] ; banc : naturel 3,05, émotion 42 %, « autre voix » 9 fois | 3,2 Go | ≈ 5 Go | 0,3-0,8 × temps réel [C] | pip (Python 3.11) | 3e : intensité seulement |
| Higgs TTS 3 4B (Boson) | 43 balises : 21 émotions, chuchoté, crié, pleurs, cris | français « tier 1 » | 5,1 Go (Q8, audio.cpp) | 5,9-9,1 Go ; clonage « pas assez de 8 Go » [É] | ? | binaires audio.cpp | non : trop lourd pour cloner |
| Fish Audio S2 Pro (GGUF) | balises libres `[angry] [whispers] [crying]` ; 3e ouvert en français (AA) | « tier 2 », balises parfois ignorées hors anglais [C] | 3,6-4,5 Go | 7,2 Go [C] | ? | s2.cpp à compiler (MSVC + CUDA) | non : installation lourde, VRAM au bord |
| Fun-CosyVoice3 0,5B | consigne `instruct2` + `[breath]`, `[laughter]` | émotion en français non prouvée ; colère courte ratée au banc (WER 29 %) | 4,4 Go | ? | 0,8 × temps réel sur 4090 | installation Linux surtout | non |
| faster-qwen3-tts | même Qwen3, calcul accéléré (CUDA graphs) | = Qwen | rien | = Qwen | ≈ 2 × temps réel sur RTX 4060 [C] | pip | pour la vitesse, pas l'émotion |

Écartés : IndexTTS-2/2.5, Step-Audio-EditX, Breeze TTS 2 (pas de français) ; FireRedTTS3 (17-20 Go), ZONOS2 (15 Go,
Linux) ; Voxtral ouvert (2 voix fixes, pas de clonage, ≥ 16 Go) ; Kyutai 1.6B (voix précalculées seulement).
Conversion de voix (garder un timbre après un jeu expressif) : Chatterbox VC (MIT, ≈ 4 Go) ou Seed-VC v1 (dépôt
archivé) — utile seulement si une voix expressive d'une autre source devait prendre le timbre de nos personnages.

**Pour installer OmniVoice ou VoxCPM2** : vider la Corbeille (≈ 9 Go, à faire par Luca) ; les environnements Python
réutilisent le PyTorch déjà téléchargé (liens physiques du cache uv), seul le modèle occupe de la place.

## 8. Gemini en production (30/09)

**Ce qui change pour Luca**
- **Réglages → Modèles de génération → Jeu des voix = Gemini 3.8 Flash TTS** (posé le 30/09) : les prochains drames
  sont joués par Gemini (chaque personnage garde sa voix Gemini du début à la fin, chaque réplique selon son ton) et les
  récits sont lus par Gemini avec la description de leur voix (voix française `qwen3:mystere` → Gemini « Algieba »).
  « Écouter » fait entendre la voix telle que les récits la diront.
- **Clés Gemini de la voix** (même carte des Réglages) : coller une ou plusieurs clés Google AI Studio ; Gemini les
  prend avant celles de Réglages → IA, pour que les voix ne mangent pas le quota des scripts. « Tester » fait dire
  « Bonjour. » et dit si le quota du jour est épuisé.
- **Bibliothèque → Retoucher → Voix** (toute vidéo produite, programmée comprise, docs/44) : pour un drame,
  « Voix des personnages » : le jeu actuel, chaque personnage avec sa voix (et sa voix Gemini), et **« Refaire les voix
  des personnages avec »** Gemini (ou les jeux locaux) ; « Refaire la vidéo » redit toutes les répliques puis remonte la
  vidéo calée sur les lèvres. Pour un récit : « Lecture de la narration » par Gemini, avec la voix choisie au-dessus.
  Le jeu choisi reste noté pour la vidéo (`videos.retouch.acting`) : une « Nouvelle prise de voix » (onglet Plans) le
  garde, donc le même timbre.

**Pourquoi la démo du 29/09 n'était pas calée sur les lèvres** : les vidéos « comparaison » posaient la voix Gemini sur
l'ancien montage (fait pour la voix Qwen), sans le calage de la production (worker/lipsync.py, docs/38) ; les répliques
de Gemini, plus longues et plus jouées, glissaient d'un plan à l'autre. En production, le montage recoupe chaque plan
autour de sa réplique et pose chaque phrase de la voix sur la phrase de la bouche (×0,8 à ×1,4 sans que la voix sonne
faux).

**Ce qui a été ajouté pour que Gemini tienne dans la bouche**
- Durée visée de chaque réplique : `lipsync.mouth_seconds` lit la transcription gardée avec le clip (faite à sa
  fabrication) et donne le temps où la bouche dit la réplique ; l'étape voix la passe au moteur (`targets`).
- `tts_runners/gemini_tts.py` : une prise hors de ×0,85-×1,3 de la bouche (marge dans le ×0,8-×1,4 du calage) est
  refaite avec une consigne de débit (« a faster pace: the whole line must fit in about 3.2 seconds »), deux fois au
  plus ; la prise la plus proche est gardée. Essai du 30/09 sur « Elle fait semblant d'être ruinée » (56cad13b) : les 17
  bouches connues ; 5 répliques sur 6 entre ×0,95 et ×1,20 dès la première prise. La 6e (« Elle doit avoir peur… J'y
  vais ce soir. », ×1,76) a une longue pause au milieu : le calage la coupe à sa pause et pose chaque morceau sur sa
  phrase de bouche.
- Pour les drames à venir, la voix se fait dans la file après les clips ou entre deux : si les clips ne sont pas encore
  transcrits, la réplique part sans durée visée et le calage fait le reste.

**Comment c'est fait**

| Où | Quoi |
|---|---|
| `catalog.json` → `acting.gemini` | `narration: true` (vaut aussi pour les récits) ; `params.gemini` des 15 voix Qwen (voix Gemini de chacune) |
| `worker/steps/tts.py` | jeu : payload `voice` = « acting:gemini » (retouche), puis `videos.retouch.acting`, puis les Réglages ; `mouth_targets` ; récit : `narration_acting` + `voice_description` ; une voix choisie à la main reste telle quelle |
| `worker/steps/voice_preview.py` | « Écouter » avec le jeu des Réglages (payload `raw` : voix brute) |
| `worker/settings_store.py` | `voice_keys` : app_secrets `gemini_voice_api_key`, `_2`… |
| `tts_runners/_common.py` | `synthesize(req, texte, ton, visée)` à 4 paramètres ; `voiced_seconds` |
| `apps/dashboard` | `app/settings/voice-actions.ts` (clés), `generation-settings.tsx` (Jeu des voix, Clés de la voix), `lib/retouch.ts` et `retouch-editor.tsx` (Voix des personnages), `retouch-actions.ts` (« acting:<jeu> » passé à `retouch_video`, sans migration) |

**Limites**
- Quota gratuit non publié : sans clé de la voix, Gemini partage les clés du LLM ; quota épuisé (429 sur toutes les
  clés, ≈ 1 min d'essais), la vidéo passe aux « Références émues » locales (journal `tts.jeu_repli`) : même personnage,
  autre timbre. Plusieurs clés de la voix évitent ce cas.
- Gemini ne clone pas (bloqué dans l'UE) : les personnages ont les voix du studio Gemini choisies d'après leur voix Qwen
  (`params.gemini`) ; une voix qui ne colle pas (« trop grave » pour Madame Figue au juge du 29/09) se change dans
  catalog.json.
- Filigrane SynthID inaudible sur l'audio Gemini ; la vidéo est déjà déclarée « contenu synthétique » (docs/05).

## Sources

- Artificial Analysis : [français, voix contrôlée](https://artificialanalysis.ai/text-to-speech/leaderboard/controlled-voice?accent=fr).
- Banc français indépendant : [chvalois/benchmark-tts](https://github.com/chvalois/benchmark-tts) (resultats/ecoute.md, EMOTIONS.md).
- MINT-Bench : [arXiv 2604.17958](https://arxiv.org/html/2604.17958) ; Hume : [RW-Voice-EQ](https://www.hume.ai/blog/newly-released-google-s-gemini-3-8-flash-tts-tops-hume-s-real-world-voiceeq-leaderboard).
- Qwen3-TTS : [dépôt](https://github.com/QwenLM/Qwen3-TTS) (le modèle Base ne prend pas de consigne ; « dessiner puis cloner »), [faster-qwen3-tts](https://github.com/andimarafioti/faster-qwen3-tts).
- Gemini TTS : [génération de voix](https://ai.google.dev/gemini-api/docs/speech-generation), [tarifs](https://ai.google.dev/gemini-api/docs/pricing).
- VoxCPM2 : [modèle](https://huggingface.co/openbmb/VoxCPM2), [guide](https://voxcpm.readthedocs.io/en/latest/usage_guide.html) ;
  OmniVoice : [modèle](https://huggingface.co/k2-fsa/OmniVoice) ; Chatterbox : [dépôt](https://github.com/resemble-ai/chatterbox) ;
  Higgs TTS 3 : [modèle](https://huggingface.co/bosonai/higgs-tts-3-4b), [consignes](https://huggingface.co/bosonai/higgs-tts-3-4b/blob/main/PROMPTING.md) ;
  Fish S2 Pro : [modèle](https://huggingface.co/fishaudio/s2-pro), [s2.cpp](https://github.com/rodrigomatta/s2.cpp) ;
  CosyVoice3 : [modèle](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512).
- Empreinte de voix du banc : [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) (wespeaker ResNet34, VoxCeleb).
