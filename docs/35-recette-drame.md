# 35 — Recette « drame » : histoires de karma en dialogues

Demandé par Luca le 2026-09-28, après l'étude des dix TikTok (docs/31) et l'essai des personnages (docs/31 §8) : « lance
le test de la voix puis la recette ». Le drame est une quatrième recette, à côté du récit narré, du chantier en accéléré
et de la visite : une histoire d'injustice jouée par des personnages (fruits, humains ou animaux au rendu de film
d'animation) qui se parlent, une réplique par plan. Migration **0021**.

## 1. Ce que Luca voit

- **Création** : trois nouveaux thèmes, **Le Karma des Fruits** (fruits, style Pixar), **Histoires de familles**
  (humains, Pixar et Disney) et **Histoires d'animaux** (DreamWorks). L'agent idées y propose des histoires (consigne
  `guide_drama`) ; ✓ lance le scénariste.
- **Onglet Agents** : « Scénariste · drame en dialogues » (`script_drama`) et « Guide · drame en dialogues »
  (`guide_drama`), modifiables et versionnés comme les autres.
- **Storyboard** : en haut, la bande **Personnages**, avec la fiche de chacun (lui seul, en pied, sur fond gris) ;
  « Refaire » refait sa fiche puis tous les plans où il apparaît, puisqu'ils la prennent en référence. Dessous, un plan
  par réplique ; la narration affichée est la réplique précédée de son personnage (« Kiwi : … »).
- **Validation (✓)** : clips MiniMax H3, où le personnage dit sa réplique et sa bouche bouge ; voix des personnages ;
  montage avec les sous-titres des répliques, la musique qui baisse sous les voix et le titre d'accroche.

## 2. Les voix : constantes (défaut) ou voix des clips

MiniMax H3 dit la réplique écrite dans le prompt, bouche comprise (docs/31 §8), mais **la voix d'un même personnage change
d'un clip à l'autre**. Test du 28/09 sur trois clips de Kiwi, avec la même description de voix
(`C:\YouTube2\bench\2026-09-28-karma-fruits\final_voix_kiwi.mp4`, script `bench_voix.py`) :

| Clip | Réplique entendue (Whisper) | Hauteur | Distance de timbre avec le 1er |
|---|---|---|---|
| Taxi (pluie) | « Ah ! 50 000 ! L'opération en coûte 30 ! » | 258 Hz | — |
| Hôpital | « Tiens bon, Groseille, grand frère va trouver l'argent. » | 129 Hz | 0,40 (autant qu'entre Kiwi et Papa Issa : 0,41) |
| Cellule | « Je l'ai rendu. Pourquoi personne ne me croit ? » | 258 Hz | 0,11 |

Les vidéos étudiées gardent la même voix pour chaque personnage : sans ça, on ne sait plus qui parle. D'où deux modes,
choisis par le **format de la série** :

- **Voix constantes (format A, défaut des trois séries)** : chaque personnage a une voix de synthèse Qwen3 (`tts_voice`,
  choisie par le scénariste dans une liste, sinon d'après sa description : sexe, âge, rôle ; jamais la même pour deux
  personnages s'il en reste). L'étape voix dit chaque réplique avec la voix de son personnage (un appel au moteur par
  voix) et construit la timeline comme pour un récit. Le clip H3 garde la bouche qui bouge sur la réplique ; sa propre
  voix est laissée de côté. **Depuis le 29/09, chaque réplique est calée sur la bouche de son clip** au montage
  (worker/lipsync.py, docs/38) : avant, elle partait 0,15 s après le début du plan, la bouche parlait avant ou après.
- **Voix des clips (format B)** : `update series set format = 'B_visual' where slug = '…'`. La voix est celle de H3,
  synchronisée au mot mais variable. Chaque clip est transcrit par Whisper (mots horodatés) : les sous-titres
  reprennent le texte du script calé sur la voix entendue, et un clip où la réplique n'est pas dite (ressemblance
  < 0,45) est refait une fois. Au montage, le son des clips devient la piste de voix.

