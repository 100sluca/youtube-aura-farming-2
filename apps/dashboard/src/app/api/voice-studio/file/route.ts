/**
 * GET /api/voice-studio/file?f=<essai> : un fichier d'essai du Studio du modificateur (docs/67), dans
 * <données>/voix-studio/essais ; le nom (empreinte du réglage) est vérifié, jamais un chemin.
 */
import { join } from "node:path";

import { fileResponse } from "@/lib/file-response";
import { dataRoot } from "@/lib/files";
import { currentAppUser } from "@/lib/supabase-admin";
import { TRIAL_NAME } from "@/lib/voice-mods";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  if (!(await currentAppUser())) return new Response("Non autorisé", { status: 401 });
  const name = new URL(req.url).searchParams.get("f") ?? "";
  const root = await dataRoot();
  if (!TRIAL_NAME.test(name) || !root) return new Response("Not found", { status: 404 });
  return fileResponse(req, join(root, "voix-studio", "essais", name), {
    "Content-Type": "audio/wav",
    "Cache-Control": "private, max-age=3600",
  });
}
