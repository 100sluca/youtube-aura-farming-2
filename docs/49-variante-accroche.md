# 49 · Accroches qui font ressentir, variante d'accroche, rétention phrase par phrase

> 2026-10-01. Retours de Luca sur les récits narrés. « Zraoua » est bonne, mais son accroche (« Ce village berbère a
> survécu 2 000 ans contre le désert. ») ne fait rien ressentir. « Naypyidaw » marche parce que « 4 milliards d'euros
> pour une ville où personne ne vit » se comprend tout de suite. « Begrâm » parle de choses importantes sans dire
> pourquoi elles comptent. Le public est jeune et ne connaît rien : l'accroche doit faire rêver (« ça existe
> vraiment ? ») ou faire sentir un enjeu. Luca veut aussi tester deux accroches d'une même vidéo, et que les courbes
> de rétention disent où et pourquoi on décroche.

## 1. Ce qui change dans l'écriture

- **Conteur** (`storycraft.STORY_PROMPT`, clé `script`) : l'accroche vise un ado de 13 ans qui fait défiler. Elle doit
  lui faire ressentir quelque chose dès la 1re seconde, par l'un de deux ressorts :
  - le **gâchis ou la perte** qu'on sent dans le ventre (l'exemple de Naypyidaw) ;
  - l'**émerveillement** d'une chose unique, comme sortie d'un film, qui existe pourtant vraiment.

  Une durée seule ou une notion abstraite ne suffit pas. Au contexte, un nom de peuple, de lieu ou de métier peu
  connu s'explique la 1re fois, si le dossier le dit.
- **Règles du récit** (`storytelling.RULES`, §6) et **relecteur** (`REVIEW_PROMPT`, points 1 et 7) : mêmes
  exigences, vérifiées à la relecture.
- **Dossier** (`sources/wikipedia.source_dossier`, paramètre `subject`) : quand l'idée ne cite que des pages de liste
  (« Liste de villes fantômes »), la page du sujet lui-même est ajoutée après elles (`subject_page`). Les faits de
  l'idée gardent leur numéro [n]. Zraoua n'avait que 3 lignes de liste : l'article du village n'avait pas été lu. Il
  raconte le départ des habitants pour un nouveau village dans la plaine à la fin des années 1970, et les tournages de
  films (« Or noir » de Jean-Jacques Annaud). Faute de matière, le récit avait comblé les trous : le manque d'eau,
  les jeunes qui partent et les anciens qui résistent ne sont dans aucune source.

Les prompts en service étaient ceux du code (01/10) : les changements servent dès que le worker redémarre.

## 2. Variante d'accroche (`worker/hookvariant.py`, migration 0037)

La même vidéo, même récit et mêmes clips ; seules les deux premières phrases changent : l'accroche et la promesse.
YouTube ne sait pas comparer deux débuts d'une même vidéo, donc la variante est un autre Short. On la publie 2 à 3
jours après l'originale, au même créneau, puis on compare l'audience encore là à 3 s et les courbes.

```bash
yt2 variant make <vidéo> --hook "…" --promise "…" --hook-title "…" --title "…" [--on-screen "…"] [--description "…"]
```

- Une production n'a qu'une vidéo par chaîne (`videos_production_channel_key`). La variante est donc une **copie de la
  production**, qui contient :
  - le script, avec la nouvelle accroche, la nouvelle promesse, le titre d'accroche et le titre YouTube ;
  - les clips et les images du storyboard, liés sur le disque (lien physique NTFS : aucun octet de plus, et effacer
    l'une ne casse pas l'autre).
- Les scènes de l'accroche et de la promesse prennent la durée de leur nouveau texte (`scene_seconds`).
- `videos.variant_of` relie la variante à l'originale.
- La variante garde la voix de l'originale, dite telle quelle sans le jeu des voix, et sa musique. Puis vient
  voix → montage → contrôle. Elle arrive **à valider** dans la Bibliothèque et n'est jamais publiée seule.
