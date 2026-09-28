# 33 · Nombres en chiffres à l'écran

> 2026-09-28. Demande de Luca, devant la vidéo « Le naufrage de l'Estonia » (production 0ac5090c) dont le titre
> d'accroche disait « Huit cent cinquante-deux morts en pleine mer » : **tout ce qui s'affiche** (sous-titres, titre
> d'accroche, textes à l'écran) écrit les nombres et les années **en chiffres**, jamais en lettres.

## 1. D'où venaient les lettres

La consigne « Règles du storytelling » demandait au scénariste « les grands nombres en toutes lettres (« trois
millions ») », pour que la voix de synthèse les lise bien. Or les sous-titres reprennent mot pour mot le texte de la
narration, et le titre d'accroche avait pris la même habitude.

## 2. La règle

- **Les agents écrivent en chiffres** : consignes `rules_storytelling` et `rules_hook_title`, prompts `script`,
  `idea` et `seo` (onglet Agents ; nouvelles versions actives le 28/09, Luca n'avait aucune version à lui sur ces
  clés). Exemples donnés : « 852 morts », « en 1994 », « 1 350 tonnes », « 3 millions », « 19e siècle », « 40 % ».
- **La voix lit en lettres** : juste avant chaque moteur de voix (`worker/providers/tts.py`), le texte passe par
  `numbers.spoken()` : « 852 » → « huit cent cinquante-deux », « 1992 » → « mille neuf cent quatre-vingt-douze »,
  « 19e » → « dix-neuvième », « 14 h 30 », « 1914-1918 » (« … à … »), « 14,5 M€ », « 21 personnes » (« vingt et
  une »). Bouton « Écouter » des Réglages compris. En anglais : années lues par paires (« nineteen ninety-four »).
- **Le correcteur compte les mots dits** : « 1994 » compte pour 4 mots (mille, neuf, cent, quatre-vingt-quatorze),
  pour les 15 mots par scène de 5 s, l'accroche de 14 mots et la narration qui remplit la vidéo. Les sous-titres
  donnent à un nombre le temps de ses mots dits ; « 1 350 » reste un seul mot à l'écran.
- **Filet de sécurité** (`numbers.to_digits`, français) : un nombre resté en lettres passe en chiffres dans le script
  dès qu'il est écrit (récits, chantiers, visites, scène réinventée) et au montage (sous-titres, titre d'accroche,
  textes à l'écran), y compris pour une vidéo écrite avant la règle : ses mots horodatés « huit », « cent »,
  « cinquante-deux » deviennent un seul mot « 852 » (`numbers.merge_timed`). Restent en lettres : « un » et « une »
  seuls (articles ; mais « Jour 1 », « le numéro 1 »), « zéro » seul, « neuf » adjectif (« un navire neuf »), « tous
  les deux », « pour cent » après un nombre, les noms propres (« les Trois Mousquetaires », « Trois-Rivières »).

Typographie : années collées (« en 1992 », « de 1914 à 1918 ») ; quantités groupées par 3 avec une espace insécable
(« 1 350 tonnes », « 10 000 »), qui ne se coupe pas en fin de ligne ; « 3 millions », « 2,5 milliards », « plus de
1 million », « 30 % », « 19e siècle ».

## 3. Vidéo Estonia

Son script a été converti en base le 28/09 pendant la fabrication des clips (titre d'accroche « 852 morts en pleine
mer », narrations des scènes 1 et 7) ; la voix, le montage et le contrôle n'avaient pas encore tourné. Pour une
vidéo déjà montée avant la règle, **Refaire le montage** suffit : le montage convertit ce qui reste en lettres.

## 4. Fichiers

`worker/numbers.py` (conversions), `worker/providers/tts.py`, `worker/subtitles.py` (`distribute_words`),
`worker/timeline.py`, `worker/storytelling.py` (consigne, correcteur, `normalize_story`), `worker/recipes.py`
(consigne du titre d'accroche, `normalize_script`), `worker/steps/assemble.py` (`plan_from`, `scene_titles`),
`worker/montage.py` (`hook_text`), `worker/hooktitle.py` (l'espace insécable reste), aperçus des onglets Montage et
Réglages ; tests : `tests/test_numbers.py`.
