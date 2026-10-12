/**
 * Studio du modificateur de voix (docs/67).
 *   POST JSON { take | sample, params } : essai d'un réglage sur l'extrait d'une prise du Studio voix (long_takes.id) ou
 *     d'un extrait enregistré ici ; crée le job long_take (action voice_mod, voie preview, quelques secondes).
 *   POST FormData { file } : un extrait enregistré au micro, rangé dans <données>/voix-studio/extraits.
 *   GET ?job=<id> : où en est l'essai ; une fois fait, les deux fichiers à comparer (original nettoyé, essai).
 * Le chemin de l'extrait n'est jamais pris dans la requête : il est lu en base (prise) ou construit dans le dossier des
 * extraits (nom vérifié).
 */
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { IS_MOCK } from "@/lib/data";
import { dataRoot } from "@/lib/files";
import { currentAppUser, supabaseAdmin } from "@/lib/supabase-admin";
import { SAMPLE_NAME, normalizeParams } from "@/lib/voice-mods";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const UUID = /^[0-9a-f-]{36}$/i;

const EXT: Record<string, string> = { "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/wav": "wav", "audio/x-wav": "wav" };
const MAX_BYTES = 15 * 1024 * 1024;

function reply(ok: boolean, message: string, status = 200, extra: Record<string, unknown> = {}) {
  return Response.json({ ok, message, ...extra }, { status, headers: { "cache-control": "no-store" } });
}

async function samplesDir(): Promise<string | null> {
  const root = await dataRoot();
  return root ? join(root, "voix-studio", "extraits") : null;
}

export async function POST(req: Request) {
  if (IS_MOCK) return reply(false, "Mode démonstration : rien n’est essayé", 400);
  if (!(await currentAppUser())) return reply(false, "Non autorisé", 401);
  const folder = await samplesDir();
  if (!folder) return reply(false, "Dossier de données introuvable", 500);

  if ((req.headers.get("content-type") ?? "").includes("multipart/form-data")) {
    const file = (await req.formData()).get("file");
    if (!(file instanceof Blob) || file.size < 2000) return reply(false, "Enregistrement vide", 400);
    if (file.size > MAX_BYTES) return reply(false, "Extrait trop long", 400);
    const name = `extrait_${Date.now()}.${EXT[(file.type || "audio/webm").split(";")[0]] ?? "webm"}`;
    await mkdir(folder, { recursive: true });
    await writeFile(join(folder, name), Buffer.from(await file.arrayBuffer()));
    return reply(true, "Extrait enregistré", 200, { sample: name });
  }

  const body = (await req.json().catch(() => null)) as { take?: string; sample?: string; params?: unknown } | null;
  if (!body) return reply(false, "Requête illisible", 400);
  let source: string | null = null;
  if (body.take && UUID.test(body.take)) {
    const { data } = await supabaseAdmin().from("long_takes").select("path").eq("id", body.take).maybeSingle();
    source = (data?.path as string | undefined) ?? null;
  } else if (body.sample && SAMPLE_NAME.test(body.sample)) {
    source = join(folder, body.sample);
  }
  if (!source) return reply(false, "Extrait introuvable", 404);
  const { data: job, error } = await supabaseAdmin()
    .from("jobs")
    .insert({ type: "long_take", priority: 3, max_attempts: 1, payload: { action: "voice_mod", source, params: normalizeParams(body.params) } })
    .select("id")
    .single();
  if (error) return reply(false, error.message, 500);
  return reply(true, "Essai lancé", 200, { job: job.id });
}

export async function GET(req: Request) {
  if (!(await currentAppUser())) return reply(false, "Non autorisé", 401);
  const id = new URL(req.url).searchParams.get("job") ?? "";
  if (!UUID.test(id)) return reply(false, "Essai inconnu", 404);
  const { data } = await supabaseAdmin().from("jobs").select("status, result, error, created_at").eq("id", id).eq("type", "long_take").maybeSingle();
  if (!data) return reply(false, "Essai inconnu", 404);
  return reply(true, String(data.status), 200, { status: data.status, result: data.result, error: data.error, created_at: data.created_at });
}
