/**
 * GET /api/media/<asset id> : sert un fichier produit par le worker (image de storyboard, clip, vidéo finale,
 * aperçu) depuis le disque du PC, avec les requêtes partielles (Range) que demande la balise <video>.
 *
 * Le chemin n'est jamais pris dans la requête : l'identifiant est cherché dans la table `assets`
 * (`local_path`), comme le fait MJClipIt. Sans identifiant connu : 404.
 */
import { extname } from "node:path";

import { fileResponse } from "@/lib/file-response";
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

  return fileResponse(req, path, {
    "Content-Type": MIME[extname(path).toLowerCase()] ?? "application/octet-stream",
    "Cache-Control": "private, max-age=60",
  });
}
