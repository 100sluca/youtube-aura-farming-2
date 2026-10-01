/**
 * GET /api/paf/video : la vidéo du dossier « Paf, j'achète » (le .mp4 le plus récent de <DATA_DIR>/paf-j-achete),
 * pour l'aperçu de l'onglet, avec les requêtes partielles (Range) de la balise <video>. Aucun chemin n'est lu dans la
 * requête.
 */
import { createReadStream } from "node:fs";
import { Readable } from "node:stream";

import { pafFolder, pafVideo } from "@/lib/paf";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const video = await pafVideo(await pafFolder());
  if (!video) return new Response("Aucune vidéo dans le dossier", { status: 404 });
  const { path, size } = video;
  const headers: Record<string, string> = { "Content-Type": "video/mp4", "Accept-Ranges": "bytes", "Cache-Control": "no-store" };

  const match = /^bytes=(\d*)-(\d*)$/.exec(req.headers.get("range") ?? "");
  if (match && size > 0) {
    const start = match[1] ? Number(match[1]) : Math.max(0, size - Number(match[2]));
    const end = match[1] && match[2] ? Math.min(Number(match[2]), size - 1) : size - 1;
    if (Number.isNaN(start) || start > end || start >= size) {
      return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
    }
    headers["Content-Range"] = `bytes ${start}-${end}/${size}`;
    headers["Content-Length"] = String(end - start + 1);
    return new Response(Readable.toWeb(createReadStream(path, { start, end })) as ReadableStream, { status: 206, headers });
  }
  headers["Content-Length"] = String(size);
  return new Response(Readable.toWeb(createReadStream(path)) as ReadableStream, { status: 200, headers });
}
