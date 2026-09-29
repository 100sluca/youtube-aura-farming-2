# 38 · Voix calées sur la bouche, aucun texte écrit par les générateurs, titre d'accroche éphémère

> 2026-09-29. Trois demandes de Luca après avoir regardé « Mamie Pomme » (Karma des Fruits, vidéo 9d189b5d) :
> 1. dans les dialogues, le personnage parle mais sa bouche n'est pas synchronisée avec la voix (« si on peut faire
>    quelque chose, c'est bien ; si on ne peut pas, tant pis ») ;
> 2. un texte en plus des sous-titres, écrit par le générateur vidéo : il ne doit plus y en avoir, surtout dans les
>    vidéos, aussi dans les images ;
> 3. dans Bibliothèque → Retoucher, pouvoir rendre le titre d'accroche éphémère : cocher, puis régler sa durée de 5 s à
>    toute la vidéo.
>
> Le même jour, après avoir regardé les trois drames calés (« Madame Figue », « Mamie Pomme », « Durian ») : des mots
> coupés en deux (« pour|quoi »), des plans où la voix est calée sur la bouche du mauvais personnage (la mère parle à
> la place de l'ananas), et l'envie de corriger plan par plan, avec une consigne, en regardant la vidéo avec le numéro
> du plan affiché (§1, §5, §6).

## 1. Voix des personnages calées sur la bouche des clips

### Ce qui n'allait pas

En voix constantes (format A, défaut des drames, docs/35 §2), MiniMax H3 dit la réplique avec sa propre voix, bouche
comprise, puis cette voix est remplacée par celle du personnage (Qwen3). Cette voix était posée 0,15 s après le début
du plan, quoi que fasse la bouche. Mesuré sur les 16 clips de « Mamie Pomme » (Whisper pour les mots, détecteur de voix
Silero pour les passages parlés) :

| Plan | Bouche du clip (passages parlés) | Voix posée | Plan coupé à |
|---|---|---|---|
| 1 « Mon fils se marie demain… et il me veut en servante. » | 0,51 → 2,69 s, pause, 3,27 → 4,96 s | 0,15 → 3,45 s, d'un trait | 5,10 s |
| 2 « J'ai vendu mon verger pour payer ses études. » | 1,35 → 4,89 s | 0,15 → 2,15 s | 4,00 s (bouche coupée en pleine phrase) |
| 3 « Maman, personne ne doit savoir que tu es ma mère. » | 1,60 → 2,08 s, pause, 2,79 → 5,18 s | 0,15 → 2,60 s | 4,80 s |
| 9 « Pour toi, j'aurais tout nettoyé… » | 1,73 → 2,40 s, pause, 2,75 → 4,83 s | 0,15 → 1,51 s | 2,80 s |

La voix finissait souvent avant que la bouche ne s'ouvre, et H3 parle plus lentement que la voix de synthèse.

### Ce qui change (worker/lipsync.py, au montage)

- Le son de chaque clip est horodaté : les mots (Whisper large-v3-turbo) et les passages où la bouche parle (Silero,
  livré avec faster-whisper, plus juste au début d'une phrase : Whisper fait souvent partir le premier mot de 0 s).
  La réplique de synthèse l'est aussi. Script `tts_runners/whisper_words.py` (environnement `tts/eval`), qui renvoie
  maintenant `speech` en plus des mots.
- Les phrases de la bouche (`lipsync.line_regions`) : les passages du détecteur qui chevauchent un mot de la réplique ;
  un mot qu'il ne couvre pas est cherché dans les passages forts du son (plan 7, « Attention la vieille ! » crié sur de
  la musique : le détecteur ne l'entendait pas) ; un premier mot que Whisper place dans un silence se rattache au
  passage parlé qui finit juste avant la suite (plan 3, « Maman, » placé à 2,26 s dans un blanc, dit à 1,60 s).
- Chaque mot de la réplique appartient à la phrase de la bouche qu'il chevauche le plus (`lipsync.assign`) ; une phrase
  sans mot (un souffle) ne compte pas. La réplique de synthèse est **coupée seulement dans un de ses vrais blancs**
  (≥ 0,1 s, d'après son énergie à 10 ms et le détecteur ; `pauses`, `cut_between`), entre le dernier mot d'une phrase et
  le premier de la suivante ; **sans blanc à cet endroit, elle n'est pas coupée** et les deux phrases de la bouche n'en
  font qu'une. Chaque morceau est **étiré ou resserré** pour durer comme sa phrase (FFmpeg `atempo` : la hauteur de la
  voix ne bouge pas ; de ×0,8 à ×1,4, au-delà la voix sonne faux) et **posé quand la bouche s'ouvre**. Fondu de 8 ms aux
  bords de chaque morceau (pas de clic).
- Mots coupés (29/09, « Madame Figue », plan 16 « Prune… Pourquoi elle dort dans ta chambre ? ») : la bouche parlait en
  trois morceaux (un souffle, « Prune… », « pourquoi elle dort… ») et Whisper plaçait « pourquoi » 0,5 s trop tôt ; la
  première version coupait la voix juste après « pour » (« pour » à 1,4 s, « quoi… » à 2,8 s). Désormais « Prune… » va
  sur le deuxième morceau et le reste d'un seul tenant sur le troisième. Sur les 40 plans parlés des trois drames,
  toutes les coupes tombent dans un blanc de la voix.
- Le plan commence **0,35 s avant que la bouche s'ouvre** : le début du clip est coupé (2 s au plus, l'image de départ
  validée au storyboard reste proche) ; il finit 0,35 s après la voix. Les longs silences du début de clip
  disparaissent : « Mamie Pomme » passe de 62,9 s à 59,6 s.
- Les **sous-titres suivent la voix calée** (mots de la voix de synthèse reportés sur les morceaux).
- Clip où la réplique n'est pas reconnue mais où quelqu'un parle : la réplique entière va du premier au dernier passage
  parlé (`span`). Clip muet, ou un simple bruit : l'ancienne pose (voix 0,15 s après le début).
- Tout se refait à chaque montage à partir de caches : répliques découpées une fois dans
  `DATA_DIR/videos/<vidéo>/lines/` (tant que `narration.wav` ne change pas : une autre voix choisie dans Retoucher les
  redécoupe), transcriptions des clips dans `assets.meta.dialogue` (mots, `speech`, ressemblance). La piste calée
  `lipsync.wav` est enregistrée comme narration (retouche, essai du son de l'onglet Montage) et sa timeline remplace
  `videos.timeline` (`aligner` = `lipsync`).
- **À la fabrication** : chaque clip de drame avec une réplique est maintenant transcrit aussi en voix constantes
  (avant : seulement en voix des clips). Une réplique que H3 ne dit pas (ressemblance < 0,45) fait refaire le clip une
  fois, comme en format B : sans elle, la bouche ne dit rien de la réplique.
- Premier montage d'une vidéo : ≈ 1 à 3 min de Whisper sur le processeur (répliques de synthèse, et clips déjà faits
  avant le 29/09) ; ensuite quelques secondes. `DRAMA_LIPSYNC=false` dans `.env` coupe le calage.

### Limites et pistes

- Le calage se fait phrase par phrase (début, pauses, fin), pas syllabe par syllabe : la bouche de H3 garde son propre
  rythme à l'intérieur d'une phrase.
- Au-delà de ×1,4, la voix n'est plus étirée : elle finit un peu avant la bouche (H3 parle souvent lentement).
- Pour une synchronisation parfaite, trois pistes, non installées (disque, temps de calcul) :
  1. **garder la voix de H3 et changer son timbre** vers la voix du personnage (conversion de voix : Seed-VC, OpenVoice)
     : bouche parfaite, voix constante ; il faudrait d'abord séparer la voix de l'ambiance du clip ;
  2. redessiner la bouche sur la voix de synthèse (LatentSync, MuseTalk) : faits pour des visages humains, peu fiables
     sur des têtes de fruits ;
  3. faire le clip à partir de la voix (Wan 2.2 S2V, InfiniteTalk) : lourd sur 8 Go, change le modèle vidéo.

## 2. Aucun texte écrit par les générateurs

### Ce qui n'allait pas

Sur « Mamie Pomme », H3 a écrit la réplique à l'image, comme un sous-titre, en plus des nôtres : « Mais… je suis ta
mère, Api. » (plan 4) et « “Pour toi, j'aurais tout nettoyé…” » (plan 9), de 1 à 2 s jusqu'à la fin du clip. Et un
panneau « SOLD » (plan 2) venait de l'image du storyboard, que le scénariste avait le droit d'écrire (« une étiquette
courte »). Le négatif « text, watermark, logo, subtitles » ne servait à rien : **MiniMax H3 tourne sans CFG**
(BasicGuider, le nœud NEGATIVE n'est relié à rien) et **Qwen-Image 2.1 à CFG 1**, ComfyUI ne calcule alors pas la
branche négative.

### Ce qui change

- **Prompt des modèles qui ignorent le négatif** (`providers/video.py` : `ignores_negative`, `says_no_text`,
  `full_prompt`) : « No text anywhere in the picture: no subtitles, no captions, no letters or words, no writing on
  signs or screens, no watermark, no logo. » est ajouté au prompt, pour les modèles dont l'encodeur est un modèle de
  langue qui comprend une négation (H3 : Qwen3-VL ; Qwen-Image : Qwen2.5-VL ; Z-Image : Qwen3). Pas aux encodeurs T5
  (Wan, LTX, Flux), qu'un « no subtitles » pousserait plutôt vers des sous-titres ; Wan à 20 passes a un vrai négatif.
- **Prompt du clip d'un drame** (`drama.clip_prompt`) : après la réplique entre guillemets (H3 doit savoir quoi dire),
  « The words are only heard, never written on screen: no subtitles, no captions. »
- **Scénariste des drames** (`drama.SCRIPT_PROMPT`, `REWRITE_HINT`, clé `script_drama` de l'onglet Agents, nouvelle
  version du code) : aucun texte écrit dans l'image, ni panneau, ni étiquette, ni enseigne, ni écran, ni lettre ; une
  idée qui passerait par un écrit se montre autrement. Les récits narrés l'interdisaient déjà.
- **Contrôle des clips de drame** (`keyframe_qc.NO_NEW_TEXT`, `steps/generate_clip.py`) : comme les chantiers et les
  visites, chaque clip de drame est regardé par le modèle de vision (Gemini) : un texte qui n'est pas déjà dans l'image
  de départ (sous-titres, légende, mots) le fait refaire une fois. Essai sur les clips de « Mamie Pomme » : plans 4 et 9
  refusés (« présence de sous-titres… qui n'étaient pas présents sur l'image 1 »), plans 1 et 2 acceptés (le panneau
  de l'image de départ ne compte pas : le refaire ne l'enlèverait pas).
- **Refaire un clip** : un job `generate_clip` avec `"redo": true` dans son payload refait le clip même s'il existe (le
  nouveau prime au montage). Plans 4 et 9 de « Mamie Pomme » refaits ainsi le 29/09 (§4).

## 3. Titre d'accroche éphémère (Bibliothèque → Retoucher)

Onglet **Textes**, sous le titre d'accroche : case **« Éphémère »**. Décochée, le titre reste toute la vidéo (comme
avant) ; cochée, le curseur **« Affiché pendant »** va de 5 s à toute la vidéo (pas de 0,5 s) ; le titre s'efface en
fondu de 0,4 s à la fin de son temps. La case part de la durée du modèle de montage ; « Rétablir » revient au titre et
à la durée automatiques. Pour cette vidéo seulement : `videos.retouch.hook_display` (docs/34 §2). Pour régler tous les
clips d'un coup : onglet Montage → Titre d'accroche → « Durée à l'écran » (tous les formats, 1 à 15 s ; même fondu).

