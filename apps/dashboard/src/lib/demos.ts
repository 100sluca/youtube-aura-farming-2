/**
 * Démos et essais faits hors de l'appli (docs/28-bibliotheque-complete.md) : vidéos rangées par des scripts dans
 * <racine>\demo (démos des formats du 25/09, faites avant que tout passe par l'appli) et <racine>\bench (bancs
 * d'essai : comparaisons de modèles, agrandissement…), à côté du dossier de données du worker (C:\YouTube2\data →
 * C:\YouTube2\demo et C:\YouTube2\bench). Rien en base : on lit le disque. Serveur uniquement.
 *
 * Une démo = un sous-dossier direct de demo\ ou bench\ qui contient au moins une vidéo. Titre et description : fichier
 * demo.json du dossier ({ "title", "description", "youtube": id de la vidéo si elle a été mise en ligne à la main }),
 * sinon premier titre de son README.md, sinon le nom du dossier.
 * On ne sert et n'efface jamais qu'un chemin situé sous une de ces deux racines.
 */
import { readdir, readFile, rm, stat } from "node:fs/promises";
import { dirname, extname, join, resolve, sep } from "node:path";

import type { DemoFolder, DemoKind, DemoVideo } from "@/lib/demo-types";
import { dataRoot, dirSize } from "@/lib/files";

const KINDS: DemoKind[] = ["demo", "bench"];

