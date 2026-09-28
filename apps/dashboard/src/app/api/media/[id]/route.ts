/**
 * GET /api/media/<asset id> : sert un fichier produit par le worker (image de storyboard, clip, vidéo finale,
 * aperçu) depuis le disque du PC, avec les requêtes partielles (Range) que demande la balise <video>.
 *
 * Le chemin n'est jamais pris dans la requête : l'identifiant est cherché dans la table `assets`
 * (`local_path`), comme le fait MJClipIt. Sans identifiant connu : 404.
 */
import { createReadStream, statSync } from "node:fs";
import { extname } from "node:path";
import { Readable } from "node:stream";

import { supabaseAdmin } from "@/lib/supabase-admin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MIME: Record<string, string> = {
  ".mp4": "video/mp4",
  ".webm": "video/webm",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".wav": "audio/wav",
  ".mp3": "audio/mpeg",
};

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return new Response("Not found", { status: 404 });
  const { data } = await supabaseAdmin().from("assets").select("local_path").eq("id", id).maybeSingle();
  const path = data?.local_path as string | undefined;
  if (!path) return new Response("Not found", { status: 404 });

  let size: number;
  try {
    size = statSync(path).size;
  } catch {
    return new Response("Fichier absent du disque", { status: 404 });
  }
  const type = MIME[extname(path).toLowerCase()] ?? "application/octet-stream";
  const headers: Record<string, string> = {
    "Content-Type": type,
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
    const stream = Readable.toWeb(createReadStream(path, { start, end })) as ReadableStream;
    return new Response(stream, { status: 206, headers });
  }
  headers["Content-Length"] = String(size);
  const stream = Readable.toWeb(createReadStream(path)) as ReadableStream;
  return new Response(stream, { status: 200, headers });
}
