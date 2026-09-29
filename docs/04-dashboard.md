# 04 · Dashboard (Next.js 16 + shadcn/ui)

Code : `apps/dashboard`. Démarrage : `npm install && NEXT_PUBLIC_MOCK=1 npm run dev`.

## 1. Navigation

> Refonte du 2026-09-25 : [`16-creation-bibliotheque-taches.md`](16-creation-bibliotheque-taches.md). Les sections
> 3, 4, 6, 7 ci-dessous décrivent les anciennes pages (Vidéos publiées, Production, Idées, Expériences), remplacées
> par la Bibliothèque, le panneau Tâches, Création et la section « Ce qui marche le mieux ».

| Route | Vue | Répond à |
|---|---|---|
| `/` | Vue d'ensemble | « où en est la chaîne aujourd'hui ? », ce qui attend une décision, ce qui marche le mieux |
| `/dashboard` | Dashboard | onglets YouTube et TikTok : les chiffres de chaque vidéo publiée (tableau triable, graphiques, Actualiser) et l'agent analyste : ce qui marche et pourquoi, leçons à valider ([`25-dashboard-statistiques.md`](25-dashboard-statistiques.md), onglet TikTok : [`39-tiktok-partout.md`](39-tiktok-partout.md)) |
| `/create` | Création | chaîne → thème → idées notées → ✓ / ✗ ; storyboards à regarder avant la fabrication |
| `/library` | Bibliothèque | toutes les vidéos (produites ici et importées de YouTube) : lecture, publication (YouTube, et TikTok par Zernio : état, lien, « Publier sur TikTok »), stats, suppression |
| `/calendar` | Calendrier | « qu'est-ce qui sort quand, et quels créneaux sont vides ? », sur YouTube et TikTok (rattrapage prévu compris, docs/39) |
| `/agents` | Agents | les agents et leurs prompts (modifiables, versionnés), la chaîne de production en direct ([`22-agents.md`](22-agents.md)) |
| `/montage` | Montage | le modèle de montage de toutes les vidéos : titre d'accroche, sous-titres, textes à l'écran placés sur un aperçu 9:16, rendu exact ([`23-montage.md`](23-montage.md)) |
| `/settings` | Réglages | chaînes (ajout, OAuth, historique), TikTok (clé Zernio, compte relié, publication automatique, rattrapage), modèles, IA, notifications, quota |

En-tête : sélecteur de chaîne (liste des chaînes par leur nom, « Toutes », « Ajouter une chaîne », mémorisé dans un
cookie), bouton **Tâches** (panneau de droite : ce qui se fabrique, file d'attente, échecs, arrêt ; pause, reprise et
ordre de la file : [`40-pause-et-ordre-de-la-file.md`](40-pause-et-ordre-de-la-file.md)), thème clair / sombre.

## 2. Vue d'ensemble `/`

- **KPI** : abonnés (+Δ 7 j), vues 7 j (Δ % vs 7 j précédents), rétention moyenne 28 j
  (`averageViewPercentage` pondérée par les vues), heures de visionnage 28 j, Shorts publiés 7 j.
- **Pipeline** : compteurs en génération / prêtes / programmées / en échec (cliquables).
- **Seuils YPP** : jauges 1 000 abonnés et 10 M vues / 90 j.
- **Vues par jour (28 j)** : barres empilées FR / EN.
- **Prochaines publications** : 6 prochains créneaux (chaîne, heure, titre, statut) ; un
  créneau vide < 48 h est signalé.
- **En production** : 5 cartes avec barre de progression et étape courante (temps réel).
- **Alertes ouvertes**.

## 3. Vidéos publiées `/videos`

Table triable/filtrable (TanStack Table) : poster, titre, chaîne, format, catégorie, date,
vues, likes, commentaires, rétention %, abonnés gagnés. Clic → panneau latéral :
- lien YouTube, 4 tuiles (vues, rétention, likes, abonnés) ;
- **courbe de rétention** (`audienceWatchRatio` × 100 en fonction du % de la vidéo) ;
- vues par jour (14 j), derniers commentaires, résumé du script (scènes, narration) ;
- action « Cloner en nouvelle idée » (concept `source = clone`, `parent_video_id`).

## 4. Production `/production`

Kanban par étape : Script → Génération des clips → Assemblage → Contrôle / revue → Prête →
En échec. Carte : titre du concept, badges FR/EN + format, progression (`v_production_progress`),
étape courante (« Clip 5/8 »), ETA, erreur + bouton Relancer. Panneau : liste des jobs (type,
statut, progression, tentatives, horodatage), journal (`job_logs`), aperçu 480p et validation
(« Approuver » → `ready`, « Refuser » → `failed` avec motif) quand `auto_publish = false`.

Temps réel : abonnement Supabase Realtime sur `jobs` et `videos` (hook `useRealtimeJobs`),
mise à jour optimiste des cartes sans rechargement.

## 5. Calendrier `/calendar`

Grille semaine × (chaîne × créneau). Cellule : titre + statut (Programmée = sur YouTube avec
`publishAt` ; Planifiée = créneau attribué, upload à venir ; Prête) ou « Vide ». Navigation par
semaine. Évolutions : glisser-déposer pour re-programmer (`videos.update`, 50 unités),
ajout/suppression de créneaux ponctuels.

## 6. Idées `/ideas`

Table des concepts (titre + hook, catégorie, score, source, statut) ; Approuver (→ production +
job `script`), Rejeter, « Générer 10 idées » (job `ideate`), ajout manuel.

## 7. Expériences `/experiments`

Comparaison A/B : vidéos, rétention moyenne, vues / vidéo, abonnés / 1 000 vues ; graphique
groupé ; tableau par catégorie. Base pour décider de la répartition des formats (`60/40`, etc.).

## 8. Réglages `/settings`

Chaînes (connexion OAuth, id YouTube, créneaux, `auto_publish`), prompts des agents (versions,
actif, diff, activation d'une proposition de l'agent d'amélioration), fournisseurs (LLM /
vidéo / TTS actifs), notifications par e-mail (mail « vidéo terminée », compte Gmail qui envoie, mail
d'essai : docs/32), jauge de quota API par chaîne. Carte **TikTok (par Zernio)** : clé API (chiffrée, vérifiée avant
d'être enregistrée), comptes TikTok connectés à Zernio, compte relié à chaque chaîne et publication automatique,
commentaires / duo / collage, étiquette « contenu généré par IA » (coupée par défaut) : docs/36.

## 9. Implémentation

- Server Components pour les lectures ; `"use client"` pour table, kanban, calendrier, toggles.
- Couche données `src/lib/data` : `index.ts` route vers `mock.ts` (déterministe, seed fixe)
  ou `supabase.ts` (requêtes sur les vues `v_video_overview`, `v_production_progress`, tables
  et RPC `next_free_slot`). Le passage au réel se fait fichier par fichier.
- Composants shadcn écrits dans `src/components/ui` (`components.json` prêt pour `npx shadcn add`).
- Auth : Supabase Auth (magic link), middleware qui redirige vers `/login` ; RLS `app_users`.
- Routes serveur : `api/youtube/connect`, `api/youtube/callback` (OAuth), `api/actions/*`
  (approuver, relancer, re-programmer) → insertion de jobs.
