# 45 · Temps de fabrication d'une vidéo (30/09)

Demande de Luca : pour chaque vidéo, savoir combien de temps elle a pris de bout en bout, et étape par étape (script,
images, chaque clip, voix, montage), avec le nombre d'images et de clips.

## Où le voir

Bibliothèque → clic sur une vidéo → section **Temps de fabrication** (sous « Fabrication ») :

- **Calcul** : la somme des temps de calcul, du script au contrôle qualité (l'envoi YouTube/TikTok n'est pas compté) ;
- **De bout en bout** : du premier départ au dernier arrêt, attentes comprises, dont le temps passé avant ta
  validation du storyboard ;
- **Produit** : nombre d'images générées (essais refusés compris) et de clips ;
- une barre par étape (script, images du storyboard, lancement du rendu, clips, voix, assemblage, contrôle, SEO), avec
  les relances et les passages ratés ;
- **Chaque clip** et **Chaque image** (dépliables) : le temps scène par scène, et la moyenne.

## Comment c'est mesuré

- `job_runs` (migration 0032) : une ligne par **passage** d'une tâche, écrite par un déclencheur sur `jobs` dès qu'une
  tâche quitte « running » (finie, ratée, retentée, en attente d'un service comme Gemini, arrêtée, coupée par un
  plantage du worker — la fin est alors son dernier battement). `jobs.started_at` ne gardait que le premier départ :
  les relances et les Refaire étaient perdus. Rien à changer dans le worker pour ça.
- Images : `assets.meta.gen_s` = le temps de chaque image du storyboard, contrôle vision compris
  (`worker/steps/storyboard.py`). Les fiches de personnages et les cartes comptent dans le temps de l'étape, pas image
  par image.
- Clips : un job `generate_clip` par scène, donc le temps d'un clip = ses passages (clip Gemini : le temps actif, pas
  l'attente entre deux vérifications).
- Vidéos faites avant le 30/09 : temps lus sur les tâches (premier départ → dernière fin), marqués approximatifs, sans
  le détail des images.

Code : `supabase/migrations/0032_temps_de_fabrication.sql`, `apps/dashboard/src/lib/timing.ts`,
`apps/dashboard/src/components/library/production-timing.tsx`.