- **Seules les phrases changées sont redites** (02/10, Lukangol : les 19 plans étaient redits pour une nouvelle
  accroche, ≈ 9 min). Le job voix reçoit `voices_from` (la vidéo d'origine) ; `steps/tts.kept_speeches` découpe dans
  sa piste (`narration.wav` + `videos.timeline`) la voix de chaque plan dont le texte n'a pas bougé, et seuls les
  autres plans passent par le moteur. La piste est ensuite reconstruite plan par plan : une accroche plus longue
  allonge son plan, la suite démarre après, sans chevauchement. Tout est redit si l'originale a été dite par une autre
  voix ou un autre moteur (jeu des voix, repli : le timbre changerait en cours de vidéo) ou si sa piste ne suit plus
  sa timeline. Le résultat du job note `kept_scenes`.
- Le correcteur signale, sans bloquer, une accroche trop longue, une ouverture de plus de 22 mots dits ou un titre
  d'accroche hors règles.

**Zraoua, 01/10** (originale `6cdfebd6`, pilote automatique) :

| | Accroche | Promesse | Vidéo |
|---|---|---|---|
| A | Ce village berbère a survécu 2 000 ans contre le désert. | Pourtant, ses habitants ont fini par tout abandonner. | `6cdfebd6` |
| B, émerveillement | Ce village de pierre perché dans le désert sert de décor de cinéma. | Pourtant, ses habitants l'ont quitté il y a presque 50 ans. | `1df9ea2e` |
| C, perte | Pendant 2 000 ans, des familles vivent dans ce village perché. | Puis tout le monde s'en va, et personne ne revient. | `53a56a12` |

## 3. Rétention phrase par phrase (analyste, docs/25)

`metrics.retention_by_scene` pose la dernière courbe relevée (`video_retention`, `sync_retention`) sur la timeline
de la voix (`videos.timeline`) : l'audience à l'entrée et à la sortie de chaque phrase dite. Dans la fiche de chaque
vidéo, l'analyste lit :

- la courbe phrase par phrase (« 0 s 100 % · 3 s 72 % · … ») ;
- les 3 plus fortes pertes (`retention_drops`) : les phrases pendant lesquelles on part le plus vite, avec leur texte.

Son prompt (`analyst`) lui demande de dire pourquoi on décroche à ce moment-là, d'en tirer une leçon « script »
quand plusieurs vidéos décrochent pour la même raison, et de comparer une variante à son originale. Ses leçons ne
vont au conteur qu'une fois validées par Luca. Les courbes arrivent 2 à 3 jours après la publication.

## 4. Voix des récits (catalog.json → acting.gemini.narration)

Devant « Bakélite » (01/10), Luca trouve la lecture de Gemini moins bonne que la voix locale « mystère » de Qwen pour
les récits. `narration` passe donc à `false` : Gemini joue toujours les voix des personnages des drames, et un récit
garde sa voix locale. Le résultat du job voix note désormais `spoken_by`, le moteur qui a vraiment parlé : Gemini, son
repli ou le moteur de la voix. `videos.tts_provider` garde le moteur de la voix choisie, que relit
« Retoucher → Voix ».

## 5. Langue des voix Gemini (tts_runners/gemini_tts.py)

Gemini recevait son style (personnage, ton, débit) en anglais et disait parfois une réplique française **en anglais**.
« Tout le collège le détestait » : Whisper entend « Attention, the ego has arrived. » pour « Attention ! L'égout est
arrivé ! », même après une nouvelle prise demandée « en français ! ». La langue de la vidéo part désormais à deux
endroits :
- en tête du style : « Speak French with a native French accent; say the text exactly as written, word for word,
  never translate it » ;
- dans `speech_config` (`language: fr-FR`). Si l'API refuse ce champ, il est retiré pour la suite du job, et la
  consigne du style suffit.

Les récits narrés ne passent plus du tout par Gemini (§4).

## 6. Réécrire le récit sur les mêmes plans (`worker/rewrite.py`)

À utiliser quand une vidéo est bonne (images, thème) mais que l'écriture ne porte pas. Le conteur réécrit ce que dit
la voix, scène par scène, sur les plans tels qu'ils sont, en suivant les remarques de Luca :
- chaque phrase colle à l'image de sa scène ;
- chaque phrase tient dans la durée de son clip (environ 2,9 mots dits par seconde de clip, plus 15 % de marge) ;
- le budget de mots total est celui de la durée visée.

Puis viennent le correcteur et le relecteur. Il y a deux réécritures au plus, chacune relue, et on garde la version
qui laisse le moins d'écarts ; ceux qui restent sont affichés. La variante part ensuite comme une variante
d'accroche : copie de la production, clips liés, voix → montage → contrôle, puis SEO refait. Prompt `script_rewrite`
(onglet Agents).

```bash
yt2 variant rewrite <vidéo> --note "ce qui ne va pas, l'angle voulu" [--page "Joseph Hackin"] [--dry]
```

`--page` ajoute une page Wikipédia au dossier. Pour Begrâm, la page « Joseph Hackin » raconte la France libre et le
cargo *Jonathan Holt* torpillé le 24 février 1941. Elle manquait au dossier : le récit d'origine citait ces faits
sans source. `--dry` affiche le texte sans rien créer.

## 7. Prises de voix par lot (Retoucher → Plans ; `worker/takes.py`, migration 0038)

Avant, on ne pouvait refaire qu'une réplique à la fois, et chaque prise refaisait toute la vidéo. Désormais :
1. la consigne de chaque plan s'enregistre pendant qu'elle s'écrit (`videos.retouch.drafts`, SQL `save_plan_note`) ;
2. **« Nouvelles prises de voix (N) »** (SQL `retake_voices`) lance un seul job tts (`takes`). Il redit chaque réplique
   qui a une consigne, ainsi que chaque prise refusée. Chaque prise est un fichier à part (asset `take`), réécouté par
   Whisper. **La vidéo ne bouge pas.**
3. chaque prise s'écoute dans son plan, avec ce que Whisper y entend. On répond **« Oui, je valide cette prise »** (on
   passe au plan suivant à écouter) ou **« Non, je ne la valide pas »** (la consigne se rouvre ; le plan repartira au
   prochain lot). SQL `keep_take`.