/** Vidéos lisibles par le navigateur, avec leur type. */
export const DEMO_VIDEO_MIME: Record<string, string> = { ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime" };

/** Vidéo finie d'un dossier (montage complet, comparaison côte à côte) plutôt qu'un clip intermédiaire. */
const MAIN = /^(final|comparaison)|_vs_/i;
const MAX_DEPTH = 4;

const isKind = (value: string): value is DemoKind => (KINDS as string[]).includes(value);

/** Dossier d'un type de démo (C:\YouTube2\demo, C:\YouTube2\bench), à côté du dossier de données du worker. */
async function kindRoot(kind: DemoKind): Promise<string | null> {
  const data = await dataRoot();
  return data ? join(dirname(data), kind) : null;
}

type Found = { path: string; size: number; mtime: number };

/** Vidéos d'un dossier et de ses sous-dossiers, chemins relatifs avec des « / ». */
async function videosIn(dir: string, prefix = "", depth = 0): Promise<Found[]> {
  if (depth > MAX_DEPTH) return [];
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  const found = await Promise.all(
    entries.map(async (e): Promise<Found[]> => {
      const rel = prefix ? `${prefix}/${e.name}` : e.name;
      if (e.isDirectory()) return videosIn(join(dir, e.name), rel, depth + 1);
      if (!e.isFile() || !DEMO_VIDEO_MIME[extname(e.name).toLowerCase()]) return [];
      try {
        const s = await stat(join(dir, e.name));
        return [{ path: rel, size: s.size, mtime: s.mtimeMs }];
      } catch {
        return []; // fichier disparu entre-temps
      }
    }),
  );
  return found.flat();
}

/** « 2026-09-28-agrandissement » → « Agrandissement », « refuge_v2 » → « Refuge v2 ». */
function prettify(folder: string): string {
  const name = folder.replace(/^\d{4}-\d{2}-\d{2}(-\d{4})?[-_]?/, "").replace(/[_-]+/g, " ").trim() || folder;
  return name.charAt(0).toUpperCase() + name.slice(1);
}

type Description = Pick<DemoFolder, "title" | "description" | "youtube_video_id">;

async function describe(dir: string, folder: string): Promise<Description> {
  try {
    const meta = JSON.parse((await readFile(join(dir, "demo.json"), "utf8")).replace(/^\uFEFF/, ""));
    if (typeof meta?.title === "string" && meta.title.trim()) {
      return {
        title: meta.title.trim(),
        description: typeof meta.description === "string" && meta.description.trim() ? meta.description.trim() : null,
        youtube_video_id: typeof meta.youtube === "string" && /^[\w-]{11}$/.test(meta.youtube) ? meta.youtube : null,
      };
    }
  } catch {
    // pas de demo.json (ou illisible) : README, puis nom du dossier
  }
  try {
    const heading = /^#\s+(.+)$/m.exec(await readFile(join(dir, "README.md"), "utf8"))?.[1]?.trim();
    if (heading) return { title: heading, description: null, youtube_video_id: null };
  } catch {
    // pas de README
  }
  return { title: prettify(folder), description: null, youtube_video_id: null };
}

async function readFolder(kind: DemoKind, root: string, folder: string): Promise<DemoFolder | null> {
  const dir = join(root, folder);
  const found = await videosIn(dir);
  if (found.length === 0) return null;
  const isMain = (v: Found) => MAIN.test(v.path.split("/").pop() ?? "");
  const byPath = (a: Found, b: Found) => a.path.localeCompare(b.path, "fr", { numeric: true });
  // Vidéos finies : la plus récente d'abord (la dernière version) ; clips : dans l'ordre des noms
  const mains = found.filter(isMain).sort((a, b) => b.mtime - a.mtime || byPath(a, b));
  const ordered = mains.length ? [...mains, ...found.filter((v) => !isMain(v)).sort(byPath)] : [...found].sort(byPath);
  const [about, size] = await Promise.all([describe(dir, folder), dirSize(dir)]);
  const videos: DemoVideo[] = ordered.map((v) => ({
    path: v.path,
    url: `/api/demos/${kind}/${[folder, ...v.path.split("/")].map(encodeURIComponent).join("/")}`,
    size_bytes: v.size,
    modified_at: new Date(v.mtime).toISOString(),
  }));
  return {
    id: `${kind}/${folder}`,
    kind,
    ...about,
    location: dir,
    // Date de la dernière vidéo finie (les clips d'essai refaits après ne la changent pas)
    modified_at: new Date(Math.max(...(mains.length ? mains : found).map((v) => v.mtime))).toISOString(),
    size_bytes: size,
    videos,
    main_count: mains.length || found.length,
  };
}

/** Tous les dossiers de démos et d'essais qui contiennent une vidéo, le plus récent d'abord. */
export async function listDemos(): Promise<DemoFolder[]> {
  const data = await dataRoot();
  if (!data) return [];
  const perKind = await Promise.all(
    KINDS.map(async (kind) => {
      const root = join(dirname(data), kind);
      let entries;
      try {
        entries = await readdir(root, { withFileTypes: true });
      } catch {
        return []; // pas encore de dossier demo ou bench
      }
      return Promise.all(entries.filter((e) => e.isDirectory()).map((e) => readFolder(kind, root, e.name)));
    }),
  );
  return perKind
    .flat()
    .filter((f): f is DemoFolder => f !== null)
    .sort((a, b) => b.modified_at.localeCompare(a.modified_at));
}

const safeSegment = (s: string) => Boolean(s) && s !== "." && s !== ".." && !/[\\/:]/.test(s);

/** Fichier vidéo demandé par /api/demos/<type>/<dossier>/<chemin> ; null s'il sort des racines ou n'est pas une vidéo. */
export async function demoFilePath(kind: string, segments: string[]): Promise<string | null> {
  if (!isKind(kind) || segments.length < 2 || !segments.every(safeSegment)) return null;
  if (!DEMO_VIDEO_MIME[extname(segments[segments.length - 1]).toLowerCase()]) return null;
  const root = await kindRoot(kind);
  if (!root) return null;
  const path = resolve(root, ...segments);
  return path.startsWith(resolve(root) + sep) ? path : null;
}

/** Efface tout le dossier d'une démo (id « demo/refuge_v2 ») ; renvoie les octets libérés. */
export async function removeDemo(id: string): Promise<number> {
  const [kind, folder, ...rest] = id.split("/");
  if (rest.length > 0 || !isKind(kind) || !safeSegment(folder ?? "")) throw new Error("Démo introuvable");
  const root = await kindRoot(kind);
  if (!root) throw new Error("Dossier des démos introuvable");
  const dir = resolve(root, folder);
  if (dirname(dir) !== resolve(root)) throw new Error("Démo introuvable");
  const info = await stat(dir).catch(() => null);
  if (!info?.isDirectory()) throw new Error("Démo déjà supprimée");
  const size = await dirSize(dir);
  await rm(dir, { recursive: true, force: true });
  return size;
}
