/**
 * GET /api/music/<id> : sert une musique de la bibliothèque (dossier « music » du dépôt, docs/26-musique.md) pour
 * l'écoute de l'onglet Montage, avec les requêtes partielles (Range) qui permettent de la lire en continu et de partir
 * du « Début » réglé. Le chemin n'est jamais pris dans la requête : l'identifiant (nom du fichier sans extension) est
 * cherché parmi les fichiers du dossier. Sans fichier : 404.
 */
import { createReadStream } from "node:fs";
import { extname } from "node:path";
import { Readable } from "node:stream";

import { libraryFiles } from "@/lib/music-library";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MIME: Record<string, string> = {
  ".mp3": "audio/mpeg",
  ".wav": "audio/wav",
  ".ogg": "audio/ogg",
  ".m4a": "audio/mp4",
  ".aac": "audio/aac",
  ".flac": "audio/flac",
};

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let key = id;
  try {
    key = decodeURIComponent(id);
  } catch {
    // déjà décodé
  }
  const file = (await libraryFiles()).get(key);
  if (!file) return new Response("Not found", { status: 404 });
  const size = file.size;
  const headers: Record<string, string> = {
    "Content-Type": MIME[extname(file.file).toLowerCase()] ?? "application/octet-stream",
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
    return new Response(Readable.toWeb(createReadStream(file.path, { start, end })) as ReadableStream, { status: 206, headers });
  }
  headers["Content-Length"] = String(size);
  return new Response(Readable.toWeb(createReadStream(file.path)) as ReadableStream, { status: 200, headers });
}