4. quand plus aucune prise n'attend, **« Refaire la vidéo avec N prises validées »** (SQL `apply_takes`) pose les
   prises validées dans la piste des répliques. Les autres restent telles que le dernier calage les a découpées. Suit
   un seul montage calé sur les lèvres, puis le contrôle.

L'onglet signale aussi les **répliques douteuses de la vidéo actuelle**, par ce que Whisper en a entendu au dernier
calage (`lines/lines.json`). La ressemblance retenue est la plus faible de deux mesures : la comparaison lettre à
lettre et la part des mots écrits retrouvés (`takes.said_ratio`, `heardRatio` côté Dashboard ; seuil 0,6). Lettre à
lettre seule, la phrase anglaise passait (0,75) ; mot à mot, elle tombe à 0,2. Sur « Tout le collège le
détestait », les plans 1, 9 et 15 sont signalés.

« Refaire le clip » reste plan par plan (≈ 7 min de GPU), puis la vidéo est remontée.

## 8. Retirer une vidéo programmée (`yt2 withdraw`)

```bash
yt2 withdraw <vidéo> [--voice qwen3:mystere]
```

La vidéo passe en **privée, sans date** sur YouTube (`YouTubeClient.unschedule`, 51 unités de quota) ; rien n'est
supprimé. Sa publication TikTok programmée est supprimée et l'envoi est gardé dans `previous_uploads`
(`release_upload`). Sans `--voice`, la vidéo revient à valider. Avec `--voice`, la narration est refaite avec cette
voix (`retouch_video`). Le 01/10 : Begrâm retirée (YouTube c9heiHQCpx0) ; Bakélite (2Kuf0dw9cFg) refaite en
« mystère », 75 s au lieu de 122.

## 9. Suivi des clés API (migration 0044, `worker/keyusage.py`)

Luca a plusieurs clés Gemini (voix et IA) et veut savoir laquelle tourne, lesquelles sont tombées, et où en sont les
quotas.
- **Relevé à chaque appel** : la rotation des clés des modèles de langue (`providers/llm.KeyedLLM`, via
  `get_llm(…, db)`) et celle de la voix Gemini (`tts_runners/gemini_tts.py`) notent l'appel dans `api_key_usage`. Une
  ligne par (empreinte de la clé, modèle, jour de quota) : appels, réussites, échecs, état, limite par jour. La clé
  n'est jamais enregistrée : seuls sa liste (`voix` ou `ia`) et son numéro.