Au montage (`hooktitle.shown_for`, `fade_filter`, `steps/assemble.py`) : l'image du titre est lue en boucle le temps de
son affichage, s'efface en fondu, puis la vidéo passe seule. Vérifié par un vrai rendu (titre présent à 0,5 s, absent
à 3 s pour 1,5 s d'affichage : `tests/test_hook_ephemeral.py`).

## 4. Essai sur « Mamie Pomme » (29/09)

Version d'avant gardée dans `C:\YouTube2\bench\2026-09-29-levres-et-texte\` (Bibliothèque → Démos et essais :
`final_1_avant`, `final_2_apres`, et les clips 4 et 9 avant / après).

- **Plans 4 et 9 refaits** (job `generate_clip` `redo`, priorité 20, ≈ 6 min chacun) : aucun texte, contrôle passé,
  réplique entendue telle quelle (ressemblance 1,0).
- **Remontage calé** : 3 min la première fois (Whisper sur 10 clips et 12 répliques), 19 s ensuite (caches). 12 plans
  parlés sur 12 calés, 59,6 s au lieu de 62,9 s, contrôle qualité passé (−14,2 LUFS). La piste calée, transcrite par
  Whisper, ressemble à 0,99 au texte du script : l'étirement ne gêne pas la compréhension.
