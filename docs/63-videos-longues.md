# 63 · Vidéos longues « histoire et mystères », narrées par Luca (04/10)

Décision de Luca (04/10, après l'étude docs/61) :
- des vidéos longues « histoire et mystères » sur sa chaîne actuelle, Arzak Parker ;
- images et clips entièrement faits par IA ;
- sa vraie voix sur les scripts, qu'il prend plaisir à lire, avec un modificateur de voix en option ;
- tout depuis l'application, sur une page dédiée.

Il demande que tout le travail sur le storytelling soit appliqué, et que sujets, titres et miniatures soient excellents.
Migrations **0053** (jobs) et **0054** (tables). Page **Vidéos longues** du dashboard.

## 1. Pour Luca

1. **Choisir un sujet.**
   - « Proposer des sujets » : 3 à 12 sujets, avec une envie facultative (« Égypte », « Moyen Âge »…).
   - Chaque sujet arrive avec son titre et deux autres, l'ouverture, la promesse, l'angle, pourquoi on clique, le
     concept de miniature, ses pages Wikipédia et une note sur 100.
   - « Mon sujet » : tu tapes ton sujet, l'agent l'emballe de la même façon.
   - « Écrire », avec une remarque si tu veux.
2. **Relire le script** (10 à 20 min d'écriture). La fiche montre l'idée centrale, la promesse, l'enjeu, la dernière
   phrase, les remarques de la relecture finale, puis chaque chapitre paragraphe par paragraphe, avec ce qu'on verra.
   - Tu corriges un paragraphe directement.
   - « Réécrire avec une remarque » refait un chapitre ; « Tout réécrire » refait la vidéo.
   - « Valider le script » : le réalisateur découpe les plans, les images partent, le Studio voix s'ouvre.
3. **Studio voix** : le texte en grand, comme un prompteur, paragraphe par paragraphe.
   - **Espace** pour enregistrer, Espace pour arrêter ; « Enchaîner » passe au paragraphe suivant.
   - Chaque prise part au worker, et Whisper dit en quelques secondes si tout le texte a été lu (« Sauté : … »).
   - Reformuler est permis : c'est ce que tu dis qui compte. Tu réécoutes et tu gardes la prise que tu préfères.
   - Pour savoir où tu en es : le niveau du micro, le choix du micro, et une pastille par paragraphe dans la colonne de
     gauche (gris : à lire, violet : vérification, vert : bon, orange : à vérifier).
   - « Terminer l'enregistrement » quand tout est lu.
4. **La suite se fait seule.** La voix est nettoyée (et modifiée si tu l'as demandé), puis le montage attend que les
   images et les clips soient faits. Un mail arrive quand la vidéo est prête.
5. **Regarder et publier.**
   - L'onglet **Vidéo** montre l'aperçu et ses chapitres ; l'onglet **Titre et miniature** les trois miniatures notées,
     les titres et la description.
   - « Programmer sur YouTube » envoie la vidéo en privé avec sa date. La date proposée est le prochain jour de sortie
     des Réglages : mardi, jeudi et samedi à 17 h par défaut.
   - L'envoi pose aussi la miniature choisie, les chapitres horodatés, les sources Wikipédia et la mention de l'IA.

**Mails.**
- « 📝 Script prêt à relire » ;
- « 🎙️ N vidéos à lire », chaque matin à 9 h tant qu'il en reste ;
- « 🎬 Vidéo longue prête ».

**Réglages** (en bas de la page) : jours et heure de sortie, durée visée (22 min), formats proposés, modificateur de voix
par défaut et voix d'arrivée.

## 2. Ce que les règles appliquent

Toutes les règles du récit de Luca (`rules_storytelling`, docs/24, 33, 37, 49, 57) sont données telles quelles aux
agents. S'y ajoutent les règles du format long (`rules_long`), tirées de l'étude du 04/10 (docs/61 et un relevé des
chaînes qui marchent) :

| Règle | D'où elle vient |
|---|---|
| La 1re minute confirme le clic : une scène au présent, la version admise, le « mais » avant 45 s, la question centrale, la promesse | Paddy Galloway, document de production de MrBeast, ouverture de SECRETS DES CIVILISATIONS (Sphinx, 708 k vues) |
| Une question centrale tenue jusqu'au bout ; révélation complète vers 80-90 % | même source ; Kallaway « relance en boucle » |
| 6 à 8 chapitres liés par « mais » et « donc », chacun finit sur une boucle ouverte | règles de Luca (South Park via Kallaway) |
| Relances vers 3, 6 et 10-12 min ; scène la plus forte entre 40 et 65 % | document MrBeast, Johnny Harris |
| Le vrai seulement : chaque fait vient du dossier ; établi, débattu ou supposé distingués ; jamais de témoin anonyme ni de thèse marginale | règles de Luca (docs/37, 49) ; on garde les formes des chaînes à succès, jamais leurs procédés |
| 150 mots par minute (22 min ≈ 3 300 mots) | 146 et 163 mots par minute mesurés sur deux vidéos françaises du créneau |
| Fin sans résumé, sans morale, sans appel à s'abonner ; la dernière phrase donne le sens et renvoie à la 1re scène | règles de Luca (« la fin s'écrit en premier ») |
| L'emballage d'abord : un sujet n'existe qu'avec son titre et sa miniature ; un nom connu du public | Galloway (30 % du temps sur l'idée et l'emballage) ; Sphinx 708 000 vues contre 14 000 pour un mur obscur, sur la même chaîne |
| Miniature : complète le titre sans le répéter, 3 éléments au plus, l'anomalie et pas la réponse, texte de 0 à 4 mots posé par le code, lisible à 160 × 90 px, honnête, 3 concepts différents | 1of10, vidIQ, Creator Insider (Test & Compare juge au temps de visionnage, pas au clic) |

**Deux formats**, alternés à la demande de Luca :
- **Mystère** (`guide_long_mystere`) : une énigme réelle menée comme une enquête.
- **Ta vie à l'époque** (`guide_long_epoque`) : une condition dure vécue en deuxième personne et au présent. Une
  colonne vertébrale la fait avancer : les heures d'une journée, ou les rangs d'une hiérarchie.

## 3. L'écriture (job long_write, voie io)

| Étape | Agent (onglet Agents) | Ce qui se passe |
|---|---|---|
| Sujets | `long_idea` | sujets + emballage ; gardés seulement si leur page Wikipédia existe |
| Dossier | code | la page principale française entière (32 000 signes), les pages suivantes (14 000), la version anglaise (20 000) et les pages anglaises proposées, numérotées [n] ; dans `<dossier>/dossier.txt` |
| Plan | `long_outline` | idée centrale, moteur, héros, enjeu, promesse, dernière phrase, ouverture, 6 à 8 chapitres (faits sourcés, question ouverte, durée) |
| Texte | `long_writer` | 3 chapitres par appel, paragraphes de 40 à 110 mots (texte lu et ce qu'on voit) |
| Correcteur | code (`lint_long`) | total à 90-112 % du budget, chapitres, paragraphes, phrases de 26 mots au plus, 1re phrase de 24 mots, formules interdites |
| Relecture | `long_review` | 2 tours de corrections, puis une relecture finale (ce que Luca voit) |
| Emballage | `long_packaging` | titres, description, tags, hashtags, commentaire épinglé, 3 miniatures, musique |
| Plans | `long_director` | après validation : un plan toutes les 12 à 20 mots dits, le mot où l'image change, image / clip / carte ; la 1re minute en clips, puis environ 1 clip pour 6 images |

Chaque étape est enregistrée dès qu'elle est faite (`script.work`). Si les modèles d'écriture forts sont épuisés, la
tâche attend une heure sans échouer et reprend où elle s'était arrêtée ; au bout de 12 h, le modèle de secours écrit.

**Vidéo Khéops montée de bout en bout** (04/10, avec une voix de test) :
- La voix de synthèse Windows a lu les 43 paragraphes à la place de Luca, envoyée par la route du Studio comme le
  navigateur.
- Résultat : 18 min 49 s en 1080p, 156 plans, 7 chapitres horodatés, −14,0 LUFS, l'image et le son de même durée
  jusqu'à la fin. Avec la voix de Luca, plus posée, ce sera plutôt 21 à 23 min.
- Temps de machine :
  - images : environ 50 s chacune ;
  - clips H3 en 832 × 480 : 5 min 10 s chacun ;
  - montage : 13 min, en plus des 3 pistes de musique générées la première fois.
  - Environ 9 h en tout ce jour-là, parce que les images et les clips passaient par la même carte graphique que les
    Shorts.
- Les prises de test sont effacées par « Tout réenregistrer » (onglet Voix). La vidéo montée reste visible jusqu'au
  nouveau montage. « Refaire certains paragraphes » rouvre le Studio en gardant les prises.

**Premier essai réel** (04/10). Les 6 sujets proposés :
- Khéops et le journal de Merer, 93/100 ;
- le feu de charbon du Titanic, 91 ;
- Pompéi, 90 ;
- Marseille en 1347, 88 ;
- un bâtisseur de Notre-Dame, 87 ;
- un forçat des galères de Louis XIV, 85.

Le script de Khéops fait 3 040 mots en 7 chapitres, environ 20 min. Il est sourcé : Pierre Tallet, Ouadi el-Jarf,
Merer, Zahi Hawass.

## 4. La voix (jobs long_take et long_make « voice »)

- **Prise.**
  - Le navigateur enregistre en webm/opus 48 kHz, sans les traitements du navigateur (annulation d'écho, réduction
    de bruit, gain automatique).
  - `POST /api/long/<id>/take` range la prise (`voix/prises/<paragraphe>_t<n>.webm`) et crée le job `long_take`,
    sur la voie preview, pris dans la seconde.
  - Whisper large-v3-turbo (processeur, `drama.transcribe`) en tire les mots horodatés.
  - Comparaison au texte, nombres dits en lettres des deux côtés : la prise est bonne à 88 % de mots retrouvés et
    sans 4 mots sautés d'affilée.
  - Essai du 04/10 avec la voix de synthèse de Windows : 37 prises bonnes sur 43, et 6 faux signalements (noms
    égyptiens, « 21e » dit « vingt et unième ») quand le seuil était à 3 mots.
- **Voix finale** (« Terminer l'enregistrement »).
  - Chaque prise gardée est coupée 0,12 s avant le 1er mot et 0,35 s après le dernier.
  - Elle est filtrée : coupe-bas 70 Hz, petit compresseur, et réduction de bruit seulement si la pièce est bruyante
    (bruit mesuré dans la prise au-dessus de −58 dB, réduction réglée sur ce bruit ; §11).
  - Elle est mise à −18 LUFS.
- **Modificateur** (option, par vidéo ou par défaut).
  - Chatterbox VC, déjà installé pour les drames (`C:\YouTube2\tts\vc`, `tts_runners/voice_convert.py`) : le jeu
    reste, le timbre devient celui d'une voix Qwen dessinée (narrateur grave, récit mystérieux…).
  - Jamais la voix d'une personne réelle.
  - Il s'applique aux prises déjà faites : changer le choix dans l'onglet Voix (« Appliquer à mes prises ») refait
    la voix finale puis le montage, sans rien réenregistrer. L'onglet dit quelle voix est dans le montage actuel
    (`voice.made_with`).
  - La voix seule du Studio passe directement dans Chatterbox, sans la séparation Demucs des drames (`clean`).
  - Depuis le 05/10, Luca règle aussi son propre modificateur, sans IA, et l'essaie sur un extrait en 1 à 2 s :
    Studio du modificateur (docs/67). Ses réglages passent avant les voix de Chatterbox dans le menu.
  - Environ 55 s pour un paragraphe de 23 s, chargement compris.

## 5. L'image et le montage (job long_make, voie gpu)

**Images.**
- 1664 × 928 avec le modèle d'image des Réglages, une image par plan.
- La bible visuelle et « cinematic widescreen film still » sont ajoutés à chaque prompt.
- Contrôle par la vision, 6 images par appel ; une image ratée est refaite une fois (« refaite » dans l'onglet
  Images).

**Clips.** 832 × 480, depuis l'image du plan, avec le modèle vidéo des Réglages (MiniMax H3), 5 s.

**Cartes.** `maps.render_clip` en 1920 × 1080. Si la carte ne peut pas se faire, une image d'IA prend sa place.

**Montage** (`longform/render.py`, `motion.py`).
- La timeline :
  - les paragraphes se suivent, avec 0,45 s de souffle entre deux paragraphes et 1,25 s entre deux chapitres ;
  - chaque plan commence au mot choisi par le réalisateur, retrouvé dans les mots horodatés de la prise ;
  - le premier plan d'un paragraphe commence dans le silence qui le précède.
- Les durées se comptent en images, à partir des temps cumulés : aucune dérive entre l'image et la voix sur 25 min.
- Les mouvements :
  - images fixes : zoom ou travelling lent, calculé image par image en Pillow (sous-pixel, sans les saccades de
    zoompan), environ 1,2 fois le temps réel, 3 plans en parallèle ;
  - clips : ralentis au plus de 25 %, puis leur dernier instant continue en image fixe animée.
- Un écran de chapitre (« CHAPITRE 2 / LA CITÉ ENGLOUTIE ») s'affiche 3,7 s sur le 1er plan de chaque chapitre, en bas
  à gauche, au-dessus des sous-titres.
- Les sous-titres sont gravés sur l'image montée (§12).
- Le son :
  - musique de fond générée par ACE-Step dans une bibliothèque à part (`DATA_DIR/music/long_<ambiance>`) : mystère,
    tension, épique, émotion, époque, 3 pistes de 3 min chacune ;
  - générée la première fois qu'elle sert, sans droits tiers (aucune réclamation Content ID possible) ;
  - enchaînée en fondus, baissée sous la voix par un compresseur commandé par la voix ;
  - le tout ramené à −14 LUFS.
- Les fichiers : `rendu/finale.mp4` (1080p) ; `apercu.mp4` (480p, lu dans la page) ; `poster.jpg`.
- Une ligne `videos` (origin `long`) relie la vidéo aux statistiques et à la Bibliothèque.

**Miniatures** (`longform/thumbnail.py`).
- L'image est générée sans texte, avec la zone du texte laissée libre.
- Le code pose le texte en Anton jaune, avec un contour noir de 9 px, sur un léger dégradé sombre. Un nombre n'est
  jamais coupé (« 7 000 » reste sur une ligne), et rien n'est posé dans les 15 % du bas.
- Format : 1280 × 720 JPEG.
- La vision note chaque miniature à la taille d'un téléphone ; la mieux notée est choisie, Luca peut en prendre une
  autre.

## 6. Ce qui relie la vidéo longue au reste

| Où | Quoi |
|---|---|
| `productions.kind = 'long'` | pause, arrêt, ordre de la file et panneau Tâches comme les Shorts ; un concept porte le titre ; exclue du tableau Création |
| `videos.origin = 'long'` | ni créneau des Shorts (`slots.py`), ni envoi automatique sur TikTok et Instagram (`plan_tiktok`, `plan_instagram`, `v_tiktok_backlog` ne prennent que `origin = 'app'`) |
| priorité 100 des images et des clips | la même que les clips des Shorts : l'ordre de la file (glisser dans Tâches, docs/40) décide qui passe d'abord sur la carte graphique |
| `YouTubeClient.upload(category=…)`, `set_thumbnail` | catégorie Éducation (27), contenu synthétique déclaré, miniature (50 unités ; refusée si la chaîne n'est pas validée par téléphone : l'erreur s'affiche dans la fiche) |
| `scheduler` 9 h | mail « vidéos à lire » |

## 7. Comment c'est fait

| Où | Quoi |
|---|---|
| `supabase/migrations/0053_videos_longues_jobs.sql` | job_type long_write, long_make, long_take |
| `supabase/migrations/0054_videos_longues.sql` | `long_videos`, `long_shots`, `long_takes`, `productions.kind`, origin `long`, réglages `app_settings.long` |
| `services/worker/worker/longform/` | `prompts.py`, `models.py`, `write.py`, `voice.py`, `motion.py`, `render.py`, `captions.py`, `thumbnail.py`, `music.py`, `flow.py` |
| `services/worker/worker/steps/long_write.py`, `long_make.py`, `long_take.py` | les trois jobs |
| `services/worker/tests/test_longform.py` | calculs : budget, correcteur, plans, comparaison voix / texte, timeline sans dérive, chapitres |
| `apps/dashboard/src/app/long/` | page, fiche (`[id]`), Studio voix (`[id]/studio`), actions |
| `apps/dashboard/src/app/api/long/[id]/` | `file` (images, clips, prises, miniatures, vidéo), `take` (envoi d'une prise), `state` (relu par le Studio) |
| `apps/dashboard/src/components/long/` | `long-view.tsx`, `long-detail.tsx`, `studio.tsx` |
| `apps/dashboard/src/lib/long.ts`, `long-types.ts` | lecture serveur, types |
| `apps/dashboard/src/lib/agent-catalog.ts` | les 8 agents et 5 consignes dans l'onglet Agents |

`WORKER_JOB_TYPES` du `.env` du worker contient `long_write,long_make,long_take` (ajouté le 04/10 sur le PC et dans
`.env.example`).

## 8. Points de Luca du 04/10 (après les premiers clips de Khéops)

| Point | Où on en est |
|---|---|
| Miniatures dans le **style de la niche**, d'autres proposées avec de meilleures notes | fait (§9) |
| **Garder** une miniature qui plaît et en refaire d'autres sans la perdre ; **3 miniatures** pour le test A/B | fait (§9) |
| Des **sujets qui ont déjà marché**, racontés autrement | fait (§9) |
| Des **faits vérifiés et vérifiables** avec de vraies sources (Wikipédia et d'autres sources légitimes), pas de désinformation | fait (§9) |
| **Bruitages** de documentaire : suspense, transitions, révélations | à faire après le montage de Khéops (il touche le montage) |
| Le **son des clips** n'est jamais utilisé | fait : le montage ne prend que l'image des clips |
| **Musique** légère, cohérente, d'ambiance, sans droits | fait : générée par ACE-Step (licence MIT) dans une bibliothèque à part, baissée sous la voix ; à écouter sur Khéops |

## 9. Sources vérifiées, sujets qui ont marché, miniatures de la niche (04/10 soir)

**Des faits vérifiés et vérifiables** (`longform/sources.py`, agent `long_factcheck`) :
- Le dossier ne s'arrête plus à Wikipédia.
  - On lit les références que les articles Wikipédia citent eux-mêmes (API `prop=extlinks`).
  - On ne garde que les sources sérieuses (`TRUSTED` : CNRS, INRAP, IFAO, Persée, HAL, OpenEdition, BnF, Louvre,
    British Museum, Smithsonian, National Geographic, UNESCO, Nature, Science, universités, Britannica, BBC, Le Monde…).
  - On les lit en entier (texte des paragraphes, analyseur HTML de Python) et on garde celles qui parlent vraiment du
    sujet : 6 au plus, 2 par site, 6 000 signes chacune, numérotées comme les pages Wikipédia.
  - Essai Khéops : Sciences et Avenir (les papyrus du port de Khéops), l'IFAO (l'institut qui fouille Ouadi el-Jarf),
    Nature (la cavité découverte dans la pyramide), Smithsonian (le plus vieux papyrus du monde). 23 s.
- La règle du récit long le dit : un fait important se confirme par deux sources ; quand elles divergent, on le dit.
- Après la relecture finale, le **vérificateur des faits** relève tous les faits du script (dates, nombres, noms,
  causes, superlatifs) et les classe :
  - confirmé (avec les numéros de ses sources) ;
  - hypothèse dite comme telle ;
  - pas dans les sources ;
  - contredit.
- Les faits non confirmés repartent au conteur avec leur correction, puis le vérificateur repasse.
- L'onglet Script montre le bilan (« 58 faits : 56 confirmés, 2 hypothèses »), ce qui reste à revoir, la liste des
  sources avec leurs liens et tous les faits vérifiés.

**Des sujets qui ont déjà marché** :
- L'agent des sujets reçoit les vidéos longues les plus vues de nos thèmes : les chaînes de la Découverte (histoire,
  mystères, science, géopolitique…), puis la veille.
- Il reprend un sujet qui a déjà marché autrement, et donne :
  - `proof`, 1 à 3 vidéos de la liste (le code jette toute preuve qui n'est pas dans la liste) ;
  - `new_angle`, ce que notre vidéo apporte.
- Les sujets avec preuve passent devant. La carte du sujet montre « A déjà marché : « … » (708 000 vues) » et notre
  angle.

**Miniatures dans le style de la niche** :
- Consigne `guide_thumb_niche`, par défaut : le monument énorme avec des humains minuscules, une anomalie qui se voit,
  un contraste froid / chaud, le « toi » de dos pour « ta vie à l'époque », 2 à 4 mots jaunes qui posent le conflit.
- « Étudier les miniatures de la niche » (agent `long_thumb_style`) : la vision regarde les miniatures des 12 vidéos
  les plus vues de la Découverte et en tire un style et des règles. Ils remplacent la consigne pour l'emballage et les
  nouvelles miniatures (`app_settings.long.thumb_style`).
- Chaque miniature a quatre boutons :
  - **Principale** : celle posée à l'envoi ; elle est forcément gardée ;
  - **Garder** : jamais remplacée ;
  - **A/B** : 3 au plus, à ajouter dans YouTube Studio → Tester et comparer, que l'API ne permet pas ;
  - **Retirer**.
- « Proposer 3 autres miniatures » (agent `long_thumbs`) :
  - de nouveaux concepts, différents de ceux qui existent ;
  - censés battre la meilleure note, dans le style de la niche ;
  - ajoutés aux autres, jamais à leur place.

## 10. Limites et suite

- Le micro compte : un micro de casque ou de téléphone suffit pour essayer. Un micro USB dynamique (50 à 80 €) quand
  la chaîne rapporte.
- La miniature personnalisée exige une chaîne validée par téléphone (YouTube Studio → Paramètres → Chaîne →
  Éligibilité aux fonctionnalités, ou youtube.com/verify). Les autorisations Google de l'appli n'y sont pour rien.
  05/10 : Khéops envoyée, miniature refusée (403 « doesn't have permissions to upload and set custom video
  thumbnails ») sur Arzak Parker. La fiche le dit en clair ; une fois la chaîne validée, **Vidéo → Publication →
  Reposer la miniature** (action `thumbnail` de long_write, 50 unités) pose la miniature choisie sur la vidéo déjà
  envoyée. Un refus n'est pas relancé tout seul. Le même soir, Luca a validé la chaîne : miniature posée à 19 h 44.
  Il a ensuite supprimé la vidéo dans Studio. **Envoyer à nouveau** (même carte, `publish` avec `again`) envoie la
  vidéo une nouvelle fois avec une nouvelle date et la miniature choisie. L'ancien envoi est gardé dans
  `videos.previous_uploads` (docs/44). L'envoi est refusé si l'ancienne vidéo est encore sur YouTube : la supprimer
  d'abord dans Studio, pour ne pas avoir de doublon.
- Les cartes en 16:9 n'ont été essayées qu'en code. Si le cadrage ne va pas, une image d'IA prend la place de la
  carte.
- À venir :
  - l'onglet Découverte dans Recherche (docs/61 §8) ;
  - des extraits de plus d'1 min pour TikTok et les Shorts ;
  - le test des titres et miniatures dans YouTube Studio.

## 11. La voix « IA » du premier montage (05/10)

Luca a enregistré les 43 paragraphes de Khéops. Dans le montage, sa voix sonnait « électrique », comme une voix de
synthèse ; ses prises, écoutées dans l'onglet Voix, non. Le modificateur, activé après coup, n'avait rien changé.

**Cause : la réduction de bruit du nettoyage.**
- `afftdn=nr=8:nf=-35` supposait un bruit de fond à −35 dB. La pièce de Luca est à −68 dB environ (−62 à −73 selon
  les 91 prises).
- Le filtre prenait donc les harmoniques et les consonnes pour du bruit et les baissait jusqu'à 8 dB, case par case
  et en variant sans cesse : le timbre métallique des voix de synthèse.

Mesuré sur le paragraphe 2, face à la prise brute :

| Bande | Ancien nettoyage | Nouveau nettoyage |
|---|---|---|
| 70-1 000 Hz | 30 % des cases abîmées (écart > 4 dB) | 2,7 % |
| 1-4 kHz | −5,1 dB, 72 % | 0,8 % |
| 4-8 kHz | −5,1 dB, 72 % | 0,5 % |
| 8-16 kHz | −5,4 dB, 80 % | 0,6 % |

**Écartés :**
- la stéréo : les deux canaux des prises sont identiques ;
- le compresseur : moins de 2 % des cases bougent ;
- le limiteur final : il touche 6,6 % des fenêtres de parole, de moins de 2 dB.

**Corrigé :**
- `voice.noise_floor` mesure le bruit de chaque prise (3e centile des niveaux sur 50 ms) ;
- `voice.denoise_filter` ne réduit le bruit qu'au-dessus de −58 dB, réglé sur ce bruit mesuré. Aucune des prises de
  Khéops n'est débruitée.

**Le modificateur ne marchait pas après coup.** `setVoiceModifier` notait le choix sans refaire la voix finale. Il la
refait maintenant, puis le montage suit (§4).

**Écoute comparative** : Bibliothèque → Démos et essais, « Vidéo longue : pourquoi ta voix sonnait « IA » dans le
montage » (`C:\YouTube2\bench\2026-10-05-voix-longue-nettoyage`) :
1. la prise brute ;
2. le montage de 10 h 24 ;
3. le même passage corrigé, sur la même musique ;
4. et 5. la voix seule, avant et après ;
6. le modificateur Chatterbox (voix « narrateur »).

Khéops a été relancé à 10 h 51 : voix nettoyée à nouveau, modificateur « Narrateur grave », puis montage.

## 12. Les sous-titres (05/10)

Demande de Luca : « il faut absolument mettre des sous-titres », le script, comme dans les Shorts.

**Ce qu'on voit.**
- Le texte du script, en bas de l'image, sur deux lignes au plus.
- Le style des Shorts ramené au 16:9 : Montserrat grasse, blanc à contour noir, le mot dit en jaune. Pas de majuscules
  partout : 20 minutes de lecture.
- Une légende par morceau de phrase : coupée à chaque fin de phrase et aux virgules (après 3 mots), 7 mots au plus. Un
  morceau trop long est partagé en parts égales, sans finir sur un petit mot qui annonce la suite (« de », « d'un »,
  « le ») ni sur un nombre séparé de son unité. Khéops : 557 légendes de 5,5 mots en moyenne.
- L'écran de chapitre est remonté de 120 px : il s'arrête à 820 px, les sous-titres commencent vers 885 px.

**Le calage sur la voix** (`longform/captions.py`).
- Le texte affiché est celui du script, pas ce que Whisper a entendu : les noms (Merer, Ouadi el-Jarf) et les nombres
  en chiffres (« 4 500 ans », docs/33) restent justes.
- Chaque mot prend le moment où Luca le dit. Les mots du script sont alignés sur les mots horodatés de la prise
  gardée, nombres dits en lettres des deux côtés, comme la vérification des prises (§4).
- Un mot reformulé, sauté ou mal entendu prend sa place entre ses voisins, au prorata de sa longueur.
- Une ponctuation isolée par des espaces (« Merer », « ici : ») reste collée à son mot.
- Le modificateur de voix garde les temps : celui de Luca les recalcule quand il change le débit (§4).

**Au montage** (`long_make`, action render).
- Après l'assemblage de l'image : `rendu/sous-titres/subtitles.ass` (et sa police), puis un passage de l'encodeur sur
  toute la vidéo (`rendu/image_sous-titree.mp4`). Environ 10 fois le temps réel avec NVENC, soit 2 min pour 18 min.
- La progression s'affiche dans Tâches (« Montage : sous-titres (45 %) ») ; l'arrêt depuis le dashboard coupe FFmpeg.
- `timeline.subtitles` dit si le montage en a.
- Réglages de la page Vidéos longues : interrupteur « Sous-titres », allumé par défaut (`app_settings.long.subtitles`).
  Il compte au prochain montage ; « Refaire le montage » l'applique à une vidéo déjà montée.

**Essai** : Bibliothèque → Démos et essais, « Vidéo longue : les sous-titres »
(`C:\YouTube2\bench\2026-10-05-sous-titres-video-longue`) : l'ouverture de Khéops et le début du chapitre 1.
