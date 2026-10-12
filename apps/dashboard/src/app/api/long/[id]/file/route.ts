/**
 * GET /api/long/<vidéo longue>/file?k=… : un fichier d'une vidéo longue (docs/63), lu sur le disque du PC.
 *   k=shot&i=<plan>   image du plan          k=clip&i=<plan>   clip du plan
 *   k=take&t=<prise>  enregistrement du Studio voix
 *   k=thumb&i=<n>     miniature n            k=preview | final | poster   vidéo montée
 * Le chemin n'est jamais pris dans la requête : il est lu en base (long_shots, long_takes, long_videos.thumbnail,
 * assets), et doit se trouver dans le dossier de la vidéo longue.
 */
import { extname, resolve } from "node:path";

import { fileResponse } from "@/lib/file-response";
import { supabaseAdmin } from "@/lib/supabase-admin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MIME: Record<string, string> = {
  ".mp4": "video/mp4",
  ".webm": "audio/webm",
  ".ogg": "audio/ogg",
  ".m4a": "audio/mp4",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".wav": "audio/wav",
  ".mp3": "audio/mpeg",
};
const UUID = /^[0-9a-f-]{36}$/i;

async function pathFor(id: string, url: URL): Promise<string | null> {
  const db = supabaseAdmin();
  const k = url.searchParams.get("k");
  const i = Number(url.searchParams.get("i"));
  if (k === "shot" || k === "clip") {
    if (!Number.isInteger(i)) return null;
    const { data } = await db.from("long_shots").select("image_path, clip_path").eq("long_id", id).eq("idx", i).maybeSingle();
    return (k === "shot" ? data?.image_path : data?.clip_path) ?? null;
  }
  if (k === "take") {
    const t = url.searchParams.get("t") ?? "";
    if (!UUID.test(t)) return null;
    const { data } = await db.from("long_takes").select("path").eq("long_id", id).eq("id", t).maybeSingle();
    return data?.path ?? null;
  }
  if (k === "thumb") {
    const { data } = await db.from("long_videos").select("thumbnail").eq("id", id).maybeSingle();
    const cands = (data?.thumbnail?.candidates ?? []) as { file?: string }[];
    return Number.isInteger(i) ? (cands[i]?.file ?? null) : null;
  }
  if (k === "preview" || k === "final" || k === "poster") {
    const { data } = await db.from("long_videos").select("video_id").eq("id", id).maybeSingle();
    if (!data?.video_id) return null;
    const col = `${k}_asset_id` as const;
    const { data: v } = await db.from("videos").select(col).eq("id", data.video_id).maybeSingle();
    const assetId = (v as Record<string, string> | null)?.[col];
    if (!assetId) return null;
    const { data: a } = await db.from("assets").select("local_path").eq("id", assetId).maybeSingle();
    return a?.local_path ?? null;
  }
  return null;
}

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!UUID.test(id)) return new Response("Not found", { status: 404 });
  const url = new URL(req.url);
  const path = await pathFor(id, url);
  if (!path) return new Response("Not found", { status: 404 });
  const { data } = await supabaseAdmin().from("long_videos").select("dir").eq("id", id).maybeSingle();
  const dir = data?.dir as string | undefined;
  if (!dir || !resolve(path).toLowerCase().startsWith(resolve(dir).toLowerCase())) return new Response("Not found", { status: 404 });
  return fileResponse(req, path, {
    "Content-Type": MIME[extname(path).toLowerCase()] ?? "application/octet-stream",
    "Cache-Control": "private, max-age=30",
  });
}
