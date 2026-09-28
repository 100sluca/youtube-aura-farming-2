/**
 * GET /api/fonts/<source~fichier> : sert une police du montage à l'aperçu de l'onglet Montage (@font-face).
 * Le chemin n'est jamais pris tel quel : source connue (app, user, win), nom de fichier sans dossier, et pour Windows
 * seulement les polices de la liste de services/worker/assets/montage/defaults.json (lib/font-files.ts).
 */
import { readFile } from "node:fs/promises";

import { fontPath } from "@/lib/font-files";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const target = await fontPath(decodeURIComponent(id));
  if (!target) return new Response("Not found", { status: 404 });
  try {
    const body = await readFile(target.path);
    return new Response(body, {
      headers: {
        "Content-Type": target.file.toLowerCase().endsWith(".otf") ? "font/otf" : "font/ttf",
        "Content-Length": String(body.length),
        "Cache-Control": "private, max-age=86400",
      },
    });
  } catch {
    return new Response("Police absente du disque", { status: 404 });
  }
}
