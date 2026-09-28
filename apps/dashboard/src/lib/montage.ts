/**
 * Lectures serveur de l'onglet Montage (docs/23-montage.md) : modèles enregistrés (montage_templates), modèle d'origine
 * et styles de départ (services/worker/assets/montage/defaults.json), polices, fonds d'aperçu (clips et images des
 * dernières productions), textes d'essai, musiques et voix d'essai (lib/music-library.ts, docs/26-musique.md).
 * Tolérant au mode démo. Serveur uniquement (clé service role).
 */
import { promises as fs } from "node:fs";

import { IS_MOCK } from "@/lib/data";
import { listFonts, readDefaults } from "@/lib/font-files";
import { loadMusicLibrary } from "@/lib/music-library";
import {
  FALLBACK_SAMPLES,
  MONTAGE_FORMATS,
  type MontageBackground,
  type MontageFormat,
  type MontagePageData,
  type MontageSamples,
  type MontageTemplate,
  type MontageTemplateRow,
  type SubtitleStyle,
} from "@/lib/montage-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

type Json = Record<string, unknown>;
const isObject = (v: unknown): v is Json => typeof v === "object" && v !== null && !Array.isArray(v);

/** Modèle enregistré complété par le modèle d'origine (un réglage ajouté plus tard prend sa valeur d'origine, comme
 * le fait pydantic côté worker). */
export function completeTemplate(origin: MontageTemplate, saved: unknown): MontageTemplate {
  const s = isObject(saved) ? saved : {};
  const layer = <K extends "hook" | "subtitles" | "titles" | "audio">(key: K): MontageTemplate[K] =>
    ({ ...origin[key], ...(isObject(s[key]) ? (s[key] as Json) : {}) }) as MontageTemplate[K];
  return { version: 1, hook: layer("hook"), subtitles: layer("subtitles"), titles: layer("titles"), audio: layer("audio") };
}

type ProductionRow = {
  id: string;
  status: string;
  script: Json | null;
  concepts: { title: string } | { title: string }[] | null;
  series: { recipe: string | null } | { recipe: string | null }[] | null;
};

const one = <T,>(v: T | T[] | null): T | null => (Array.isArray(v) ? (v[0] ?? null) : v);

function langText(v: unknown): string {
  if (!isObject(v)) return "";
  const text = v.fr ?? v.en ?? Object.values(v)[0];
  return typeof text === "string" ? text.trim() : "";
}

async function exists(file: string | null): Promise<boolean> {
  if (!file) return false;
  try {
    await fs.access(file);
    return true;
  } catch {
    return false;
  }
}

/**
 * Fonds proposés (un clip par production récente, puis quelques images) et textes d'essai. Les textes viennent d'abord
 * de la vidéo du premier fond de chaque format (celui montré d'emblée), pour que l'aperçu ne mêle pas le clip d'une
 * vidéo et l'accroche d'une autre (docs/28) ; un fond dont la vidéo n'est pas encore montée le dit dans son libellé.
 */
