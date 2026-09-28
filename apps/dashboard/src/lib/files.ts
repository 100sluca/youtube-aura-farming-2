/**
 * Fichiers produits par le worker sur le PC (DATA_DIR du worker) : taille occupée et effacement, pour la
 * Bibliothèque et le gestionnaire de tâches. Serveur uniquement.
 *
 * Le dossier de données n'est pas configuré côté dashboard : on le retrouve à partir des chemins enregistrés dans
 * `assets.local_path` (…/videos/<id vidéo>/final.mp4, …/productions/<id production>/clips/scene_01.mp4). On
 * n'efface jamais qu'un dossier dont le nom est exactement l'identifiant attendu, sous un dossier « videos » ou
 * « productions » : un chemin inattendu en base ne peut pas faire effacer autre chose.
 */
import { readdir, rm, stat } from "node:fs/promises";
import { basename, dirname, join } from "node:path";

import { supabaseAdmin } from "@/lib/supabase-admin";

export interface OwnedDirs {
  video: string | null; // <DATA_DIR>/videos/<id vidéo>
  production: string | null; // <DATA_DIR>/productions/<id production>
}

/** Remonte un chemin jusqu'au dossier nommé `id` placé sous `parentName` (videos | productions). */
function ownedAncestor(path: string, id: string, parentName: "videos" | "productions"): string | null {
  let dir = dirname(path);
  for (let depth = 0; depth < 4; depth++) {
    if (basename(dir) === id && basename(dirname(dir)) === parentName) return dir;
    const up = dirname(dir);
    if (up === dir) break;
    dir = up;
  }
  return null;
}

/** Racine des données (le dossier qui contient « videos » et « productions »), déduite d'un chemin connu. */
export function dataRootOf(path: string): string | null {
  let dir = dirname(path);
  for (let depth = 0; depth < 5; depth++) {
    const name = basename(dir);
    if (name === "videos" || name === "productions") return dirname(dir);
    const up = dirname(dir);
    if (up === dir) break;
    dir = up;
  }
  return null;
}

/** Dossier de données du worker (celui qui contient « videos » et « productions »), d'après un asset en base. */
export async function dataRoot(): Promise<string | null> {
  const { data } = await supabaseAdmin()
    .from("assets")
    .select("local_path")
    .not("local_path", "is", null)
    .in("kind", ["final", "preview", "poster", "storyboard", "clip", "narration"])
    .order("created_at", { ascending: false })
    .limit(5);
  for (const r of data ?? []) {
    const root = dataRootOf(r.local_path as string);
    if (root) return root;
  }
  return null;
}

/** Taille des dossiers d'une vidéo produite (vidéo + production), à partir du dossier de données. */
export async function videoFootprint(root: string | null, videoId: string, productionId: string | null): Promise<number> {
  if (!root) return 0;
  const [v, p] = await Promise.all([
    dirSize(join(root, "videos", videoId)),
    productionId ? dirSize(join(root, "productions", productionId)) : Promise.resolve(0),
  ]);
  return v + p;
}

/** Dossiers d'une vidéo et/ou de sa production, d'après les chemins des assets en base (ou ceux fournis). */
export async function ownedDirs(
  { videoId, productionId }: { videoId: string | null; productionId: string | null },
  paths?: string[],
): Promise<OwnedDirs> {
  let known = paths;
  if (!known) {
    const filter = [videoId ? `video_id.eq.${videoId}` : null, productionId ? `production_id.eq.${productionId}` : null].filter(Boolean).join(",");
    if (!filter) return { video: null, production: null };
    const { data } = await supabaseAdmin().from("assets").select("local_path").or(filter).not("local_path", "is", null).limit(300);
    known = (data ?? []).map((r) => r.local_path as string);
  }
  let video: string | null = null;
  let production: string | null = null;
  let root: string | null = null;
  for (const p of known) {
    if (videoId) video ??= ownedAncestor(p, videoId, "videos");
    if (productionId) production ??= ownedAncestor(p, productionId, "productions");
    root ??= dataRootOf(p);
  }
  // Dossiers que le worker crée toujours au même endroit, même sans asset enregistré
  if (root) {
    if (videoId) video ??= join(root, "videos", videoId);
    if (productionId) production ??= join(root, "productions", productionId);
  }
  return { video, production };
}

/** Taille d'un dossier (récursive) en octets ; 0 s'il n'existe pas. */
export async function dirSize(dir: string | null): Promise<number> {
  if (!dir) return 0;
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return 0;
  }
  const sizes = await Promise.all(
    entries.map(async (e) => {
      const p = join(dir, e.name);
      if (e.isDirectory()) return dirSize(p);
      try {
        return (await stat(p)).size;
      } catch {
        return 0; // fichier disparu entre-temps
      }
    }),
  );
  return sizes.reduce((a, b) => a + b, 0);
}

/** Efface un dossier possédé (nom = identifiant attendu, sous videos/ ou productions/). Renvoie les octets libérés. */
export async function removeOwnedDir(dir: string | null, id: string): Promise<number> {
  if (!dir || basename(dir) !== id || !["videos", "productions"].includes(basename(dirname(dir)))) return 0;
  const size = await dirSize(dir);
  await rm(dir, { recursive: true, force: true });
  return size;
}
