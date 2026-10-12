/**
 * GET /api/long/<vidéo longue>/state : ce que relit le Studio voix pendant l'enregistrement (prises et leur
 * vérification par Whisper, tâches en cours). Route GET et non action (docs/56 : les actions passent une par une).
 */
import { getLongTakes, longJobs } from "@/lib/long";
import { supabaseAdmin } from "@/lib/supabase-admin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return new Response("Not found", { status: 404 });
  const [{ data: lv }, takes, jobs] = await Promise.all([
    supabaseAdmin().from("long_videos").select("stage, voice_done_at, error").eq("id", id).maybeSingle(),
    getLongTakes(id),
    longJobs(id),
  ]);
  if (!lv) return new Response("Not found", { status: 404 });
  return Response.json({ stage: lv.stage, voice_done_at: lv.voice_done_at, error: lv.error, takes, jobs }, { headers: { "cache-control": "no-store" } });
}
