# 18 · Voix de la narration : plusieurs moteurs, choix et écoute depuis le dashboard

> Mesures du 28/09/2026 (temps par Short, mots mal compris, débit) et modèles à essayer ensuite : `29-banc-voix.md`.

> 2026-09-25, à la demande de Luca : « plus de choix dans les voix françaises », un autre modèle de voix, et le
> choisir comme on choisit les modèles d'image et de vidéo, pour tester plusieurs voix françaises.

## 1. Ce qui change pour Luca

**Réglages → Modèles de génération → Voix de la narration** : une liste par langue, rangée par moteur (Kokoro, …),
avec la licence (« publiable » ou non) et l'état « installé / à installer », comme pour les images et la vidéo.
Sous la liste, une phrase d'essai modifiable et le bouton **Écouter** : le PC fait dire la phrase par la voix choisie
(à la vitesse de la chaîne de cette langue) et le lecteur apparaît en dessous ; les six derniers essais restent
affichés pour comparer. Rien n'est enregistré tant qu'on ne clique pas sur « Enregistrer les modèles » ; la voix
enregistrée sert aux prochaines narrations (étape « voix » des productions).

L'essai passe par la file du worker (tâche « Essai de voix », visible dans le panneau Tâches) : il part juste après
la tâche en cours sur la carte graphique, donc jusqu'à quelques minutes d'attente si un clip Wan est en train de se
calculer.

## 2. Comment ça marche

| Élément | Rôle |
|---|---|
| `services/worker/workflows/catalog.json` → `tts` | un moteur de voix : libellé, détail, licence, `publishable`, `check` (fichiers qui doivent exister sous `C:\YouTube2` pour dire « installé »), `runtime` et `options` |
| `catalog.json` → `voices` | voix proposées par langue : `id` = « moteur:voix », `label`, `params` (réglages propres au moteur) |
| `app_settings.generation.voices` | la voix retenue par langue (« moteur:voix » ; un nom seul, ancien format, est une voix Kokoro) |
| `worker/providers/tts.py` | Kokoro dans le processus du worker ; les autres moteurs en sous-processus (`VenvTTS`) |
| `services/worker/tts_runners/<moteur>.py` | le script d'un moteur, exécuté par **son** Python (`C:\YouTube2\tts\<moteur>\venv`) ; protocole commun dans `_common.py` |
| job `voice_preview` (migration 0010) | l'essai du bouton « Écouter » : `DATA_DIR/previews/voices/<job>.wav`, servi par `/api/voice-preview/<job>` |
| `yt2 voice list`, `yt2 voice say moteur:voix` | les mêmes essais en ligne de commande, sans base |

Pourquoi un Python par moteur : les modèles de voix récents sont des modèles PyTorch qui imposent leurs versions
(torch, transformers, Python 3.10 à 3.12) ; les installer dans le Python du worker (3.13) ou dans celui de ComfyUI
risquerait de casser l'un ou l'autre. Chaque moteur vit donc dans son dossier, et le worker lui passe les textes de
toutes les scènes d'une vidéo en une fois (le modèle se charge une seule fois, puis toute sa mémoire est rendue).

L'étape « voix » des productions et l'essai passent par la **voie GPU** du worker (une tâche à la fois) : un moteur
PyTorch et Wan ne tiennent pas ensemble dans les 8 Go de la carte ; avant un moteur sur GPU, le worker vide ComfyUI
(`/free`). Le montage attend de toute façon tous les clips : la voix ne retarde pas la vidéo.

Vitesse : `channels.voice_speed` (1,05 par défaut). Kokoro la règle lui-même ; pour un moteur qui ne sait pas le faire,
le worker l'applique après coup avec FFmpeg (`atempo`, hauteur de voix conservée).

## 3. Ajouter un moteur

1. Écrire `services/worker/tts_runners/<moteur>.py` avec `_common.run(synthesize, prepare=…)` (le fichier ne doit pas
   porter le nom de la bibliothèque du moteur : `supertonic_tts.py`, pas `supertonic.py`).
