/**
 * Musiques de fond côté dashboard (docs/26-musique.md) : la bibliothèque de Luca (dossier « music » du dépôt, table
 * music_tracks), tenue à jour comme le fait le worker (worker/music.py : sync_library) — nouveau fichier ajouté (à
 * décrire), fichier retiré marqué absent, sonie mesurée par FFmpeg (EBU R128) —, et les vidéos d'essai de l'onglet Son
 * (dernières vidéos montées, leur voix, la musique que le montage leur donnerait). Serveur uniquement.
 */
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";

import { readDefaults } from "@/lib/font-files";
import type { AudioConstants, MontageFormat, MusicLibrary, MusicTrack, TestVideo } from "@/lib/montage-types";
import { MONTAGE_FORMATS } from "@/lib/montage-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

export const MUSIC_DIR = process.env.MUSIC_LIBRARY_DIR ?? path.join(process.cwd(), "..", "..", "music");
const AUDIO_EXT = /\.(mp3|wav|ogg|m4a|flac|aac)$/i;
const MEASURE_PER_LOAD = 8; // nouvelles pistes mesurées à l'ouverture de la page (≈ 1 s chacune) ; le reste au prochain passage

export interface LibraryFile {
  file: string;
  path: string;
  size: number;
  mtimeMs: number;
}

/** Fichiers audio du dossier par identifiant (nom sans extension) ; un nom en double garde le premier, comme le worker. */
export async function libraryFiles(): Promise<Map<string, LibraryFile>> {
  const out = new Map<string, LibraryFile>();
  let names: string[];
  try {
    names = await fs.readdir(MUSIC_DIR);
  } catch {
    return out;
  }
  names.sort((a, b) => (a.toLowerCase() < b.toLowerCase() ? -1 : a.toLowerCase() > b.toLowerCase() ? 1 : 0));
  for (const name of names) {
    if (!AUDIO_EXT.test(name)) continue;
    const id = path.parse(name).name.trim().slice(0, 120);
    if (!id || out.has(id)) continue;
    const full = path.join(MUSIC_DIR, name);
    const st = await fs.stat(full).catch(() => null);
    if (st?.isFile()) out.set(id, { file: name, path: full, size: st.size, mtimeMs: st.mtimeMs });
  }
  return out;
}

export interface Loudness {
  lufs: number | null;
  peakDb: number | null;
  durationS: number | null;
}

/** Résumé du filtre ebur128 de FFmpeg (même lecture que worker/media.py : parse_ebur128). */
export function parseEbur128(stderr: string): Loudness {
  const summary = stderr.includes("Summary:") ? stderr.slice(stderr.lastIndexOf("Summary:")) : "";
  const i = /I:\s+(-?\d+(?:\.\d+)?) LUFS/.exec(summary);
  const peak = /Peak:\s+(-?\d+(?:\.\d+)?|-inf) dBFS/.exec(summary);
  const dur = /Duration: (\d+):(\d+):(\d+(?:\.\d+)?)/.exec(stderr);
  const lufs = i ? Number(i[1]) : null;
  return {
    lufs: lufs !== null && lufs > -60 ? lufs : null,
    peakDb: peak && peak[1] !== "-inf" ? Number(peak[1]) : null,
    durationS: dur ? Math.round((Number(dur[1]) * 3600 + Number(dur[2]) * 60 + Number(dur[3])) * 1000) / 1000 : null,
  };
}

/** Sonie intégrée, crête et durée d'un fichier audio (FFmpeg, une lecture). null si FFmpeg est introuvable. */
export function measureLoudness(file: string): Promise<Loudness | null> {
  return new Promise((resolve) => {
    execFile(
      "ffmpeg",
      ["-hide_banner", "-nostats", "-i", file, "-af", "ebur128=framelog=quiet:peak=true", "-f", "null", "-"],
      { timeout: 180_000, maxBuffer: 32 * 1024 * 1024, windowsHide: true },
      (error, _stdout, stderr) => resolve(error && !stderr ? null : parseEbur128(String(stderr))),
    );
  });
}

