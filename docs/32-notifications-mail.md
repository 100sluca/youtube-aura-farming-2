# 32 · Un mail quand une vidéo est terminée

Demande de Luca (28/09) : recevoir un mail dès qu'une vidéo est finie, pour savoir qu'il peut aller la regarder ;
l'adresse se règle dans les Réglages.

## 1. Mise en route (une fois)

1. Sur le compte Gmail qui enverra les mails (le tien, ou un second compte) : la validation en deux étapes doit être
   active, puis <https://myaccount.google.com/apppasswords> → créer un mot de passe d'application nommé
   « YouTube 2.0 ». Google affiche 16 lettres (les espaces ne comptent pas).
2. Dashboard → **Réglages → Notifications par e-mail** : adresse qui reçoit, compte Gmail qui envoie (vide = la même
   adresse), coller les 16 lettres → « Enregistrer le mot de passe ».
3. **« Envoyer un mail d'essai »** : le worker l'envoie dans les 20 s ; la ligne passe au vert, ou affiche le refus de
   Gmail (mot de passe faux, validation en deux étapes coupée…).

Si le téléphone ne sonne pas pour un mail que l'adresse s'envoie à elle-même, mettre un second compte Gmail comme
compte qui envoie (avec son propre mot de passe d'application).

## 2. Le mail

- **Quand** : dans les 20 s qui suivent le contrôle final (step `qa`) d'une vidéo, la première fois qu'elle le passe,
  qu'elle attende la validation ou parte en publication automatique. Refaire son montage (onglet Montage) ne renvoie
  pas de mail ; « Refaire » une production crée une nouvelle vidéo, donc un nouveau mail.
- **Objet** : « 🎬 Vidéo terminée : <titre> ».
- **Contenu** : l'image de la vidéo (poster du montage), durée, chaîne, thème, ce qui reste à faire (« Autoriser la
  publication » dans sa fiche, ou rien en publication automatique) et un bouton vers sa fiche
  (`http://localhost:3000/library?video=<id>`, qui s'ouvre sur le PC du dashboard ; autre adresse : `DASHBOARD_URL`
  dans le `.env` du worker).
- Gratuit : serveur d'envoi de Gmail (smtp.gmail.com, port 465), jusqu'à 500 mails par jour.

## 3. Fonctionnement

- Boîte d'envoi = table `alerts` (migration 0019 : colonnes `kind` et `email_error`). Le step qa y dépose une alerte
  `video_ready` (sauf s'il en existe déjà une pour cette vidéo), le bouton d'essai une alerte `test` ; le planificateur
  du worker les envoie toutes les 20 s, les essais d'abord (`worker/notify.py`).
- Réglages en base : `app_settings.notifications` (`email_to`, `on_video_ready`, `sender`) et le mot de passe chiffré
  dans `app_secrets.smtp_password`, comme les clés d'IA (le navigateur n'en voit que les 4 derniers caractères). Ils
  priment sur le `.env` du worker : `ALERT_EMAIL_TO`, `NOTIFY_ON_REVIEW`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
  `SMTP_PASS`, `RESEND_API_KEY`, `DASHBOARD_URL`.
- Envoi raté : l'erreur s'affiche dans Réglages (« Dernier mail refusé… ») ; les mails « vidéo terminée » attendent
  avec une pause croissante (1, 2, 4… 30 min, pour que Gmail ne bloque pas le compte) et sont abandonnés au bout de
  6 h ; un mail d'essai réussi lève la pause et fait partir ceux en attente. Sans mot de passe, ils attendent sans
  rien tenter. Un mail d'essai raté n'est pas retenté : on corrige, puis on refait l'essai.
- Case « Vidéo terminée » décochée : aucune alerte n'est déposée ; celles déjà en attente sont closes sans mail.
- Les autres alertes (job en échec définitif, quota, tampon faible) restent en base sans mail : elles n'étaient
  jamais parties (aucun serveur d'envoi réglé jusqu'ici ; 65 en attente le 28/09) et inonderaient la boîte (tampon
  faible chaque matin, un mail par clip en échec). À rebrancher par une case si besoin.

## 4. Fichiers

- `supabase/migrations/0019_email_notifications.sql` (appliquée le 28/09).
- Worker : `worker/notify.py` (réglages, mail, boîte d'envoi), `steps/qa.py`, `scheduler.py` (toutes les 20 s au lieu
  de 2 min), `config.py` (`SMTP_PORT`, `DASHBOARD_URL`) ; tests `tests/test_notify.py`.
- Dashboard : `lib/notify.ts`, `lib/notify-types.ts`, `app/settings/notify-actions.ts`,
  `components/settings/notifications-settings.tsx`, `app/settings/page.tsx` (carte « Notifications par e-mail »,
  ancre `/settings#notifications`).
