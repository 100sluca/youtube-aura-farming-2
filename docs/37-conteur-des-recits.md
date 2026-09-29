# 37 · Le conteur des récits : l'histoire d'abord, les plans ensuite

> 2026-09-29. Demande de Luca en lisant « Le trésor de Begrâm » (production 3a600c14, série « Histoires vraies »,
> 40 s) : « trop raccourci », « décousu », ça ne suit ni les normes du storytelling ni la psychologie humaine ; il faut
> de l'intrigue, du contexte, des clips d'une minute à une minute trente, et un agent storytelling « extrêmement bon »
> nourri des règles qu'il a rassemblées (3 C, montrer plutôt que dire, enjeux, « donc / pourtant », une seule idée,
> l'accroche de Kallaway et de Jenny Hoyos, l'ironie dramatique). Même chose pour les histoires d'animaux. Le Karma des
> Fruits garde sa structure, tirée de vidéos qui marchent, mais reçoit aussi les règles.

## 1. Le constat

Le texte lu par Luca (huit scènes de 4 à 6 s, 88 mots) :

> En 1937, une cache secrète livre des trésors venus d'Asie. À 60 km de Kaboul, Begrâm cache l'ancienne cité
> d'Alexandrie du Caucase. La chambre 10 dévoile des sculptures en ivoire et des verres rares. Le trésor mêle des
> ivoires indiens, des laques chinoises et des verres romains. Joseph et Ria Hackin mettent au jour cet ensemble en 1937.
> Mais cette salle fut murée avant la guerre face au danger. Partagées entre la France et l'Afghanistan, ces pièces
> rejoignent Kaboul. Une cache secrète murée qui gardait les secrets de la route.