- **États** : en service, quota du jour épuisé (jusqu'à minuit heure de Los Angeles, soit vers 9 h à Paris), limite
  par minute, refusée. La limite par jour est celle que Google annonce dans son refus (« limit: 10 requests per day »).
- **Alerte** quand une clé tombe (quota du jour ou refus), une fois par jour et par clé : « Clé voix n°2 sur 5
  (gemini-3.8-flash-tts) : quota du jour épuisé · les appels passent à la clé n°3 ».
- **Voix Gemini** : une clé épuisée ou refusée n'est plus essayée jusqu'à la fin du job. Avant, chaque réplique
  recommençait par la clé n°1.
- **Gestionnaire des tâches → « Clés API aujourd'hui »** (`components/tasks/api-keys-panel.tsx`) : pour chaque modèle,
  la clé en service, le nombre de clés disponibles et une pastille par clé (verte : en service, barrée : tombée ; au
  survol, le détail).
- **Réglages → Quotas des modèles** (`components/settings/quotas-card.tsx`) : comment marchent les quotas, puis pour
  chaque modèle les clés, la limite par clé et par jour constatée, les réussites du jour et ce qui reste possible.

## 10. Le son des drames : ambiance des clips, bruitages, voix des clips

Devant « Tout le collège le détestait » (2c288b3d), Luca a fait trois remarques.

**Le clip brut sonne mieux que la vidéo.** Aucun plan n'avait été refait : chaque plan n'a qu'un clip (29/09). Le
« petit carré » de Retoucher → Plans montre le clip avec le son du modèle vidéo (H3). La voix y colle aux lèvres et
l'ambiance est présente. En voix constantes, le montage remplace ce son par les voix de synthèse (Gemini, dont
certaines en anglais). D'où `yt2 variant clip-voices <vidéo>` : une copie de la vidéo qui garde le son de ses clips
(format B, `drama.build_dialogue_track`), à comparer avec l'originale. Rappel : H3 change la voix d'un personnage d'un
clip à l'autre (docs/35), c'est pour cela que les drames étaient passés en voix constantes. Copie faite le 01/10 :
9f663307.

**Les plans sans réplique sont muets.** En voix constantes, le montage (`assemble.drama_sound`) pose désormais, sous
chaque plan sans réplique, le son de son clip : l'ambiance faite par H3 (cantine), qui part du début gardé par le
calage (`SfxCue.offset`). Les plans parlés gardent la seule voix de synthèse.

**Des bruitages plan par plan, sans Gemini.** Quinze étiquettes de drame s'ajoutent à la bibliothèque (`worker/sfx.py`),
générées en local par Stable Audio Open dans ComfyUI (`yt2 sfx generate`) :
- fonds : cafeteria, whispers, classroom, school_hallway, cutlery, crowd_murmur ;
- ponctuels : laughter, gasp, school_bell, bag_rummage, cloth_rustle, small_metal, door_slam, running, heartbeat.

Le **bruiteur** (`worker/sfx_pick.py`, prompt `sfx_pick`) les choisit d'après l'image et la réplique de chaque plan.
Sur un plan sans réplique, il met deux étiquettes, le lieu et le geste ou la réaction ; sur un plan parlé, une ambiance
discrète au plus. Il tourne seul au premier montage d'un drame qui n'a aucun bruitage (`assemble.pick_drama_sfx`), ou à
la demande :

```bash
yt2 sfx pick <vidéo> [--remount]
```

« Tout le collège », le 01/10 : couloir (plans 1-2), cantine (3-6, chuchotements au plan 3), sac fouillé et petit
objet en métal (plan 7), sac fouillé et stupeur (plan 10), salle de classe (8-16).

## 11. Drames en voix des clips par défaut (migration 0045)

Luca, le 01/10 : « les voix du modèle vidéo sont exceptionnelles, pile calées sur les lèvres, adaptées aux
personnages : conservons ces voix ; en cas de nécessité pour un plan, on redemande à Gemini ». Le modèle est MiniMax
H3, en local dans ComfyUI : il génère l'image et la voix ensemble.
- **Les séries de drames passent au format B** (`series.format = 'B_visual'`) : le son des clips fait la piste de
  voix. Les clips se fabriquent comme avant (H3 dit la réplique, Whisper vérifie qu'elle est dite, sinon le clip est
  refait). Seul le montage change.
- **Bruitages dans les deux formats** : le bruiteur choisit les étiquettes au premier montage ; en voix des clips,
  l'ambiance est déjà dans le son des clips, et seuls les bruitages s'ajoutent.
- **Une vidéo bascule d'un mode à l'autre** dans Retoucher → Voix, menu « Refaire les voix des personnages avec » :
  « Voix des clips (MiniMax H3) » ou un jeu de voix de synthèse (Gemini…). SQL `set_drama_voices(vidéo, clips, voix,
  retouche)` : le format de la vidéo, puis `retouch_video`.
- **Un plan seulement en voix de synthèse** : Retoucher → Plans, même circuit (consigne, « Nouvelles prises de
  voix », valider, refaire la vidéo). En voix des clips, une prise validée est notée dans `videos.retouch.lines`
  ({plan : prise}). Le montage la pose à la place du son du clip, là où le clip disait sa réplique (premier mot
  entendu) : `assemble.replaced_lines`, `drama.build_dialogue_track(replace=…)`.