- Un premier remontage avec le seul détecteur de voix laissait deux plans en retard (plan 3 : 0,5 s ; plan 7 : 1,6 s) :
  d'où les passages forts du son et le rattachement du premier mot (§1).

Écart entre la bouche qui s'ouvre (ou se ferme) et la voix, en secondes (positif : la voix part ou finit trop tôt) :

| Plan | Bouche du clip | Avant : début / fin | Après : début / fin |
|---|---|---|---|
| 1 | 0,51 → 4,96 s | +0,36 / +1,51 | 0,00 / +0,08 |
| 2 | 1,35 → 4,89 s | +1,20 / +1,85 | 0,00 / +0,35 |
| 3 | 1,60 → 5,18 s | +1,45 / +2,20 | 0,00 / +0,05 |
| 4 | 1,47 → 4,70 s | +1,32 / +0,30 | 0,00 / +0,17 |
| 5 | 1,73 → 4,89 s | +1,58 / +1,21 | 0,00 / 0,00 |
| 7 | 1,45 → 5,18 s | +1,30 / +1,67 | 0,00 / +0,23 |
| 8 | 1,22 → 5,18 s | +1,07 / +1,43 | 0,00 / +0,35 |
| 9 | 1,60 → 5,18 s | +1,45 / +1,29 | 0,00 / +0,35 |
| 12 | 0,61 → 4,96 s | +0,46 / +1,05 | 0,00 / 0,00 |
| 13 | 0,45 → 4,99 s | +0,30 / +1,45 | 0,00 / 0,00 |
| 14 | 0,48 → 5,18 s | +0,33 / +2,57 | 0,00 / +0,35 |
| 16 | 2,11 → 4,86 s | +1,96 / +0,77 | 0,00 / +0,35 |