| Constat | Cause | Correction |
|---|---|---|
| Huit faits posés les uns après les autres, sans fil | Le scénariste écrivait le script scène par scène dans le JSON (image, mouvement, narration, texte à l'écran) : chaque scène devenait un fait isolé | Le **conteur** écrit l'histoire en entier, seule ; le code la découpe ensuite en scènes sans en changer un mot ; le **réalisateur** fait les plans |
| Pas de héros, pas d'enjeu, pas d'intrigue | Les règles parlaient de l'enjeu d'un lieu, pas d'un héros qui veut quelque chose ; rien sur la promesse, l'ironie, les « mais / donc » | **Règles du récit** réécrites (§ 3) ; l'agent idées cherche des histoires (héros, désir, obstacle, moteur), plus des sujets |
| Trop court pour comprendre | 40 s, 8 scènes | **75 s** (1 min 15 ; 56 à 94 s admis) pour les histoires vraies et les animaux ; le conteur reçoit un budget de mots (≈ 218) |
| « Mais cette salle fut murée avant la guerre » : contresens | Deux phrases de la page mélangées : la salle « murée, sans doute à la veille d'une attaque », dans l'Antiquité, et les fouilleurs qui « disparaissent tragiquement lors de la Seconde Guerre mondiale » | Le relecteur vérifie chaque fait contre le dossier ; le conteur relit les pages entières |
| L'histoire était pourtant dans le dossier | Page Wikipédia : Foucher repère le site en 1923 mais Paris l'envoie fouiller ailleurs ; Ria Hackin trouve la salle en 1937, murée à la veille d'une attaque, les étagères effondrées ; les fouilles s'arrêtent inachevées en 1940, le couple Hackin disparaît pendant la guerre ; des pièces du musée de Kaboul sont remises à l'abri à Paris en 1997-1999 | Le conteur doit chercher dans le dossier le héros, l'ironie et le renversement (méthode, § 4) |

## 2. Le nouveau déroulé (étape script des récits narrés)

```
idée validée (✓ Création)
  → CONTEUR (prompt script) : l'histoire en entier (StoryDraft) — idée unique, moteur, héros et enjeu,
    DERNIÈRE PHRASE écrite d'abord, puis les temps : accroche, promesse, contexte, conflit(s), renversement,
    réponse, chute ; chaque temps avec ce qu'on doit y voir
  → CORRECTEUR DU RÉCIT (code, storycraft.lint_story) + RELECTEUR (prompt script_review, checklist du récit)
  → le fond : si le relecteur refuse, le conteur réécrit (avec ses remarques et les écarts mesurés) ; cette
    réécriture est RELUE ; un 2e refus donne une 2e réécriture, qui n'est plus relue
  → la forme : s'il reste des écarts mesurables (rythme, longueurs, budget), une passe qui ne touche pas au fond,
    gardée si elle en corrige
  → DÉCOUPAGE (code, storycraft.split_scenes) : phrase par phrase, sans changer un mot
  → RÉALISATEUR (prompt script_shots) : un plan par scène (image, mouvement, texte à l'écran, carte, continuité),
    bible visuelle, boucle, musique, métadonnées ; une scène oubliée est redemandée une fois
  → ASSEMBLAGE (code, storycraft.build_script) → correcteur du script (storytelling.lint_script) → storyboard
```

Appels au LLM (chaîne d'écriture de Réglages → IA) : 3 au minimum (conteur, relecteur, réalisateur), 8 au plus. Le
récit est gardé dans le script (`ScriptV1.story`) ; une scène réinventée ensuite change la narration du script, pas ce
brouillon. Les recettes à scénariste propre (chantier, visite, drame) ne changent pas de déroulé.

**Modèles forts seulement pour le conteur et son relecteur** (`steps/script.py`, `strong_writers`) : ils n'utilisent
pas les modèles de secours de la chaîne d'écriture (nom en « lite » ou « nano », Gemini 3.5 Flash-Lite aujourd'hui). Si
tous les autres sont épuisés (quota), la tâche **attend une heure** sans échouer (panneau Tâches : « Le conteur attend
un modèle d'écriture fort ») et recommence ; après 12 h d'attente, elle se contente du secours (journal
`script.modele_de_secours`). Le réalisateur, lui, prend toute la chaîne. Raison : l'essai du § 10, où Flash-Lite a écrit
un récit trop court, monotone, avec une mort inventée.

## 3. Les règles du récit (clé `rules_storytelling`, onglet Agents)

Communes à toute histoire, en voix off ou en dialogues ; données à l'agent idées, au conteur, au relecteur, à la scène
réinventée et au scénariste des drames. Onze règles et une checklist :

| Règle | D'où elle vient |
|---|---|
| Une seule idée ; couper dates, grades et chiffres de décor | Luca (« une seule idée centrale ») ; le chiffre qui porte l'enjeu se garde (V2) |
| Les 3 C : contexte (qui, où, quand, ce que le héros veut), conflit, conclusion | Luca |
| L'enjeu : ce que le héros veut, ce qu'il perd s'il échoue | Luca |
| « Mais » et « donc » : chaque temps est une conséquence ou un obstacle du précédent ; la règle porte sur le lien, pas sur le mot ; un rebondissement toutes les 7-8 s | Trey Parker et Matt Stone cités par Kallaway (V3 0:24-3:23), Jenny Hoyos (V1 22:55) |
| Montrer, pas dire : actions et détails au lieu d'adjectifs | Luca |
| L'accroche sans délai : le sujet exact dans la 1re phrase, un contraste ; les 4 erreurs (délai, confusion, hors-sujet, désintérêt) ; relire l'accroche seule ; elle ferait un bon titre ; l'image dit la même chose au même instant | Kallaway (V2), Jenny Hoyos (V1 2:22, 9:41) |
| La 2e phrase est une promesse qui annonce la fin ; accroche + promesse en 6 s | Jenny Hoyos, « hook + foreshadow » (V1 20:48) |
| Boucles ouvertes, mécanisme (3 tentatives, compte à rebours), la promesse tenue puis une fin tordue | Jenny Hoyos (V1 16:24-18:35) |
| L'ironie dramatique en 4 temps (l'erreur, l'évidence, l'entêtement, le retour de bâton) | Luca |
| Des humains et un angle rare | Luca ; « story lens » de Kallaway (V3 8:01) |
| Des mots d'enfant de 10 ans (CM2 au plus), le ton d'une histoire racontée à un ami, des phrases de longueurs variées (bords dentelés) | Jenny Hoyos (V1 3:50, 5ᵉ année US), Kallaway (V3 3:23 : Gary Provost ; 5:20 : le ton) |
| La fin écrite en premier, avec l'accroche ; elle peut être partagée seule ; on coupe net après | Kallaway, « Direction » et « the last dab » (V3 6:53) ; Jenny Hoyos (V1 6:42 : couper la dernière seconde a fait passer une vidéo de 83 à 88 % de rétention) |

Les règles de l'image, qui faisaient la 4ᵉ partie de l'ancien texte, sont une consigne à part : `rules_images`
(réalisateur, scène réinventée). Celles de la voix (budget de mots, phrases de 3 à 16 mots, nombres en chiffres) sont
dans le prompt du conteur.

## 4. Le conteur (clé `script`, « Conteur · histoires »)

Il reçoit le brief du thème, les règles du récit, l'idée, les faits sourcés, le **dossier** (pages Wikipédia entières,
française et anglaise), la durée visée avec son budget de mots, les règles du titre d'accroche, la stratégie, les leçons
validées et le texte de trois vidéos de la chaîne qui ont bien marché (pour le ton). Il rend, dans cet ordre :
`central_idea`, `engine` (enquête, ironie dramatique, course contre la montre, trésor sous les yeux, l'erreur à un
million…), `protagonist`, `stakes`, `ending` (la dernière phrase, écrite avant le reste), puis `beats` — chaque temps a
un `part` (hook, promise, context, conflict, twist, payoff, ending), un `text` (ce que dit la voix) et un `show` (ce qu'on
doit voir) — et `hook_title`. Le prompt contient un exemple de construction (le galion San José, pour la forme).

