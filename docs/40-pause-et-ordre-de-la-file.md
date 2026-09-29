# 40 · Pause et ordre de la file (panneau Tâches)

Demandé par Luca le 2026-09-29 : dans le panneau Tâches (bouton en haut à droite), on ne pouvait qu'**arrêter** une
vidéo. Il voulait :
- **mettre en pause** une vidéo, celle en cours comprise, et la **reprendre** plus tard, sans rien perdre de ce qui est
  fait (9 clips sur 13 faits restent faits) ;
- **tout mettre en pause sauf une vidéo**, à faire en priorité, puis reprendre les autres quand il veut ;
- **changer l'ordre de la file** (faire passer la 7e en premier).

Migration `0027_pause_ordre_file.sql`, aucun changement du worker.

## 1. Les gestes

| Où | Geste | Effet |
|---|---|---|
| Vidéo **en cours**, bouton **Pause ▾** | **Tout de suite** | Le calcul en cours sur la carte graphique (clip, images du storyboard, voix) s'arrête dans les 5 s et sera refait à la reprise ; tout ce qui est fini est gardé. |
| | **À la fin du clip en cours** | Le clip (ou les images, la voix) se termine, rien n'est perdu ; la carte « Pause demandée » dit vers quelle heure. Ensuite rien d'autre de cette vidéo ne part. « Annuler la pause » ou « Pause tout de suite » restent possibles pendant ce temps. |
| Vidéo en cours dont l'étape n'utilise pas la carte graphique (script, SEO, montage) | **Pause** | L'étape finit (elle ne bloque pas les autres vidéos, et un appel LLM coupé serait perdu), puis la vidéo attend. |
| Vidéo **en file** ou **en préparation** | **Pause** | Elle garde sa place et attend. |
| Rubrique **En pause** | **Reprendre** | Elle retrouve sa place dans la file, **jamais devant la vidéo en cours** (celle-ci finit d'abord). |
| | ⋯ **Reprendre en premier** | Reprise, puis n° 1 de la file (juste après la vidéo en cours). |
| File d'attente | poignée **⠿** (glisser), **En premier**, ⋯ **Monter / Descendre d'une place** | Nouvel ordre ; la vidéo en cours finit toujours d'abord : « en premier » = la suivante. |
| ⋯ de n'importe quelle vidéo de la file | **Tout mettre en pause sauf celle-ci** | Toutes les autres vidéos se mettent en pause et celle-ci passe en tête. Si une autre vidéo calcule sur la carte graphique, sous-menu : l'arrêter **tout de suite** ou **à la fin de son clip**. |
| En-tête du panneau | **Tout mettre en pause ▾** / **Tout reprendre** | Idem pour toutes les vidéos de la file. |
| ⋯ | **Arrêter la fabrication** (deux clics) | L'ancien « Arrêter », inchangé : rien n'est supprimé, la vidéo passe dans « Arrêtées » (Reprendre / Supprimer). |

Une vidéo dont le storyboard attend le ✓ de Luca n'est pas dans la file : elle ne se met pas en pause (« Tout mettre en
pause » ne la touche pas). Une vidéo déjà terminée non plus : ses retouches (Retoucher, redo_plan, priorité 20) passent
toujours.

Le panneau range maintenant les vidéos ainsi : **En cours**, **En file d'attente** (numérotée, c'est l'ordre des
clips), **En préparation** (script et images du storyboard : ils passent avant les clips par leur priorité, pour que
Luca valide vite ; non numérotée), **En pause** (dans l'ordre de la file), puis Storyboards à valider, Autres tâches,
Échecs, Arrêtées. Une vidéo en pause s'affiche « En pause · 9 clips sur 13 faits ». Une tâche programmée plus tard
(script réécrit à 9 h 30…) s'affiche « prévue à 09:30 » et sa fin estimée en tient compte.

## 2. Ce qui est gardé

Tout ce qui est fini reste : clips, images, voix, script, SEO. Les steps sont idempotents (un clip déjà fait est sauté
à la reprise). Seul le calcul interrompu par « Tout de suite » repart de zéro : un clip Wan ou H3 ne peut pas reprendre
à mi-chemin. Il repart sans compter un essai de plus (le job garde ses 3 essais).

## 3. L'ordre de la file

`claim_jobs` sert les jobs par **priorité** (aperçus 5, retouches 20, images de storyboard 80-90, clips et voix 100…),
puis par **place de leur vidéo dans la file**, puis par ancienneté ; les vidéos en pause sont sautées.

- Place d'une vidéo (`production_queue_key`) : celle choisie par Luca (`productions.queue_at`), sinon l'heure de ses
  premiers clips (le ✓ du storyboard), sinon celle de sa création.
- Conséquence voulue : les vidéos sortent **l'une après l'autre**. Avant, les clips de deux vidéos validées dans la même
  seconde s'intercalaient (Villa Ocre et « Elle fait semblant d'être ruinée » en étaient toutes deux à 9 clips sur 13
  et 19 le 29/09 au matin) ; depuis la migration, la Villa Ocre a fini ses clips d'abord.
