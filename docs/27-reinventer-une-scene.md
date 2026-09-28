# 27 · Réinventer une scène du storyboard

> 2026-09-28. Demande de Luca, devant le storyboard « Le miroir qui ouvre sur un dressing secret » (production
> 825eda53) : la scène 4 (« Un pivot invisible supporte tout le poids ») montre un mécanisme seul, planté dans un
> parquet, sans rapport visible avec le miroir. L'image respecte son prompt, mais le plan est hors sujet. « Refaire »
> ne donne qu'une autre image du même prompt ; il faut pouvoir **réinventer la scène** : un autre plan, donc une autre
> image, et une narration qui va avec, en restant cohérent avec les scènes qui l'entourent.

## 1. Dans Création

Storyboard ouvert en grand (« Regarder et choisir ») : chaque scène montre maintenant sa **narration** (ce que dit la
voix pendant l'image), puis la description de son plan, ses images et deux boutons :

- **Refaire** : de nouvelles images du même prompt (inchangé) ;
- **Réinventer** : un petit champ « Qu'est-ce qui ne va pas ? » (facultatif, 500 caractères) puis **Réinventer la
  scène**. Le scénariste réécrit la scène : autre idée de plan, image de départ, mouvement, narration, texte à l'écran.
  Ses anciennes images quittent la planche et deux nouvelles arrivent (≈ 1 à 2 min quand la carte graphique est libre ;
  sinon après la tâche GPU en cours).

Pendant le travail, la vignette de la scène tourne (carte de Création et tiroir), la page se met à jour toutes les 5 s,
et **Valider et fabriquer** / **Gemini** attendent la fin (valider au milieu mélangerait l'ancien et le nouveau
script). Une scène réinventée porte le badge « réinventée » et, à la place du prompt anglais, **son nouveau plan en une
phrase en français** (le prompt reste au survol). On peut la réinventer encore : les versions déjà écartées sont
données au scénariste pour qu'il n'y revienne pas.

Commande équivalente : `yt2 storyboard reinvent PRODUCTION <index de la scène> ["remarque"]` (index du script,
`yt2 storyboard show`).

## 2. Ce que fait le worker

Le bouton met en file un job `storyboard` (priorité 80, comme Refaire) avec
`{"scenes": [4], "reinvent": true, "note": "…"}` ; pas de nouveau type de job. Le step storyboard
(`worker/steps/storyboard.py`) :

1. appelle le scénariste (`worker/reinvent.py`, modèle d'écriture, chaîne de Réglages → IA) ;
2. enregistre le script (`productions.script`, et `videos.narration_text`) ;
3. retire de la planche les anciennes images de la scène (lignes `assets` ; les fichiers restent dans le dossier de
   la production et partent avec elle) ;
4. remplace dans le job `reinvent` par `reinvented` : la scène, son numéro, la remarque, l'idée, les écarts restants,
   la version d'avant et celle d'après. Relancé après une panne des images (ComfyUI éteint), le job ne réécrit donc
   pas la scène une seconde fois ; le dashboard lit l'idée et l'état « réinventée » dans ce payload ;
5. fait les images de la scène comme un Refaire (candidates, contrôle par vision des formats visuels), puis remet le
   storyboard à valider avec une alerte « Scène 4 réinventée : … ».

Une scène refaite ou réinventée revient toujours à Luca : `STORYBOARD_AUTOPASS` ne s'applique qu'au premier storyboard.

## 3. Ce que reçoit le scénariste (agent `scene_rewrite`)

Prompt système `scene_rewrite` (onglet Agents : « Scénariste · scène réinventée », modifiable et versionné). Il
demande une scène qui garde sa place dans le récit (même rôle, même durée, narration qui part de la scène précédente
et amène la suivante, telles qu'elles sont écrites), une idée vraiment différente des versions écartées, **le sujet
visible dans l'image** (un détail se montre sur le sujet et dans son décor, jamais seul sur fond neutre), les mêmes
mots que les autres scènes pour les éléments communs (le modèle d'image ne connaît que le prompt de sa scène), une
image réaliste faisable, un seul mouvement possible depuis l'image.

Message : le thème et l'idée (et, pour une série documentaire, les faits sourcés et le dossier des pages sources), les
**consignes du scénariste du format** (version active de `script`, `script_timelapse` ou `script_tour`, pour le sens des
champs), les règles du storytelling (récits), le script scène par scène avec la scène visée marquée, le budget de mots
(10 à 15 pour 5 s), ce qu'en dit Luca (ou, sans remarque : « hors sujet, casse l'enchaînement »), les versions déjà
écartées, et la contrainte de continuité si la scène suivante part de la dernière image du clip.

Réponse : `{"idea": "…", "scene": {visual_prompt, motion_prompt, narration, on_screen_text, …}}`. Le code garde
l'index, le rôle, la durée et la mécanique de l'ancienne scène, puis la recette remet la sienne (`apply_rewrite`) :

- **récit** : la scène devient une coupe (`continues_previous = false` : elle a sa propre image) ; une scène carte
  seulement s'il n'y en a pas d'autre ;
- **visite** : `interior`, `floor`, `leads_to` repris s'ils manquent ; les passages sont recalculés, celui qui suit la
  pièce prend sa nouvelle ouverture ;
- **chantier** : la retouche (`edit_prompt`) de l'étape ; refaire l'image d'une étape refait les retouches qui en
  dérivent, comme Refaire.

Le correcteur (`lint_script` ou `lint_recipe_script`) vérifie le script obtenu. Un écart **nouveau** (sur la scène
réécrite, ou un écart d'ensemble qui n'existait pas), une image identique à une version écartée ou une narration
perdue renvoie la scène une fois au scénariste avec la liste ; la meilleure des deux réponses est gardée.

## 4. Autres changements

- **Refaire ne fait plus perdre l'image retenue** quand la génération échoue : l'image retenue d'une scène ne change
  qu'une fois la nouvelle faite. Le 28/09 à 13 h 33, un Refaire de la scène 2 du miroir a échoué (ComfyUI éteint) et
  la scène était restée sans image retenue, ce qui bloquait la validation.
- Les étiquettes des tâches donnent le numéro de scène que Luca voit (« Scène 4 · image 1/2 ») : les scripts
  numérotent parfois leurs scènes à partir de 1.
- Valider exige une image retenue pour chaque scène réinventée, même si ses nouvelles images n'ont pas pu se faire.
- En amont, les **règles du storytelling** (§4 Image) disent maintenant : « Chaque image se rattache au sujet au premier
  coup d'œil : un détail se montre sur le sujet et dans son décor, jamais seul sur fond neutre ; un objet qui revient
  d'une scène à l'autre est décrit avec les mêmes mots » (version 3 de `rules_storytelling`, en service puisque Luca
  suit le texte du code).

## 5. Code

- Worker : `worker/reinvent.py` (prompt, requête, fusion, contrôles), `worker/models.py` (`SceneDraft`,
  `SceneRewrite`), `worker/steps/storyboard.py` (`_reinvent`, `_select`), `worker/prompts.py` (clé `scene_rewrite`),
  `worker/cli.py` (`yt2 storyboard reinvent`) ; tests `tests/test_reinvent.py`.
- Dashboard : `app/production/actions.ts` (`reinventScene`, garde de `approveStoryboard`),
  `components/production/storyboard-panel.tsx` (narration, Réinventer, état en cours), `components/create/storyboard-review.tsx`,
  `lib/data/supabase.ts` (`busy`, `reinvented`, `idea`, `narration` de chaque scène), `lib/agent-catalog.ts` et
  `lib/agents.ts` (agent et activité).
- Aucune migration : le job reste un job `storyboard`, l'historique vit dans son payload.
