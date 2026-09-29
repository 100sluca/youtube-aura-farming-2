# 42. Reprise après un plantage

Demande de Luca (29/09) : si la web app, le worker ou ComfyUI plante, reprendre là où on en était sans perdre le
travail déjà fait sur les clips, les storyboards, etc.

## 1. Ce qui était déjà gardé

| Travail | Où il est enregistré | Après un plantage |
|---|---|---|
| Script, SEO | `productions` en base, dès qu'ils sont écrits | pas refait (step idempotent) |
| Images du storyboard | `C:\YouTube2\data\…\storyboard\` + une ligne `assets` **par image**, dès qu'elle est faite | seules les scènes sans image sont refaites |
| Choix, Refaire, Réinventer, Valider dans Création | server actions : écrits en base au clic | rien à perdre, même si le dashboard tombe |
| Clips | un job `generate_clip` par scène ; `clips\scene_NN.mp4` + `assets` quand le fichier est complet | seul le clip en cours repart de zéro |
| Voix | `narration.wav` + `videos.timeline` | toute la voix est redite (quelques minutes) |
| Montage | refait en entier à partir des clips et de la voix | rien de perdu |

ComfyUI tombé en plein calcul : relancé par le worker (docs/28), la tâche est reprise toute seule.

## 2. Ce qui manquait, corrigé le 29/09

1. **Reprise immédiate au démarrage du worker** (`worker/main.py:recover_after_crash`, `Db.recover_after_crash`).
   Avant, les tâches du worker mort restaient « en cours » 15 à 20 min (`requeue_stale_jobs`, toutes les 5 min).
   Maintenant, dès que le superviseur relance le worker (30 s après un plantage) ou au lancement de `worker.bat` après
   une coupure, ses tâches repartent. Chacune reçoit une ligne dans son journal, et une alerte « Reprise après un arrêt
   du worker : N tâche(s) relancée(s) » s'affiche.
2. **Rendu orphelin retiré de ComfyUI.** Si le worker meurt pendant un clip, ComfyUI continue de calculer ce clip
   pour personne. Au redémarrage, la file de ComfyUI est vidée et le calcul interrompu avant que la reprise en
   soumette un nouveau.
3. **Un plantage ne coûte plus de tentative** (migration `0029`, `requeue_stale_jobs` ; même règle au démarrage).
   Avant, deux plantages sur le même clip plus une vraie panne l'envoyaient en échec définitif.
4. **Storyboard : image enregistrée mais pas encore retenue.** Un arrêt entre les deux laissait une scène sans image
   retenue, et « Valider » refusait. À la reprise, la dernière image de la scène devient la retenue.

## 3. Ce qui reste perdu

Le calcul **en cours** au moment du plantage (un clip, une image, la voix) repart de zéro : ComfyUI ne sait pas
reprendre un rendu à moitié fait. Tout ce qui était fini est gardé.
