/**
 * GET /api/music/<id> : sert une musique de la bibliothèque (dossier « music » du dépôt, docs/26-musique.md) pour
 * l'écoute de l'onglet Montage, avec les requêtes partielles (Range) qui permettent de la lire en continu et de partir
 * du « Début » réglé. Le chemin n'est jamais pris dans la requête : l'identifiant (nom du fichier sans extension) est
 * cherché parmi les fichiers du dossier. Sans fichier : 404.
 */
import { extname } from "node:path";

import { fileResponse } from "@/lib/file-response";
import { libraryFiles } from "@/lib/music-library";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MIME: Record<string, string> = {
  ".mp3": "audio/mpeg",
  ".wav": "audio/wav",
  ".ogg": "audio/ogg",
  ".m4a": "audio/mp4",
  ".aac": "audio/aac",
  ".flac": "audio/flac",
};

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let key = id;
  try {
    key = decodeURIComponent(id);
  } catch {
    // déjà décodé
  }
  const file = (await libraryFiles()).get(key);
  if (!file) return new Response("Not found", { status: 404 });
  return fileResponse(req, file.path, {
    "Content-Type": MIME[extname(file.file).toLowerCase()] ?? "application/octet-stream",
    "Cache-Control": "private, max-age=60",
  });
}
