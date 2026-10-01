# 29 · Banc d'essai des voix : combien de temps pour dire un Short, et avec quelle qualité

> Suite le 29/09 : l'émotion dans les voix, avec un banc sur les répliques d'un drame (`41-voix-emotion.md`).

> 2026-09-28, demande de Luca : « le même tableau que pour les vidéos et les images » (`21-modeles-hugging-face-8go.md`
> §7-8), pour les voix : combien de caractères en combien de temps, le temps total, la qualité ; ensuite, installer
> d'autres modèles pour les écouter. Phase de test : **les licences ne comptent pas** (un mot au plus). Machine :
> RTX 3070 8 Go, i7-14700K, 32 Go de RAM ; 6,9 Go libres sur C: ce jour.

## En bref

- **Qwen3-TTS est la meilleure voix installée, sauf pour la vitesse.** Il fait 0 à 2 % de mots mal compris (3 voix sur
  6 sans aucune faute) et donne les lectures les plus vivantes. En revanche, il met 2 à 2,5 min par Short, soit
  45 à 55 min par semaine. Deux précisions :
  - Ces temps ont été mesurés pendant une production, RAM saturée : au calme, il va plus vite.
  - La version accélérée de la communauté (faster-qwen3-tts, « CUDA graphs ») dépasse 2 × le temps réel sur une carte
    8 Go, soit ≈ 20 s par Short avec les mêmes voix.
- **Kokoro est le plus rapide.** Il lui faut 6 s par Short sur le processeur (4,7 × le temps réel), avec 1 % d'erreurs.
  Mais il n'a qu'une voix, et plate.
- **Pocket TTS (Estelle)** : 20 s par Short et 1 % d'erreurs. Il a trois défauts :
  - c'est la lecture la plus monotone ;
  - il parle très vite : 26,5 caractères par seconde de voix, contre 16 à 21 pour les autres ;
  - il laisse un bruit (« pas ») au début.
- **Supertonic 3** : 27 à 32 s par Short, mais 2 à 8 % d'erreurs. Il écorche :
  - les nombres composés : « soixante-dix » entendu « 60 dix », « dix-neuf cent quatre-vingt-douze » → « DX9-192 » ;
  - les noms propres : Rhin → « Rennes », Main → « Maine ».
  
  À éviter pour les récits, pleins de dates et de chiffres.
- **Pour faire mieux**, on s'appuie sur le classement français à l'aveugle d'Artificial Analysis (votants natifs).
  Aucun de nos 4 moteurs n'y figure. Les meilleurs modèles ouverts sont Voxtral (1066), Fish Audio S2 Pro (1056),
  OpenAudio S1 Mini (1054), Higgs Audio V3 (1053) et XTTS-v2 (1022). Les premiers modèles en ligne sont Cartesia
  (1342), ElevenLabs v3 (1260-1287) et Gemini 3.8 Flash TTS (1216). Sur cette machine, avec ≈ 7 Go de disque libre,
  l'ordre proposé (§3) :
  1. faster-qwen3-tts : rien à télécharger ;
  2. OmniVoice : 3,3 Go ;
  3. VoxCPM2 : 5 Go ;
  4. Chatterbox Multilingual V3 : 3,2 Go ;
  5. Fish S2 Pro en GGUF (4,5 Go), ou Voxtral quantifié (2,4 à 4,3 Go, 2 voix fixes).

## 1. Le banc

- **Texte** : une vraie narration de Short (production dc8c681d, canal Rhin-Main-Danube, scènes 1 à 7) : 573
  caractères, 86 mots, nombres en toutes lettres comme les écrit l'agent script (« treize cent cinquante », « dix-neuf
  cent quatre-vingt-douze »), noms propres, mots longs. Vitesse 1,05, celle de la chaîne.
- **Deux façons de faire parler une voix**, choisies pour coller à la production :
  - **Qwen3-TTS, sur la carte graphique** : un essai par voix passe par la file du worker, comme le bouton « Écouter »
    des Réglages (tâche « Essai de voix »). Le worker l'intercale entre deux clips et vide ComfyUI avant. Un essai
    « Bonjour. » mesure le chargement.
  - **Les moteurs sur le processeur** : le banc les lance lui-même, scène par scène, comme l'étape « voix » des
    productions (un texte par scène, modèle chargé une fois). C'est important : dites d'un seul bloc, Kokoro et
    Supertonic mettent 2,5 à 3 fois plus longtemps (mesuré).
