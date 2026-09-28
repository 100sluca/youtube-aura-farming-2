/**
 * GET /api/voice-preview/<job id> : sert l'essai de voix écrit par le worker (job voice_preview, docs/18-voix.md).
 *
 * Comme /api/media, le chemin n'est jamais pris dans la requête : il vient de jobs.result.path, et doit désigner un
 * .wav du dossier DATA_DIR/previews/voices du worker.
 */
import { readFile } from "node:fs/promises";

import { supabaseAdmin } from "@/lib/supabase-admin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return new Response("Not found", { status: 404 });
  const { data } = await supabaseAdmin().from("jobs").select("status, result").eq("id", id).eq("type", "voice_preview").maybeSingle();
  const path = (data?.result as { path?: string } | null)?.path;
  if (data?.status !== "done" || !path || !/[\\/]previews[\\/]voices[\\/][0-9a-f-]{36}\.wav$/i.test(path)) {
    return new Response("Not found", { status: 404 });
  }
  try {
    const body = await readFile(path);
    return new Response(body, {
      headers: { "Content-Type": "audio/wav", "Content-Length": String(body.length), "Cache-Control": "private, max-age=3600" },
    });
  } catch {
    return new Response("Fichier absent du disque", { status: 404 });
  }
}
