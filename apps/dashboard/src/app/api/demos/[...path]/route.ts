/**
 * GET /api/demos/<demo|bench>/<dossier>/<chemin de la vidéo> : sert une vidéo de démo ou d'essai faite hors de
 * l'appli (C:\YouTube2\demo, C:\YouTube2\bench, docs/28), avec les requêtes partielles (Range) que demande la balise
 * <video>. Le chemin est vérifié par lib/demos.ts : une vidéo sous l'une de ces deux racines, rien d'autre (404).
 */
import { extname } from "node:path";

import { DEMO_VIDEO_MIME, demoFilePath } from "@/lib/demos";
import { fileResponse } from "@/lib/file-response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const segments = (await params).path.map((s) => {
    try {
      return decodeURIComponent(s);
    } catch {
      return s; // déjà décodé
    }
  });
  const path = await demoFilePath(segments[0] ?? "", segments.slice(1));
  if (!path) return new Response("Not found", { status: 404 });

  return fileResponse(req, path, {
    "Content-Type": DEMO_VIDEO_MIME[extname(path).toLowerCase()] ?? "application/octet-stream",
    "Cache-Control": "private, max-age=60",
  });
}
