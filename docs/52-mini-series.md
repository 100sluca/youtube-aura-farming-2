# 52 · Mini-séries des drames : une histoire en 3 parties, la suite selon les vues (01/10)

Demande de Luca (01/10, après docs/51) : des histoires en plusieurs parties qui coupent en pleine action, pour que les
gens veuillent la suite. On publie la partie 1 ; si elle marche, on fait et on publie la partie 2 quelques jours après ;
sinon on écarte la piste. 3 parties au plus.

## 1. Pour Luca

**Création → carte « Mini-séries »** :

- chaque mini-série en cours : ses 3 parties (publiée, programmée, en fabrication, ou « à venir » avec ce qu'elle
  racontera), et pour chaque partie sortie depuis 48 h son verdict : vues YouTube + TikTok à 48 h, médiane de la
  chaîne au même âge, rapport (×1,8) ;
- **Lancer la partie N** : la suite part (script, puis son storyboard arrive à valider dans Création, comme d'habitude).
  Le bouton existe aussi avant le verdict (« maintenant », pour fabriquer les parties d'avance) et sous le seuil
  (« quand même ») ;
- **Arrêter la mini-série** : plus aucune suite proposée ;
- **Pilote des suites** (interrupteur) : coupé, la suite au-dessus du seuil t'est proposée (alerte + bouton) ; allumé,
  elle est fabriquée et programmée sans toi (storyboard sans revue, comme le pilote automatique, docs/46) ;
- **Seuil** : ×0,75, la médiane (défaut), ×1,5 ou ×2.

En ligne de commande : `yt2 arc list | show <arc> | adopt <production> | launch <arc> [--autopilot] | tick | settings
[--autopilot on|off] [--threshold 1.5] [--hours 48] [--parts 3]`.

## 2. Déroulé

1. **L'histoire entière d'abord** : au script d'un drame, le showrunner (prompt `arc_outline`, onglet Agents) écrit
   la prémisse, la première réplique (l'injustice), l'interdit planté, le retournement de valeur, la morale, puis les
   3 parties : ce qui s'y passe, sur quoi chacune s'ouvre et coupe (`story_arcs.outline`). Règles tirées des modèles
   de docs/51 §3.
2. **Partie 1** : le scénariste du drame reçoit ce plan (`arcs.part_brief`, il prime sur la fin « partie 1 ou histoire
   complète » de ses consignes) : première réplique imposée, interdit avant la moitié, coupe en pleine action, dernier
   plan « Partie 2 bientôt ».
3. **48 h après la sortie** (`arcs.tick`, toutes les 2 min) : vues YouTube à 48 h (relevés horaires) + vues TikTok à 48 h,
   comparées à la médiane des vidéos de l'appli de la même chaîne sorties depuis 60 jours (au même âge). Moins de
   3 vidéos de comparaison : la suite est proposée (« pas assez de recul »). Verdict dans `story_arcs.decisions`.
4. **Partie 2 et 3** (`arcs.launch_part`) : même idée, même chaîne, mêmes réglages ; les fiches des personnages de la
   partie 1 sont recopiées (mêmes visages, le storyboard ne les redessine pas) et `keep_cast` leur rend leurs voix.
   Le scénariste reçoit le plan, les répliques des parties d'avant et la distribution imposée ; le titre devient
   « Partie 2 : … » (aussi après l'agent SEO), le dernier plan « Partie 3 bientôt », sauf la dernière partie.
5. La suite prend le prochain créneau libre : elle sort au plus tôt ≈ 2 à 3 jours après la partie d'avant (48 h
   d'attente + fabrication).

Une partie publiée hors de l'appli, un PC éteint autour de la 48e heure : on prend les compteurs actuels de YouTube.

## 3. Premier essai

« La fille du gardien » (production 64711c48, à valider dans la Bibliothèque) est devenue la partie 1 de la mini-série
0dd8c7bb (`yt2 arc adopt`) : partie 2 = le réexamen public, coupée sur l'enveloppe qui tombe du sac de Nadia ;
partie 3 = la tricherie de Madame Kanté démasquée, Issa réintégré. Le verdict tombera 48 h après sa sortie.

## 4. Code

| Où | Quoi |
|---|---|
| `supabase/migrations/0042_mini_series.sql` | `story_arcs`, `productions.arc_id / arc_part`, `app_settings.miniseries` |
| `worker/arcs.py` | showrunner (`ARC_PROMPT`), `part_brief`, `keep_cast`, `finish_part`, `views_48h`, `judge`, `tick`, `launch_part`, `adopt` |
| `worker/steps/script.py` | `_arc` : plan écrit avant la partie 1 (un échec du plan n'empêche pas la vidéo) ; consignes de la partie |
| `worker/steps/seo.py` | « Partie N : » gardé devant le titre des suites |
| `worker/scheduler.py` | `arcs.tick` toutes les 2 min |
| `worker/autopilot.py` | les suites ne comptent pas dans les vidéos du pilote |
| `worker/cli_arcs.py` | `yt2 arc …` |
| `apps/dashboard` | `components/create/miniseries-card.tsx`, `lib/miniseries.ts`, `app/create/miniseries-actions.ts` |
| `tests/test_arcs.py` | verdict, consignes de partie, titres, distribution gardée |
