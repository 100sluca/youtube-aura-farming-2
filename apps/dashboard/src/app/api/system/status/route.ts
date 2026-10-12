/**
 * GET /api/system/status : état de la machine pour le bloc « Machine » (docs/28), interrogé toutes les 5 à 15 s.
 * Une route plutôt qu'une action serveur : Next exécute les actions une par une, et cette lecture (jusqu'à 4 s quand
 * ComfyUI est occupé) faisait attendre les clics de la page (docs/56-dashboard-rapide.md).
 */
import { getSystemStatus } from "@/lib/system";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(await getSystemStatus(), { headers: { "cache-control": "no-store" } });
}
