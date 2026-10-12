/**
 * POST /api/online/push : construit l'instantané et l'envoie au site en ligne (docs/65-site-en-ligne.md). Appelée toutes
 * les 5 minutes par src/instrumentation.ts (version de production du dashboard), ou à la main pour forcer un envoi.
 */
import { pushOnlineSnapshot } from "@/lib/online-push";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  const result = await pushOnlineSnapshot();
  if (!result.ok) console.warn(`[site en ligne] envoi raté : ${result.error}`);
  return Response.json(result, { status: result.ok ? 200 : 502, headers: { "cache-control": "no-store" } });
}