Fin à +0,35 s : la bouche bouge encore jusqu'à la coupe du plan, la voix ayant atteint son étirement maximal (×1,4).

## 5. Qui parle : le bon personnage

Contrôle Gemini des 5 plans à deux personnages de « Mamie Pomme » (quatre images prises pendant la réplique) : **4 fois
sur 5, H3 a fait parler la mère** (plans 7, 8, 12 et 16 : le citron, le fils ou l'ananas devaient parler), comme Luca
l'avait vu. Le prompt disait « Api says in French… » : un nom que H3 ne peut relier à aucun visage, et « she/her » dans
le mouvement du plan désignait souvent la mère.

- **Prompt du clip** (`drama.clip_prompt`, `worker/speaker.py`) : une légende des personnages du plan, décrits par ce
  qui se voit (le début de leur fiche et leur premier vêtement : « Api is a 30-year-old lawyer whose whole head is a
  perfect shiny polished red apple with a small green leaf, a tailored navy suit ») et, à plusieurs, **par leur place
  dans l'image de départ**, lue par Gemini (« on the left, kneeling down ») ; puis « Only Monsieur Ananas speaks… Mamie
  Pomme keeps their mouth closed and only listens. »
- **Contrôle des clips** (`keyframe_qc.clip_requirements`) : pour un plan dialogué à plusieurs, Gemini vérifie que c'est
  la bouche de celui qui parle qui bouge et que les autres gardent la bouche fermée ; sinon le clip est refait une fois.
- Les clips déjà faits ne changent pas : un plan fautif se corrige avec l'onglet Plans (§6).

## 6. Corriger un plan : Retoucher → Plans

Pour les drames, l'écran Retoucher s'ouvre sur l'onglet **Plans** :

- sur la vidéo, un repère **« Plan 7 · Madame Citron »** (le plan à l'écran et qui parle) change à chaque plan, pour
  toutes les vidéos ;
- un **menu des plans** (« Plan 7 · Madame Citron · « Attention, la vieille !… » »), qui suit la vidéo pendant la
  lecture (« Suivre la vidéo ») et s'arrête sur le plan dès qu'une consigne est en cours d'écriture ; choisir un plan
  place la vidéo dessus ;
- pour le plan : qui parle, qui est à l'image, la réplique, et **le clip brut avec la voix du modèle vidéo** (on voit
  quelle bouche bouge) ;
- **« Ta consigne pour ce plan »** et deux boutons :
  - **Refaire le clip** : le clip est refait avec la consigne, que le modèle de langue (Gemini, avec l'image de départ)
    transforme en note de réalisation anglaise pour H3 (« The golden pineapple man on the left speaks; the apple woman
    on the right keeps her mouth closed ») ; contrôle, puis montage avec les voix recalées ;
  - **Nouvelle prise de voix** : la même voix redit la seule réplique du plan avec une autre graine ; la consigne peut
    demander une prononciation (« dis A-pi » : la voix lit « A-pi », les sous-titres gardent « Api ») ou un débit
    (×0,8 à ×1,2), pas une émotion (Qwen3-TTS garde le timbre du personnage et ne joue pas sur commande). Les autres
    répliques restent telles quelles, et leur transcription est gardée (seule la nouvelle repasse par Whisper).
- les consignes déjà données pour le plan (date, clip et/ou voix, texte) ; elles restent dans `videos.retouch.plans`.

SQL `redo_plan(vidéo, plan, consigne, clip, voix)` (migration **0028**) : mêmes conditions que Retoucher (vidéo montée,
pas encore sur YouTube, rien en cours pour elle), puis `generate_clip` (`redo`, `note`) et/ou `tts` (`scene`, `take`,
`note`), priorité 20, `assemble` (remontage calé) qui en dépend, `qa`. La vidéo revient à valider, une vidéo autorisée
perd son créneau. Durée : ≈ 7 min par clip sur la carte graphique (plus l'attente du clip en cours), ≈ 1 min pour une
prise de voix, puis montage et contrôle.

Les trois drames regardés le 29/09 (« Madame Figue », « Mamie Pomme », « Durian ») étaient déjà envoyés sur YouTube,
programmés pour le 1er octobre : YouTube ne permet pas d'en remplacer le fichier, Retoucher les laisse donc en lecture
seule. Les corriger demande de les retirer de YouTube (YouTube Studio), puis de les rouvrir à la retouche.

## 7. Fichiers

| Où | Quoi |
|---|---|
| services/worker/worker/lipsync.py | calage : phrases de la bouche, mots par phrase, coupes dans les blancs, étirement, piste et timeline, caches (`cached_lines`, empreintes des répliques) |
| services/worker/worker/speaker.py | qui parle : fiches courtes (`visual_tag`), légende, place dans l'image (`locate`), exigence du contrôle, notes de réalisation et de voix |
| services/worker/worker/steps/tts.py | nouvelle prise d'une seule réplique (payload `scene`, `take`, `note`) |
| services/worker/worker/providers/tts.py | `speak_many(…, seed=)` : une autre prise |
| supabase/migrations/0028_corriger_un_plan.sql | SQL `redo_plan` |
| apps/dashboard/src/components/library/retouch-plans.tsx | onglet Plans, repère « Plan N » sur la vidéo |
| services/worker/tts_runners/whisper_words.py | mots + passages parlés (Silero) |
| services/worker/worker/steps/assemble.py | `prepare_video` (calage des drames en voix constantes), `RenderPlan.clip_offsets` (début des clips coupé), titre éphémère (boucle, fondu) |
| services/worker/worker/steps/generate_clip.py | transcription des clips de drame en voix constantes, contrôle « texte » des clips de drame, payload `redo` |
| services/worker/worker/providers/video.py | `NO_TEXT`, `ignores_negative`, `says_no_text`, `full_prompt` |
| services/worker/worker/keyframe_qc.py | `NO_NEW_TEXT`, exigence des clips de drame |
| services/worker/worker/drama.py | `clip_prompt`, `SCRIPT_PROMPT`, `REWRITE_HINT` |
| services/worker/worker/hooktitle.py, retouch.py | `shown_for`, `fade_filter` ; `HookDisplay`, `Retouch.hook_display` |
| services/worker/worker/config.py | `DRAMA_LIPSYNC` |
| apps/dashboard/src/components/library/retouch-editor.tsx, lib/retouch.ts, lib/retouch-types.ts, app/library/retouch-actions.ts | case « Éphémère », curseur, enregistrement |
| services/worker/tests/test_lipsync.py, test_plans.py, test_no_text.py, test_hook_ephemeral.py, test_workflows.py, test_hooktitle.py | tests |