async function backgroundsAndSamples(): Promise<{ backgrounds: MontageBackground[]; samples: MontageSamples }> {
  const db = supabaseAdmin();
  const { data } = await db
    .from("productions")
    .select("id, status, script, concepts(title), series(recipe)")
    .not("script", "is", null)
    .order("created_at", { ascending: false })
    .limit(40);
  const prods = (data ?? []) as ProductionRow[];
  const info = new Map<string, { format: MontageFormat; title: string; unfinished: boolean }>();
  for (const p of prods) {
    const recipe = one(p.series)?.recipe;
    const format: MontageFormat = MONTAGE_FORMATS.includes(recipe as MontageFormat) ? (recipe as MontageFormat) : "story";
    // Montage pas encore fait : la vidéo n'est que dans Bibliothèque → En fabrication
    info.set(p.id, { format, title: one(p.concepts)?.title ?? "Vidéo sans titre", unfinished: !["ready", "archived"].includes(p.status) });
  }

  const ids = prods.map((p) => p.id);
  const { data: assets } = ids.length
    ? await db
        .from("assets")
        .select("id, production_id, kind, scene_index, local_path")
        .in("production_id", ids)
        .in("kind", ["clip", "storyboard"])
        .order("created_at", { ascending: false })
        .limit(600)
    : { data: [] };
  type AssetRow = { id: string; production_id: string; kind: "clip" | "storyboard"; scene_index: number | null; local_path: string | null };
  const rows = (assets ?? []) as AssetRow[];
  const byProduction = (kind: AssetRow["kind"]) => {
    const picked = new Map<string, AssetRow>();
    for (const a of rows.filter((r) => r.kind === kind)) {
      const cur = picked.get(a.production_id);
      // une scène du milieu montre mieux le lieu que la première (souvent l'accroche)
      if (!cur || (a.scene_index === 1 && cur.scene_index !== 1)) picked.set(a.production_id, a);
    }
    return ids.map((id) => picked.get(id)).filter((a): a is AssetRow => Boolean(a));
  };
  const clips = byProduction("clip").slice(0, 12);
  const withClip = new Set(clips.map((c) => c.production_id));
  const images = byProduction("storyboard").filter((a) => !withClip.has(a.production_id)).slice(0, 6);
  const candidates = [...clips, ...images];
  const ok = await Promise.all(candidates.map((a) => exists(a.local_path)));
  const shown = candidates.filter((_, i) => ok[i]);
  const backgrounds = shown.map((a) => {
    const p = info.get(a.production_id)!;
    return {
      assetId: a.id,
      kind: a.kind === "clip" ? ("clip" as const) : ("image" as const),
      url: `/api/media/${a.id}`,
      format: p.format,
      label: `${p.title}${a.scene_index !== null ? ` · scène ${a.scene_index + 1}` : ""}${p.unfinished ? " · pas encore montée" : ""}`,
    };
  });

  // Textes d'essai : la production du premier fond de chaque format d'abord, puis les plus récentes
  const firstShown = new Set<string>();
  const formatsShown = new Set<MontageFormat>();
  for (const a of shown) {
    const { format } = info.get(a.production_id)!;
    if (!formatsShown.has(format)) {
      formatsShown.add(format);
      firstShown.add(a.production_id);
    }
  }
  const ordered = [...prods].sort((a, b) => Number(firstShown.has(b.id)) - Number(firstShown.has(a.id)));
  const samples: MontageSamples = structuredClone(FALLBACK_SAMPLES);
  const seen = { hook: new Set<MontageFormat>(), subtitle: new Set<MontageFormat>(), title: new Set<MontageFormat>() };
  for (const p of ordered) {
    const { format } = info.get(p.id)!;
    const script = p.script ?? {};
    const scenes = Array.isArray(script.scenes) ? (script.scenes as Json[]) : [];
    const hook = langText(script.hook_title);
    if (hook && !seen.hook.has(format)) {
      samples[format].hook = hook;
      seen.hook.add(format);
    }
    const narration = scenes.map((s) => langText(s.narration)).find((t) => t.split(/\s+/).length >= 6);
    if (narration && format === "story" && !seen.subtitle.has(format)) {
      samples.story.subtitle = narration;
      seen.subtitle.add(format);
    }
    const title = scenes.map((s) => langText(s.on_screen_text)).find(Boolean);
    if (title && format !== "timelapse" && !seen.title.has(format)) {
      samples[format].title = title;
      seen.title.add(format);
    }
  }
  return { backgrounds, samples };
}

export async function getMontageData(): Promise<MontagePageData> {
  const defaults = await readDefaults();
  const origin = completeTemplate(defaults.template as MontageTemplate, defaults.template);
  const presets = defaults.subtitle_presets as Record<string, SubtitleStyle>;
  const fonts = await listFonts();
  if (IS_MOCK) {
    const music = await loadMusicLibrary(true);
    return { templates: [], origin, presets, fonts, backgrounds: [], samples: FALLBACK_SAMPLES, music, mock: true };
  }

  const [{ data, error }, extra, music] = await Promise.all([
    supabaseAdmin().from("montage_templates").select("id, name, template, is_default, updated_at").order("name"),
    backgroundsAndSamples(),
    loadMusicLibrary(false),
  ]);
  const templates: MontageTemplateRow[] = error
    ? []
    : (data ?? []).map((r) => ({
        id: r.id as string,
        name: r.name as string,
        template: completeTemplate(origin, r.template),
        isDefault: Boolean(r.is_default),
        updatedAt: r.updated_at as string,
      }));
  return { templates, origin, presets, fonts, ...extra, music, mock: false };
}