type Row = {
  id: string;
  file: string;
  title: string;
  description: string;
  moods: string[] | null;
  formats: string[] | null;
  weight: number;
  enabled: boolean;
  gain_db: number;
  start_s: number;
  note: string;
  lufs: number | null;
  duration_s: number | null;
  file_size: number | null;
  file_mtime: string | null;
  missing: boolean;
};

/** Le fichier mesuré est-il toujours le même (nom, taille, date à la seconde près) ? */
function sameFile(row: Row, f: LibraryFile): boolean {
  return (
    row.file === f.file &&
    Number(row.file_size) === f.size &&
    row.file_mtime !== null &&
    Math.abs(Date.parse(row.file_mtime) - f.mtimeMs) < 1000
  );
}

async function measureInto(id: string, f: LibraryFile): Promise<void> {
  const loud = await measureLoudness(f.path);
  if (!loud) return;
  await supabaseAdmin()
    .from("music_tracks")
    .update({
      file: f.file,
      lufs: loud.lufs,
      peak_db: loud.peakDb,
      duration_s: loud.durationS,
      file_size: f.size,
      file_mtime: new Date(Math.floor(f.mtimeMs / 1000) * 1000).toISOString(),
      missing: false,
    })
    .eq("id", id);
}

const defaultTitle = (id: string) => {
  const t = id.replace(/_/g, " ").trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
};

/** music_tracks mis à jour avec le dossier, puis la bibliothèque pour l'onglet Montage (et l'écran de retouche). */
export async function syncTracks(): Promise<{ tracks: MusicTrack[]; error: string | null }> {
  const db = supabaseAdmin();
  const files = await libraryFiles();
  const first = await db.from("music_tracks").select("*");
  if (first.error) {
    const missingTable = /music_tracks/.test(first.error.message);
    return { tracks: [], error: missingTable ? "Migration 0018 absente : relance le lanceur (il applique les migrations)" : first.error.message };
  }
  let rows = (first.data ?? []) as Row[];
  const byId = new Map(rows.map((r) => [r.id, r]));
  let changed = false;
  const toMeasure: [string, LibraryFile][] = [];
  for (const [id, f] of files) {
    const row = byId.get(id);
    if (!row) {
      await db.from("music_tracks").upsert({ id, file: f.file, title: defaultTitle(id) }, { onConflict: "id", ignoreDuplicates: true });
      toMeasure.push([id, f]);
      changed = true;
    } else if (row.lufs === null || !sameFile(row, f)) {
      toMeasure.push([id, f]);
    } else if (row.missing) {
      await db.from("music_tracks").update({ missing: false, file: f.file }).eq("id", id);
      changed = true;
    }
  }
  const batch = toMeasure.slice(0, MEASURE_PER_LOAD);
  for (let i = 0; i < batch.length; i += 3) {
    await Promise.all(batch.slice(i, i + 3).map(([id, f]) => measureInto(id, f)));
    changed = true;
  }
  const gone = rows.filter((r) => !files.has(r.id) && !r.missing).map((r) => r.id);
  if (gone.length) {
    await db.from("music_tracks").update({ missing: true }).in("id", gone);
    changed = true;
  }
  if (changed) {
    const again = await db.from("music_tracks").select("*");
    rows = (again.data ?? rows) as Row[];
  }

  const { data: used } = await db.from("videos").select("music_track").not("music_track", "is", null).limit(5000);
  const uses = new Map<string, number>();
  for (const u of used ?? []) uses.set(u.music_track as string, (uses.get(u.music_track as string) ?? 0) + 1);
  const tracks = rows
    .sort((a, b) => (a.id < b.id ? -1 : 1))
    .map((r) => ({
      id: r.id,
      file: r.file,
      url: `/api/music/${encodeURIComponent(r.id)}`,
      title: r.title || r.id,
      description: r.description ?? "",
      moods: r.moods ?? [],
      formats: (r.formats ?? []).filter((f): f is MontageFormat => MONTAGE_FORMATS.includes(f as MontageFormat)),
      weight: Number(r.weight ?? 1),
      enabled: r.enabled !== false,
      gainDb: Number(r.gain_db ?? 0),
      startS: Number(r.start_s ?? 0),
      note: r.note ?? "",
      lufs: r.lufs === null ? null : Number(r.lufs),
      durationS: r.duration_s === null ? null : Number(r.duration_s),
      missing: r.missing || !files.has(r.id),
      uses: uses.get(r.id) ?? 0,
    }));
  return { tracks, error: null };
}