- Réordonner (`reorder_queue`) : les vidéos de la liste se partagent les places qu'elles occupaient déjà, dans le
  nouvel ordre. Les autres ne bougent pas, et une vidéo validée ensuite arrive toujours au bout. La vidéo dont un clip
  ou la voix tourne est toujours gardée devant.
- Reprendre (`unpause_productions`) : si la vidéo reprise était devant celle en cours, elles échangent leur place ;
  plusieurs vidéos reprises gardent leur ordre entre elles.
- « Tout mettre en pause sauf celle-ci » (`focus_production`) : pause des autres + celle-ci en tête ; les autres
  gardent leur ordre pour la reprise.
- Le panneau refait le même calcul pour trier et dater (`apps/dashboard/src/lib/tasks.ts`, `queueKey`) : la file de
  la carte graphique est déroulée dans l'ordre de `claim_jobs`, vidéos en pause exclues.

## 4. Base et code

- `supabase/migrations/0027_pause_ordre_file.sql` : colonnes `productions.paused_at` et `productions.queue_at` ;
  fonctions `production_queue_key`, `claim_jobs` (redéfinie), `set_queue_order`, `gpu_running_productions`,
  `reorder_queue`, `pause_productions(ids, now)`, `unpause_productions(ids)`, `focus_production(id, now)`,
  `cancel_production` (redéfinie : un arrêt efface la pause, et les jobs interrompus par la pause repartent avec
  Reprendre).
- Pause « tout de suite » : le job en cours passe `cancelled` avec l'erreur `Mise en pause` ; le worker l'arrête comme
  pour Arrêter (`worker/main.py` lit le statut toutes les 5 s, `worker/cancel.py`, prompt ComfyUI annulé) ; la reprise
  remet en file les jobs portant ce marqueur. Aucun fichier du worker n'a changé.
- Dashboard : `app/tasks/actions.ts` (`pauseProductions`, `unpauseProductions`, `reorderQueue`, `focusProduction`),
  `lib/tasks.ts`, `lib/task-types.ts` (rubriques `preparing` et `paused`, `allTasks`), `components/tasks/task-manager.tsx`,
  `lib/library.ts` (la Bibliothèque montre aussi « En pause » pour une vidéo en fabrication).

## 5. Vérifié le 29/09

- SQL : 28 vérifications dans une transaction annulée (données factices, vraie file neutralisée) : une vidéo après
  l'autre, pause « à la fin du calcul » (le clip continue) et « tout de suite » (job interrompu puis remis en file sans
  compter d'essai), reprise sans passer devant la vidéo en cours, ordre choisi, « sauf celle-ci », Arrêter puis
  Reprendre une vidéo en pause, aperçu de voix toujours servi en premier, clés égales départagées.
- Navigateur, avec trois vidéos d'essai dont les clips ne pouvaient pas partir (programmés dans 10 ans) : En premier,
  glisser-déposer, Monter / Descendre, Pause, Reprendre en premier, confirmation d'Arrêter, « Tout mettre en pause sauf
  celle-ci » (à la fin du clip en cours de la Villa Ocre) puis « Tout reprendre ». Vidéos d'essai supprimées ensuite,
  vraies vidéos remises à leur place naturelle (aucune pause, aucune place choisie). Écran de téléphone vérifié.

## 6. Limites

- Glisser-déposer : souris seulement ; sur téléphone, « En premier » et le menu ⋯ (Monter / Descendre).
- Une vidéo « Gemini en ligne » (docs/17) dont le clip attend Gemini n'est pas interrompue par « Tout de suite » (le
  job attend en file, il n'occupe pas la carte graphique) : la pause la retient à son prochain passage. Un clip Gemini
  coupé pendant l'envoi de sa demande peut être redemandé à la reprise.
- La fin estimée reste une estimation (médianes des 300 derniers jobs de chaque type).
