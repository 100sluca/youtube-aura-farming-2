# 47 · Retoucher une vidéo déjà sortie, puis la republier

> 2026-10-01. Demande de Luca : comme une vidéo programmée (docs/44), une vidéo **publiée** doit pouvoir rouvrir la page
> Retoucher (titre, sous-titres, musique, voix, plans) pour la refaire.

## 1. Ce qui change pour Luca

- **Bibliothèque → vidéo Publiée → « Retoucher »** : le bouton est là aussi. La page affiche un encadré bleu « Déjà
  sortie sur YouTube » ; « Refaire la vidéo » demande une confirmation.
- Ensuite, tout se passe comme pour une vidéo programmée : montage (et voix si besoin) → contrôle → **à valider** →
  publiée comme une **nouvelle vidéo** sur YouTube puis TikTok au créneau choisi.
- La version sortie **reste sur YouTube et TikTok** (Luca la supprime lui-même s'il veut) et **garde ses vues** : elle
  devient une fiche à part dans la Bibliothèque (statut Publiée, sans fichier sur le PC, non retouchable), toujours
  relevée chaque heure et lue par l'analyste. Les stats de la nouvelle version repartent de zéro, sans se mélanger.
- « Anciennes versions envoyées » (page Retoucher) affiche « Sortie le … » pour une version qui était sortie.

## 2. Comment c'est fait

| Où | Quoi |
|---|---|
| supabase/migrations/0034_retoucher_publiee.sql | `videos.archived_at`, `videos.remade_as` ; unicité (production, chaîne) limitée aux vidéos non archivées ; `release_upload`, `retouch_video`, `redo_plan` acceptent « published » |
| supabase/migrations/0036_instagram_publication.sql | (autre session) reprend `release_upload` avec Instagram en plus : **partir de ce fichier** pour la modifier |
| services/worker/worker/steps/script.py | `on conflict (production_id, channel_id) where archived_at is null` |
| services/worker/worker/dag.py, steps/storyboard.py, steps/qa.py | les fiches archivées sont ignorées |
| apps/dashboard/src/lib/retouch.ts, retouch-types.ts | « published » retouchable, `video.published`, `publishedAt` des anciens envois, fiche archivée bloquée |
| apps/dashboard/src/components/library/retouch-editor.tsx, library-sheet.tsx | encadré et confirmation « déjà sortie », bouton Retoucher |

`release_upload` sur une vidéo publiée : l'id YouTube est retiré de la vidéo, puis une fiche archivée est créée
(copie du titre, de la description, de la timeline, du TikTok…, `youtube_video_id`, `published_at`, `files_deleted_at`
= maintenant, `scheduled_at` = null pour que TikTok ne la reprenne pas, miniature YouTube). `video_stats`,
`video_metrics_daily`, `video_retention`, `video_comments`, `video_snapshots` et `tiktok_posts` passent sur cette
fiche. La vidéo de l'appli garde son id, ses fichiers et sa production, et note l'envoi dans `previous_uploads`
(`published_at`, `archive_id`). La publication TikTok déjà sortie n'est pas touchée.

Essai du 01/10 (transaction annulée) sur « Canal Rhin-Main-Danube » (5571fed9) : fiche archivée publiée avec
gkHGRfTPS3I et ses 25 relevés, vidéo en « rendering », montage + contrôle en file.

## 3. Limites

- YouTube ne remplace pas le fichier : sans suppression à la main dans YouTube Studio, les deux versions restent en ligne.
- Le temps de fabrication (job_runs) reste sur la vidéo refaite.
