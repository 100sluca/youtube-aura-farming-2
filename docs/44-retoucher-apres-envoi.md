# 44 · Retoucher une vidéo déjà programmée, puis la republier

> 2026-09-30. Demande de Luca : une vidéo programmée sur YouTube doit rester retouchable (titre, titre éphémère,
> sous-titres, musique, volumes, voix, plans), puis repartir sur YouTube et TikTok. « On laisse les vidéos telles quelles
> sur YouTube, j'irai à la main les retirer en cas de besoin. »

## 1. Ce qui change pour Luca

- **Bibliothèque → vidéo programmée → « Retoucher »** : le bouton est là aussi pour une vidéo au statut *Programmée*
  (docs/34 : avant, il disparaissait dès l'envoi sur YouTube).
- La page Retoucher affiche un encadré bleu : la version envoyée reste sur YouTube (lien vers YouTube Studio) ; la
  publication TikTok encore programmée sera annulée ; déjà sortie sur TikTok, elle y reste.
- « Refaire la vidéo » (et « Refaire le clip » / « Nouvelle prise de voix » de l'onglet Plans) demandent une
  confirmation, puis tout se passe comme une retouche ordinaire : voix si besoin → montage → contrôle, la vidéo revient
  **à valider**. « Publier cette vidéo ? » → autoriser / programmer : elle part comme une **nouvelle vidéo YouTube**,
  puis sur TikTok au même créneau (planificateur habituel, docs/36).
- **« Anciennes versions envoyées »** (page Retoucher) : les envois remplacés, avec leur lien YouTube Studio pour les
  supprimer, et leur état TikTok.
- Une vidéo **déjà sortie** (statut Publiée) se retouche aussi depuis le 01/10 : sa version sortie et ses stats
  passent sur une fiche archivée (docs/47).

## 2. Comment c'est fait

| Où | Quoi |
|---|---|
| supabase/migrations/0031_retoucher_apres_envoi.sql | `videos.previous_uploads` ; `release_upload` ; `retouch_video` et `redo_plan` acceptent « scheduled » |
| services/worker/worker/steps/tiktok_publish.py | job `tiktok_publish {"delete_post": id}` : supprime chez Zernio l'ancienne publication pas encore sortie |
| services/worker/worker/tiktok/zernio.py | `delete_post` (`DELETE /v1/posts/{id}` ; une publication sortie est refusée par Zernio) |
| services/worker/worker/tiktok/post.py | `idempotency_key(..., generation)` : nouvelle clé après chaque envoi remplacé |
| apps/dashboard/src/lib/retouch.ts, retouch-types.ts | statut « scheduled » retouchable, `previousUploads`, état TikTok |
| apps/dashboard/src/components/library/retouch-editor.tsx, retouch-plans.tsx, library-sheet.tsx | encadré, confirmation, anciennes versions, bouton Retoucher |

`release_upload(p_video)` (appelé par `retouch_video` et `redo_plan`) : si la vidéo a un `youtube_video_id`, elle doit
être « scheduled » ; les jobs TikTok en file sont annulés (refus si un envoi TikTok tourne) ; une publication TikTok
programmée est supprimée par un job ; `{youtube_video_id, youtube_publish_at, scheduled_at, tiktok, replaced_at}` part
dans `previous_uploads` ; `youtube_video_id`, `youtube_publish_at` et `tiktok` sont remis à null. Le step `upload`
renvoie alors le nouveau fichier (il ne refuse que si `youtube_video_id` est déjà rempli).

Clé d'idempotence Zernio : sans `generation`, la vidéo refaite aurait repris la clé `vidéo:1` de sa première
publication et Zernio aurait renvoyé l'ancienne (409). `generation` = nombre d'envois remplacés ; 0 garde les clés
d'avant.

Essai du 30/09 (transaction annulée) sur « Il pouvait se venger… » (cab6db86) : vidéo en « rendering », envoi archivé
(sOyFPq7J4Wg), TikTok remis à null, montage + contrôle + suppression de la publication Zernio mis en file.

## 3. Limites

- YouTube ne remplace pas le fichier d'une vidéo, et l'appli ne supprime rien sur YouTube : Luca supprime l'ancienne
  version dans YouTube Studio (sinon les deux sortent).
- TikTok : une publication déjà sortie ne peut pas être retirée par Zernio ; à supprimer dans l'appli TikTok.