const narrationLoudness = new Map<string, number | null>(); // chemin|date → LUFS : une narration n'est mesurée qu'une fois

// ---- Choix automatique d'une piste, recopié de worker/music.py (mood_ids, choose_track) ------------------------------

function words(text: string): string[] {
  const plain = text.normalize("NFKD").replace(/[^\x00-\x7F]/g, "").toLowerCase();
  return plain.replace(/[^a-z]+/g, " ").split(" ").filter(Boolean);
}

/** Ambiances de la bibliothèque pour ce qu'écrit le scénariste ou une série (« mysterious » → mystere). */
export function moodIds(value: string | null | undefined, c: AudioConstants): string[] {
  const out: string[] = [];
  for (const w of words(value ?? "")) {
    for (const m of w in c.moods ? [w] : (c.aliases[w] ?? [])) if (!out.includes(m)) out.push(m);
  }
  return out;
}

/** Tirage selon la préférence, le même que le worker pour une même production (sha1 de la clé). */
function weightedPick(pool: MusicTrack[], key: string): MusicTrack {
  const total = pool.reduce((s, t) => s + t.weight, 0);
  const u = (parseInt(createHash("sha1").update(key).digest("hex").slice(0, 13), 16) / 16 ** 13) * total;
  let acc = 0;
  for (const t of pool) {
    acc += t.weight;
    if (u < acc) return t;
  }
  return pool[pool.length - 1];
}

/** La piste que le montage donnerait à une vidéo (worker/music.py : choose_track), null s'il n'y en a pas pour ce format. */
export function chooseTrack(
  tracks: MusicTrack[],
  recipe: MontageFormat,
  mood: string | null,
  key: string,
  seriesMoods: string[],
  c: AudioConstants,
): string | null {
  const usable = tracks.filter((t) => t.enabled && !t.missing && t.weight > 0 && t.formats.includes(recipe)).sort((a, b) => (a.id < b.id ? -1 : 1));
  if (!usable.length) return null;
  const wanted = moodIds(mood, c);
  const order = [...wanted, ...wanted.flatMap((m) => c.related[m] ?? []), ...seriesMoods.flatMap((s) => moodIds(s, c))];
  for (const m of new Set(order)) {
    const pool = usable.filter((t) => t.moods.includes(m));
    if (pool.length) return weightedPick(pool, key).id;
  }
  return weightedPick(usable, key).id;
}

// ---- Vidéos d'essai ----------------------------------------------------------------------------------------------------

type TimelineJson = { scenes?: { words?: { start: number; end: number }[] }[] };
type VideoRow = {
  id: string;
  title: string | null;
  production_id: string | null;
  timeline: TimelineJson | null;
  audio_mix: { narration_lufs?: number | null } | null;
  music_track: string | null;
  preview_asset_id: string | null;
  final_asset_id: string | null;
  poster_asset_id: string | null;
  duration_s: number | null;
};
type ProductionRow = { id: string; script: { music_mood?: string | null } | null; series: { recipe: string | null; music_moods: string[] | null } | null };

const exists = async (file: string | null | undefined) => Boolean(file && (await fs.stat(file).catch(() => null))?.isFile());

/** Dernières vidéos montées encore sur le disque, avec leur voix (récits), leur musique et celle que le montage leur
 * donnerait : de quoi écouter une musique sur la vraie image et la vraie voix. Les récits d'abord. */
