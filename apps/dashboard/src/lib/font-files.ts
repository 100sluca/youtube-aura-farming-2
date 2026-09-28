/**
 * Polices du montage (onglet Montage, docs/23-montage.md), lues comme le fait le worker (worker/subtitles.py : read_face)
 * dans les mêmes dossiers, dans le même ordre (worker/montage.py : font_registry) :
 *   - app  : services/worker/assets/fonts (livrées avec l'appli) ;
 *   - user : DATA_DIR/fonts (ajoutées depuis l'onglet) ;
 *   - win  : une sélection de polices de Windows (liste « windows_fonts » de services/worker/assets/montage/defaults.json).
 * Serveur uniquement.
 */
import { promises as fs } from "node:fs";
import path from "node:path";

import { dataRoot } from "@/lib/files";
import type { FontFaceInfo } from "@/lib/montage-types";
import { faceIsBold } from "@/lib/montage-text";

const WORKER_DIR = path.join(process.cwd(), "..", "..", "services", "worker");
export const APP_FONTS_DIR = path.join(WORKER_DIR, "assets", "fonts");
export const DEFAULTS_FILE = path.join(WORKER_DIR, "assets", "montage", "defaults.json");
const WINDOWS_FONTS_DIR = path.join(process.env.WINDIR ?? "C:\\Windows", "Fonts");
const YT2_HOME = process.env.YT2_HOME ?? "C:/YouTube2";
export const FONT_EXT = /\.(ttf|otf)$/i;
export const MAX_FONT_BYTES = 15 * 1024 * 1024;

export interface MontageDefaults {
  template: unknown;
  subtitle_presets: Record<string, unknown>;
  windows_fonts: string[];
  audio: Record<string, unknown>; // constantes du mixage et ambiances des musiques (worker/music.py)
}

export async function readDefaults(): Promise<MontageDefaults> {
  const raw = JSON.parse(await fs.readFile(DEFAULTS_FILE, "utf8")) as Partial<MontageDefaults>;
  return {
    template: raw.template ?? {},
    subtitle_presets: raw.subtitle_presets ?? {},
    windows_fonts: raw.windows_fonts ?? [],
    audio: raw.audio ?? {},
  };
}

/** Dossier des polices ajoutées depuis l'onglet (DATA_DIR/fonts du worker, hors de Documents). */
export async function userFontsDir(): Promise<string> {
  const root = process.env.YT2_DATA_DIR ?? (await dataRoot()) ?? path.join(YT2_HOME, "data");
  return path.join(root, "fonts");
}

type ParsedFont = Omit<FontFaceInfo, "id" | "source" | "file" | "url" | "isBold">;

/** Noms, graisse, italique et métriques d'un fichier TrueType/OpenType ; null s'il est illisible (ou sans nom). */
export function parseFont(buf: Buffer): ParsedFont | null {
  try {
    const numTables = buf.readUInt16BE(4);
    const tables = new Map<string, number>();
    for (let i = 0; i < numTables; i++) {
      const rec = 12 + 16 * i;
      tables.set(buf.toString("latin1", rec, rec + 4), buf.readUInt32BE(rec + 8));
    }
    const names = readNames(buf, tables.get("name"));
    if (!names[1]) return null;
    let unitsPerEm = 1000;
    let weight = 400;
    let italic = false;
    let winAscent = 0;
    let winDescent = 0;
    let hheaAscent = 0;
    let hheaDescent = 0;
    const head = tables.get("head");
    if (head !== undefined) unitsPerEm = buf.readUInt16BE(head + 18) || 1000;
    const hhea = tables.get("hhea");
    if (hhea !== undefined) {
      hheaAscent = buf.readInt16BE(hhea + 4);
      hheaDescent = -buf.readInt16BE(hhea + 6);
    }
    const os2 = tables.get("OS/2");
    if (os2 !== undefined) {
      weight = buf.readUInt16BE(os2 + 4) || 400;
      italic = (buf.readUInt16BE(os2 + 62) & 1) === 1;
      winAscent = buf.readUInt16BE(os2 + 74);
      winDescent = buf.readUInt16BE(os2 + 76);
    }
    if (!winAscent) {
      winAscent = hheaAscent;
      winDescent = hheaDescent;
    }
    const subfamily = names[17] || names[2] || "Regular";
    return {
      family: names[1],
      typographicFamily: names[16] || names[1],
      fullName: names[4] || `${names[1]} ${subfamily}`,
      subfamily,
      weight,
      italic: italic || /italic|oblique/i.test(subfamily),
      unitsPerEm,
      hheaAscent,
      hheaDescent,
      winAscent,
      winDescent,
    };
  } catch {
    return null;
  }
}

