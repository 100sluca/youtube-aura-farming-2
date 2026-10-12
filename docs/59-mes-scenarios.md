# 59 · Mes scénarios : une idée écrite par Luca, réalisée par une équipe d'agents (02/10)

Demande de Luca (02/10) : « j'ai des idées de scénarios libres, j'aimerais bien les réaliser » ; il faut pouvoir les
soumettre à une équipe d'agents qui les met en forme (storyboard, puis vidéo) sans les trahir. Premiers scénarios : le
chien qui vide le frigo dès que son maître a le dos tourné, et le chien sournois qui fait accuser le bébé d'avoir cassé
la lampe. Migration **0048**.

## 1. Pour Luca

**Création → carte « Mon scénario »** (sous le pilote automatique) :

- écrire l'idée avec ses mots, aussi brute qu'on veut (qui fait quoi, dans quel ordre) ;
- facultatif : un **titre**, le **style** (réaliste « prise de vue réelle », film d'animation Pixar, animaux qui parlent
  façon DreamWorks, fruits ; **réaliste par défaut**), les **paroles** (sans paroles, quelques répliques, dialogues) et la **durée** (30 à 75 s) ;
  laissés sur « L'équipe choisit », c'est le metteur en scène qui décide ;
- **Confier à l'équipe** : la production part tout de suite. Elle passe dans « En préparation » (≈ 5 min d'écriture),
  puis son storyboard arrive dans « Storyboards à regarder », à valider (✓) comme celui d'un drame : fiches des
  personnages en haut, un plan par action, Refaire et Réinventer comme d'habitude ;
- sous le formulaire, les derniers scénarios : où en est chacun (l'équipe écrit, storyboard à valider, montage, prête,
  ratée → **Relancer**) et **« Ce que l'équipe a compris »** : l'histoire en une phrase, le style, les paroles, la durée,
  les personnages, les temps de l'histoire avec le passage de ton texte que chacun réalise (« ajouté par l'équipe » pour
  un temps qu'elle a ajouté), ce qu'elle a décidé là où ton texte ne disait rien, et les points délicats à filmer.

Les trois agents sont dans l'**onglet Agents** (« Metteur en scène · ton scénario », « Scénariste · ton scénario »,
« Relecteur · fidélité à ton scénario »), modifiables et versionnés comme les autres.

## 2. L'équipe

| Agent | Prompt | Reçoit | Rend |
|---|---|---|---|
| Metteur en scène | `scenario_adapt` | ton texte mot pour mot, tes choix, les styles, la langue, les règles du titre d'accroche | la mise en scène (`ScenarioPlan`) : titre, histoire en une phrase, genre, style, paroles, durée, **décor** (anglais, repris dans chaque image), personnages (prénom, rôle, apparence et voix en anglais), **temps de l'histoire** avec `from_text` (le passage de ton texte réalisé), titre d'accroche, `choices`, `risks` |
| Scénariste | `script_scenario` | ton texte, la mise en scène, la musique disponible, les voix de synthèse s'il y a des paroles | le script d'un drame (`ScriptV1`) : distribution, 5 à 24 plans d'**une action** de 2 à 5 s, personnages à l'image, réplique seulement si prévue, image de départ et mouvement en anglais avec le son d'ambiance |
| Relecteur de fidélité | `scenario_review` | ton texte, la mise en scène, les plans | ok, ou 8 problèmes au plus : action oubliée ou trahie, deux actions dans un plan, personnage absent de `characters`, chute peu visible, paroles non respectées |

Déroulé (`steps/script.py`, `_write_scenario`) : mise en scène → tes choix l'emportent (`scenario.settle`) → elle est
gardée dans `concepts.scenario.plan`, le titre de l'idée devient le sien, le style et la durée sont posés sur la
production → plans → normalisation de drame (`scenario.normalize` : aucune réplique en « sans paroles », apparence du
metteur en scène gardée sur les fiches, puis `drama.normalize`) → correcteur (`scenario.lint`) et relecteur → deux
réécritures au plus ; la première est relue à son tour ; une réécriture qui n'est demandée que par le correcteur n'est
gardée que si elle corrige. Les agents écrivent avec les modèles forts de la chaîne d'écriture (comme le conteur) et
attendent une heure si tous sont épuisés. Jamais de mini-série (`arcs`) : ton scénario est une histoire entière.

Ensuite tout est celui d'un **drame** (docs/35) : fiche de chaque personnage puis plans avec les fiches en références,
storyboard à valider, clips MiniMax H3 qui font le son du plan (« Nobody speaks: only ambient sound » sur un plan muet)
et disent les répliques, montage avec titre d'accroche, sous-titres des répliques et musique (thème en voix des clips,
format B ; voix de synthèse au choix dans Retoucher).

## 3. Essais à blanc du 02/10 (vrais modèles, rien d'écrit en base)