Budget de mots dits (2,9 mots par seconde de vidéo, respirations comprises) :

| Durée visée | Mots visés | Admis |
|---|---|---|
| 30 s (maisons de rêve) | 87 | 74 à 97 |
| 40 s | 116 | 99 à 130 |
| 75 s (histoires vraies, animaux) | 218 | 185 à 244 |
| 90 s | 261 | 222 à 292 |

## 5. Ce que le code mesure

**Le récit** (`lint_story`, avant le découpage) : il commence par l'accroche et finit par la chute ; une promesse dans
les 3 premiers temps, un contexte avant le conflit, au moins un conflit ; accroche de 14 mots dits au plus ; accroche
et promesse de 22 mots à elles deux ; contexte avant 12 s ; phrases de 18 mots au plus ; dès 8 phrases, au moins 15 %
de phrases courtes (5 mots ou moins) et 15 % de longues (12 ou plus) ; ni « et ensuite », ni « puis », ni « après ça » ;
chute de 12 mots au plus ; au plus un nombre par tranche de 10 s (4 au moins) ; budget de mots ; titre d'accroche ;
pas d'appel à l'action, de formule d'ouverture interdite ni de superlatif vide. Un nombre compte pour les mots qui le
disent (« 1937 » = 4 mots).

**Le script découpé** (`lint_script`, inchangé) : rôles, révélation avant 12 s, mots par scène, narration qui couvre
70 % de la durée, une seule carte, durée à ± 25 %. Ce qui reste après les reprises est gardé dans `productions.lint`
(les écarts du récit préfixés « récit : »).

## 6. Le découpage (code)

`split_scenes` regroupe les phrases d'un même temps jusqu'à 16 mots dits par scène ; une scène n'est jamais à cheval
sur deux temps ; la première phrase de l'accroche est seule dans la scène 1 ; au-delà de 24 scènes, le regroupement
s'élargit. Durée d'une scène = sa voix (3,2 mots/s, débit mesuré de Qwen3-TTS « mystère ») + 0,45 s de silence, au
dixième supérieur, entre 2 et 8 s, jamais moins que ce qu'admet le correcteur. Rôles : la scène 1 = hook, la 1re scène
de contexte = reveal, promesse et contexte = setup, conflit et renversement = escalation, réponse = payoff, la dernière
= loop. Une vidéo de 75 s fait ainsi 15 à 19 scènes (8 avant) : **2 fois plus d'images et de clips à calculer**
(principe de gratuité : le temps de calcul compte moins que la qualité).

## 7. Le réalisateur (clé `script_shots`, « Réalisateur · histoires »)

