# 55 · Les créneaux libres d'abord (YouTube, TikTok, Instagram)

Règle de Luca, le 2026-10-01 :

> Trois vidéos par jour sur YouTube, TikTok et Instagram, à 9 h, 13 h et 18 h. Si je retire une vidéo programmée
> (par exemple en la passant en non répertoriée dans YouTube Studio), son créneau est libre : la prochaine vidéo de
> l'appli le prend. On remplit d'abord les créneaux libres entre aujourd'hui et la dernière date programmée ; seulement
> si tout est pris, on passe au jour d'après.

Code : `worker/slots.py`, migration `0046_creneaux_libres.sql`, tests `tests/test_slots.py`.

## 1. Ce qui existait

- `channels.publish_slots` vaut déjà `{09:00, 13:00, 18:00}` (heure de Paris).
- `next_free_slot` (SQL, 0001) donnait déjà le premier créneau sans vidéo, mais sur 14 jours seulement.
- Ce que Luca changeait dans YouTube Studio n'était pas lu : une vidéo passée en non répertoriée restait
  « programmée » dans l'appli, son créneau restait pris.
- TikTok et Instagram prenaient toujours l'heure de la vidéo sur YouTube.

## 2. Ce que fait l'appli maintenant

**Synchro horaire (h05, et bouton « Actualiser » du Dashboard)** — `steps/sync.py` lit déjà l'état de chaque vidéo
programmée (videos.list, 1 unité pour 50 vidéos). `slots.follow_youtube` en tire :

| Dans YouTube Studio | Dans l'appli |
|---|---|
| passée en **non répertoriée** | retirée du planning (« Privée sur YouTube » dans la Bibliothèque), créneau libre |
| passée en **privée sans date** (avant son heure) | idem |
| **supprimée** | idem |
| **déplacée** à une autre date | l'appli suit la nouvelle date ; l'ancien créneau YouTube est libre |
| retirée puis **reprogrammée** | elle revient « programmée » à sa nouvelle date |
| privée sans date **après** son heure | alerte « Vidéo restée privée après le créneau » (comme avant) |

Une vidéo retirée (SQL `withdraw_from_schedule`) ne sort plus nulle part : ses publications TikTok et Instagram encore
seulement programmées chez Zernio sont supprimées (jobs `delete_post`, comme pour une retouche, docs/44). Si Luca la
reprogramme dans YouTube Studio, TikTok et Instagram la republient (clé `withdrawn` de `videos.tiktok` /
`videos.instagram`). Une alerte « Créneau libéré : 03/10 à 13:00 » apparaît dans le dashboard (pas de mail).

Garde-fous : si YouTube ne renvoie aucune vidéo (mauvais compte, panne), rien n'est retiré ; si un envoi TikTok ou
Instagram de cette vidéo tourne, le retrait attend la synchro suivante.

**Planificateur (toutes les 5 min, `plan_uploads`)** — `slots.fill_free_slots` avance d'abord chaque vidéo prête, pas
encore envoyée sur YouTube, dans le premier créneau libre (au moins 2 h devant, le temps de l'envoi), la plus proche
d'abord : chacune libère le sien pour la suivante. Son envoi YouTube part alors tout de suite (72 h avant le créneau,
comme toujours). Les nouvelles vidéos prennent ensuite le premier créneau libre (`next_free_slot`, désormais sur
120 jours : il y a toujours un « jour d'après »).

Une date choisie à la main (bouton « Programmer » de Création, `schedule_video`) ne bouge jamais :
`videos.slot_pinned`. « Autoriser » (`approve_video`) prend le premier créneau libre, que le planificateur peut encore
avancer.

**TikTok et Instagram** — chaque publication automatique va au premier créneau libre de sa plateforme
(`slots.free_post_slot`). Un créneau y est pris par une publication déjà programmée chez Zernio, ou réservé par une autre
vidéo qui partira à son heure YouTube. Sans trou, c'est donc l'heure de la vidéo sur YouTube, comme avant ; s'il y a un
trou (publication supprimée chez Zernio, vidéo retirée), la vidéo suivante le prend, quitte à sortir sur TikTok avant
YouTube. Le suivi d'une publication programmée repasse toutes les 3 h : une publication supprimée chez Zernio (404)
passe « cancelled » et libère son créneau. Les publications demandées à la main (Bibliothèque) et le rattrapage
(docs/39) gardent leur heure.

## 3. Limites

- Le créneau libéré n'est vu qu'à la synchro suivante (1 h au plus), et une vidéo n'avance que dans un créneau à plus
  de 2 h : un créneau libéré trop tard reste vide.
- Une vidéo déjà envoyée sur YouTube n'est jamais déplacée par l'appli (seulement celles qui attendent leur envoi).
- Déplacer une vidéo dans YouTube Studio ne déplace pas ses publications TikTok / Instagram (docs/36 §Limites).
- L'appli ne corrige pas deux vidéos que Luca met lui-même à la même heure dans YouTube Studio.

## 4. Premier cas réel (01/10, 18 h 20)

La lecture à blanc de YouTube a trouvé deux vidéos renvoyées l'après-midi (retouche après envoi) dont la date dans
YouTube ne correspondait plus à l'appli : « Elle vend son verger… » (appli 02/10 9 h, YouTube 01/10 22 h) et « Elle
oublie 50 000 € dans un taxi… » (appli 05/10 18 h, YouTube 04/10 18 h, la même heure qu'« Aouli »). La synchro de
19 h 05 aligne l'appli sur YouTube et libère 02/10 9 h et 05/10 18 h.
