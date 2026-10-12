/**
 * GET /api/paf/video : la vidéo du dossier « Paf, j'achète » (le .mp4 le plus récent de <DATA_DIR>/paf-j-achete),
 * pour l'aperçu de l'onglet, avec les requêtes partielles (Range) de la balise <video>. Aucun chemin n'est lu dans la
 * requête.
 */
import { fileResponse } from "@/lib/file-response";
import { pafFolder, pafVideo } from "@/lib/paf";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const video = await pafVideo(await pafFolder());
  if (!video) return new Response("Aucune vidéo dans le dossier", { status: 404 });
  return fileResponse(req, video.path, { "Content-Type": "video/mp4", "Cache-Control": "no-store" });
}
