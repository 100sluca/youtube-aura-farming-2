-- 0019 : notifications par e-mail (docs/32-notifications-mail.md)
--
-- La table alerts sert de boîte d'envoi : toutes les 20 s, le worker (worker/notify.py) envoie les alertes dont la
-- sorte est cochée dans Réglages → Notifications (app_settings « notifications » ; mot de passe d'application Gmail
-- chiffré dans app_secrets « smtp_password »).
--   kind        : video_ready = vidéo montée et contrôlée (step qa, une fois par vidéo), test = mail d'essai des
--                 Réglages ; null = alertes internes (échecs, quota, tampon), qui ne partent plus par mail
--   email_error : dernier refus du serveur d'envoi (affiché dans Réglages)
--   acknowledged_at (déjà là, plus lu par le dashboard depuis la refonte du 25/09) : alerte close sans mail
--                 (mail d'essai refusé, « Vidéo terminée » décoché entre-temps)
alter table alerts add column if not exists kind text;
alter table alerts add column if not exists email_error text;
create index if not exists alerts_outbox_idx on alerts (created_at) where emailed_at is null and acknowledged_at is null;
create index if not exists alerts_video_kind_idx on alerts (video_id, kind) where kind is not null;