Neuf voix de personnages dessinées le 28/09 (Qwen3 VoiceDesign, `tts_runners/qwen3_design.py`, 3 essais chacune ;
`C:\YouTube2\tts\qwen3\voices\perso_*.wav`), en plus des six voix de narration, et proposées aussi dans Réglages :

| Voix | Pour |
|---|---|
| `qwen3:perso_patron` | patron autoritaire, homme de 55 ans |
| `qwen3:perso_humble` | jeune homme humble, voix qui tremble |
| `qwen3:perso_mielleuse` | femme mielleuse qui devient cassante |
| `qwen3:perso_mamie` | vieille dame douce et fragile |
| `qwen3:perso_papi` | vieil homme bienveillant, père qui console |
| `qwen3:perso_fillette` | fillette de 10 ans |
| `qwen3:perso_garcon` | garçon timide de 12 ans |
| `qwen3:perso_ado` | ado moqueur |
| `qwen3:perso_jeune_femme` | jeune femme douce |

## 3. Comment ça marche

| Étape | Ce que fait le drame | Code |
|---|---|---|
| Script | distribution `cast` (key, name, look et voice en anglais, tts_voice, role) ; par scène `characters` (3 au plus) et `lines` (une réplique : who, text, tone). Normalisation : clés, personnage qui parle mis à l'image, répliques d'un même personnage réunies, durée = 0,8 s + mots / 2,5 (5,1 s au plus, un clip H3), nombres en chiffres, narration « Nom : réplique » pour l'affichage. Correcteur : 10 à 24 plans, 2 à 6 personnages décrits (12 mots au moins) avec une voix, une voix par plan, 12 mots par réplique, 60 % de plans dialogués, titre d'accroche, durée ±25 %. Une reprise en cas d'écart | `worker/drama.py` (normalize, lint, SCRIPT_PROMPT, IDEA_GUIDE), `recipes.py` (RECIPES, has_prompt, montage_format), `steps/script.py` (liste des voix dans le message) |
| Storyboard | une fiche par personnage (assets kind `character`, meta.key, retenue), puis chaque plan avec les fiches de ses personnages en images de référence, citées `<image1>`… (« Kiwi is the character of <image1> ») ; payload `characters` pour en refaire une | `steps/storyboard.py` (_sheets), `providers/video.py` (add_references sur TextEncodeQwenImage21, résolution 768 ; styles pixar_fruit, pixar_human, dreamworks_animal ; négatif sans « cartoon ») |
| Clips | prompt : le film, le mouvement, puis « Kiwi says in French, in a soft trembling young male voice, stunned whisper: "cinquante mille…" » (nombres en lettres) ; plan sans réplique : « Nobody speaks » (sinon H3 invente des paroles). Format B : transcription et nouvel essai | `drama.clip_prompt`, `steps/generate_clip.py`, `tts_runners/whisper_words.py` (environnement `tts/eval`) |
| Voix | format A : une voix par personnage (drama.assign_voices) | `steps/tts.py` (_drama) |
| Montage | le drame se monte comme un récit (modèle de montage : titre, sous-titres, musique des récits) ; format B : timeline et piste de voix tirées des clips | `steps/assemble.py` (montage_format, dialogue_timeline, build_dialogue_track) |
| Réinventer | le scénariste garde personnages et réplique de la scène | `reinvent.py` (FORMAT_HINTS, apply_rewrite) |

