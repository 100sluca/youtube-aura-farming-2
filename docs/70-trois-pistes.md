# 70 · Trois pistes : drames plus rapides, citations d'auteurs, histoires vraies (12/10)

Retour de Luca (12/10), après le bilan de docs/69 :
- **drames** : trop de temps morts, des échanges et des visuels trop lents, face aux vidéos modèles qu'il a envoyées ;
- **citations** : elles font des vues sur TikTok, sont très faciles et rapides à faire ; il veut aussi de vraies
  citations de personnalités (Einstein, Maupassant…), prises sur un site des plus grandes citations, qui touchent ;
- **histoires vraies** : le format qui plaît, à continuer d'améliorer.

Migration **0057**. Chiffres relevés en base le 12/10 vers 11 h (vues YouTube en direct, TikTok synchronisé à 10 h).

## 1. Où on en est

| Format | YouTube : vidéos, vues moyennes (médiane) | TikTok : posts, vues moyennes (médiane) |
|---|---|---|
| Histoires vraies | 13 · 649 (566) | 11 · 540 (256) ; record : Aouli, 1 953 |
| Lieux insolites (timelapse) | 2 · 564 | 2 · 501 |
| Rénovations (timelapse) | 8 · 328 (181) | 4 · 283 |
| Drames (familles, karma, animaux) | 10 · 92 (26) | 10 · 516 (567) |
| Citations | 1 · 137 | 4 · 755 à 770 |

**Les citations sur TikTok, honnêtement.** Elles tiennent le niveau de tout le reste : depuis le 04/10, presque chaque
post fait 750 à 820 vues, quel que soit le format. C'est la base que TikTok donne au compte. Les citations n'en sortent
pas encore (3 s de visionnage moyen pour 6 à 8 s), mais elles l'atteignent pour 15 s de calcul au lieu de plusieurs
heures. C'est ce qui en fait une bonne piste.

## 2. Drames : les temps morts

### Mesure

