/**
 * GET /api/system/memory : programmes qui prennent le plus de mémoire (fenêtre « Machine », docs/28). Environ 2 s de
 * PowerShell : en route plutôt qu'en action serveur, pour ne pas bloquer les clics derrière (docs/56).
 */
import { memoryHogs } from "@/lib/system";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(await memoryHogs(), { headers: { "cache-control": "no-store" } });
}
