# 30 · Bibliothèque complète : vidéos en fabrication, démos et essais

Demande de Luca (28/09) : l'onglet Montage montrait « 852 morts en pleine mer » (l'Estonia) alors que la vidéo
n'était pas dans la Bibliothèque ; le refuge v2 et d'autres démos restaient introuvables. Il veut tout voir, tout
regarder, et pouvoir supprimer à la main.

## 1. Pourquoi des vidéos manquaient

| Vidéos | Où elles étaient | Pourquoi invisibles |
|---|---|---|
| En fabrication (Estonia, Canal Rhin-Danube v2, miroir, Villa Ocre) | base : production + vidéo `pending` | la Bibliothèque ne listait que les vidéos dont le montage existe (`final_asset_id`) |
| Démos du 25/09 (refuge v1 et v2, chalet v1 et v2, cabane) | `C:\YouTube2\demo\…` | faites par des scripts hors de la base, avant la règle « tout passe par l'appli » |
| Bancs d'essai (agrandissement, H3 contre Wan, premier clip Wan 14B) | `C:\YouTube2\bench\…` | comparaisons techniques, jamais en base |
| Refuge v2 et chalet v1 mis en ligne à la main (26 et 27/09) | YouTube, et en base comme vidéos importées | déjà dans Vidéos → Importées, mais lus depuis YouTube, sans lien avec le fichier du PC |

L'onglet Montage prend ses fonds d'aperçu dans les clips et images des 40 dernières productions, finies ou non, et
prenait ses textes d'essai dans la plus récente : le fond du Canal Rhin-Danube v2 portait l'accroche de l'Estonia.

## 2. Ce qui change

- **Vidéos → En fabrication** : toute vidéo de l'appli dès que son script est écrit (la ligne `videos` naît au step
  script), avec l'étape du panneau Tâches (« Storyboard à valider », « Clip 3 sur 7 », « En file · clip 1 sur 7 »,
  « Arrêtée »…), l'avancement, la fin estimée et une image du storyboard en vignette. Sa fiche montre les clips déjà
  faits (lisibles), le storyboard et le script, et propose « Voir le storyboard dans Création », « Arrêter la
  fabrication » ou « Reprendre », et Supprimer (refusé tant qu'un calcul tourne : l'arrêter d'abord).
- **Démos et essais** (second onglet, adresse `/library?vue=demos`) : chaque sous-dossier de `C:\YouTube2\demo` et
  `C:\YouTube2\bench` qui contient une vidéo. Vidéos finies (`final…`, `comparaison…`, `…_vs_…`) en tête, clips à la
  demande, emplacement sur le PC, **Supprimer le dossier** (tout le dossier ; rien en base ni sur YouTube). Titre et
  description : `demo.json` du dossier (`title`, `description`, `youtube` = identifiant de la vidéo si elle a été mise
  en ligne à la main), sinon le premier titre du `README.md`, sinon le nom du dossier. Fiches écrites le 28/09 pour
  les 8 dossiers existants.
- **Montage** : les textes d'essai viennent de la vidéo du premier fond de chaque format ; le libellé d'un fond dont
  la vidéo n'est pas encore montée finit par « · pas encore montée ».
- **Panneau Tâches** : un « Refaire » ou « Réinventer » de scène raté (par exemple ComfyUI éteint) ne fait plus
  passer la production pour bloquée (« En échec ») : le storyboard reste utilisable et la fabrication continue.
- `/library?video=<id>` ouvre directement la fiche d'une vidéo.

## 3. Pour les essais à venir

Un essai technique (comparer deux réglages, un modèle) va dans `C:\YouTube2\bench\<AAAA-MM-JJ>-<sujet>\` avec un
`demo.json` : il apparaît tout seul dans Démos et essais. Une vidéo destinée à la chaîne passe par l'appli (règle
du 25/09).

## 4. Fichiers

- Dashboard : `lib/library.ts` (toutes les vidéos, `makingOf` d'après `getTaskBoard`, clips déjà faits),
  `lib/library-types.ts` (groupe `en_cours`, `LibraryMaking`), `lib/demos.ts` et `lib/demo-types.ts`, route
  `app/api/demos/[...path]` (lecture avec Range ; un chemin hors des deux dossiers, ou qui n'est pas une vidéo : 404),
  `app/library/page.tsx` et `actions.ts`, `components/library/{library-tabs,demo-view,library-view,library-sheet}.tsx`,
  `lib/montage.ts` (`backgroundsAndSamples`), `lib/tasks.ts` (échec d'une scène refaite), `lib/deletion.ts`.
- Aucune migration, aucun changement du worker.