| Scénario | Mise en scène | Plans | Relecture |
|---|---|---|---|
| Le chien et le frigo | « Le braquage du frigo », Pixar, sans paroles, 42 s, 7 temps ; sandwich jambon-fromage, cuisine ouverte sur le salon pour voir le frigo depuis le canapé, dernier plan cadré comme le premier | 13 plans, 41 s | 1re version refusée (le chien regardait « hors champ » au lieu du maître, trois plans à plusieurs actions, indices cachés incomplets) → réécrite, acceptée |
| Le chien sournois | « Le Chien Sournois », Pixar, sans paroles, 45 s, 12 temps ; Jack Russell, la lampe se brise assez loin du bébé (ton de comédie), sourire final face caméra | 12 plans, 45 s | 1re version refusée (plan en vue subjective où le chien est listé à l'image) → réécrite, acceptée |

Corrigé après ces essais : les personnages s'appelaient « Le chien » / « La maman » (et leurs clés « chien »,
« maman » se retrouvaient dans les prompts anglais) → un **prénom** est demandé ; le lieu n'était pas décrit avec les
mêmes mots d'un plan à l'autre → le metteur en scène écrit un **décor** fixe que le scénariste reprend.

Corrigé au premier storyboard réel (02/10, 17 h) : la fiche de Biscuit le montrait **debout sur ses pattes arrière**
(la consigne des fiches des drames dit « debout, de la tête aux chaussures »), et chaque plan reprend la fiche. Un vrai
animal (chien, chat…, hors styles DreamWorks et fruits, et s'il n'est pas décrit habillé) reçoit « a real four-legged
animal that always stays on all four paws » dans son apparence (`scenario.four_legs`), et sa fiche est faite « on all
four paws, from nose to tail » (`drama.SHEET_FOUR_LEGS`). Les deux storyboards ont été arrêtés après leurs fiches et
relancés avec la correction.

Changé à la demande de Luca (02/10, 17 h 10, « sur les vidéos de chien, je voulais des vidéos réalistes ») : le
metteur en scène avait choisi Pixar pour les deux. Le **réaliste** (`cinematic_real`) est maintenant le style par défaut
de l'équipe (l'animation seulement si le texte la demande ou si l'histoire est impossible en vrai) ; en réaliste, les
mots de dessin animé sont retirés des apparences (`scenario.real_look` : « cartoon-like eyes ») et les fiches sont des
**photos de référence** (« Reference photograph », pas « Character design reference sheet »). Les deux productions
Pixar (6a0f440f, 6f428da4) ont été arrêtées, leurs idées passées en réaliste et relancées.

## 4. Code

| Où | Quoi |
|---|---|
| `supabase/migrations/0048_mes_scenarios.sql` | `concepts.scenario`, thème caché `mes_scenarios` (recette drama, format B, inactif, poids 0 : ni idées automatiques, ni liste des thèmes, ni pilote), `submit_scenario` (idée + production, priorité 50) |
| `worker/scenario.py` | `ScenarioBrief`, `ScenarioPlan`, `settle`, `brief_text`, `plan_text`, `script_listing`, `normalize`, `lint`, prompts `ADAPT_PROMPT`, `SCRIPT_PROMPT`, `REVIEW_PROMPT`, `STYLES` |
| `worker/steps/script.py` | `_write_scenario`, `_review_scenario` (avant la recette : un concept avec `scenario`) |
| `worker/prompts.py` | clés `scenario_adapt`, `script_scenario`, `scenario_review` |
| `worker/providers/video.py`, `worker/drama.py`, `worker/steps/generate_clip.py` | style `cinematic_real` (image photoréaliste, négatif sans « visages »), `realistic_motion` pour ses clips, `FILM["cinematic_real"]` |
| `apps/dashboard` | `components/create/scenario-card.tsx`, `lib/scenarios.ts`, `lib/scenario-types.ts`, `app/create/scenario-actions.ts` (`submitScenario`, `relaunchScenario`), `app/create/page.tsx`, `lib/agent-catalog.ts` (3 agents, étape « Équipe de ton scénario »), `lib/agents.ts` (activité de l'équipe) |
| `tests/test_scenario.py` | choix de Luca prioritaires, normalisation sans paroles, correcteur, déroulé complet avec relecture et réécriture |

## 5. Limites

- Un plan = un clip de 5 s au plus : une action longue est coupée en plusieurs plans ; le rythme reste celui d'un drame.
- La bibliothèque de musiques n'a pas d'ambiance « comédie / malice » pour les récits : le scénariste prend la plus
  proche (« posé », « découverte »). Ajouter une piste joyeuse ou malicieuse aux récits améliorerait ces vidéos.
- MiniMax H3 : licence de test seulement (docs/21), comme pour les drames.
