/**
 * Réponse HTTP d'un fichier du disque (vidéo, son, image), avec les requêtes partielles (Range) que demandent
 * <video> et <audio>. Partagée par /api/media, /api/demos, /api/music et /api/paf/video.
 *
 * Le fichier est lu en mémoire puis refermé avant de répondre, jamais servi en flux : Chrome lit une vidéo par une
 * requête « bytes=0- » qu'il cesse de lire dès que sa mémoire tampon est pleine (vidéo en pause), et le flux gardait
 * le fichier ouvert tant que la page restait affichée. Sous Windows, le worker ne pouvait alors plus remplacer
 * final.mp4 (01/10 : remontage d'une retouche en échec, « Accès refusé »). Une plage ouverte est servie par morceaux
 * de CHUNK octets ; le navigateur demande la suite.
 */
import { open, stat } from "node:fs/promises";

const CHUNK = 4 * 1024 * 1024;

export async function fileResponse(req: Request, path: string, headers: Record<string, string>): Promise<Response> {
  let size: number;
  let mtime: number;
  try {
    ({ size, mtimeMs: mtime } = await stat(path));
  } catch {
    return new Response("Fichier absent du disque", { status: 404 });
  }
  // Change quand le worker réécrit le fichier : le navigateur ne mélange pas les morceaux de deux versions.
  const base = { ...headers, "Accept-Ranges": "bytes", ETag: `"${size.toString(36)}-${Math.floor(mtime).toString(36)}"` };

  let start = 0;
  let end = size - 1;
  const match = /^bytes=(\d*)-(\d*)$/.exec(req.headers.get("range") ?? "");
  const partial = Boolean(match && size > 0);
  if (match && partial) {
    start = match[1] ? Number(match[1]) : Math.max(0, size - Number(match[2]));
    end = match[1] && match[2] ? Math.min(Number(match[2]), size - 1) : size - 1;
    if (start > end || start >= size) return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
    end = Math.min(end, start + CHUNK - 1);
  }

  const body = new Uint8Array(Math.max(0, end - start + 1));
  let read = 0;
  try {
    const file = await open(path, "r");
    try {
      while (read < body.length) {
        const { bytesRead } = await file.read(body, read, body.length - read, start + read);
        if (!bytesRead) break; // fichier raccourci entre-temps (le worker le réécrit)
        read += bytesRead;
      }
    } finally {
      await file.close();
    }
  } catch {
    return new Response("Fichier illisible", { status: 404 });
  }

  if (!partial) return new Response(body.subarray(0, read), { headers: { ...base, "Content-Length": String(read) } });
  if (!read) return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
  return new Response(body.subarray(0, read), {
    status: 206,
    headers: { ...base, "Content-Range": `bytes ${start}-${start + read - 1}/${size}`, "Content-Length": String(read) },
  });
}