2. Installer son environnement dans `C:\YouTube2\tts\<moteur>\` (`venv\` + `models\`) : `scripts/install_tts.ps1`.
3. Déclarer le moteur dans `catalog.json` → `tts` (avec `check`, et `runner` si le script a un autre nom) et ses voix
   dans `voices`.
4. Vérifier : `yt2 voice list`, puis `yt2 voice say <moteur>:<voix> --online` (le premier essai télécharge ce qui manque).

## 4. Moteurs installés le 25/09/2026

`powershell -ExecutionPolicy Bypass -File services\worker\scripts\install_tts.ps1` refait tout (≈ 14 Go sous
`C:\YouTube2\tts`), sauf les voix Qwen, créées ensuite par `tts_runners/qwen3_design.py` (voir l'en-tête du script).

| Moteur | Licence | Voix françaises | Où il tourne | Mesures (phrase d'essai) |
|---|---|---|---|---|
| **Qwen3-TTS** 12 Hz (`qwen3`), Base 0.6B | Apache 2.0 | 6 voix « dessinées » : narrateur grave, conteuse chaleureuse, récit mystérieux, présentatrice énergique, présentateur dynamique, voix élégante | carte graphique, après vidage de ComfyUI | 6,5 s de voix en 25 s, chargement compris ; création d'une voix ≈ 13 s par essai, 4,2 Go de VRAM au plus |
| Kyutai **Pocket TTS** 3.3.0 (`pocket`) | CC BY 4.0 (créditer Kyutai) | 1 : Estelle (femme, native ; enregistrement CC0 de Kyutai) | processeur | 3,1 s de voix en 7 s ; débit rapide (≈ 28 car./s) |
| **Supertonic 3** (`supertonic`) | OpenRAIL-M : dire que la voix est générée par IA | 10 : F1-F5, M1-M5 (voix non natives : accent à juger à l'oreille) | processeur (ONNX), 44,1 kHz | 4,0 s de voix en 4,7 s |
| Kokoro 82M (`kokoro`) | Apache 2.0 | 1 : Siwis (femme) | processeur, dans le worker | 4,1 s de voix en 3,7 s |

Les voix Qwen ont été créées le 25/09 (3 essais par voix, graine retenue d'après le débit visé `design.cps`) ; les
autres essais restent dans `C:\YouTube2\tts\qwen3\voices\_essais\`. Pour refaire une voix qui ne plaît pas : changer
sa `seed` (ou sa description) dans `catalog.json`, puis `qwen3_design.py … --only <nom> --force`.

Vérifié de bout en bout le 25/09 : « Écouter » sur Estelle → job `voice_preview` pris par le worker → 5,9 s de voix
calculées en 9,8 s → lecteur dans Réglages.

Pourquoi ceux-là (recherche du 25/09, sources en bas de page) :
- **Qwen3-TTS** a la meilleure intelligibilité publiée en français parmi les modèles ouverts (taux d'erreur de mots
  2,9 % pour le 0.6B, contre 5,2 % pour ElevenLabs sur le même jeu de test) et son modèle **VoiceDesign** crée une voix
  d'après une description : aucune personne réelle n'est imitée. Le modèle Base reprend ensuite ce timbre à partir
  d'une référence de 8 à 10 s (`C:\YouTube2\tts\qwen3\voices\`), phrase par phrase (le débit accélère sur les textes
  longs).
- **Pocket TTS** : modèle français de Kyutai (laboratoire français) sorti le 23/09/2026, léger, sur le processeur :
  aucune concurrence avec ComfyUI. Seule Estelle est une voix française native (les 26 autres voix de Pocket parlent
  français avec un accent étranger ; « cosette » et « jean » sont en plus non commerciales).
- **Supertonic 3** : 10 voix prêtes à l'emploi, très rapide. Dépôt archivé le 09/09/2026.
- **Écartés** : licences non commerciales (Voxtral TTS de Mistral, pourtant le meilleur en français ; Fish Audio,
  F5-TTS, XTTS-v2, OmniVoice…), Chatterbox Multilingual V3 (MIT mais français plus faible, filigrane, PyTorch 2.6
  imposé), modèles trop gros pour 8 Go (Higgs TTS 3, MOSS-TTS, VoxCPM2), aucune API gratuite sans limite.

## 5. Précautions juridiques

- **La voix est un attribut de la personnalité** (Cour de cassation, 1re civ., 24 juin 2026) : cloner la voix de
  quelqu'un sans son accord est fautif, même si l'enregistrement est sous licence libre (la licence couvre le droit
  d'auteur, pas le consentement). D'où les voix dessinées de Qwen, les voix fournies avec les modèles, ou plus tard la
  voix de Luca ou d'un comédien sous contrat.
- **Mention « voix générée par IA »** dans la description de chaque vidéo : exigée par la licence de Supertonic et
  par l'article 226-8 du Code pénal pour un contenu audio créé par IA ; YouTube demande aussi de signaler le contenu
  synthétique réaliste.
- **Crédit** pour Pocket TTS (CC BY 4.0) : « Voix : Kyutai Pocket TTS (CC BY 4.0) ».

## Sources (vérifiées le 25/09/2026)

- Qwen3-TTS : [dépôt et mesures multilingues](https://github.com/QwenLM/Qwen3-TTS), [VoiceDesign 1.7B](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign),
  [Base 0.6B](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base) (Apache 2.0), [débit sur texte long (#239)](https://github.com/QwenLM/Qwen3-TTS/issues/239).
- Pocket TTS : [dépôt](https://github.com/kyutai-labs/pocket-tts), [modèle français (PR #321)](https://github.com/kyutai-labs/pocket-tts/pull/321),
  [poids sans clonage (CC BY 4.0)](https://huggingface.co/kyutai/pocket-tts-without-voice-cloning), [origine des voix](https://huggingface.co/kyutai/tts-voices).
- Supertonic 3 : [modèle et licence OpenRAIL-M](https://huggingface.co/Supertone/supertonic-3), [dépôt archivé](https://github.com/supertone-oss-archive/supertonic).
- Classement français à l'aveugle : [Artificial Analysis, voix contrôlée, accent français](https://artificialanalysis.ai/text-to-speech/leaderboard/controlled-voice?accent=fr).
- Écartés : [Voxtral TTS (CC BY-NC)](https://huggingface.co/mistralai/Voxtral-4B-TTS-2603), [Chatterbox](https://github.com/resemble-ai/chatterbox),
  [Higgs TTS 3](https://huggingface.co/bosonai/higgs-tts-3-4b).
- Droit : [Cour de cassation, 24/06/2026, droit à la voix](https://feral.law/en/publications/droit-a-la-voix-la-cour-de-cassation-a-consacre-un-nouvel-attribut-de-la-personnalite/),
  [article 226-8 du Code pénal](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000049571542).
