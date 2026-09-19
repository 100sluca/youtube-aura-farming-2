# 04 · Dashboard (Next.js 16 + shadcn/ui)

Code : `apps/dashboard`. Démarrage : `npm install && NEXT_PUBLIC_MOCK=1 npm run dev`.

## 1. Navigation

| Route | Vue | Répond à |
|---|---|---|
| `/` | Vue d'ensemble | « où en est la chaîne aujourd'hui ? » |
| `/videos` | Vidéos publiées | vues, likes, commentaires, abonnés gagnés, rétention par vidéo |
| `/production` | Production | « où en sont les vidéos en cours de fabrication ? » |
| `/calendar` | Calendrier | « qu'est-ce qui sort quand, et quels créneaux sont vides ? » |
| `/ideas` | Idées | backlog de concepts, validation, génération |
| `/experiments` | Expériences | format A vs B, catégories |
| `/alerts` | Alertes | échecs, quota, créneaux vides |
| `/settings` | Réglages | chaînes (OAuth), créneaux, prompts, fournisseurs, notifications |

Sélecteur de chaîne (Toutes / FR / EN) dans l'en-tête, propagé par `?channel=`.

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
vidéo / TTS actifs), e-mail d'alerte, jauge de quota API par chaîne.

## 9. Implémentation

- Server Components pour les lectures ; `"use client"` pour table, kanban, calendrier, toggles.
- Couche données `src/lib/data` : `index.ts` route vers `mock.ts` (déterministe, seed fixe)
  ou `supabase.ts` (requêtes sur les vues `v_video_overview`, `v_production_progress`, tables
  et RPC `next_free_slot`). Le passage au réel se fait fichier par fichier.
- Composants shadcn écrits dans `src/components/ui` (`components.json` prêt pour `npx shadcn add`).
- Auth : Supabase Auth (magic link), middleware qui redirige vers `/login` ; RLS `app_users`.
- Routes serveur : `api/youtube/connect`, `api/youtube/callback` (OAuth), `api/actions/*`
  (approuver, relancer, re-programmer) → insertion de jobs.
