/**
 * POST /api/fonts (formulaire, champ « file ») : ajoute une police .ttf ou .otf pour le montage, dans DATA_DIR/fonts
 * (hors de Documents : l'accès contrôlé aux dossiers de Windows n'y bloque pas l'écriture). Le worker la trouve au
 * montage suivant (worker/montage.py : font_registry). Une route plutôt qu'une action serveur : les actions sont
 * limitées à 1 Mo, une police peut peser plus.
 */
import { promises as fs } from "node:fs";
import path from "node:path";

import { revalidatePath } from "next/cache";

import { IS_MOCK } from "@/lib/data";
import { FONT_EXT, MAX_FONT_BYTES, parseFont, userFontsDir } from "@/lib/font-files";
import { currentAppUser } from "@/lib/supabase-admin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const reply = (ok: boolean, message: string, status = ok ? 200 : 400, extra: Record<string, unknown> = {}) =>
  Response.json({ ok, message, ...extra }, { status });

export async function POST(req: Request) {
  if (IS_MOCK) return reply(false, "Indisponible en mode démo");
  if (!(await currentAppUser())) return reply(false, "Non autorisé", 401);
  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return reply(false, "Envoi illisible");
  }
  const file = form.get("file");
  if (!(file instanceof File)) return reply(false, "Aucun fichier");
  if (!FONT_EXT.test(file.name)) return reply(false, "Police .ttf ou .otf attendue");
  if (file.size > MAX_FONT_BYTES) return reply(false, "Fichier trop lourd (15 Mo au plus)");
  const buf = Buffer.from(await file.arrayBuffer());
  const parsed = parseFont(buf);
  if (!parsed) return reply(false, "Ce fichier n’est pas une police lisible");

  const dir = await userFontsDir();
  await fs.mkdir(dir, { recursive: true });
  const ext = path.extname(file.name).toLowerCase();
  const base = path.basename(file.name, path.extname(file.name)).replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "police";
  let name = `${base}${ext}`;
  for (let i = 2; await exists(path.join(dir, name)); i++) name = `${base}-${i}${ext}`;
  await fs.writeFile(path.join(dir, name), buf);
  revalidatePath("/montage");
  return reply(true, `« ${parsed.fullName} » ajoutée`, 200, { id: `user~${name}`, family: parsed.family });
}

async function exists(p: string): Promise<boolean> {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}