/** Table « name » : IDs 1, 2, 4, 16, 17, en anglais US de préférence (comme read_font_names du worker). */
function readNames(buf: Buffer, offset: number | undefined): Record<number, string> {
  const out: Record<number, string> = {};
  if (offset === undefined) return out;
  const count = buf.readUInt16BE(offset + 2);
  const strOff = offset + buf.readUInt16BE(offset + 4);
  for (let j = 0; j < count; j++) {
    const rec = offset + 6 + 12 * j;
    const [pid, eid, lid, nid, length, noff] = [0, 2, 4, 6, 8, 10].map((k) => buf.readUInt16BE(rec + k));
    if (![1, 2, 4, 16, 17].includes(nid)) continue;
    const raw = buf.subarray(strOff + noff, strOff + noff + length);
    if (pid === 3 && [0, 1, 10].includes(eid)) {
      if (!(nid in out) || lid === 0x409) out[nid] = utf16be(raw);
    } else if (pid === 1 && !(nid in out)) {
      out[nid] = raw.toString("latin1");
    }
  }
  return out;
}

function utf16be(raw: Buffer): string {
  const swapped = Buffer.alloc(raw.length - (raw.length % 2));
  for (let i = 0; i + 1 < raw.length; i += 2) {
    swapped[i] = raw[i + 1];
    swapped[i + 1] = raw[i];
  }
  return swapped.toString("utf16le");
}

async function listDir(dir: string): Promise<string[]> {
  try {
    return (await fs.readdir(dir)).filter((f) => FONT_EXT.test(f)).sort();
  } catch {
    return [];
  }
}

/** Fichier d'une police d'après son identifiant (« source~fichier ») ; null si l'identifiant n'est pas acceptable. */
export async function fontPath(id: string): Promise<{ source: FontFaceInfo["source"]; file: string; path: string } | null> {
  const m = /^(app|user|win)~([^\\/]+)$/.exec(id);
  if (!m || !FONT_EXT.test(m[2]) || m[2].includes("..")) return null;
  const [, source, file] = m as unknown as [string, FontFaceInfo["source"], string];
  if (source === "app") return { source, file, path: path.join(APP_FONTS_DIR, file) };
  if (source === "user") return { source, file, path: path.join(await userFontsDir(), file) };
  const { windows_fonts } = await readDefaults();
  if (!windows_fonts.some((n) => n.toLowerCase() === file.toLowerCase())) return null;
  return { source, file, path: path.join(WINDOWS_FONTS_DIR, file) };
}

/** Toutes les polices, dans l'ordre du worker : livrées, ajoutées, Windows. */
export async function listFonts(): Promise<FontFaceInfo[]> {
  const { windows_fonts } = await readDefaults();
  const userDir = await userFontsDir();
  const entries: { source: FontFaceInfo["source"]; file: string; path: string }[] = [
    ...(await listDir(APP_FONTS_DIR)).map((file) => ({ source: "app" as const, file, path: path.join(APP_FONTS_DIR, file) })),
    ...(await listDir(userDir)).map((file) => ({ source: "user" as const, file, path: path.join(userDir, file) })),
    ...windows_fonts.map((file) => ({ source: "win" as const, file, path: path.join(WINDOWS_FONTS_DIR, file) })),
  ];
  const faces = await Promise.all(
    entries.map(async (e) => {
      try {
        const parsed = parseFont(await fs.readFile(e.path));
        if (!parsed) return null;
        const id = `${e.source}~${e.file}`;
        return { ...parsed, id, source: e.source, file: e.file, url: `/api/fonts/${encodeURIComponent(id)}`, isBold: faceIsBold(parsed) };
      } catch {
        return null; // police de Windows absente de ce PC
      }
    }),
  );
  return faces.filter((f): f is FontFaceInfo => f !== null);
}
