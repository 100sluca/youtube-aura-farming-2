/**
 * GET /api/montage-preview/<job id>[?image=1] : sert le rendu exact d'un modèle de montage écrit par le worker (job
 * montage_preview, docs/23-montage.md), la vidéo (avec les requêtes partielles que demande <video>) ou son image.
 * Comme /api/voice-preview, le chemin vient de jobs.result et doit désigner un fichier <job>.mp4 / .jpg du dossier
 * DATA_DIR/previews/montage.
 */
import { readFile } from "node:fs/promises";

import { supabaseAdmin } from "@/lib/supabase-admin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return new Response("Not found", { status: 404 });
  const image = new URL(req.url).searchParams.has("image");
  const { data } = await supabaseAdmin().from("jobs").select("status, result").eq("id", id).eq("type", "montage_preview").maybeSingle();
  const result = (data?.result ?? {}) as { path?: string; poster?: string };
  const file = image ? result.poster : result.path;
  const pattern = new RegExp(`[\\\\/]previews[\\\\/]montage[\\\\/]${id}\\.${image ? "jpg" : "mp4"}$`, "i");
  if (data?.status !== "done" || !file || !pattern.test(file)) return new Response("Not found", { status: 404 });
  let body: Buffer;
  try {
    body = await readFile(file);
  } catch {
    return new Response("Fichier absent du disque", { status: 404 });
  }
  const headers: Record<string, string> = {
    "Content-Type": image ? "image/jpeg" : "video/mp4",
    "Accept-Ranges": "bytes",
    "Cache-Control": "private, max-age=3600",
  };
  const size = body.length;
  const match = /^bytes=(\d*)-(\d*)$/.exec(req.headers.get("range") ?? "");
  if (match && size > 0) {
    const start = match[1] ? Number(match[1]) : Math.max(0, size - Number(match[2]));
    const end = match[1] && match[2] ? Math.min(Number(match[2]), size - 1) : size - 1;
    if (start > end || start >= size) return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
    return new Response(new Uint8Array(body.subarray(start, end + 1)), {
      status: 206,
      headers: { ...headers, "Content-Range": `bytes ${start}-${end}/${size}`, "Content-Length": String(end - start + 1) },
    });
  }
  return new Response(new Uint8Array(body), { headers: { ...headers, "Content-Length": String(size) } });
}
