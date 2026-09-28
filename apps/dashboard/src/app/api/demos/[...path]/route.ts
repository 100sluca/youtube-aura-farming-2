/**
 * GET /api/demos/<demo|bench>/<dossier>/<chemin de la vidéo> : sert une vidéo de démo ou d'essai faite hors de
 * l'appli (C:\YouTube2\demo, C:\YouTube2\bench, docs/28), avec les requêtes partielles (Range) que demande la balise
 * <video>. Le chemin est vérifié par lib/demos.ts : une vidéo sous l'une de ces deux racines, rien d'autre (404).
 */
import { createReadStream, statSync } from "node:fs";
import { extname } from "node:path";
import { Readable } from "node:stream";

import { DEMO_VIDEO_MIME, demoFilePath } from "@/lib/demos";

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

  let size: number;
  try {
    size = statSync(path).size;
  } catch {
    return new Response("Fichier absent du disque", { status: 404 });
  }
  const headers: Record<string, string> = {
    "Content-Type": DEMO_VIDEO_MIME[extname(path).toLowerCase()] ?? "application/octet-stream",
    "Accept-Ranges": "bytes",
    "Cache-Control": "private, max-age=60",
  };
  const range = req.headers.get("range");
  const match = range ? /^bytes=(\d*)-(\d*)$/.exec(range) : null;
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
