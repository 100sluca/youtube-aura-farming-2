# 22 · Onglet Agents : prompts modifiables et chaîne de production

> 2026-09-28. Demande de Luca : retrouver dans l'interface les agents qui travaillent (idées, scripts…), lire et
> modifier leur prompt système depuis le dashboard, ce prompt servant ensuite au worker, et voir la chaîne complète de
> fabrication d'une vidéo, de l'idée à la publication.

## 1. Ce qu'on trouve

Menu **Agents** (`/agents`), entre Calendrier et Réglages, avec deux vues :

- **Agents et prompts** : les 9 agents dans l'ordre de la chaîne, puis les 5 consignes communes. Chaque carte donne la
  version en service et son origine, l'activité des 7 derniers jours (tâches, ou verdicts et refus pour les
  contrôleurs), et signale un nouveau texte du code ou une proposition de l'agent amélioration.
- **Chaîne de production** (`/agents?vue=chaine`) : les 5 étapes (Idées, Écriture, Storyboard, Fabrication,
  Publication) et la boucle d'apprentissage. Chaque étape est colorée selon sa nature : agent IA (violet, prompt
  modifiable), modèle local sur la carte graphique (bleu), programme (gris), toi (ambre). En direct : le modèle réglé
  (LLM, vision, images, vidéo, voix), la version du prompt, les tâches en cours ou en file, ce qui attend une décision
  (idées à trier, storyboards à valider, vidéos à autoriser, programmées, publiées). Un clic sur un agent ouvre son
  prompt ; un clic sur une étape « Toi » ou un modèle ouvre l'écran où elle se pilote.

Fiche d'un agent (`/agents/<clé>`) : l'éditeur du prompt, l'historique des versions et, à côté, comment il travaille
(quand il tourne, son modèle, ce qu'il reçoit avec son prompt, ce qu'il rend, ce qui se passe ensuite).

## 2. Les agents et les consignes

| Clé | Agent | Job | Rôle |
|---|---|---|---|
| `idea` | Agent idées | ideate | idées notées par thème |
| `script` | Conteur · histoires (Scénariste · histoires jusqu'au 29/09) | script | l'histoire des thèmes racontés, écrite en entier avant le découpage ([`37-conteur-des-recits.md`](37-conteur-des-recits.md)) |
| `script_review` | Relecteur · histoires | script | relit l'histoire avec la checklist du récit, la fait réécrire une fois |
| `script_shots` | Réalisateur · histoires | script | les plans de chaque scène d'une histoire découpée par le code |
| `script_timelapse` | Scénariste · chantier | script | étapes d'un chantier en accéléré |
| `script_tour` | Scénariste · visite | script | parcours d'une maison de luxe |
| `seo` | Agent SEO | seo | titre, description, tags, hashtags |
| `keyframe_qc` | Contrôleur des images | storyboard | vision : images clés des chantiers et visites |
| `clip_qc` | Contrôleur des clips | generate_clip | vision : clips des chantiers et visites |
| `strategy` | Agent stratégie | strategy | ajustements hebdomadaires à valider |
| `improve` | Agent amélioration | improve | meilleures versions des prompts idées et script |
| `analyst` | Agent analyste | analyze | ce qui marche et pourquoi, leçons à valider dans Dashboard ([`25-dashboard-statistiques.md`](25-dashboard-statistiques.md)) |

Depuis le 29/09 (docs/37) : `rules_storytelling` s'appelle « Règles du récit » (l'art de raconter, commun à toute
histoire, donné aussi au relecteur et au scénariste des drames) et `rules_images` (« Règles de l'image · histoires »)
va au réalisateur et à la scène réinventée ; `hint_continuity` va au réalisateur.
Consignes communes (glissées dans le message, avec les données de la tâche) : `rules_storytelling` (règles du
storytelling, agent idées et scénariste histoires), `guide_timelapse` et `guide_tour` (agent idées, thèmes visuels),
`rules_hook_title` (titre d'accroche, scénaristes chantier et visite), `hint_continuity` (continuité entre clips,
scénariste histoires).

## 3. Comment une modification est prise en compte

Tout vit dans `prompt_templates` (migration 0012), une ligne par version, une seule version en service par clé :

- **texte du code** (`created_by = 'code'`) : le worker enregistre à chaque démarrage le texte de chaque clé
  (`worker/prompts.py`, fonction SQL `sync_code_prompt`). Comme il se relance seul quand son code change, un prompt
  modifié dans le code arrive en base aussitôt. Il devient la version en service si l'on suivait le code ; si une
  version choisie à la main est en service, elle le reste et le dashboard affiche « Nouveau texte du code »
  (différences, « Utiliser le texte du code ») ;
- **ta version** (`'human'`) : « Enregistrer » crée une nouvelle version, en service tout de suite (`save_prompt`) ;
- **proposition** (`'improve_agent'`) : l'agent amélioration propose, inactif ; « Utiliser » la met en service.

Le worker lit la version en service à **chaque appel d'agent** : une modification sert dès la tâche suivante, sans
relancer quoi que ce soit. Une production garde la trace de la version de script utilisée (`prompt_template_id`),
ce qui permet à l'agent amélioration de comparer les versions. L'historique ne perd rien : « Utiliser » remet
n'importe quelle version en service, « Repartir de celle-ci » la recopie dans l'éditeur, « Différences » compare
à la version en service.

## 4. Ce qui reste dans le code

- Le **message** de chaque tâche (thème, idée, faits sourcés, statistiques…) : la fiche de l'agent le décrit.
- Le **correcteur** (`worker/storytelling.py`, `lint_recipe_script`) garde ses propres valeurs : changer « 14 mots »
  dans les règles du storytelling ne change pas sa limite (la fiche de la consigne le rappelle).
- Les **exigences** des contrôleurs, scène par scène (`keyframe_qc.requirements`), et ce que le code ajoute aux
  prompts d'image et de mouvement (`recipes.image_prompt`, `motion_prompt`).
- Le **brief des thèmes** (table `series`) et le **modèle** : tous les agents utilisent le fournisseur de
  Réglages → Intelligence artificielle.

## 5. Commandes

```
yt2 prompts list          version en service de chaque clé, origine, nouveau texte du code
yt2 prompts show seo      texte en service (--version N pour une autre)
yt2 prompts sync          enregistrer le texte du code (fait à chaque démarrage du worker)
```

## 6. Fichiers

- `supabase/migrations/0012_agents_prompts.sql` : clés libres, `created_by = 'code'`, `sync_code_prompt`,
  `save_prompt`, `activate_prompt`.
- Worker : `worker/prompts.py` (`code_prompts`, `active_prompt`, `prompt_text`, `sync_code_prompts`), appelé par les
  steps ideate, script, seo, strategy, improve, storyboard et generate_clip ; `tests/test_prompts.py`.
- Dashboard : `src/lib/agent-catalog.ts` (agents, consignes, étapes de la chaîne), `src/lib/agents.ts` (lectures),
  `src/app/agents/` (pages, actions), `src/components/agents/` (liste, schéma, éditeur, comparaison).
  Un nouvel agent : sa clé dans `worker/prompts.py`, sa fiche dans `agent-catalog.ts` ; en attendant, il apparaît
  sous « Autres prompts du worker ».

## 7. Pistes

- Choisir un modèle par agent (Claude pour les scripts, Gemini pour le reste…).
- Modifier le brief des thèmes depuis le même onglet.
- Essayer un prompt sur une idée avant de le mettre en service (bac à sable, sans créer de production).
- Afficher dans la fiche la rétention moyenne des vidéos produites par chaque version.