- **Conditions** : le banc a tourné pendant la fabrication de la vidéo Rhin-Danube (clips MiniMax H3), avec 0,6 à
  3 Go de RAM libre. Les deux premières voix Qwen (narrateur, conteuse) sont passées quand la RAM était la plus
  saturée ; le chargement de Qwen (47 s) est sans doute moitié moindre au calme.
- **Mesures** :

| Mesure | Ce que c'est |
|---|---|
| Chargement | démarrage du moteur et du modèle ; payé une fois par vidéo (Kokoro reste chargé dans le worker : rien à payer) |
| Calcul | temps pour dire les 573 caractères, chargement exclu |
| Caractères / s | caractères dits par seconde de calcul |
| × temps réel | secondes de voix obtenues par seconde de calcul (> 1 : plus rapide que la parole) |
| 1 000 caractères · un Short · semaine | chargement + calcul ; semaine = 21 Shorts |
| Débit de parole | caractères par seconde de voix : rythme perçu (≈ 16 : posé, ≈ 21 : rapide) |
| VRAM · RAM | hausse de la mémoire de la carte pendant l'essai · pic de RAM des processus du moteur |
| Mots mal compris (WER) | part des mots que Whisper large-v3-turbo n'entend pas comme écrits (mot sauté, mal prononcé, accent). Deux écarts dus à Whisper lui-même sont neutralisés : « km » pour « kilomètres », et « chalands » (mot rare, entendu « chalants » ou « chalons » pour les 18 voix) |
| Variation de hauteur | écart-type de la hauteur de la voix en demi-tons : ≈ 2 = monotone, ≥ 3 = lecture vivante |

- **Écouter** : `C:\YouTube2\bench\2026-09-28-1408-voix\index.html`. La page a un lecteur par voix, un tableau triable
  et ce que Whisper a entendu. Les mêmes chiffres sont dans `README.md` et `results.csv` (pour Excel).
- **Refaire** (depuis `C:\YouTube2`, `.env` du worker exporté) :

```bash
UV_PROJECT_ENVIRONMENT=C:/YouTube2/worker-venv uv run --frozen --project <dépôt>/services/worker \
    python <dépôt>/services/worker/scripts/bench_voice.py run --voices qwen3            # carte graphique : file du worker
UV_PROJECT_ENVIRONMENT=C:/YouTube2/worker-venv uv run --frozen --project <dépôt>/services/worker \
    python <dépôt>/services/worker/scripts/bench_voice.py run --direct --voices kokoro,pocket,supertonic --dir <banc>
C:/YouTube2/tts/eval/venv/Scripts/python.exe <dépôt>/services/worker/scripts/bench_voice.py eval <banc>
C:/YouTube2/tts/eval/venv/Scripts/python.exe <dépôt>/services/worker/scripts/bench_voice.py report <banc>
```

Options de `bench_voice.py` :
- `--voices` : moteurs ou voix (`qwen3,pocket:estelle`) ;
- `--dir` : complète un banc existant, par exemple avec un nouveau moteur ;
- `eval` : attend d'avoir ≈ 3 Go de RAM libre avant de charger Whisper, qui ne tourne donc jamais pendant un clip H3.

L'outil d'évaluation (Whisper, 1,6 Go) s'installe avec `install_tts.ps1 -Engine eval`.

## 2. Voix installées : mesures du 28/09

| Moteur (voix) | Mots mal compris | Lecture | Calcul sur | Mémoire | Disque | Chargement | 1 000 caractères | Un Short (573 car.) | Semaine (21) | Débit |
|---|---|---|---|---|---|---|---|---|---|---|
| **Qwen3-TTS 0.6B** (6 voix dessinées) | **0 à 2,1 %** (3 voix sans faute) | **vivante (2,6-3,6)** | carte graphique | VRAM 3,0-3,4 Go + RAM 2,5 Go | 15 Go | 47 s* | 3-4 min | 2-2,6 min | 42-54 min | 16,4-21,4 |
| Kokoro 82M (Siwis) | 1,1 % | moyenne (2,6) | processeur | RAM 0,5 Go | 0,3 Go | 2,5 s, une fois | **10 s** | **6 s** | **2 min** | 20,5 |
| Pocket TTS 3.3 (Estelle) | 1,1 % + bruit au début | **monotone (2,0)** | processeur | RAM 1 Go | 0,8 Go | 4,6 s | 32 s | 20 s | 7 min | **26,5 (très rapide)** |
| Supertonic 3 (10 voix) | 2,1 à 8,4 % | 2,2-3,5 | processeur | RAM 0,5 Go | 0,4 Go | 3-5 s | 44-53 s | 27-32 s | 9-11 min | 17,6-23 |

