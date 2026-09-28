# 12 · Séries de contenu, storytelling addictif, continuité des clips, premiers rendus

> Livré le 2026-09-21, à la suite de la mise en route de ComfyUI par Luca (Wan 2.2 disponible) et de sa
> demande : cinq catégories de vidéos, un agent de scénario qui applique les règles du storytelling
> addictif dans le script comme dans la conception des images, et une vidéo cohérente de bout en bout
> (première image, puis chaque clip repart de la dernière image du précédent).
> Machine : RTX 3070 8 Go, i7-14700K, 32 Go de RAM. Migration : `0003_series_sources_storytelling.sql`.

## 1. Les cinq catégories, et ce qu'elles deviennent

| Demande | Série (`series.slug`) | Matière | Voie visuelle | Statut |
|---|---|---|---|---|
| Faits Wikipédia du jour, format storytelling | `histoires_wikipedia` | fil du jour Wikipédia (éphéméride, articles les plus lus), recherches tournantes, pages au hasard | image → vidéo, style `history_cinematic` | **active** |
| Animaux étranges, dangereux, curieux | `animaux_etranges` | recherches Wikipédia tournantes (venins, abysses, mimétisme, parasites, records…) | image → vidéo, style `wildlife_doc` | **active** |
| Rénovations, passages secrets, maisons de rêve (contenu initial) | `maisons_de_reve` | l'agent idée seul, 20 catégories | image → vidéo, style `modern_minimal` | **active** (les 13 concepts existants y sont rattachés) |
| Edits Minecraft à émotion | `minecraft` | l'agent idée seul (scénarios) | à choisir, voir §3 | **inactive** jusqu'au choix de la voie |
| Vidéos virales récupérées puis expliquées | aucune | — | — | **écartée** : republier des clips tiers expose la chaîne (contenu réutilisé non monétisable, Content ID, trois avertissements = compte fermé), voir `10-etude-option-videos-virales.md`. Ce qui en reste : la variante « tendances » (chercher ce qui marche pour nourrir l'agent idée, sans rien télécharger), à écrire plus tard. |

Une série est une ligne éditoriale en base (table `series`) : source de matière, brief donné aux agents,
catégories, style visuel, format, durée cible, ambiances musicales, poids dans la production
quotidienne, chaîne cible. Les concepts et les productions s'y rattachent. Ajouter une série = une
ligne dans la table ; ajuster un ton = modifier son `brief`, sans toucher au code.

```
uv run yt2 series list                    séries, concepts en attente, produits
uv run yt2 ideate animaux_etranges        6 idées pour une série (agent idée, LLM)
uv run yt2 concepts list --status proposed
uv run yt2 concepts show 3fa2b1c0         accroche, prémisse, faits et sources
uv run yt2 concepts approve 3fa2b1c0 9d…  valider (rejet : reject)
uv run yt2 produce 3fa2b1c0               créer la production et lancer le script
uv run yt2 wiki today [--series …] [--full]   la matière du jour, sans LLM
uv run yt2 script lint <production>       le script face aux règles de storytelling
```

Le planificateur fait le reste : toutes les heures, chaque série active garde au moins
`IDEAS_PER_SERIES` (6) concepts en attente ; toutes les 15 minutes, `start_productions` transforme les
concepts approuvés en productions (`PRODUCTIONS_PER_DAY` = 3, `MAX_PRODUCTIONS_IN_FLIGHT` = 3), répartis
entre séries selon leurs poids. C'est le lien concept approuvé → production qui manquait : jusqu'ici, rien
ne créait de production. `AUTO_PRODUCE=0` pour garder la main (`yt2 produce`).

## 2. Le storytelling addictif, dans le prompt et dans le code

Les règles sont écrites une fois, dans `worker/storytelling.py` (`RULES`), et injectées telles quelles
dans les prompts des agents idée et script, avec le brief de la série. Ce qui se mesure est vérifié en
code (`lint_script`) ; un script en défaut repart une fois au LLM avec la liste des problèmes ; ce qui
reste est conservé dans `productions.lint` et lisible avec `yt2 script lint`.

**Structure** (six scènes de 5 s, chacune avec un rôle `role`) :

| Rôle | Quand | Ce que fait la scène | Vérifié en code |
|---|---|---|---|
| `hook` | 0-3 s | promesse ou contradiction concrète en 14 mots au plus, le sujet visible dès la première image | longueur, formules interdites (bonjour, aujourd'hui, saviez-vous…) |
| `setup` | 3-8 s | contexte minimum, enjeu, boucle ouverte | — |
| `reveal` | avant 12 s | première réponse concrète, qui ouvre une nouvelle question | la scène `reveal` commence avant la 12e seconde |
| `escalation` | 12-25 s | chiffres, comparaisons, renversement par « mais » / « sauf que » | — |
| `payoff` | 22-28 s | réponse finale, image la plus forte | — |
| `loop` | fin | dernier plan qui renvoie au premier, dernière phrase qui rebondit sur l'accroche, aucun appel à l'action | `loop_note` présent, appels à l'action interdits |

**Voix** (lue par Kokoro) : phrases de 4 à 14 mots, 12 mots au plus par scène de 5 s (vérifié : au-delà
la voix déborde et le montage ralentit le clip), du concret à chaque scène, « mais » et « donc » plutôt
que « et puis », pas de superlatifs vides (vérifié), pas de sigles ; séries documentaires : rien qui ne
soit dans les faits sourcés.

**Image** : une seule action ou un seul mouvement de caméra par scène, changement de valeur de plan
entre scènes (le « changement visuel toutes les 3-4 secondes »), sujet centré pour un téléphone, texte
à l'écran de 5 mots au plus (vérifié), l'image la plus spectaculaire gardée pour la révélation.

Les prompts v2 en base (`prompt_templates`, idée et script) sont génériques : ligne éditoriale = la
série, règles = le code. L'agent d'amélioration continue de proposer des versions de prompt ; les
règles, elles, se changent dans le code avec leurs tests (`tests/test_storytelling.py`).

## 3. Minecraft : la voie visuelle reste à choisir

Recherche du 2026-09-21. Aucune plateforme en ligne ne rend des scènes Minecraft à partir d'un
scénario par API. Trois voies réalistes :

| Voie | Comment | Pour | Contre |
|---|---|---|---|
| **Blender + MCprep, piloté par script** | Blender tourne sans interface (`blender -b … --python scene.py`) ; l'extension libre [MCprep](https://github.com/Moo-Ack-Productions/MCprep) importe mondes et personnages Minecraft avec leurs rigs ; un script Python pose caméra, personnages, animations, puis rend | vrai rendu Minecraft, cohérence parfaite, réutilisable à l'infini, gratuit | un vrai chantier : bibliothèque de poses et de décors à constituer, temps de rendu CPU/GPU, plusieurs jours de développement |
| **Génération IA « style Minecraft »** | même pipeline que les autres séries : image de storyboard avec un prompt (ou une LoRA) Minecraft, puis animation Wan | zéro développement, disponible tout de suite | les blocs fondent et se déforment sur 5 s ; l'audience Minecraft repère le faux |
| Mine-imator, Prisma3D | outils gratuits d'animation Minecraft, à la main | simples | pas de ligne de commande ni d'API : impossible à automatiser |

Les modèles de monde IA (Oasis de Decart, poids 500M ouverts, [oasis-model.github.io](https://oasis-model.github.io/)) génèrent un Minecraft jouable
image par image à partir de touches clavier, pas une scène scénarisée : inadaptés à ce besoin.

Recommandation : tester d'abord la voie IA sur deux concepts (elle ne coûte rien, le style `minecraft`
existe dans `STYLE_PRESETS`), juger sur pièce ; si l'émotion passe malgré les déformations, activer la
série ; sinon, planifier Blender + MCprep comme un projet à part (série B). La série reste `is_active =
false` en attendant : `update series set is_active = true where slug = 'minecraft'` pour l'activer.

## 4. Image → vidéo et continuité de bout en bout

La route image → vidéo (docs/09 §2.1) est confirmée par le premier rendu : l'image de storyboard était
bonne, la vidéo a animé ce qu'elle montrait. La demande de Luca (chaque clip repart de la dernière image
du précédent) est implémentée avec un garde-fou :

1. le storyboard produit une image pour les scènes qui **coupent** ; les scènes qui **prolongent** le plan
   précédent (`continues_previous = true`, décidé par l'agent script scène par scène) n'ont pas d'image :
   leur clip part de la dernière image du clip précédent (`media.last_frame`, extraite par FFmpeg) ;
2. le job du clip qui prolonge dépend du clip précédent (`dag.enqueue_render_dag`) ; les autres se
   rendent dans l'ordre des scènes sans dépendance ;
3. après `CONTINUITY_MAX_CHAIN` (3) clips enchaînés, la scène suivante repart d'une image de storyboard :
   chaque génération ajoute un peu de flou et de dérive de couleur, on ne laisse pas la chaîne s'user ;
4. la scène 1 et la scène `loop` sont toujours des coupes : la boucle finale reprend le cadrage du
   premier plan par son propre storyboard.

`CLIP_CONTINUITY` : `script` (défaut, l'agent décide), `chain` (tout enchaîner), `cut` (tout couper).
Pourquoi ne pas tout enchaîner : la règle de rétention demande un changement visuel toutes les 3-4
secondes ; une coupe nette vers un nouveau cadrage est plus forte qu'un plan qui se prolonge, et elle
remet les compteurs de qualité à zéro. La bonne vidéo mélange les deux, et c'est le script qui le sait.

Un vrai « première + dernière image » (le clip se termine exactement sur l'image du plan suivant) existe
pour Wan 2.2 14B (`WanFirstLastFrameToVideo`) mais pas pour le 5B ; à reprendre avec le 14B.

## 5. La machine, les modèles, les premiers rendus

**Installé le 2026-09-21** : ComfyUI 0.36 portable dans `C:\Users\Luca\Downloads\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable`
(19 Go de modèles, sur un C: presque plein : 37 Go libres), ComfyUI Manager, Wan 2.2 **TI2V-5B** fp16,
Wan 2.2 Fun Control 5B, encodeur umt5, VAE Wan 2.2. Pas de ComfyUI-GGUF, pas de LoRA, pas de modèle image.
Les workflows du dépôt visaient les 14B GGUF : trois workflows 5B ont été écrits (`workflows/README.md`).

**Premier rendu** (`scripts/bench_video.py`, prompt « bibliothèque qui s'ouvre sur un escalier ») :

| Étape | Réglage | Temps | VRAM |
|---|---|---|---|
| image de storyboard | 5B, une image, 768×1344, 20 passes | 30 s | — |
| clip 5 s | 5B image → vidéo, 480×832, 24 i/s, 121 images, 20 passes, CFG 5 | 3 min 42 s | 7,6 Go |
| clip 5 s en 720p | idem, 704×1280 (résolution native du 5B) | **jamais fini** : délai d'une heure du worker dépassé, interruption demandée à 55 min et ignorée (ComfyUI ne la lit qu'entre deux passes) ; 7,9 Go sur 8 occupés, la carte déborde | 7,9 Go |

Le 5B en 720p est donc hors de portée de cette carte ; à 480p, il fonctionne mais reste mou. Sur cette
machine, la qualité passera par le 14B en 4 passes (ci-dessous), pas par plus de pixels avec le 5B.

Verdict de Luca : l'image est bonne, la vidéo ne convainc pas. Diagnostic au visionnage : la porte
s'ouvre, mais la géométrie fond (le panneau à lattes devient une deuxième porte puis des étagères), le
plan est figé, l'ensemble est mou. Quatre causes, dans l'ordre :

1. **480p sous la résolution native** : le 5B est entraîné en 720p ; à 480×832, il n'a pas les détails
   qu'il sait produire. L'essai à 704×1280 a été arrêté après 55 minutes sans résultat : la carte n'a pas
   la mémoire pour le 5B fp16 à cette taille. `VIDEO_SIZE` reste vide.
2. **Un prompt d'image à la place d'un prompt de mouvement** : le banc envoyait la description de la
   photo ; le modèle image → vidéo attend une action (« la caméra avance lentement pendant que la porte
   pivote sur ses charnières, tout le reste est immobile »). Le pipeline sépare déjà `visual_prompt` et
   `motion_prompt` ; le banc le fait maintenant aussi.
3. **Le négatif** : Wan a été entraîné avec son négatif officiel (chinois) ; il est appliqué désormais à
   tout workflow Wan.
4. **Le 5B est le plus petit de la famille** : il tient mal les objets rigides sur 5 s. C'est la limite
   qu'on ne franchira pas avec lui.

**La voie « meilleure qualité sur 8 Go »**, celle que le dépôt visait dès docs/08 et docs/11 :

| Rôle | Modèle | Pourquoi | Poids |
|---|---|---|---|
| image de storyboard | **Z-Image Turbo** (6B, Apache 2.0, 8 passes) | l'image fixe est le plafond de qualité de la vidéo ; Z-Image est le meilleur photoréalisme qui tienne sur 8 Go, en 15-30 s | 20 Go (bf16 + Qwen3-4B) |
| animation | **Wan 2.2 I2V 14B** GGUF Q4_K_M + LoRA lightx2v **4 passes** | tient la géométrie et suit le mouvement ; 4 passes sans CFG = plus rapide que le 5B en 20 passes (2-4 min par clip mesurés ailleurs sur des cartes 8 Go, à confirmer ici) | 19 Go |
| voix | Kokoro (`kokoro-v1.0.onnx`, `voices-v1.0.bin`) | manquant : aucune narration possible sans | 0,36 Go |

Trois gestes, à faire dans cet ordre (rien n'est téléchargé sans vous) :

1. Faire de la place sur C: (environ 60 Go) puis déplacer ComfyUI de `Downloads` vers
   `C:\ComfyUI_windows_portable` (le lanceur le trouve tout seul). Jamais sur D:, disque externe branché à
   l'occasion.
2. Dans ComfyUI Manager : installer **ComfyUI-GGUF** (city96), redémarrer ComfyUI.
3. `powershell -ExecutionPolicy Bypass -File services\worker\scripts\download_models.ps1` (≈ 40 Go,
   reprise possible), puis dans `services/worker/.env` : `VIDEO_PROVIDER=comfy_wan22_i2v_4step`,
   `COMFY_IMAGE_WORKFLOW=zimage_turbo`, et relancer le banc :
   `uv run python scripts/bench_video.py --providers comfy_wan22_i2v_4step --prompts 3 --out C:\YouTube2\bench`.

Budget GPU une fois en place : 6 scènes × (30 s + 3 min) ≈ 20 min par Short, soit une heure par jour pour
trois Shorts. En attendant, le 5B à 480p (≈ 25 min par Short) sert à roder le pipeline de bout en bout,
pas à publier.

## 6. Wikipédia comme matière première

`worker/sources/wikipedia.py`, sans clé :

- fil du jour (`/api/rest_v1/feed/featured/AAAA/MM/JJ`) : article du jour (absent sur fr), articles les
  plus lus la veille, éphéméride ; recherche et pages au hasard par l'API action ; extrait en texte brut
  avec URL canonique et numéro de révision ;
- configuration par série (`series.source_config`) : `feeds`, `queries` (tournent avec le jour de
  l'année), `queries_per_day`, `search_limit`, `random`, `min_words`, `exclude` (regex sur titre et
  description : fictions, célébrités vivantes, crimes… pour la série histoires) ;
- les pages déjà exploitées par un concept de la série sont écartées pendant 120 jours ; cache d'une
  journée dans `C:\YouTube2\data\sources\wikipedia\<lang>\` ;
- l'agent idée reçoit la matière numérotée `[n]` et doit citer la source de chaque fait ; une idée avec
  moins de deux faits sourcés est écartée ; `concepts.sources` et `concepts.facts` gardent la trace ;
  l'agent script reçoit les faits et n'a pas le droit de compléter ; l'agent SEO ajoute en fin de
  description « Sources (Wikipédia, CC BY-SA 4.0) » avec les pages (les faits sont libres, l'attribution
  couvre la reprise de formulations) ;
- User-Agent identifiable avec contact (`WIKIPEDIA_USER_AGENT`, défaut avec `ALERT_EMAIL_TO`), une
  requête à la fois, pause entre les appels : ce que demande Wikimedia.

Vérifié le 2026-09-21 : `yt2 wiki today` ramène 6 pages pour chaque série (fr).

## 7. Mise en route et ce qui manque encore

Fait aujourd'hui : migration 0003 appliquée à la base locale (4 séries, prompts v2 actifs, 13 concepts
rattachés), 3 workflows 5B validés par un rendu réel, 5 tests ajoutés (29 → 41), commande `yt2` étendue.

Il manque, pour une première production complète :

| Manque | Effet | Geste |
|---|---|---|
| **Clé LLM** : `.env` n'a ni `ANTHROPIC_API_KEY`, ni Mistral, ni Gemini ; seul Ollama répond, avec `qwen3-coder` (modèle de code) | scripts médiocres, JSON parfois invalide | renseigner une clé (Claude Sonnet 5 recommandé), ou `ollama pull qwen3:8b` + `OLLAMA_MODEL=qwen3:8b` |
| **Kokoro** absent de `C:\YouTube2\models` | aucune voix, le job `tts` échoue | `download_models.ps1 -SkipWan -SkipZImage` |
| Musique : `C:\YouTube2\data\music\<ambiance>\` vide | montage sans musique (accepté) | déposer des pistes libres (YouTube Audio Library) |
| ~~Dashboard toujours sur des données factices~~ | branché le 2026-09-22 : idées, production, storyboard, vidéo, publication et réglages IA depuis l'écran (docs/13) | |

Premier essai conseillé, dans l'ordre : `yt2 ideate animaux_etranges` → `yt2 concepts list` →
`yt2 concepts approve <id>` → attendre la production automatique (ou `yt2 produce <id>`) →
`yt2 storyboard show <production>` → `pick` / `redo` → `approve` → clips, voix, montage → vidéo en
`review` dans `C:\YouTube2\data\videos\<id>\`.

## Sources

- Nœuds et gabarits Wan 2.2 dans ComfyUI : [docs.comfy.org](https://docs.comfy.org/tutorials/video/wan/wan2_2) ;
  LoRA lightx2v 4 passes : [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged),
  [lightx2v/Wan2.2-Distill-Loras](https://huggingface.co/lightx2v/Wan2.2-Distill-Loras).
- Blender sans interface : [Mastering the Blender CLI](https://renderday.com/blog/mastering-the-blender-cli) ;
  MCprep : [github.com/Moo-Ack-Productions/MCprep](https://github.com/Moo-Ack-Productions/MCprep) ;
  outils d'animation Minecraft : [Minecraft Animation Wiki](https://minecraftanimation.fandom.com/wiki/List_of_commonly_used_Minecraft_animation_programs_and_their_foremost_users).
- Oasis (Decart) : [oasis-model.github.io](https://oasis-model.github.io/), [decart.ai](https://decart.ai/).
- Wikimedia : [REST API feed/featured](https://fr.wikipedia.org/api/rest_v1/), [API action](https://www.mediawiki.org/wiki/API:Main_page),
  [politique User-Agent](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy),
  [licence CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.fr).