- **Ce que Whisper entend** (onglet Plans) : en voix des clips, la transcription du clip (`assets.meta.dialogue`) ; en
  voix de synthèse, celle du dernier calage.

Basculées le 01/10 : « Tout le collège le détestait » (2c288b3d) et « Elle oublie 50 000 € » (4527aef0). Les trois
drames déjà programmés sur YouTube restent en voix de synthèse : les basculer les ferait repartir comme de nouvelles
vidéos.

**Mots en trop autour d'une réplique (01/10 soir).** H3 ajoute parfois des mots avant ou après la réplique : « Les
développeurs, au lieu de voir, assez pour une porte », « Ah, Mellé, t'as porté… », « Personne ne viendra, je l'ai ».
En voix des clips, le montage ne garde que la réplique : `drama.line_window` cherche, dans les mots que Whisper entend,
la fenêtre la plus ressemblante à la réplique écrite (des mots du bord ne sont écartés que si la ressemblance gagne au
moins 0,04) ; `drama.line_cut` en tire le début coupé du clip (0,35 s avant la réplique, image et son ensemble :
`dialogue_heads` → `RenderPlan.clip_offsets` et `build_dialogue_track(heads=…)`) ou la fin de la scène (avant le
premier mot en trop). Sur les 6 drames du 28/09 : 9 plans touchés, dont « Des salaudes décidables » avant « Non. Ce
n'est pas à moi » (4527aef0). Une suite de mini-série prend désormais le format de sa série, plus celui de la partie 1
(`arcs.launch_part`).

Basculées à la demande de Luca le 01/10 au soir (voix des clips, montage refait) : « La fille du gardien » (972f19d7),
« Il pouvait se venger » (cab6db86), « Elle fait semblant d'être ruinée » (56cad13b), toutes trois programmées, et
« Elle vend son verger » (9d189b5d), publiée. Leurs envois YouTube restent en place (Luca les supprime dans YouTube
Studio, sinon les deux versions sortent) ; les publications TikTok et Instagram encore programmées sont annulées ; les
vidéos reviennent à valider. La copie « voix dessinées » de « Tout le collège » (50a4c966), refusée, reste telle
quelle : l'originale 2c288b3d est déjà en voix des clips, sans aucune prise de synthèse.

**Mixage d'une vidéo en voix des clips (Retoucher → Musique et son, 01/10 soir).** Luca n'entendait plus que la musique
en réglant son volume : l'écran traitait la vidéo comme « sans voix » (`voiced` = format A seulement). Il montrait
alors le curseur « Musique » des chantiers (`solo_db`), que le montage n'utilise pas ici : avec une piste de voix, il
prend « Musique sous la voix » (`music_db`) et la baisse sous les répliques (`duck_db`). Désormais :
- le montage enregistre le son des clips mis bout à bout (`dialogue.wav`) comme voix de la vidéo (asset `narration`,
  `meta.provider = clips`) ; « Nouveau mixage » le joue sous la musique, aux niveaux réglés ; les 7 drames déjà en voix
  des clips ont reçu cet asset sans être remontés ;
- curseurs « Voix des clips », « Musique sous la voix », « Baisse pendant que la voix parle », et sous-titres
  modifiables, comme pour une vidéo narrée ;
- **case « Bruitages »** pour toute vidéo qui peut en avoir (drames, chantiers, visites) : `videos.retouch.sfx`
  (vrai / faux ; absent = le défaut du format, voir §13) ; cochée, le volume des bruitages (−20 à +12 dB). L'écoute du
  navigateur ne joue jamais les bruitages : ils ne s'entendent qu'une fois la vidéo refaite.

## 13. Drames sans bruitages ajoutés, son coupé plan par plan (01/10 soir)

Luca : « il y a déjà des bruitages sur les clips d'origine, on n'est pas obligé d'en mettre en plus » ; et, devant
« Tout le collège le détestait », sur un plan « les bruitages n'apportent rien, ils sont plus bruyants qu'autre
chose » : il veut cocher les plans dont il retire le son, puis confirmer d'un bouton qui refait la vidéo.

- **Aucun bruitage ajouté par défaut sur un drame** (`Retouch.bruitages(drama=True)` = faux sans retouche) : le
  bruiteur (`sfx_pick`) ne tourne plus, les étiquettes sfx ne sont plus mixées. La case « Bruitages » de Retoucher →
  Musique et son les remet pour une vidéo (`retouch.sfx = true`). Chantiers et visites gardent les leurs ; la case les
  retire (`retouch.sfx = false`). L'ambiance des clips sous les plans muets d'un drame en voix de synthèse reste : c'est
  le son du clip, pas un bruitage ajouté. Au passage, cette ambiance n'était jamais posée (`drama_sound` : le paramètre
  `ambience` était écrasé par une liste du même nom).