\* Mesuré RAM saturée pendant un clip H3 : sans doute 15-20 s au calme. Le chargement de Qwen est payé à chaque vidéo
(le modèle est rechargé par l'étape « voix »), d'où l'écart entre 1 000 caractères et « calcul seul » (5-8 caractères/s).

Voix par voix :

| Voix | Mots mal compris | Écarts entendus par Whisper | Variation de hauteur | Débit | Voix pour 573 car. | Un Short |
|---|---|---|---|---|---|---|
| qwen3:mystere (récit mystérieux, h) | 0 % | — | 2,6 | 16,4 | 34,9 s | 2 min 35 |
| qwen3:energique_h (présentateur dynamique) | 0 % | — | 3,5 | 21,3 | 26,9 s | 2 min |
| qwen3:energique_f (présentatrice énergique) | 0 % | — | 3,1 | 21,4 | 26,8 s | 2 min 03 |
| qwen3:narrateur (narrateur grave) | 1,1 % | Main → « mann » | 2,8 | 17,2 | 33,3 s | 2 min 33 |
| qwen3:elegante (voix élégante, luxe) | 1,1 % | Seize → « zezes » | 3,6 | 18,2 | 31,4 s | 2 min 13 |
| qwen3:narratrice (conteuse chaleureuse) | 2,1 % | Main → « mâne », Seize → « ces » | 3,1 | 18,5 | 30,9 s | 2 min 18 |
| kokoro:ff_siwis | 1,1 % | Seize → « ces » | 2,6 | 20,5 | 28,0 s | 6 s |
| pocket:estelle | 1,1 % | « pas » ajouté au début | 2,0 | 26,5 | 21,7 s | 20 s |
| supertonic:F3 | 2,1 % | Main → « Maine », « dix » avalé | 3,2 | 17,6 | 32,5 s | 32 s |
| supertonic:F5 | 2,1 % | Rhin → « Rennes », Main → « Maine » | 2,4 | 19,0 | 30,2 s | 31 s |
| supertonic:M5 | 4,2 % | Rhin, Main, dix-neuf cent… | 2,6 | 18,2 | 31,4 s | 28 s |
| supertonic:F1, M2, M3, M4 | 5,3 % | Rhin, Main, soixante-dix → « 60 dix », 1992 | 2,2-3,5 | 18,6-23,0 | 24,9-31,4 s | 27-32 s |
| supertonic:F4 | 6,3 % | « digues », « en » pour « ans » | 2,2 | 21,6 | 26,5 s | 27 s |
| supertonic:F2 | 7,4 % | Rhin, nombres | 3,3 | 20,5 | 28,0 s | 32 s |
| supertonic:M1 | 8,4 % | Rhin, Main, 743 pour 793, 13 150 pour 1 350 | 3,5 | 18,9 | 30,4 s | 30 s |

Hauteur médiane (pour situer les voix) : narrateur 88 Hz, mystère 109 Hz, M5 94 Hz… jusqu'à conteuse 324 Hz. Mesure
indicative (méthode YIN, erreurs d'octave possibles sur les voix aiguës).

## 3. Les autres modèles : ce qu'on pourrait installer pour les écouter

Classement français à l'aveugle d'Artificial Analysis (« voix contrôlée », une voix d'homme et une de femme clonées pour
tous les modèles, votants de langue maternelle, relevé le 28/09) : les Elo ne se comparent qu'à l'intérieur de ce
classement. Banc français indépendant : chvalois/benchmark-tts, 12-13/09/2026, sur RTX 4090, avec 9 auditeurs. Autres
chiffres : [É] = annoncé par l'éditeur, [C] = retour de la communauté.

| Modèle | Qualité en français | À télécharger | Mémoire | Vitesse publiée → Short estimé ici | Voix françaises | Licence | Tient ? |
|---|---|---|---|---|---|---|---|
| **faster-qwen3-tts** (même Qwen3, CUDA graphs) | = nos voix Qwen (WER FR 2,93 % [É]) | **rien** (0.6B déjà là) | ≈ 3-4 Go VRAM | 2,26 × temps réel sur RTX 4060 8 Go [C] → **≈ 15-20 s** | nos 6 voix dessinées | Apache | **oui** |
| Qwen3-TTS 1.7B Base | WER FR 2,86 % (0.6B : 2,93) [É] : gain faible | 3,9 + 0,7 Go | ≈ 6 Go VRAM | 1,83 × avec CUDA graphs (4060) [C] → ≈ 20-25 s | voix dessinées (VoiceDesign) | Apache | oui |
| **OmniVoice** (0,6B) | banc indépendant : **WER 1,9-3,6 %**, 1er des < 1B, 72 % au duel « émotion » ; [É] WER 3,35 % | 3,3 Go (GGUF Q8 ≈ 1 Go) | pic 5,5-6,7 Go | RTF 0,23-0,29 sur 4090 → ≈ 30-60 s (estimé) | voix créée par attributs (genre, âge, hauteur) + clonage | CC BY-NC | **oui** |
| **VoxCPM2** (2B) | banc : WER 3,2-6,3 %, naturel 3,20 (le meilleur mesuré ≤ 2B) ; [É] WER 4,5 % | 5,0 Go (GGUF 3,6) | ≈ 8 Go (10 Go vus sur 4090) : juste | RTF 1,6 sur 4060 [C] (plus lent que la parole) → ≈ 1-2 min | voix par description + clonage, 48 kHz | Apache | juste |
| **Chatterbox Multilingual V3** (0,5B) | banc : WER 4,2-7,5 %, meilleur naturel des < 1B (3,05) mais accent entendu 6 fois | 3,2 Go (fichiers v3 seuls) | 6,1-7,7 Go : juste | ONNX RTF 0,39-0,57 sur RTX 3070 portable [C] → ≈ 20-40 s | clonage + curseur d'émotion | MIT (+ filigrane) | juste |
| Fish Audio S2 Pro (GGUF Q6_K) | **AA FR 1056** (n° 2 ouvert) ; WER 3,05 % [É] | 4,5 Go | 6-8 Go [C] | inconnue sur 3070 (s2.cpp, « alpha ») | clonage + 15 000 balises d'émotion | recherche (NC) | juste |
| Voxtral 4B (int4 ou GGUF) | **AA FR 1066** (n° 1 ouvert) ; WER 3,22 % [É] | 2,4-4,3 Go | 3,8 Go (int4) [C] | 4,6 × temps réel sur 3090 [C] → ≈ 15-25 s | 2 voix fixes (fr_female, fr_male), pas de clonage | CC BY-NC | juste (outils Windows jeunes) |
| XTTS-v2 (fork coqui-tts) | AA FR 1022 ; banc : WER 6,6 %, naturel 2,86 | 2,1 Go | 3,8-5,9 Go | RTF 0,24 sur 4090 → ≈ 20-40 s | clonage (6 s) | CPML (NC) | oui |
| Kyutai TTS 1.6B en_fr | WER FR 2,96 % (texte long) [É] | 4,1 Go | 6-8 Go | 3,2 × sur H100 | voix fixes (CML-TTS) | CC BY | oui |
| dots.tts MF (2B, août 2026) | WER FR 3,26 % [É] | 5,2 Go | pic 5,7 Go | RTF 0,13-0,21 sur H800 | clonage seulement | Apache | oui (Windows non documenté) |
| Pocket TTS `french_24l` | = le modèle installé (WER 4,70 contre 4,56 %) [É] | 0,67 Go | processeur | ≈ 2 × plus lent → ≈ 40 s | Estelle | CC BY | oui, sans intérêt chiffré |
| Magpie TTS Multilingual 357M (NVIDIA, juillet 2026) | CER FR 1,54 % [É] | 1,5 Go + NeMo | ? | 14,7 × sur H100 | 5 voix fixes | NVIDIA | installation lourde (WSL) |

Impossibles ou sans objet sur cette machine :
- trop lourds : Higgs TTS 3 (9,3 Go, ≈ 11 Go de VRAM), FireRedTTS3 (12,3 Go, 17 Go de VRAM), MOSS-TTS 8B en bf16 ;
- sans français : IndexTTS2, Spark-TTS, Dia, VibeVoice ;
- illisible en français : F5-TTS de base (plus de 100 % d'erreurs).

Nouveaux modèles de juillet à septembre 2026 dans les tendances Hugging Face : presque aucun ne parle français
(Breeze TTS 2, n° 1 des ouverts d'Artificial Analysis, ne parle qu'anglais et chinois).

## 4. En ligne, gratuit : pour comparer à l'oreille

| Service | Gratuit | Limite | Elo AA (voix du service → français) |
|---|---|---|---|
| Gemini 3.8 Flash TTS (clé AI Studio) | oui | quotas non publiés, filigrane SynthID | 1267 → **1216** |
| Azure Speech F0 (Denise, Henri, Vivienne) | 0,5 M caractères / mois | 20 requêtes / min, API officielle | Azure HD 1127 (anglais) |
| Google Cloud Chirp 3 HD | 1 M caractères / mois | facturation à activer | 1053 (anglais) |
| ElevenLabs Free | ≈ 10 min / mois | pas d'usage commercial, mention obligatoire | 1197 → 1287 |
| Inworld | jusqu'à 70 min | licence commerciale incluse | 1246 → 1256 |
| Edge TTS | sans quota publié | pas d'API officielle (contournement interdit par Microsoft) | — |

Aucun n'est gratuit sans limite : ces services servent à comparer à l'oreille, pas à produire (règle de gratuité, ADR-007).

## 5. Suite proposée

1. **faster-qwen3-tts** sur nos 6 voix Qwen : même qualité, jusqu'à 6 fois plus rapide annoncé ; rien à télécharger
   (un paquet Python dans `C:\YouTube2\tts\qwen3`). À mesurer ici avec `bench_voice.py`.
2. **OmniVoice** (3,3 Go) à écouter face à Qwen : c'est le meilleur du banc français indépendant, et ses voix se créent
   par attributs, sans cloner personne.
3. **Refaire la mesure de Qwen au calme** (sans clip H3) pour le vrai temps de chargement.
4. Supertonic : ne plus le proposer pour les récits (nombres et noms propres), ou n'y garder que F3 et F5.
5. Disque : ≈ 7 Go libres, donc un seul nouveau modèle à la fois.

## Sources

- Classements Artificial Analysis (relevé du 28/09/2026) : [français, voix contrôlée](https://artificialanalysis.ai/text-to-speech/leaderboard/controlled-voice?accent=fr),
  [voix des fournisseurs](https://artificialanalysis.ai/text-to-speech/leaderboard/provider-voice), [méthode](https://artificialanalysis.ai/text-to-speech/methodology).
- Banc français indépendant : [chvalois/benchmark-tts](https://github.com/chvalois/benchmark-tts/blob/main/resultats/comparatif.md)
  ([écoute](https://github.com/chvalois/benchmark-tts/blob/main/resultats/ecoute.md)).
- Qwen3-TTS : [rapport technique](https://arxiv.org/html/2601.15621v1), [faster-qwen3-tts](https://github.com/andimarafioti/faster-qwen3-tts).
- OmniVoice : [modèle](https://huggingface.co/k2-fsa/OmniVoice), [article](https://arxiv.org/abs/2604.00688).
- VoxCPM2 : [modèle](https://huggingface.co/openbmb/VoxCPM2), [dépôt](https://github.com/OpenBMB/VoxCPM).
- Chatterbox : [V3](https://www.resemble.ai/resources/chatterbox-multilingual-v3-tts-with-embedded-watermarking-for-25-languages),
  [ONNX](https://huggingface.co/KitsuMate/chatterbox-multilingual-v3-onnx).
- Fish Audio S2 Pro : [modèle](https://huggingface.co/fishaudio/s2-pro), [s2.cpp](https://github.com/rodrigomatta/s2.cpp).
- Voxtral : [modèle](https://huggingface.co/mistralai/Voxtral-4B-TTS-2603), [voxtral-int4](https://github.com/TheMHD1/voxtral-int4).
- XTTS-v2 : [coqui-tts (Idiap)](https://github.com/idiap/coqui-ai-TTS) ; Kyutai TTS : [tts-1.6b-en_fr](https://huggingface.co/kyutai/tts-1.6b-en_fr) ;
  dots.tts : [dépôt](https://github.com/rednote-hilab/dots.tts) ; Pocket TTS : [modèle français (PR #321)](https://github.com/kyutai-labs/pocket-tts/pull/321) ;
  Magpie : [modèle](https://huggingface.co/nvidia/magpie_tts_multilingual_357m).
- En ligne : [Gemini API](https://ai.google.dev/gemini-api/docs/pricing), [Azure Speech](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/),
  [Google Cloud TTS](https://cloud.google.com/text-to-speech/pricing), [ElevenLabs](https://elevenlabs.io/pricing), [Inworld](https://inworld.ai/pricing).