Dashboard : `lib/agent-catalog.ts`, `lib/agents.ts`, `lib/types.ts` (CastMember, CharacterSheet), `lib/data/supabase.ts`
(fiches retenues des personnages), `components/create/character-strip.tsx`, `app/production/actions.ts` (redoCharacter).
Migration `0021_recette_drame.sql` : valeur `character` de asset_kind, recette `drama` dans les contraintes de `series`
et `performance_lessons`, les trois séries (format A, 70 s, ambiances sentimental, tragique, triste, mystère).
Tests : `tests/test_drama.py` (14, dont l'étape voix avec deux moteurs de fréquences différentes).

## 4. Les six vidéos de test

Les six scripts de docs/31 §5, prêts à produire dans `services/worker/scripts/demo/drama_*.json` (distribution, prompts
anglais, répliques françaises, voix), importés par `scripts/demo_formats.py <script> --series <série>` : chacun devient
une vraie production de l'app, storyboard à valider dans Création.

| Script | Série | Plans | Durée prévue |
|---|---|---|---|
| La valise de Madame Figue (partie 1) | karma_fruits | 16 | 59 s |
| Mamie Pomme (partie 1) | karma_fruits | 16 | 62 s |
| Le testament de Mamie Mangue (complète) | karma_fruits | 19 | 69 s |
| Durian, le paria (partie 1) | karma_fruits | 16 | 53 s |
| La fille du gardien (partie 1) | histoires_familles | 16 | 58 s |
| Le garage de Papa Bruno (complète) | histoires_animaux | 18 | 61 s |

Calcul : 4 à 6 fiches (≈ 40 s chacune), 2 images par plan (réglage « storyboard_candidates », ≈ 55 à 100 s avec
références), puis un clip H3 par plan (≈ 6 à 7 min) : ≈ 40 min de storyboard et ≈ 2 h de clips par vidéo.

## 5. Limites connues

- Un plan dure 5,1 s au plus (un clip H3) : une réplique de 12 mots au plus.
- En voix constantes, la bouche de H3 suit sa propre voix, qui n'est pas celle qu'on entend : depuis le 29/09 la voix
  du personnage est posée sur les phrases de la bouche (début, pauses, fin : docs/38), pas syllabe par syllabe.
- **Aucun texte écrit par les générateurs (règle de Luca, 29/09, docs/38)** : H3 écrivait parfois la réplique à
  l'image comme un sous-titre (« Mamie Pomme », plans 4 et 9) et un panneau « SOLD » passait de l'image au clip. Le
  scénariste n'écrit plus aucun texte dans l'image (ni panneau, ni étiquette, ni écran), le prompt du clip dit que la
  réplique s'entend sans s'écrire, et chaque clip de drame est regardé par le contrôle des clips (Gemini) : un texte
  ajouté par le clip le fait refaire une fois.
- Un accessoire nommé dans la consigne des références passe sur tous les personnages : « keep … eyes, glasses,
  clothes » a mis des lunettes à Prune et à Kiwi (storyboard de Madame Figue, plans 2, 9, 10 et 11). La consigne
  (`drama.REFS_INTRO`) n'en nomme plus aucun depuis le 28/09 au soir ; ces quatre plans ont été refaits avec elle,
  leurs premières images restent au choix.
- Un plan dont le prompt ne dit pas le lieu reprend le fond gris uni de la fiche (Mamie Mangue, plan 16 : Cerise sur
  fond de studio). Le scénariste doit toujours écrire le lieu, même en gros plan (`SCRIPT_PROMPT`, `REWRITE_HINT`) ;
  le lieu a été ajouté aux 9 plans des scripts de test qui n'en avaient pas (28/09 au soir).
- La fiche d'un tout-petit, seule sur fond gris, ne dit rien de sa taille : Tom (chiot de 8 ans) était dessiné aussi
  grand que son père sur 6 plans de Papa Bruno. Le prompt d'un plan précise maintenant « a small child about half as
  tall as the adults » pour un chiot, un chaton ou un enfant de moins de 10 ans (`drama._size`) ; les enfants de
  12 ans, bien rendus, n'en ont pas besoin.
- ~~Un panneau à texte s'écrit dans la langue de la vidéo (« VENDU »)~~ : remplacé le 29/09 par « aucun texte écrit ».
- MiniMax H3 : licence de test seulement (à revoir avant publication, docs/21).
