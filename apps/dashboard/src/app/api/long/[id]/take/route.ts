/**
 * POST /api/long/<vidéo longue>/take : une prise du Studio voix (docs/63 §4). Corps FormData : para (clé du paragraphe,
 * « c2p3 »), file (l'enregistrement du navigateur, webm/opus). La prise est rangée dans le dossier de la vidéo
 * (voix/prises/<para>_t<n>.webm), devient la prise gardée du paragraphe, et le worker la vérifie aussitôt (job
 * long_take, voie preview : Whisper dit si tout le texte est lu). Route et non action : les actions sont limitées à
 * 1 Mo, une prise d'une minute en fait environ un.
 */
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { IS_MOCK } from "@/lib/data";
import { PARA_KEY } from "@/lib/long-types";
import { currentAppUser, supabaseAdmin } from "@/lib/supabase-admin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_BYTES = 60 * 1024 * 1024;
const EXT: Record<string, string> = { "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/wav": "wav", "audio/x-wav": "wav" };

function reply(ok: boolean, message: string, status = 200, extra: Record<string, unknown> = {}) {
  return Response.json({ ok, message, ...extra }, { status, headers: { "cache-control": "no-store" } });
}

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  if (IS_MOCK) return reply(false, "Mode démonstration : rien n’est enregistré", 400);
  if (!(await currentAppUser())) return reply(false, "Non autorisé", 401);
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return reply(false, "Vidéo inconnue", 404);
  const form = await req.formData();
  const para = String(form.get("para") ?? "");
  const file = form.get("file");
  if (!PARA_KEY.test(para)) return reply(false, "Paragraphe inconnu", 400);
  if (!(file instanceof Blob) || !file.size) return reply(false, "Enregistrement vide", 400);
  if (file.size > MAX_BYTES) return reply(false, "Enregistrement trop long (60 Mo au plus)", 400);

  const db = supabaseAdmin();
  const { data: lv } = await db.from("long_videos").select("id, dir, stage, script, production_id, channel_id").eq("id", id).maybeSingle();
  if (!lv) return reply(false, "Vidéo inconnue", 404);
  if (!lv.dir) return reply(false, "Dossier de la vidéo absent : le script doit d’abord être écrit", 400);
  const known = ((lv.script?.chapters ?? []) as { paragraphs: { key: string }[] }[]).some((c) => c.paragraphs.some((p) => p.key === para));
  if (!known) return reply(false, "Ce paragraphe n’est plus dans le script", 400);

  const { data: last } = await db.from("long_takes").select("take").eq("long_id", id).eq("para", para).order("take", { ascending: false }).limit(1);
  const take = (last?.[0]?.take ?? 0) + 1;
  const type = (file.type || "audio/webm").split(";")[0];
  const folder = join(lv.dir, "voix", "prises");
  const path = join(folder, `${para}_t${take}.${EXT[type] ?? "webm"}`);
  await mkdir(folder, { recursive: true });
  await writeFile(path, Buffer.from(await file.arrayBuffer()));

  await db.from("long_takes").update({ chosen: false }).eq("long_id", id).eq("para", para);
  const ins = await db
    .from("long_takes")
    .insert({ long_id: id, para, take, path, mime: type, status: "checking", chosen: true })
    .select("id")
    .single();
  if (ins.error) return reply(false, ins.error.message, 500);
  await db.from("jobs").insert({
    type: "long_take",
    production_id: lv.production_id,
    channel_id: lv.channel_id,
    priority: 5,
    max_attempts: 2,
    payload: { long_id: id, take_id: ins.data.id, para },
  });
  return reply(true, `Prise ${take} enregistrée`, 200, { take_id: ins.data.id, take });
}
