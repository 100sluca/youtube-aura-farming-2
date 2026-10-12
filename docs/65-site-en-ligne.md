# 65 · Site en ligne : les stats et la fabrication depuis le téléphone (Aura)

Demande de Luca (04/10) : voir de n'importe où, sur le téléphone, les statistiques de tous les comptes (YouTube,
TikTok, Instagram), l'argent, la rétention, les dernières vidéos sorties, l'état de la fabrication (pourcentage des
vidéos en cours) et la page Recherche (niches, vidéos à reproduire, stratège). Un site sur Cloudflare, protégé par un
mot de passe.

## 1. En bref

- **Adresse** : celle du Worker Cloudflare `aura-stats` (sous-domaine workers.dev du compte Cloudflare de Luca). Elle
  n'est pas écrite dans le dépôt, qui est public : on la trouve dans `apps/dashboard/.env.local` (`ONLINE_URL`) ou
  dans le tableau de bord Cloudflare → Workers & Pages → aura-stats.
- **Mot de passe** : secret `PASSWORD` du Worker. Session de 30 jours sur l'appareil. 8 essais ratés depuis une même
  adresse : 15 minutes de blocage.
- **Données** : le dashboard du PC (version de production, `launcher/dashboard.ps1`) envoie toutes les 5 minutes un
  instantané de ~120 Ko. Le site garde le dernier : **PC éteint, il montre les derniers chiffres reçus** et le dit
  (voyant vert : moins de 15 min ; orange : jusqu'à 1 h ; rouge : plus).
- **Lecture seule** : le site ne peut rien lancer, arrêter ni valider sur le PC. Il n'a aucune clé, aucun accès à la
  base ; il ne connaît que ce que le PC lui envoie.
- Sur iPhone ou Android : « Ajouter à l'écran d'accueil » l'ouvre comme une appli.
- **Design** : shadcn/ui, sobre (demande de Luca du 04/10 : simple, propre, sans effet décoratif), thème sombre et
  couleurs d'origine gardés.

## 2. Les cinq onglets

| Onglet | Ce qu'il montre |
|---|---|
| **Direct** | Voyant du PC et ce que fait la carte graphique ; vues des 7 derniers jours tous réseaux (et évolution) ; vues par jour sur 28 jours, réseau par réseau (toucher une barre donne le détail du jour) ; abonnés, vidéos sorties, rétention et heures vues YouTube ; une carte par compte ; les 3 premières vidéos en fabrication ; les prochaines sorties ; l'avis de l'agent analyste |
| **Vidéos** | Totaux par réseau, puis les 40 dernières vidéos : une ligne par vidéo avec ses vues sur YouTube, TikTok et Instagram, la part vue, l'accroche à 3 s, la note Top / Moyen / Flop. Un toucher ouvre le détail (24 h, 7 j, j'aime, partages, durée moyenne, abonnés gagnés, avis de l'analyste, liens) |
| **Fabrique** | Worker, ComfyUI, mémoire, carte graphique ; chaque vidéo en route avec son pourcentage, son étape, ses clips et son heure de fin estimée (mêmes calculs que le panneau Tâches) ; storyboards et vidéos à valider ; retouches et autres tâches |
| **Argent** | Revenus réels (0 € : aucun seuil atteint) ; ce que vaudraient les vues des 28 derniers jours si elles étaient payées (taux de docs/61) ; progression vers le Programme Partenaire YouTube et TikTok Creator Rewards |
| **Recherche** | Rapport du stratège et « la vidéo à faire maintenant », verdict par niche, 30 vidéos à reproduire (ce que Gemini en a vu, notre version), 40 niches et leur courbe, Découverte (chaînes qui percent, argent estimé), questions posées au stratège |

## 3. Comment c'est fait

```
PC (dashboard de production, port 3000)                 Cloudflare (Worker aura-stats)
 src/instrumentation.ts ── toutes les 5 min ──┐
 POST /api/online/push                        │
   lib/online-snapshot.ts : assemble          │  POST /api/ingest (jeton INGEST_TOKEN) → KV « snapshot »
   lib/online-push.ts : envoie ───────────────┘  POST /api/login (PASSWORD) → cookie signé 30 j
 GET /api/online/snapshot : le même JSON          GET  /api/snapshot (cookie) → dernier instantané
                                                  public/ : la page (aucune donnée dedans)
```

- **Instantané** (`apps/dashboard/src/lib/online-snapshot.ts`) : réutilise les calculs des pages existantes
  (`getStatsPage`, `getTikTokStatsPage`, `getInstagramStatsPage`, `getNetworkAccounts`, `getTaskBoard`,
  `getSystemStatus`, `getResearchOverview`, `getDiscovery`), donc les mêmes chiffres que le dashboard. Une partie en
  erreur n'empêche pas les autres de partir (`errors`, affiché en bas du site). Pas de fichier du PC : les vignettes
  servies par `/api/media` sont retirées, seules celles de YouTube, TikTok et Instagram restent.
- **Envoi** : seulement en production (`NODE_ENV=production`) et si `ONLINE_URL` et `ONLINE_INGEST_TOKEN` sont dans
  `apps/dashboard/.env.local`. Les `next dev` des sessions et le PC du frère de Luca n'envoient rien. Premier envoi
  45 s après le démarrage. `ONLINE_PUSH_MINUTES` change la cadence (5 par défaut : 288 écritures KV par jour, sous la
  limite gratuite de 1 000).
- **Site** (`apps/online`) : un Worker (`src/index.ts`), un espace KV et la page dans `web/` : React, Tailwind et
  **shadcn/ui** (mêmes composants que le dashboard, copiés dans `web/src/components/ui` : Card, Tabs, Badge, Progress,
  Table, Accordion, Select, Chart…), graphiques shadcn sur Recharts, police Geist. Thème unique sombre (encre chaude,
  orange « signal », une couleur par réseau), défini en variables shadcn dans `web/src/index.css`. Vite construit la
  page dans `dist/` (ignoré par git) avant chaque `wrangler dev` ou `wrangler deploy`. React échappe tout texte de
  l'instantané ; liens et images seulement en http(s) ; en-têtes `noindex`, CSP stricte, pas d'iframe.
- Les types de l'instantané existent deux fois : `apps/dashboard/src/lib/online-snapshot.ts` (qui l'assemble) et
  `apps/online/web/src/lib/snapshot.ts` (qui l'affiche). Les changer ensemble.

## 4. Gestes utiles

```bash
# forcer un envoi tout de suite (dashboard de production allumé)
curl -X POST http://localhost:3000/api/online/push
# voir ce qui part
curl http://localhost:3000/api/online/snapshot
# changer le mot de passe (déconnecte toutes les sessions)
cd apps/online && npx wrangler secret put PASSWORD
# redéployer après une modification de apps/online
cd apps/online && npx wrangler deploy
# essayer en local : secrets dans apps/online/.dev.vars (ignoré par git), puis
cd apps/online && npx wrangler dev   # construit la page au démarrage seulement : le relancer après une modif de web/
# vérifier les types (Worker et page)
cd apps/online && npm run typecheck
```

`wrangler` est connecté au compte Cloudflare de Luca sur ce PC (connexion du 04/10 par code). Le jeton d'envoi est
le même des deux côtés : secret `INGEST_TOKEN` du Worker = `ONLINE_INGEST_TOKEN` du dashboard ; pour le changer, le
changer aux deux endroits.

## 5. Limites

- Les chiffres ont le retard de leurs sources : YouTube Analytics 2 à 3 jours (les jours récents en pointillés sur le
  graphique), relevés TikTok et Instagram de Zernio toutes les ~90 min, plus jusqu'à 5 min d'envoi.
- Les estimations d'argent sont des ordres de grandeur (docs/61), pas des relevés : aucune plateforme ne paie encore.
- Les vidéos en fabrication n'ont pas d'image (leurs storyboards restent sur le PC).
- Une vidéo longue (docs/63) n'a pas d'avancement global : le site montre celui de l'étape en cours.
