/**
 * GET /api/tasks/board : la file du gestionnaire de tâches, relue toutes les 3 s (panneau ouvert) ou 15 s. Une route
 * plutôt qu'une action serveur : Next exécute les actions une par une, et cette lecture faisait attendre les clics de la
 * page derrière elle (docs/56-dashboard-rapide.md).
 */
import { getTaskBoard } from "@/lib/tasks";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(await getTaskBoard(), { headers: { "cache-control": "no-store" } });
}
