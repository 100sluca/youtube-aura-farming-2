# ADR-006 · Tout en local d'abord (dashboard + worker sur le PC, Supabase pour la base)

**Statut** : accepté · 2026-09-19

## Contexte
Luca veut démarrer sans infrastructure : un fichier `.bat` lance le projet sur son PC Windows.
Le GPU est local de toute façon (génération vidéo). Reste la question de la base de données.

## Décision
- **Dashboard** : `npm run dev` sur le PC (port 3000), sans connexion (`DASHBOARD_AUTH=none`) ;
  les routes serveur utilisent la clé service role. Hébergement (Vercel ou Cloudflare) plus tard,
  sans changer le code : passer `DASHBOARD_AUTH=supabase` et remplir `app_users`.
- **Worker** : fenêtre console lancée par le `.bat` (pas de service Windows pour l'instant).
- **Base** : **Supabase hébergé (offre gratuite)** plutôt qu'un Postgres local. Zéro installation,
  Realtime + Storage + sauvegardes inclus, accessible depuis n'importe où le jour où le dashboard
  est hébergé. Le code ne dépend que de `DATABASE_URL` : un Postgres local (ou `supabase start`
  via Docker) reste possible si l'on veut couper toute dépendance.
- **Lanceur** : `launcher/youtube-shorts-daily - demarrer.bat` + fiche mémo, à copier dans
  `C:\Users\Luca\Desktop\Projets_Code-start\youtube-shorts-daily-2026_09_19\`.

## Conséquences
- (+) Aucune infra à payer ni maintenir ; le projet démarre en un double-clic.
- (+) Migration vers un hébergement = deux variables d'environnement.
- (−) L'offre gratuite Supabase met un projet en pause après 7 jours sans requête : le worker
  synchronise chaque jour, ce qui suffit ; sinon le réveiller depuis le tableau de bord Supabase.
- (−) Le dashboard n'est visible que sur le PC tant qu'il n'est pas hébergé (ou via Tailscale).
