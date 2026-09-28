/** Lectures serveur de Réglages → Modèles de génération : le catalogue des workflows du worker
 * (services/worker/workflows/catalog.json), les fichiers de modèles que ComfyUI voit, et le réglage
 * app_settings « generation ». À n'importer que depuis des Server Components ou des actions serveur. */
import { promises as fs } from "node:fs";
import path from "node:path";

import { IS_MOCK } from "@/lib/data";
import {
  DEFAULT_GENERATION,
  normalizeVoiceId,
  type CatalogEntry,
  type GenerationCatalog,
  type GenerationKind,
  type GenerationSettings,
  type VoiceEntry,
  type VoiceLang,
} from "@/lib/generation-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

// Le dashboard tourne dans apps/dashboard : les workflows du worker sont deux dossiers plus haut.
const WORKFLOW_DIR = process.env.COMFY_WORKFLOW_DIR ?? path.join(process.cwd(), "..", "..", "services", "worker", "workflows");
const COMFY_URL = (process.env.COMFY_BASE_URL ?? "http://127.0.0.1:8188").replace(/\/$/, "");
// Racine de ce que le worker installe hors du dépôt (moteurs de voix : tts/<moteur>, modèles Kokoro : models/)
const YT2_HOME = process.env.YT2_HOME ?? "C:/YouTube2";
// Entrées des nœuds de chargement qui désignent un fichier de modèle
const MODEL_INPUTS = ["unet_name", "clip_name", "clip_name1", "clip_name2", "vae_name", "lora_name", "ckpt_name"];

type RawEntry = { label: string; detail?: string; license?: string; publishable?: boolean };
/** Moteur de voix (catalog.json → tts) : `check` = chemins relatifs à YT2_HOME qui doivent exister. */
type RawEngine = RawEntry & { check?: string[] };
type RawVoice = string | { id: string; label?: string };
type RawCatalog = Partial<Record<GenerationKind, Record<string, RawEntry>>> & {
  tts?: Record<string, RawEngine>;
  voices?: Partial<Record<VoiceLang, RawVoice[]>>;
};
type WorkflowJson = Record<string, { inputs?: Record<string, unknown> }>;

async function readJson<T>(file: string): Promise<T | null> {
  try {
    return JSON.parse(await fs.readFile(file, "utf8")) as T;
  } catch {
    return null;
  }
}

/** Fichiers de modèles cités par un workflow (format API) : ce que ComfyUI devra trouver. */
async function workflowFiles(name: string): Promise<string[] | null> {
  const wf = await readJson<WorkflowJson>(path.join(WORKFLOW_DIR, `${name}.json`));
  if (!wf) return null;
  const files = new Set<string>();
  for (const node of Object.values(wf)) {
    for (const key of MODEL_INPUTS) {
      const value = node?.inputs?.[key];
      if (typeof value === "string" && value) files.add(value);
    }
  }
  return [...files];
}

/** Options d'une entrée « liste » de /object_info : ancien format [[...]] ou nouveau ["COMBO", { options }]. */
function comboOptions(spec: unknown): string[] {
  if (!Array.isArray(spec)) return [];
  if (Array.isArray(spec[0])) return spec[0].filter((o): o is string => typeof o === "string");
  const options = (spec[1] as { options?: unknown } | undefined)?.options;
  return Array.isArray(options) ? options.filter((o): o is string => typeof o === "string") : [];
}

/** Fichiers de modèles que ComfyUI voit, d'après les listes des nœuds de chargement. null si ComfyUI est éteint. */
async function comfyFiles(): Promise<Set<string> | null> {
  try {
    const res = await fetch(`${COMFY_URL}/object_info`, { cache: "no-store", signal: AbortSignal.timeout(5000) });
    if (!res.ok) return null;
    const info = (await res.json()) as Record<string, { input?: { required?: Record<string, unknown> } }>;
    const out = new Set<string>();
    for (const node of Object.values(info)) {
      for (const [key, spec] of Object.entries(node.input?.required ?? {})) {
        if (MODEL_INPUTS.includes(key)) for (const file of comboOptions(spec)) out.add(file);
      }
    }
    return out;
  } catch {
    return null;
  }
}

async function exists(file: string): Promise<boolean> {
  try {
    await fs.access(file);
    return true;
  } catch {
    return false;
  }
}

/** Voix proposées pour une langue, avec leur moteur ; un moteur sans entrée dans `tts` (ancien catalogue) = Kokoro. */
async function voiceEntries(raw: RawCatalog, lang: VoiceLang): Promise<VoiceEntry[]> {
  const engines = raw.tts ?? {};
  const missingByEngine = new Map<string, string[]>();
  for (const [name, e] of Object.entries(engines)) {
    const checks = await Promise.all((e.check ?? []).map(async (rel) => ((await exists(path.join(YT2_HOME, rel))) ? null : rel)));
    missingByEngine.set(name, checks.filter((c): c is string => c !== null));
  }
  const list = raw.voices?.[lang] ?? [DEFAULT_GENERATION.voices[lang]];
  return list.map((v) => {
    const id = normalizeVoiceId(typeof v === "string" ? v : v.id);
    const [engine, voice] = id.split(":", 2);
    const e = engines[engine];
    return {
      id,
      engine,
      label: (typeof v === "string" ? null : v.label) || voice,
      engineLabel: e?.label ?? engine,
      detail: e?.detail ?? "",
      license: e?.license ?? "",
      publishable: e?.publishable !== false,
      missing: missingByEngine.get(engine) ?? [],
    };
  });
}

export async function getGenerationCatalog(): Promise<GenerationCatalog> {
  const raw = (await readJson<RawCatalog>(path.join(WORKFLOW_DIR, "catalog.json"))) ?? {};
  const available = await comfyFiles();
  const entries = (kind: GenerationKind): Promise<CatalogEntry[]> =>
    Promise.all(
      Object.entries(raw[kind] ?? {}).map(async ([name, e]) => {
        const files = await workflowFiles(name);
        return {
          name,
          kind,
          label: e.label,
          detail: e.detail ?? "",
          license: e.license ?? "",
          publishable: e.publishable !== false,
          files: files ?? [],
          missing: files === null ? [`${name}.json`] : available ? files.filter((f) => !available.has(f)) : null,
        };
      }),
    );
  const [image, video, fr, en] = await Promise.all([entries("image"), entries("video"), voiceEntries(raw, "fr"), voiceEntries(raw, "en")]);
  return { image, video, voices: { fr, en }, comfyOnline: available !== null };
}

export async function getGenerationSettings(): Promise<GenerationSettings> {
  if (IS_MOCK) return DEFAULT_GENERATION;
  const { data } = await supabaseAdmin().from("app_settings").select("value").eq("key", "generation").maybeSingle();
  const v = (data?.value ?? {}) as Partial<GenerationSettings>;
  const voices = { ...DEFAULT_GENERATION.voices, ...(v.voices ?? {}) };
  return {
    image_workflow: v.image_workflow || DEFAULT_GENERATION.image_workflow,
    video_workflow: (v.video_workflow || DEFAULT_GENERATION.video_workflow).replace(/^comfy_/, ""),
    storyboard_candidates: Number(v.storyboard_candidates) || DEFAULT_GENERATION.storyboard_candidates,
    voices: { fr: normalizeVoiceId(voices.fr) || DEFAULT_GENERATION.voices.fr, en: normalizeVoiceId(voices.en) || DEFAULT_GENERATION.voices.en },
  };
}