- **Retoucher → Plans → « Couper le son de plans »** : une case par plan, puis « Couper le son de N plans et refaire
  la vidéo » (action `muteClips`, `videos.retouch.muted` = index des plans, SQL `retouch_video` sans voix). Décocher
  rend le son. Au montage (`prepare_video`) :
  - plan sans réplique : son du clip coupé (silence dans la piste de voix des clips ; pas d'ambiance en voix de
    synthèse), ni bruitage ; la musique continue ;
  - plan avec réplique, en voix des clips : la **voix seule** du clip remplace son son (`drama.isolate_voices` →
    `tts_runners/isolate_voice.py`, Demucs htdemucs de l'environnement `C:\YouTube2\tts\vc`, sur le processeur,
    ≈ 10 s par clip plus 10 s de chargement ; fichier `scene_NN.voix.wav` à côté du clip, refait si le clip est plus
    récent). Séparation impossible : le plan garde son son, noté `voix_seule_impossible` dans le résultat du montage ;
  - une prise de synthèse validée (`retouch.lines`) prime sur la voix seule.
- Essai sur les clips de « Tout le collège » (sans toucher à la vidéo) : plan 3 sans réplique de −19,8 à −91 dB ;
  plan 4 parlé, bruit avant la réplique de −50 à −76 dB, réplique entendue mot pour mot par Whisper.
- « Elle fait semblant d'être ruinée » (56cad13b, à valider) remontée sans bruitages ajoutés le 01/10 à 18 h. « La
  fille du gardien » et « Il pouvait se venger », validées et programmées par Luca, gardent les leurs.

## 12. Une voix fixe par personnage, sur le jeu de H3 (banc du 01/10)

H3 donne de très bonnes voix, mais la voix d'un même personnage change d'un clip à l'autre, et donc d'un épisode à
l'autre. Luca : « utile seulement si chaque personnage garde sa voix à chaque nouvelle vidéo ». La **conversion de
voix** garde le jeu de H3 (rythme, émotion, calage sur les lèvres) et ne change que le timbre, vers la voix
**dessinée** du personnage (sa voix Qwen, « garçon timide »…, la même dans toutes les vidéos d'une série).
- `tts_runners/voice_convert.py`, environnement `C:\YouTube2\tts\vc` (`install_tts.ps1 -Engine vc` : Python 3.11,
  PyTorch 2.6 CUDA 12.4, chatterbox-tts, demucs, `setuptools<81` car le filigrane `perth` importe `pkg_resources`).
  Pour chaque clip, trois étapes :
  1. Demucs (htdemucs) sépare la voix de l'ambiance ;
  2. Chatterbox VC (MIT) convertit la voix vers la référence ;
  3. la voix convertie est ramenée à la longueur et au niveau de la voix d'origine, puis remélangée à l'ambiance.
- `scripts/bench_vc.py <vidéo> [--refs dessinee,h3]` : convertit, puis crée une vidéo par référence (copie de la
  production en voix des clips, `retouch.lines` = les fichiers convertis, asset `take` de source `vc`, posés dès 0 s
  par `assemble.replaced_lines`). Fichiers dans `C:\YouTube2\bench\2026-10-01-voix-fixes` (`*.voix.wav` = la voix
  seule).

Résultats sur « Tout le collège le détestait » (12 répliques, 32 s de calcul sur la RTX 3070) :

| Personnage | Ressemblance entre ses répliques, voix H3 | Après conversion |
|---|---|---|
| Litchi | 0,67 | 0,83 |
| Madame Poire | 0,53 | 0,77 |
| Durian | 0,54 | 0,63 |
| Pastèque | 0,59 | 0,62 |

Ressemblance moyenne (cosinus, empreinte wespeaker) entre les répliques d'un même personnage ; 1 = même voix.
Whisper comprend presque tout ; deux pertes chez Pastèque (« puant » → « tuant », « Tais-toi » → « Chut, dis-toi »).
Vidéo à comparer : « Partie 1 : Tout le collège le détestait · voix dessinées » (50a4c966). Si Luca l'adopte, il reste
à brancher la conversion au montage des drames, plan par plan, avec cache.
