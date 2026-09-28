/** Lectures serveur de l'écran Réglages (réglages IA, indices des clés, quota ; les prompts : lib/agents.ts). Tolérant
 * au mode démo. À n'importer que depuis des Server Components ou des actions serveur (clé service role). */
import { IS_MOCK } from "@/lib/data";
import { KEY_NAME, effectiveChain, type KeyHint, type LlmSettings, type Provider } from "@/lib/llm-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

/** Modèles proposés par défaut (liste vérifiée sur ai.google.dev le 2026-09-21) ; « Charger depuis Google » complète. */
export const PRESET_MODELS: Record<Provider, string[]> = {
  gemini: [
    "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite",
    "gemini-3.1-pro-preview", "gemini-3.1-flash-lite", "gemini-3-flash-preview",
    "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro",
  ],
  anthropic: ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001"],
  mistral: ["mistral-small-latest", "mistral-medium-latest", "mistral-large-latest"],
  ollama: ["qwen3:8b", "qwen2.5:7b", "llama3.1:8b"],
};

const DEFAULT_BASE: Pick<LlmSettings, "provider" | "fallbacks" | "models"> = {
  provider: "gemini",
  fallbacks: ["anthropic", "mistral", "ollama"],
  models: { gemini: "gemini-3.8-flash", anthropic: "claude-sonnet-5", mistral: "mistral-small-latest", ollama: "qwen3:8b" },
};

export const DEFAULT_LLM: LlmSettings = {
  ...DEFAULT_BASE,
  custom_models: { gemini: [], anthropic: [], mistral: [], ollama: [] },
  writer_models: { gemini: "", anthropic: "", mistral: "", ollama: "" },
  chains: { writer: effectiveChain({}, "writer", DEFAULT_BASE), default: effectiveChain({}, "default", DEFAULT_BASE) },
};

export async function getLlmSettings(): Promise<LlmSettings> {
  if (IS_MOCK) return DEFAULT_LLM;
  const { data } = await supabaseAdmin().from("app_settings").select("value").eq("key", "llm").maybeSingle();
  const v = (data?.value ?? {}) as Partial<LlmSettings>;
  return {
    provider: v.provider ?? DEFAULT_LLM.provider,
    fallbacks: v.fallbacks ?? DEFAULT_LLM.fallbacks,
    models: { ...DEFAULT_LLM.models, ...(v.models ?? {}) },
    custom_models: { ...DEFAULT_LLM.custom_models, ...(v.custom_models ?? {}) },
    writer_models: { ...DEFAULT_LLM.writer_models, ...(v.writer_models ?? {}) },
    chains: { writer: effectiveChain(v, "writer", DEFAULT_BASE), default: effectiveChain(v, "default", DEFAULT_BASE) },
  };
}

/** Clés enregistrées par fournisseur, dans l'ordre (numéro et 4 derniers caractères ; jamais la clé). */
export async function getSecretHints(): Promise<Partial<Record<Provider, KeyHint[]>>> {
  if (IS_MOCK) return {};
  const { data } = await supabaseAdmin().from("app_secrets").select("name, hint");
  const out: Partial<Record<Provider, KeyHint[]>> = {};
  for (const r of data ?? []) {
    const m = KEY_NAME.exec(r.name as string);
    if (!m) continue;
    (out[m[1] as Provider] ??= []).push({ slot: Number(m[2] ?? 1), hint: (r.hint as string | null) ?? "…" });
  }
  for (const list of Object.values(out)) list.sort((a, b) => a.slot - b.slot);
  return out;
}

export interface ChannelVideoCounts {
  app: number;
  imported: number;
  importing: boolean; // import de l'historique en file ou en cours
}

/** Vidéos produites et importées par chaîne (Réglages → Chaînes : suppression possible, historique). */
export async function getChannelVideoCounts(channelIds: string[]): Promise<Record<string, ChannelVideoCounts>> {
  if (IS_MOCK) return {};
  const db = supabaseAdmin();
  const count = async (id: string, origin: "app" | "imported") =>
    (await db.from("videos").select("id", { count: "exact", head: true }).eq("channel_id", id).eq("origin", origin)).count ?? 0;
  const { data: jobs } = await db.from("jobs").select("channel_id").eq("type", "import_channel").in("status", ["queued", "running"]);
  const importing = new Set((jobs ?? []).map((j) => j.channel_id as string));
  const entries = await Promise.all(
    channelIds.map(async (id) => [id, { app: await count(id, "app"), imported: await count(id, "imported"), importing: importing.has(id) }] as const),
  );
  return Object.fromEntries(entries);
}

/** Unités consommées aujourd'hui et envois du jour par chaîne (table api_quota_usage). Les envois (videos.insert) et
 * search.list ont chez Google leur propre compteur de 100 appels par jour : ils ne comptent pas dans les 10 000 unités. */
export async function getQuotaToday(): Promise<Record<string, { units: number; uploads: number }>> {
  if (IS_MOCK) return {};
  const today = new Date().toISOString().slice(0, 10);
  const { data } = await supabaseAdmin().from("api_quota_usage").select("channel_id, endpoint, units").eq("day", today);
  const out: Record<string, { units: number; uploads: number }> = {};
  for (const r of data ?? []) {
    const key = (r.channel_id as string | null) ?? "-";
    out[key] ??= { units: 0, uploads: 0 };
    if (r.endpoint === "videos.insert") out[key].uploads += 1;
    else if (r.endpoint !== "search.list") out[key].units += Number(r.units) || 0;
  }
  return out;
}