async function testVideos(tracks: MusicTrack[], c: AudioConstants): Promise<TestVideo[]> {
  const db = supabaseAdmin();
  const { data } = await db
    .from("videos")
    .select("id, title, production_id, timeline, audio_mix, music_track, preview_asset_id, final_asset_id, poster_asset_id, duration_s")
    .not("preview_asset_id", "is", null)
    .order("created_at", { ascending: false })
    .limit(30);
  const videos = (data ?? []) as VideoRow[];
  if (!videos.length) return [];
  const ids = videos.map((v) => v.id);
  const assetIds = videos.flatMap((v) => [v.preview_asset_id, v.final_asset_id].filter((x): x is string => Boolean(x)));
  const pids = [...new Set(videos.map((v) => v.production_id).filter((x): x is string => Boolean(x)))];
  const [{ data: files }, { data: narrations }, { data: prods }] = await Promise.all([
    db.from("assets").select("id, local_path").in("id", assetIds),
    db.from("assets").select("id, video_id, local_path").eq("kind", "narration").in("video_id", ids).order("created_at", { ascending: false }),
    pids.length ? db.from("productions").select("id, script, series(recipe, music_moods)").in("id", pids) : Promise.resolve({ data: [] }),
  ]);
  const pathOf = new Map((files ?? []).map((a) => [a.id as string, a.local_path as string | null]));
  const narrationOf = new Map<string, { id: string; path: string }>();
  for (const n of narrations ?? []) {
    if (!narrationOf.has(n.video_id as string)) narrationOf.set(n.video_id as string, { id: n.id as string, path: n.local_path as string });
  }
  const prodOf = new Map(((prods ?? []) as unknown as ProductionRow[]).map((p) => [p.id, p]));
  const byId = new Map(tracks.map((t) => [t.id, t]));

  const out: TestVideo[] = [];
  for (const v of videos) {
    if (!v.preview_asset_id || !(await exists(pathOf.get(v.preview_asset_id)))) continue;
    const prod = v.production_id ? prodOf.get(v.production_id) : undefined;
    const series = Array.isArray(prod?.series) ? prod?.series[0] : prod?.series;
    const recipe = series?.recipe;
    const format: MontageFormat = MONTAGE_FORMATS.includes(recipe as MontageFormat) ? (recipe as MontageFormat) : "story";
    let voice: TestVideo["voice"] = null;
    const narration = narrationOf.get(v.id);
    const wordsOf = (v.timeline?.scenes ?? []).flatMap((s) => s.words ?? []).map((w) => [w.start, w.end] as [number, number]);
    if (narration && wordsOf.length) {
      const st = await fs.stat(narration.path).catch(() => null);
      if (st && st.size > 2000) {
        const key = `${narration.path}|${st.mtimeMs}`;
        if (!narrationLoudness.has(key)) {
          narrationLoudness.set(key, v.audio_mix?.narration_lufs ?? (await measureLoudness(narration.path))?.lufs ?? null);
        }
        voice = { url: `/api/media/${narration.id}`, lufs: narrationLoudness.get(key) ?? null, words: wordsOf };
      }
    }
    const current = v.music_track && byId.get(v.music_track);
    const auto =
      current && current.enabled && !current.missing && current.weight > 0
        ? current.id
        : chooseTrack(tracks, format, prod?.script?.music_mood ?? null, v.production_id ?? v.id, series?.music_moods ?? [], c);
    out.push({
      videoId: v.id,
      title: v.title ?? "Vidéo sans titre",
      format,
      durationS: Number(v.duration_s ?? (wordsOf.length ? wordsOf[wordsOf.length - 1][1] + 1 : 30)),
      videoUrl: `/api/media/${v.preview_asset_id}`,
      posterUrl: v.poster_asset_id ? `/api/media/${v.poster_asset_id}` : null,
      hasFinal: await exists(v.final_asset_id ? pathOf.get(v.final_asset_id) : null),
      voice,
      musicTrack: v.music_track,
      autoTrack: auto,
    });
    if (out.length >= 12) break;
  }
  return out.sort((a, b) => Number(Boolean(b.voice)) - Number(Boolean(a.voice)));
}

export async function audioConstants(): Promise<AudioConstants> {
  const { audio } = await readDefaults();
  return audio as unknown as AudioConstants;
}

/** Bibliothèque de l'onglet Montage : pistes (dossier tenu à jour), vidéos d'essai et constantes du mixage. */
export async function loadMusicLibrary(mock: boolean): Promise<MusicLibrary> {
  const constants = await audioConstants();
  if (mock) return { folder: MUSIC_DIR, tracks: [], videos: [], constants, error: null };
  const { tracks, error } = await syncTracks();
  const videos = await testVideos(tracks, constants).catch(() => []);
  return { folder: MUSIC_DIR, tracks, videos, constants, error };
}
