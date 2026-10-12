/**
 * GET /api/retouch/<video id>/state : avancement de la retouche en cours (Bibliothèque → Retoucher, docs/34), relu
 * toutes les 2 s pendant que la vidéo est refaite. Une route plutôt qu'une action serveur : Next exécute les actions une
 * par une, et cette lecture faisait attendre les autres boutons de la page (docs/56-dashboard-rapide.md).
 */
import { getRetouchState } from "@/lib/retouch";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return Response.json(null, { status: 404 });
  return Response.json(await getRetouchState(id), { headers: { "cache-control": "no-store" } });
}
