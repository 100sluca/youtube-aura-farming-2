/**
 * Démarrage du serveur Next. Site en ligne (docs/65-site-en-ligne.md) : la version de production du dashboard (celle de
 * launcher/dashboard.ps1, toujours allumée) pousse l'instantané des stats toutes les ONLINE_PUSH_MINUTES (5 par défaut)
 * en appelant sa propre route POST /api/online/push. Rien en développement (next dev des sessions), rien sans
 * ONLINE_URL et ONLINE_INGEST_TOKEN dans .env.local.
 */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs" || process.env.NODE_ENV !== "production") return;
  if (!process.env.ONLINE_URL || !process.env.ONLINE_INGEST_TOKEN) return;
  const flag = globalThis as { __onlinePush?: boolean };
  if (flag.__onlinePush) return;
  flag.__onlinePush = true;

  const self = process.env.ONLINE_SELF_URL ?? `http://127.0.0.1:${process.env.PORT ?? 3000}`;
  const minutes = Math.max(1, Number(process.env.ONLINE_PUSH_MINUTES) || 5);
  const push = () =>
    fetch(`${self}/api/online/push`, { method: "POST", signal: AbortSignal.timeout(120_000) }).catch((e) =>
      console.warn(`[site en ligne] ${e instanceof Error ? e.message : e}`),
    );
  setTimeout(push, 45_000); // le temps que le serveur écoute
  setInterval(push, minutes * 60_000);
}