Il reçoit le récit, les scènes (index, rôle, durée, narration, ce que le conteur veut y montrer), les règles de l'image,
la consigne de continuité, les musiques disponibles, le style, les faits et le dossier (pour l'exactitude des images).
Il rend un plan par scène (`visual_prompt`, `motion_prompt`, `on_screen_text`, `continues_previous`, `map`), la bible
visuelle commune (`design_bible`, ajoutée à chaque image), la boucle, l'ambiance musicale et des métadonnées. Le code
garde la narration du conteur mot pour mot ; une scène sans plan prend ce que le conteur voulait y montrer ; une seule
carte (la première) ; un texte à l'écran de plus de 5 mots est retiré ; la scène 1 et la boucle sont des coupes.
« Réinventer » une scène d'un récit donne à l'agent `scene_rewrite` les consignes du réalisateur et les règles du récit
et de l'image ; il réécrit aussi la narration de la scène.

## 8. Ailleurs

- **Agent idées** (clé `idea`) : une idée est une histoire (accroche = sujet + contraste ; prémisse = héros, désir,
  obstacle, risque, renversement ; angle = le moteur) ; 8 à 12 faits qui couvrent le contexte, l'enjeu, le conflit, les
  rebondissements et la fin ; la durée du thème est dans son message.
- **Drames** (Karma des Fruits, Histoires de familles, Histoires d'animaux) : le scénariste reçoit les règles du récit,
  avec la mention que la structure du format prime ; rien d'autre ne change.
- **Contrôle qualité** : la borne de durée passe de 58 à 180 s (un Short dure jusqu'à 3 min) ; elle aurait refusé les
  drames de 70 s comme les récits de 75 s. L'agent stratégie peut proposer jusqu'à 180 s.
- **Migration 0022** (appliquée le 29/09) : briefs des séries « Histoires vraies » et « Animaux étranges » réécrits
  (une histoire, un héros, le contexte, les « mais / donc »), durée cible 75 s. Maisons de rêve reste à 30 s.
- **Dashboard** (onglet Agents) : « Conteur · histoires », « Relecteur · histoires », « Réalisateur · histoires »,
  consignes « Règles du récit » et « Règles de l'image · histoires », étape « Réalisateur » dans la chaîne de production.

## 9. Ce que disent les trois vidéos de référence

Transcriptions lues en entier le 29/09 : V1 = interview de Jenny Hoyos chez Jay Clouse (octobre 2023, 38 min), V2 =
Kallaway, « Give me 15 mins, and I'll make your hooks impossible to skip » (juillet 2025), V3 = Kallaway, « How To
Become A Master Storyteller » (novembre 2024). Ce qu'elles corrigent dans le résumé reçu par Luca :

- « But » se traduit par **« mais »** (« pourtant » est plus étroit), et la règle porte sur le lien entre les événements :
  changer le mot sans créer de cause ni d'obstacle ne sert à rien.
- **The last dab** est la dernière ligne elle-même ; la méthode « partir de la fin » s'appelle « Direction » (Kallaway
  écrit la première et la dernière ligne ensemble ; Jenny écrit l'accroche, puis la dernière ligne, puis la promesse).
- Le minutage 0-4 / 4-8 / 8-12 / 12-45 / 45-55 / 55-60 s n'est dans aucune vidéo : accroche + promesse tiennent en 3 s
  environ chez Jenny (6 s ici, en voix off), la transition est une seule phrase, la fin coupe dès la réponse.
- Niveau de langue : Jenny vise la 5ᵉ année américaine ou moins (CM2 au plus), Kallaway la 6ᵉ pour l'accroche.
- « Ni dates inutiles, ni grades » n'y figure pas (extrapolation raisonnable) ; leurs accroches sont pleines de
  chiffres : celui qui porte l'enjeu ou le contraste se garde.
- Aucune des trois ne parle des Shorts de plus de 60 s. Extrapolation : 4 conflits en 30 s chez Kallaway, soit 8 à 12
  « mais / donc » pour 60 à 90 s, avec des relances.

## 10. Essai sur Begrâm (nuit du 28 au 29/09)

Nouvelle production **a76d07e3** (même idée que 3a600c14, qui continue en 40 s pour comparer). Trois écritures, les
quotas des meilleurs Flash étant épuisés cette nuit-là (3.8, 3.7 et 3.6 répondaient 429) :

| Essai | Modèles qui ont écrit | Résultat | Ce qu'on en a tiré |
|---|---|---|---|
| 1 | 3.6 Flash puis 3.5 Flash | 172 mots, 62 s ; une héroïne (Ria Hackin), une quête, la découverte, la guerre, une chute ; mais « elle refuse d'abandonner », « meurent au combat » (inventés, le second apparu à la réécriture, jamais relue) et la carte sur l'accroche | règle anti-invention détaillée, la réécriture est relue, la carte interdite sur l'accroche et la boucle, budget de mots chiffré (« ajoute environ 46 mots ») |
| 2 | 3.5 Flash, 3 Flash preview, 3.5 Flash-Lite | 209 mots, 72,8 s, 15 scènes, promesse qui annonce la fin, carte au contexte ; la 2e relecture a relevé 5 dramatisations ; restait un rythme uniforme (aucune phrase courte) | passe « forme » finale, consigne de rythme chiffrée (1 phrase sur 5 de 5 mots ou moins) |
| 3 | 3.5 Flash-Lite seul | 143 mots, 52,6 s, rythme toujours plat, « le couple périt en mer » (inventé, pourtant relevé par le relecteur) | le conteur et son relecteur attendent un modèle fort (§ 2) |

Le récit de l'essai 2, pour juger la construction :

> Une pièce scellée en Afghanistan cachait des trésors de Rome, d'Inde et de Chine. Mais ses découvreurs vont
> disparaître avant d'avoir pu raconter toute l'histoire. En 1937, les archéologues Joseph et Ria Hackin fouillent la
> cité antique de Begrâm. À 60 kilomètres de Kaboul, ce site était une étape majeure de la route de la soie. Ils percent
> un mur de briques antiques et découvrent la chambre numéro 10. À l'intérieur, des étagères entières d'ivoires, de
> verres peints et de laques se sont effondrées. […] Ils disparaissent tragiquement durant la guerre, emportant avec eux
> les secrets de leurs trouvailles. Leurs notes de terrain ne seront publiées que bien plus tard, sans leur témoignage
> direct. Les pièces sont aujourd'hui partagées entre les musées de Paris et de Kaboul. Les derniers secrets de Begrâm
> sont restés dans l'ombre.

La réécriture de a76d07e3 est reprogrammée le 29/09 à 9 h 30 (heure de Paris), après la remise à zéro des quotas
Gemini (minuit, heure du Pacifique) : le storyboard suit, à valider dans Création.

## 11. Fichiers et tests

- Worker : `worker/storycraft.py` (nouveau : budget, découpage, correcteur du récit, assemblage, prompts du conteur,
  du relecteur et du réalisateur), `worker/storytelling.py` (RULES réécrites, IMAGE_RULES), `worker/steps/script.py`
  (`_write_story`, `_review_story`, `_shots` ; les drames reçoivent les règles), `worker/models.py` (StoryDraft,
  StoryBeat, Shot, ShotList, `ScriptV1.story`), `worker/prompts.py` (clés script_shots et rules_images),
  `worker/reinvent.py`, `worker/steps/ideate.py`, `worker/steps/qa.py`, `worker/recipes.py`.
- Base : `supabase/migrations/0022_conteur_recits.sql`.
- Dashboard : `src/lib/agent-catalog.ts`, `src/lib/agents.ts`, `src/components/agents/agent-icon.tsx`.
- Tests : `tests/test_storycraft.py` (nouveau : budget, correcteur, découpage mot pour mot, assemblage, déroulé
  conteur → relecteur → réécriture → réalisateur, scène oubliée), `tests/test_prompts.py`, `tests/test_reinvent.py`,
  `tests/test_recits_carte.py`.

## 12. Suite

- Les TikTok que Luca va envoyer : les analyser comme ceux des fruits (docs/31) et en tirer un exemple de
  construction et des moteurs pour le conteur.
- Comparer la rétention des récits de 75 s à celle des 40 s (Dashboard, agent analyste) ; tester une « Partie 1 / 2 »
  si les 75 s décrochent.
- Les récits déjà en fabrication avec l'ancien scénariste (Begrâm 3a600c14, « Le coup d'État sans une goutte de sang »,
  « Le siège de Varsovie ») sortiront en 40 s ; pour les refaire avec le conteur, une nouvelle production du même
  concept (« Refaire avec les réglages actuels » recopie l'ancien script).
