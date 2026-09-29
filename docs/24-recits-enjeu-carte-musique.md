# 24 — Récits : enjeu, scène carte, modèle d'écriture

> Mise à jour du 2026-09-29 : l'écriture des récits est refondue (un conteur écrit l'histoire en entier, un relecteur
> la juge, le code la découpe, un réalisateur fait les plans ; 75 s) : voir
> [`37-conteur-des-recits.md`](37-conteur-des-recits.md). Le § 2 ci-dessous décrit l'ancien scénariste.

Demandé par Luca le 2026-09-28 après la vidéo « Canal Rhin-Danube : 70 ans de travaux fous » (production 1f5d87f0,
série « Histoires vraies ») : on ne comprend pas l'enjeu (« controversé » n'est jamais expliqué, on ne sait pas à quoi
sert le canal ni pourquoi il compte), pas assez d'émotion ni de rythme, pas de titre d'accroche, pas de musique, et il
voudrait une carte : partir de haut, zoomer sur l'endroit exact, montrer la ligne du canal d'un bout à l'autre.

## 1. Diagnostic

| Constat | Cause | Correction |
|---|---|---|
| « Controversé » jamais expliqué, aucun enjeu | L'agent idée n'avait gardé que **3 faits** de la page Wikipédia (inauguration, 70 ans, chalands de 1 350 t) ; le scénariste avait pour consigne « un fait par scène, sans jamais compléter » : il a rempli avec du vide. La page contenait pourtant Charlemagne (793, 7 000 hommes), le canal Ludwig (1845, bombardé), la mer du Nord → mer Noire, la vallée de l'Altmühl sacrifiée | Le scénariste relit les **pages sources entières** (+ la version anglaise) ; l'agent idée garde **6 à 10 faits** qui couvrent enjeu, conflit, personnes, échelle ; nouvelle section « enjeu et émotion » des règles |
| Script plat | Écrit par **Gemini 3.5 Flash-Lite** (le plus faible, choisi le 25/09 quand les Flash répondaient 503) | **Chaîne d'écriture** : Gemini 3.8 Flash → 3.7 → 3.6 → 3.5 Flash-Lite pour l'agent idées, les scénaristes et le relecteur ; plusieurs clés par fournisseur (§3) |
| Rien ne vérifie le fond | Le correcteur ne mesure que des longueurs, rôles, durées | **Relecteur** (nouvel agent `script_review`) : enjeu compris avant 10 s, promesses tenues, conflit et humain, faits du dossier, titre vrai ; ses remarques font réécrire le script une fois |
| Manque de rythme | Consigne à 2,6 mots/s alors que la voix Qwen3 « mystère » parle à **3,2 mots/s** : 1,4 s de blanc par scène de 5 s | 3 mots/s (15 mots par scène de 5 s), le correcteur exige une narration qui couvre au moins 70 % de la durée |
| « Ligne de partage des eaux » effacée | Le correcteur prenait « **partage** » pour un appel à l'action (« partagez ») : la reprise a supprimé le fait | Expression corrigée : seules les formes d'appel (« partagez », « partage cette vidéo », « en commentaire »…) |
| Pas de titre d'accroche | Le modèle de montage ne l'affichait que sur les chantiers et visites | Déjà fait par la session « Éditeur de template de montage » (titre sur les 3 formats, docs/23) |
| Pas de musique | `DATA_DIR/music/mysterious` n'existe pas (les pistes ACE-Step ne couvrent que luxe, chill, élégant, épique, inspirant, entraînant) | Pistes de Luca : session « Musiques pour vidéos YouTube » (onglet Montage → Son) ; en attendant, repli sur une ambiance voisine (`media.MOOD_FALLBACKS`) |
| Titre d'accroche faux (« Le chantier secret qui a coupé l'Europe en deux ») | Rien n'exigeait qu'il soit vrai | Consigne `rules_hook_title` : histoires vraies = vrai, sans contresens, il pose l'enjeu |

## 2. Script des récits

- **Dossier** (`sources/wikipedia.source_dossier`) : chaque page source du concept relue en entier (12 000 caractères)
  et sa version anglaise (8 000), en cache pour la journée dans `DATA_DIR/sources/wikipedia/pages`. Il part dans le
  message du scénariste (« seule base des affirmations ») et du relecteur.
- **Règles** (`storytelling.RULES`, clé `rules_storytelling`) : section « Enjeu et émotion » (ce que c'est, où, pourquoi
  ça compte avant 10 s ; chaque promesse tenue dans la scène ou la suivante ; un conflit et son prix ; de l'humain ;
  une échelle qu'on ressent ; le ton d'un conteur ; pas de remplissage). Structure : une scène de 4 à 6 s par tranche
  de 5 s de la durée cible. Dates : l'année seule.
