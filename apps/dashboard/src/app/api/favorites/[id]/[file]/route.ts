/**
 * GET /api/favorites/<id favori>/<fichier> : sert une image gardée d'un storyboard favori (copie dans
 * DATA_DIR/favorites/<id>/, docs/19). Le chemin n'est jamais pris dans la requête : le nom de fichier doit être celui
 * d'une image enregistrée pour ce favori (favorites.images), sinon 404. Une nouvelle copie porte un nouveau nom, d'où
 * un cache long.
 */
import { readFile } from "node:fs/promises";
import { extname } from "node:path";

import { favoriteImagePath } from "@/lib/favorites";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MIME: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
};

export async function GET(_req: Request, { params }: { params: Promise<{ id: string; file: string }> }) {
  const { id, file } = await params;
  // Noms écrits par lib/favorites.ts : scene_01_<asset>.png, rien à décoder
  if (!/^[0-9a-f-]{36}$/i.test(id) || !/^[\w.-]+$/.test(file)) return new Response("Not found", { status: 404 });
  const path = await favoriteImagePath(id, file);
  if (!path) return new Response("Not found", { status: 404 });
  let body: Buffer;
  try {
    body = await readFile(path);
  } catch {
    return new Response("Fichier absent du disque", { status: 404 });
  }
  return new Response(new Uint8Array(body), {
    headers: {
      "Content-Type": MIME[extname(path).toLowerCase()] ?? "application/octet-stream",
      "Content-Length": String(body.length),
      "Cache-Control": "private, max-age=86400",
    },
  });
}
