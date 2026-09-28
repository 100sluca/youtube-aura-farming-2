/**
 * GET /api/system/ping : numéro du processus du serveur. Après « Redémarrer le dashboard », la page interroge cette route
 * jusqu'à ce qu'un nouveau serveur réponde (autre numéro), puis se recharge (docs/28-sante-machine.md).
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ pid: process.pid, uptimeS: Math.round(process.uptime()) }, { headers: { "cache-control": "no-store" } });
}
