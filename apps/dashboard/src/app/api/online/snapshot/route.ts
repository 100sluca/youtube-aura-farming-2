/**
 * GET /api/online/snapshot : l'instantané envoyé au site en ligne (docs/65-site-en-ligne.md), pour le regarder sur le PC.
 */
import { buildOnlineSnapshot } from "@/lib/online-snapshot";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(await buildOnlineSnapshot(), { headers: { "cache-control": "no-store" } });
}