Les 10 drames publiés, mesurés au montage final (coupes à l'image, silences de la piste de voix sous −35 dB) :

| | Plans | Plan moyen | Silence dans la voix | Plus long blanc |
|---|---|---|---|---|
| Nos drames | 4 à 17 | 4,3 à 7,4 s | **20 à 46 %** | **1,4 à 4,4 s** |
| Modèles TikTok (docs/31, docs/51) | ≈ 25 répliques en 70-80 s | 2 à 3 s | — | — |

### Causes, trouvées dans le code

1. **Le silence avant la réplique n'était jamais coupé.** H3 ouvre la bouche 0,5 à 2,7 s après le début du clip.
   Le montage ne coupait le début du clip que si H3 ajoutait des mots en trop.
2. **La durée prévue servait de minimum.** Une réplique dite en 2,4 s gardait les 3,6 s prévues par le script.
3. **Trop peu de plans, trop longs.** Le script demandait 14 à 20 plans pour 60 à 80 s (≈ 4 s chacun). Il acceptait
   40 % de plans muets de 2,5 à 5 s et des répliques de 12 mots.
4. **H3 parle lentement** : ≈ 2,2 mots/s, contre 2,5 à 3 chez les modèles. Il marque 1 à 1,5 s de silence sur
   chaque « … ».
5. **Les consignes de ton** (« smug, slow » en exemple) le ralentissaient encore.

### Ce qui change (worker/drama.py, worker/steps/assemble.py)

- **Montage**, pour toute vidéo remontée et tous les nouveaux drames :
  - chaque plan parlé commence 0,2 s avant le premier mot entendu ;
  - il finit 0,3 s après le dernier mot, sans durée minimum prévue (1,2 s au moins) ;
  - un plan muet d'un drame en dialogues dure 1,2 à 2,2 s. Un scénario surtout muet (« Mes scénarios », le chien)
    garde ses plans d'action de 1,5 à 5 s.
- **Lecture des clips à ×1,12**, image et voix ensemble (`drama.PACE`, atempo garde le timbre). Une prise de voix de
  synthèse validée dans Retoucher garde son débit.
- **Scénariste** :
  - 22 à 28 plans au lieu de 14 à 20, une réplique de 4 à 9 mots (10 au plus), 80 % de plans parlés ;
  - un bloc RYTHME : entrer au milieu de l'action, champ-contrechamp serré, un retournement toutes les 3 ou 4
    répliques, jamais deux plans muets de suite, ni « slow » ni points de suspension.
- **Correcteur** : 14 à 30 plans, 75 % parlés, deux plans muets de suite refusés.
- **H3** : « Right at the start of the shot … at a brisk, natural pace, without pausing ». Les « … » d'une réplique
  sont dits comme une virgule, le sous-titre les garde.

### Résultat sur les mêmes clips

Les drames publiés, remontés avec la nouvelle coupe (timeline recalculée, rien d'écrit en base) :

| Drame | Avant | Après | Voix pendant |
|---|---|---|---|
| Cahier volé | 42,8 s | **27,0 s** | 61 % → 70 % du temps |
| La fille du gardien | 74,3 s | **55,0 s** | 73 % → 75 % du temps |
| Les 10 drames (coupe seule, sans ×1,12) | — | −14 à −32 % | 77 à 92 % du temps |

Essai à voir et à écouter : **Bibliothèque → Démos et essais**, « Drames : le rythme resserré ». Le dossier est
`C:\YouTube2\bench\2026-10-12-rythme-drames` : 1-2 Cahier volé, 3-4 La fille du gardien, avant puis après. Les
vidéos publiées n'ont pas été touchées.

Ce qui reste dans les vieux drames : le débit de H3 dans les longues répliques (8 à 11 mots en 5 s) et les silences
des « … ». Les deux disparaissent avec le nouveau scénariste.

**Coût** : 22 à 28 clips H3 au lieu de 14 à 20, soit ≈ 2 h 10 de machine par drame au lieu de ≈ 1 h 30.

## 3. Citations d'auteurs

**Pourquoi Wikiquote.** Les comptes de citations collent de fausses phrases sur Einstein ou Aristote (docs/58 §1).
Wikiquote range chaque citation avec sa source : œuvre, édition, page. Il met à part celles qu'on ne peut pas sourcer
(« Citations rapportées », « attribuées ») et celles qui parlent de l'auteur. On ne garde que les premières. L'API est
gratuite et sans clé. Les textes sont sous CC BY-SA 4.0, et la description de la vidéo cite l'auteur, l'œuvre et la
page.

**Nouveau thème « Citations d'auteurs »** (série `citations_auteurs`, migration 0057, active, poids 1). Il apparaît
dans Création comme les autres.

1. **La réserve** (`worker/sources/wikiquote.py`).
   - 90 auteurs connus dont la page existe en français : Hugo, Maupassant, Einstein, Marc Aurèle, Sénèque,
     Saint-Exupéry, Oscar Wilde, Camus, Gandhi, Martin Luther King, Frida Kahlo, Coco Chanel, Van Gogh…
   - La liste est réglable : `source_config.authors`.
   - À chaque demande d'idées : 10 auteurs tirés au hasard, en mettant les plus récents en dernier ; 5 citations
     inédites chacun ; 6 à 40 mots ; ni réplique de théâtre ou de film, ni extrait tronqué.
   - Cache d'un mois par auteur (`DATA_DIR/sources/wikiquote`).
2. **L'agent idées choisit, il n'écrit pas** (guide `guide_quote_auteur`, onglet Agents).
   - Il retient les citations qui parlent de la vie de chacun et se comprennent seules.
   - Le code vérifie que chaque idée recopie une citation de la réserve. Une citation réécrite est écartée.
   - Un auteur par idée du lot. Une citation n'est jamais proposée deux fois.
3. **Le scénariste met en scène** (`script_quote_auteur`).
   - L'image rappelle l'univers de l'auteur (une côte normande peinte pour Maupassant), jamais son visage.
   - Le code remet ensuite la citation exacte, signée « — Auteur », quoi qu'il ait écrit.
4. **Montage** : celui des citations (zoom lent, ≈ 15 s de calcul, musique générée ; TikTok et Instagram mettent la
   leur).

**Premier essai (12/10, 6 idées dans Création, à valider ou refuser)** : Einstein (« Nous ne pouvons pas désespérer
des hommes, puisque nous sommes nous-mêmes des hommes. »), Martin Luther King, Lao Tseu (deux citations : depuis,
c'est un auteur par lot), Zola, Cicéron. Le choix est inégal : la réplique de Gervaise (Zola) ou Cicéron sont moins
fortes. La règle « une réplique de personnage de roman ne vaut que dans son histoire » a été ajoutée au guide.

## 4. Histoires vraies

**La rétention est déjà bonne.** Relevé YouTube Analytics (part des spectateurs encore là) :

| Histoire | Vues YouTube | À 10 s | À la moitié | À la fin |
|---|---|---|---|---|
| Begrâm | 533 | 112 % | 79 % | 68 % |
| Mer d'Aral | 1 113 | 96 % | 66 % | 59 % |
| Zraoua | 999 | 105 % | 72 % | 55 % |
| Lukangol | 1 077 | 98 % | 59 % | 43 % |
| Naypyidaw | 999 | 94 % | 55 % | 41 % |
| Stanford | 54 | 71 % | 39 % | 39 % |

Au-dessus de 100 %, des spectateurs reviennent en arrière. Ce qui fait la différence, c'est le **sujet**. Les lieux
abandonnés, disparus ou démesurés gagnent : Aouli 1 953 vues sur TikTok, mer d'Aral, Lukangol, Naypyidaw, Zraoua, le
canal Rhin-Main-Danube. Les biographies (Stanford 54), les inventions (Bakélite 289), un épisode de guerre (Varsovie
425) et une vidéo trop longue (Skrunda-1, 109 s, 157) font moins.

**Proposé** : une leçon pour l'agent idées des récits, à valider dans le Dashboard. Elle dit de choisir d'abord un
lieu abandonné, disparu ou démesuré qui pose une énigme visible dès la première image, et de viser 65 à 90 s.

**À décider par Luca dans le Dashboard.** L'analyste a proposé le 09/10 de « bannir définitivement les fables
d'animation (fruits, animaux) ». C'est le contraire de ce que Luca veut (améliorer les drames) : à refuser, ou à
laisser en attente jusqu'aux drames rythmés.

## 5. Fichiers

- Worker :
  - `worker/drama.py` (rythme, coupe, PACE, consignes) ;
  - `worker/steps/assemble.py` (`RenderPlan.clip_speed`) ;
  - `worker/sources/wikiquote.py` (nouveau) ;
  - `worker/quotes.py`, `worker/recipes.py`, `worker/steps/ideate.py`, `worker/steps/script.py`,
    `worker/steps/seo.py` ;
  - tests : `test_drama`, `test_plans`, `test_no_text`, `test_prompts`, `test_wikiquote` (nouveau). 617 tests passent.
- Dashboard : `src/lib/agents.ts`, `src/lib/agent-catalog.ts` (onglet Agents : scénariste et guide des citations
  d'auteurs, fiche du scénariste des drames).
- Base : `supabase/migrations/0057_citations_auteurs.sql`, appliquée à la main et inscrite dans
  `supabase_migrations.schema_migrations`.
