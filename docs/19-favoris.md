# 19 · Storyboards favoris

Demande de Luca (2026-09-25) : garder les storyboards dont il aime l'idée et les images, pour les retrouver plus tard
et les refaire, même s'il ne les fabrique pas tout de suite.

## 1. Garder : l'étoile

- **Création → Storyboards à regarder** : étoile à côté du badge « à regarder », et en haut du storyboard ouvert en
  grand. **Bibliothèque → fiche d'une vidéo → Fabrication** : bouton « Garder en favori ».
- Un favori garde **l'idée** (titre, accroche, prémisse, faits sourcés), **le script**, les modèles utilisés et **une
  copie de l'image retenue de chaque scène** dans `<DATA_DIR>/favorites/<id favori>/` (≈ 1,3 Mo par image, ≈ 10 Mo
  par storyboard).
- La copie rend le favori indépendant de la vidéo : **✗ Abandonner** le storyboard ou supprimer la vidéo efface le
  dossier de la production, pas celui du favori (le bouton d'abandon le rappelle : « le favori reste »).
- Tant que la production existe, le favori suit le choix d'images : il est recopié quand on retient une autre image,
  au ✓ (Valider et fabriquer, local ou Gemini) et juste avant la suppression de la production.
- Recliquer sur l'étoile allumée retire le storyboard des favoris (un favori par production).

## 2. Retrouver : menu **Favoris** (`/favorites`)

Une carte par favori, du plus récent au plus ancien : titre, thème, date, accroche, planche des images, où en est
l'original (attend encore dans Création, en fabrication, dans la Bibliothèque, abandonné ou supprimé) et combien de
fois il a été refait. « Revoir » ouvre chaque scène en grand avec son texte (narration ou texte à l'écran) et sa
description d'image. Recherche dès 7 favoris. Filtre : la chaîne de l'en-tête (« Toutes » = tout).

## 3. Refaire

- **Refaire avec ces images** : nouvelle production pour la même chaîne, même script, storyboard déjà en place. Le job
  `script` voit le script existant et ne rappelle pas le LLM, crée la vidéo, puis le job `storyboard` saute les scènes
  déjà illustrées (idempotence de `worker/steps/storyboard.py`) : le storyboard revient dans **Création → Storyboards
  à regarder** en quelques secondes, dès que la file de la carte graphique le prend. On peut encore y changer une image
  (« Refaire » une scène garde le modèle d'image d'origine), puis ✓.
- **Nouvelles images** : même idée, même script, storyboard refait avec les modèles des réglages actuels.
- Dans les deux cas, les clips suivent le modèle vidéo **des réglages actuels** (le modèle de l'original n'est gardé
  que pour mémoire) ; l'agent SEO repasse sur le titre et la description.
- **Retirer** (deux clics) : le favori et ses copies d'images sont effacés ; l'original, s'il existe encore, ne bouge
  pas.

Rien à relancer côté worker : tout passe par des jobs qu'il connaît déjà (`script`, `seo`, `storyboard`).

## 4. Fichiers

- Base : `supabase/migrations/0011_favorites.sql` (table `favorites`, SQL `restore_favorite` : production, images et
  job `script` dans une seule transaction, le worker ne voit jamais une production sans ses images).
- Dashboard : `lib/favorites.ts` (copies, synchro, refaire, retirer), `lib/favorite-types.ts`, `app/favorites/`
  (page et actions), `app/api/favorites/[id]/[file]/route.ts` (images, chemin cherché en base),
  `components/favorites/` (étoile, page) ; branchements dans `components/create/`,
  `components/library/library-sheet.tsx`, `app/production/actions.ts` (choisir, valider) et `lib/deletion.ts` (avant
  suppression).
- On n'efface qu'un dossier nommé exactement par l'identifiant du favori, sous `favorites` (même règle que
  `lib/files.ts`).

## 5. Limites

- Un favori dont la chaîne a changé de langue ne peut pas être refait tel quel (le script n'est écrit que dans la
  langue d'origine) : `restore_favorite` le refuse avec un message.
- Seule l'image retenue de chaque scène est gardée, pas les autres candidates.