- **Correcteur** (`lint_script`) : 15 mots par scène de 5 s, narration ≥ 70 % de la durée, une seule scène carte.
  `normalize_story` : une carte vide disparaît, une carte dure 4 à 7 s, ni elle ni la scène suivante ne prolongent un
  clip (la carte n'est pas un plan filmé ; `dag.continuity_plan` fait de même).
- **Relecteur** (`steps/script.py`, prompt `REVIEW_PROMPT`, clé `script_review`, modifiable dans l'onglet Agents) :
  verdict `ok` + 6 problèmes au plus. Déroulé : écriture → correcteur → relecture → si problèmes, **une** réécriture
  avec la liste → si des écarts mesurables restent, une dernière reprise ciblée. Au plus 4 appels au LLM par script.
  Si le relecteur ne répond pas, le script continue sans lui (journal `script.relecture_indisponible`).
- **Série « Histoires vraies »** (migration **0017**) : brief réécrit (enjeu, conflit, personnes, scène carte, 6 à 10
  faits, le scénariste relit les pages), **durée cible 40 s** (8 scènes).

## 3. Chaînes de modèles et clés multiples

Demandé par Luca le 28/09 (Gemini 3.8 Flash surchargé pendant l'essai) : Réglages → Intelligence artificielle.

- **Clés API** : plusieurs clés par fournisseur (`app_secrets` : `gemini_api_key`, `gemini_api_key_2`, `_3`…), ajoutées
  à la suite ; « Tester » essaie une clé seule, « Retirer » la supprime (en deux clics).
- **Deux chaînes** (`app_settings.llm.chains`) : **écriture** (agent idées, scénaristes, relecteur :
  `get_llm(writer=True)`) et **autres agents** (SEO, contrôles des images et des clips, stratégie, amélioration,
  analyse). Chacune : 1er choix, 2e choix… jusqu'à 8, chaque choix = fournisseur + modèle, ordre réglable (flèches),
  bouton « Tester ». Un fournisseur sans clé est sauté.
- **À chaque appel** (`providers/llm.py`) : pour un choix, toutes les clés de son fournisseur — quota épuisé (429) ou
  clé refusée (401, 403, clé invalide) → **clé suivante** ; surcharge (5xx, réseau : un nouvel essai après 4 s),
  modèle inconnu (404), réponse illisible, ou toutes les clés épuisées → **choix suivant** ; si tout a échoué pour
  surcharge ou limite par minute → un second tour après 20 s. Les pannes récentes sont retenues (quota du jour : 1 h,
  limite par minute : 1 min, clé refusée : 1 h, surcharge : 3 min) : ce qui vient d'échouer passe après le reste,
  sans jamais être exclu.
- **Journal** du worker : `llm.cle_suivante`, `llm.choix_suivant`, `llm.chaine_epuisee`, `llm.second_tour` ; le
  scénariste note quel modèle a répondu à chaque appel (`script.modeles` dans le journal de sa tâche).
- **Réglé le 28/09** : écriture gemini-3.8-flash → 3.7-flash → 3.6-flash → 3.5-flash-lite ; autres agents
  3.5-flash-lite → 3.1-flash-lite → 2.5-flash-lite ; une seule clé Gemini enregistrée. Le quota gratuit des Flash
  récents est court (≈ 20 requêtes par jour relevé le 25/09) : un script en consomme 2 à 4.
- Sans chaînes en base, elles se déduisent des anciens réglages (fournisseur principal, secours, modèle d'écriture).
- En ligne de commande : `yt2 settings key gemini <clé>` (ajoute ; `--slot N` remplace la clé n° N ; valeur `-` la
  retire), `yt2 settings llm --writer-chain "gemini:gemini-3.8-flash,gemini:gemini-3.5-flash-lite" --chain "…"`,
  `yt2 settings test gemini --model gemini-3.7-flash --key 2`, `yt2 settings show`.

## 4. Scène carte

Une scène du script (de préférence la 2e) porte un champ `map` ; elle est **rendue par le code** (`worker/maps.py`),
ni image ni clip d'IA :

```json
"map": {"place": "Canal Rhin-Main-Danube", "ends": ["Bamberg", "Kelheim"],
        "context": ["Mer du Nord", "Mer Noire"], "lines": ["Rhin", "Main (rivière)", "Danube"]}
```

- `place` : le lieu, comme le titre de sa page Wikipédia ; son tracé se dessine en or (canal, fleuve, route, contour
  d'une île). Un lieu sans tracé (ville, monument) reçoit un anneau qui pulse et son nom.
- `ends` : 0 à 2 repères aux deux bouts du tracé ; le tracé part du premier.
- `context` : 0 à 3 grands repères montrés sur une vue large avant la plongée (s'ils sont loin du lieu).
- `lines` : 0 à 3 fleuves, routes ou frontières en bleu fin, avec leur nom : ce que le lieu relie. Précision entre
  parenthèses (« Main (rivière) ») pour trouver la bonne page, affichée sans elle.

Déroulé (6 s) : globe vu de l'espace qui tourne vers le lieu → vue large (mer du Nord, mer Noire, Rhin, Main, Danube)
→ plongée → tracé doré de Bamberg à Kelheim → fin tenue avec une légère avancée. L'image du storyboard est la fin de
la scène.

Données, toutes gratuites et sans clé :

| Quoi | Source | Licence, mention |
|---|---|---|
| Fond satellite | Sentinel-2 cloudless **2016** d'EOX, tuiles XYZ (`tiles.maps.eox.at`) | CC BY 4.0 : mention gravée en bas de l'image et ajoutée à la description YouTube |
| Coordonnées, identifiant Wikidata | API Wikipédia (`prop=coordinates|pageprops`) | — |
| Tracés | OpenStreetMap par Overpass (`nwr["wikidata"=…]; out geom`), serveur de secours kumi.systems ; repli Nominatim | ODbL : « © contributeurs OpenStreetMap » (image et description) |

Rendu : projection orthographique calculée avec numpy (1080×1920, 30 i/s), deux niveaux de tuiles mélangés, tracé et
étiquettes par Pillow (police Montserrat SemiBold du worker), images envoyées à FFmpeg (libx264 CRF 17). Mesuré le
28/09 sur le canal : **≈ 3 min pour 6 s** sur le processeur (une scène d'IA en prend ≈ 6), 2 000 à 3 000 tuiles au
premier rendu d'une région (≈ 50 Mo, 40 s), puis tout vient du cache `DATA_DIR/maps/tiles` ; lieux en cache dans
`DATA_DIR/maps/geo`. Une carte impossible (lieu introuvable, réseau) : la scène repasse par l'image et le clip d'IA de
son `visual_prompt` (journaux `storyboard.carte_indisponible`, `clip.carte_indisponible`).

Limites connues : une seule carte par Short ; les étiquettes peuvent se toucher si deux repères sont très proches ;
les régions qui chevauchent l'antiméridien ou les pôles n'ont pas été essayées ; Overpass public répond parfois 429
(nouvel essai après 20 puis 45 s, puis le serveur de secours).

## 5. Musique

Traitée par la session « Musiques pour vidéos YouTube » (pistes de Luca, volumes réglables dans l'onglet Montage). Côté
récits, seul ajout ici : une ambiance vide se replie sur une voisine (`media.MOOD_FALLBACKS`, ex. mysterious → suspense
→ emotional) et l'absence de musique est journalisée aussi pour les récits (`assemble.sans_musique`).

## 6. Essai sur le canal

Nouvelle production **dc8c681d** (même concept, nouveau script, 41 s, 8 scènes, 98 mots) créée le 28/09 à 12 h 22 ;
l'ancienne vidéo (1f5d87f0) reste pour comparer. « Refaire avec les réglages actuels » ne convient pas pour ça : il
recopie l'ancien script. Script obtenu : carte en scène 2 (mer du Nord, mer Noire, Rhin, Main, Danube, canal de Bamberg
à Kelheim), seize écluses et ligne de partage des eaux, chalands de 1 350 t, dégâts écologiques, Charlemagne en 793,
coût ; le relecteur a demandé une précision (scène 2). Encore perfectible : l'accroche reste « 70 ans de travaux » au lieu
du rêve de Charlemagne, et l'ordre n'est pas chronologique. Storyboard en attente de validation dans Création
(12 h 36).

Fichiers : `worker/maps.py`, `worker/storytelling.py`, `worker/steps/script.py`, `worker/steps/ideate.py`,
`worker/sources/wikipedia.py`, `worker/models.py` (MapSpec, ScriptReview), `worker/steps/storyboard.py`,
`worker/steps/generate_clip.py`, `worker/dag.py`, `worker/steps/seo.py`, `worker/providers/llm.py`,
`worker/settings_store.py`, `worker/cli.py`, `supabase/migrations/0017_recits_enjeu.sql`, dashboard :
`lib/agent-catalog.ts`, `lib/agents.ts`, `lib/llm-types.ts`, `lib/settings-data.ts`,
`components/settings/llm-settings.tsx`, `app/settings/actions.ts`. Tests : `tests/test_recits_carte.py`,
`tests/test_llm_chain.py`.
