# 56 · Un dashboard rapide (version de production, chargements, clics)

Demande de Luca, le 2026-10-02 :

> Le frontend met beaucoup de temps à charger à chaque fois que je clique sur un bouton. Faut-il le refaire dans un
> autre langage ?

Non : le langage n'y était pour rien. Quatre causes, mesurées, et quatre corrections, dans cet ordre.

Code : `launcher/dashboard.ps1`, `apps/dashboard/next.config.ts`, `src/app/loading.tsx`, `src/app/api/system/*`,
`src/app/api/tasks/board`, `src/app/api/retouch/[id]/*`, `src/lib/get-json.ts`.

## 1. Ce qui ralentissait

- **Le mode développement.** `C:\YouTube2\dashboard.bat` lançait `next dev` depuis le 25/09 : chaque page recompilée
  et rendue avec tous les contrôles de débogage de React, sans optimisation, et un serveur qui grossissait (11 Go le
  28/09, docs/28). Les requêtes à la base prennent environ 10 ms ; les pages, elles, mettaient 0,4 à 1,5 s.
- **Aucun écran de chargement.** Après un clic sur un lien, l'ancienne page restait figée jusqu'à ce que la nouvelle
  soit entièrement prête.
- **Les clics faisaient la queue.** Next exécute les actions serveur une par une pour chaque onglet. Or le panneau
  Tâches relisait sa file toutes les 3 s, le bloc Machine l'état du PC toutes les 5 à 15 s (jusqu'à 4 s d'attente quand
  ComfyUI est occupé), Retoucher l'avancement toutes les 2 à 3 s, toujours par des actions : un clic attendait derrière.
- **Chaque bouton recalculait la page deux fois.** Une action qui appelle `revalidatePath` renvoie déjà la page
  recalculée dans sa réponse ; le `router.refresh()` qui suivait en refaisait une seconde.

## 2. Version de production servie en continu (`launcher/dashboard.ps1`)

`C:\YouTube2\dashboard.bat` lance maintenant ce superviseur (le bouton « Redémarrer le dashboard » aussi) :

- il sert la dernière version construite (`apps/dashboard/.next-live/a` ou `b`) dès son démarrage ;
- toutes les 10 s, il compare le code (`src`, `public`, `package.json`, `next.config.ts`, `.env.local`…) à celui de la
  version servie ; quand le code a changé et n'a plus bougé depuis 30 s, il construit la nouvelle version dans l'autre
  dossier (6 à 20 s, priorité basse) pendant que l'ancienne sert, puis bascule (environ une seconde de coupure) ;
- une construction ratée laisse l'ancienne version en place ; le bloc Machine l'affiche (avec la fin du journal) et la
  suivante part au prochain changement du code ;
- pas de construction sous 3 Go de mémoire libre : elle attend la fin du gros rendu ;
- si aucune version n'a jamais pu être construite, il lance `next dev` (lent, mais l'appli s'ouvre) ;
- une clé fixe des actions serveur, propre au PC (`.next-live/actions.key`, hors dépôt), garde les mêmes noms
  d'actions d'une version à l'autre : les boutons d'une page restée ouverte marchent encore après une mise à jour.

Journal : `C:\YouTube2\data\logs\dashboard.log`. État lu par le bloc Machine : `.next-live/status.json`.

Pour les sessions de code : `.claude/launch.json` → « dashboard » lance `next dev` sur le port **3001** (rechargement
à chaud) ; « dashboard-live » ouvre la version servie sur le port 3000, à jour une quarantaine de secondes après la
dernière modification.

LANCER.bat convertit l'ancien lanceur de l'installation du frère (`npm run dev`) ; INSTALLER.bat écrit directement le
nouveau.

## 3. Écrans de chargement

- `src/app/loading.tsx` : silhouette de la page, affichée dès le clic (moins de 10 ms mesurés).
- Le sélecteur de chaîne de l'en-tête (seule lecture de la base dans la mise en page) est dans son propre `Suspense` :
  sinon la mise en page bloquait la navigation et l'écran de chargement ne s'affichait pas.
- Un petit rond tourne sur le lien cliqué du menu tant que la page n'est pas là (`useLinkStatus`).

## 4. Lectures répétées par des routes GET

Une lecture répétée passe par une route GET (`getJson` de `src/lib/get-json.ts`), jamais par une action serveur :

| Lecture | Route |
|---|---|
| état de la machine (bloc Machine) | `/api/system/status` |
| ce qui prend la mémoire | `/api/system/memory` |
| file des tâches | `/api/tasks/board` |
| avancement d'une retouche | `/api/retouch/<vidéo>/state` |
| réécriture du récit | `/api/retouch/<vidéo>/rewrite` |

Les actions restent pour les gestes (pause, arrêt, publier…).

## 5. Un seul calcul de page par clic

Les `router.refresh()` placés après une action qui appelle déjà `revalidatePath` sont retirés (Création, Bibliothèque,
Tâches, Montage, Réglages, Dashboard, sélecteur de chaîne). Restent ceux qui suivent une action sans revalidation ou
la fin d'une attente (retouche finie, mail de test envoyé…). Les gestes les plus fréquents s'affichaient déjà tout de
suite (✓ / ✗ de Création, étoile des favoris).

Réglages : la liste des modèles de ComfyUI (`/object_info`, 2 Mo, près d'une seconde) est gardée en mémoire et relue
en arrière-plan au plus une fois par minute.

## 6. Mesures (serveur seul, moyenne de 5 passages)

| Page | `next dev` | production |
|---|---|---|
| Vue d'ensemble | 846 ms | 199 ms |
| Création | 461 ms | 156 ms |
| Bibliothèque | 1 408 ms | 163 ms |
| Dashboard | 1 432 ms | 164 ms |
| Calendrier | 498 ms | 15 ms |
| Montage | 427 ms | 51 ms |
| Agents | 746 ms | 23 ms |
| Réglages | 1 486 ms | 41 ms (800 ms à la première visite) |

Dans le navigateur : écran de chargement en moins de 10 ms, page complète en 0,3 à 0,4 s, fiche d'une vidéo de la
Bibliothèque en 30 à 190 ms. Mémoire du serveur : 0,3 Go au lieu de 1,7 Go (et 11 Go après trois jours).

## 7. Au passage : `launcher/restart.ps1`

Quand les programmes avaient été lancés par l'ancien lanceur du Bureau, « Redémarrer » remontait de la fenêtre du
programme jusqu'à celle du lanceur et arrêtait tout son arbre : ComfyUI, le worker et le dashboard ensemble. Il
s'arrête maintenant à la fenêtre du programme lui-même.
