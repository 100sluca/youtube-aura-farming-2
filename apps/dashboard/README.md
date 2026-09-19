# Dashboard YouTube 2.0

Next.js 16 (App Router) · React 19 · Tailwind v4 · shadcn/ui · Recharts · TanStack Table · Supabase.

```bash
npm install
NEXT_PUBLIC_MOCK=1 npm run dev      # données factices déterministes, aucun backend requis
npm run lint && npx tsc --noEmit && npm run build
```

## Pages
`/` vue d'ensemble · `/videos` vidéos publiées (table + panneau rétention) · `/production` kanban des
productions (jobs) · `/calendar` créneaux par chaîne · `/ideas` backlog de concepts · `/experiments`
format A vs B · `/alerts` · `/settings` (chaînes / OAuth, prompts, fournisseurs, quota).
Le sélecteur Toutes / FR / EN de l'en-tête écrit `?channel=`. Spécification : `../../docs/04-dashboard.md`.

## Structure
```
src/app/              pages (Server Components) + api/youtube/{connect,callback} (OAuth Google)
src/components/ui/    composants shadcn écrits à la main (components.json prêt pour `npx shadcn add`)
src/components/       briques métier (kpi-card, kanban-board, videos-table, slot-cell, …)
src/lib/types.ts      modèle du domaine (miroir de supabase/migrations/0001_init.sql)
src/lib/data/         contract.ts (interface DataSource) · mock.ts · supabase.ts (à brancher) · index.ts
src/lib/crypto.ts     AES-GCM des refresh tokens (même format que le worker Python)
src/hooks/            use-realtime-jobs.ts (stub : futur abonnement Supabase Realtime sur `jobs`)
```

## Brancher Supabase
1. Renseigner `.env.local` (voir `../../.env.example`) et retirer `NEXT_PUBLIC_MOCK`.
2. Implémenter fonction par fonction `src/lib/data/supabase.ts` : chaque stub nomme la table, la vue
   (`v_video_overview`, `v_production_progress`) ou la RPC (`next_free_slot`) à interroger.
3. Ajouter l'auth (Supabase Auth par lien magique + middleware) : les routes OAuth exigent déjà
   un utilisateur présent dans `app_users` (`currentAppUser()`).

## Notes de versions
- `@tanstack/react-table` v9 (`useTable` + `tableFeatures`, pas `useReactTable`).
- `lucide-react` v1 (noms d'icônes : `TriangleAlert`, `X`, `CircleCheck`…).
- `recharts` 3 : `src/components/ui/chart.tsx` adapte les types de tooltip/légende de shadcn.
- `next/font/google` (Geist) télécharge les polices au build : prévoir une police locale hors ligne.
