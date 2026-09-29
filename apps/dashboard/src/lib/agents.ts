/** Lectures serveur de l'onglet Agents (docs/22-agents.md) : versions des prompts (prompt_templates), activité des
 * agents sur 7 jours, et ce que la chaîne de production montre en direct (modèles réglés, tâches, ce qui attend).
 * Tolérant au mode démo. À n'importer que depuis des Server Components ou des actions serveur (clé service role). */
import { promises as fs } from "node:fs";
import path from "node:path";

import { AGENTS, type ModelSlot, type WaitingKey } from "@/lib/agent-catalog";
import type { AgentActivity, PipelineLive, PromptOrigin, PromptState, PromptVersion } from "@/lib/agent-types";
import { IS_MOCK } from "@/lib/data";
import { getGenerationSettings } from "@/lib/generation-data";
import type { Provider } from "@/lib/llm-types";
import { getLlmSettings, getSecretHints } from "@/lib/settings-data";
import { supabaseAdmin } from "@/lib/supabase-admin";
import type { JobType } from "@/lib/types";

const WEEK_MS = 7 * 24 * 3600 * 1000;

type PromptRow = {
  id: string;
  agent: string;
  version: number;
  content: string;
  notes: string | null;
  created_by: string;
  created_at: string;
  is_active: boolean;
  parent_id: string | null;
};

const PROMPT_COLUMNS = "id, agent, version, content, notes, created_by, created_at, is_active, parent_id";

function toVersion(r: PromptRow): PromptVersion {
  const origin: PromptOrigin = r.created_by === "code" || r.created_by === "improve_agent" ? r.created_by : "human";
  return {
    id: r.id,
    version: r.version,
    content: r.content,
    notes: r.notes,
    origin,
    createdAt: r.created_at,
    active: Boolean(r.is_active),
    parentId: r.parent_id,
  };
}

/** Le texte du code dont descend une version, en remontant ses parents (null si la chaîne est rompue). */
function codeBase(v: PromptVersion, byId: Map<string, PromptVersion>): PromptVersion | null {
  const seen = new Set<string>();
  let cur: PromptVersion | undefined = v;
  while (cur && !seen.has(cur.id)) {
    if (cur.origin === "code") return cur;
    seen.add(cur.id);
    cur = cur.parentId ? byId.get(cur.parentId) : undefined;
  }
  return null;
}

function stateOf(key: string, rows: PromptVersion[]): PromptState {
  const versions = [...rows].sort((a, b) => b.version - a.version);
  const active = versions.find((v) => v.active) ?? null;
  const latestCode = versions.find((v) => v.origin === "code") ?? null;
  const byId = new Map(versions.map((v) => [v.id, v]));
  let codeUpdate: PromptVersion | null = null;
  if (active && latestCode && active.id !== latestCode.id) {
    const base = codeBase(active, byId);
    if (base ? base.id !== latestCode.id : latestCode.createdAt > active.createdAt) codeUpdate = latestCode;
  }
  const proposals = versions.filter((v) => v.origin === "improve_agent" && !v.active && (!active || v.version > active.version));
  return { key, versions, active, latestCode, codeUpdate, proposals };
}

/** Toutes les clés de prompt en base, avec leurs versions. */
export async function getPromptStates(): Promise<Record<string, PromptState>> {
  if (IS_MOCK) return {};
  const { data } = await supabaseAdmin().from("prompt_templates").select(PROMPT_COLUMNS);
  const byKey = new Map<string, PromptVersion[]>();
  for (const r of (data ?? []) as PromptRow[]) {
    const list = byKey.get(r.agent) ?? [];
    list.push(toVersion(r));
    byKey.set(r.agent, list);
  }
  return Object.fromEntries([...byKey].map(([key, rows]) => [key, stateOf(key, rows)]));
}

export async function getPromptState(key: string): Promise<PromptState> {
  if (IS_MOCK) return stateOf(key, []);
  const { data } = await supabaseAdmin().from("prompt_templates").select(PROMPT_COLUMNS).eq("agent", key);
  return stateOf(key, ((data ?? []) as PromptRow[]).map(toVersion));
}

// ---------------------------------------------------------------------------------------------------------------
// Activité des agents
// ---------------------------------------------------------------------------------------------------------------

/** Scénariste qui écrit pour un thème, d'après sa recette (series.recipe). */
function scriptAgent(recipe: string | null | undefined): string {
  return recipe === "timelapse" ? "script_timelapse" : recipe === "tour" ? "script_tour" : recipe === "drama" ? "script_drama" : "script";
}

type JobRow = {
  type: JobType;
  status: string;
  finished_at: string | null;
  production: { series: { recipe: string | null } | null } | null;
  /** Job storyboard d'une scène réinventée (docs/27) : payload.reinvent, puis payload.reinvented une fois réécrite. */
  asked?: unknown;
  rewritten?: unknown;
};

const JOB_COLUMNS = "type, status, finished_at, asked:payload->reinvent, rewritten:payload->reinvented, production:productions(series:series(recipe))";

/** Par agent : tâches terminées et en échec sur 7 jours, en cours, en file ; verdicts des contrôleurs. */
export async function getAgentActivity(): Promise<Record<string, AgentActivity>> {
  if (IS_MOCK) return {};
  const db = supabaseAdmin();
  const since = new Date(Date.now() - WEEK_MS).toISOString();
  const types = [...new Set(AGENTS.filter((a) => !a.vision).map((a) => a.job))];
  const [recent, live, qc] = await Promise.all([
    db.from("jobs").select(JOB_COLUMNS).in("type", types).in("status", ["done", "failed"]).gte("finished_at", since).limit(5000),
    db.from("jobs").select(JOB_COLUMNS).in("type", types).in("status", ["queued", "running"]).limit(1000),
    db
      .from("assets")
      .select("kind, created_at, ok:meta->qc->>ok")
      .in("kind", ["storyboard", "clip"])
      .not("meta->qc", "is", null)
      .gte("created_at", since)
      .limit(5000),
  ]);
  const out: Record<string, AgentActivity> = {};
  const entry = (key: string) => (out[key] ??= { done: 0, failed: 0, running: 0, queued: 0, lastAt: null });
  const agentOf = (j: JobRow) => {
    if (j.type === "script") return scriptAgent(j.production?.series?.recipe);
    if (j.type === "storyboard") return j.asked || j.rewritten ? "scene_rewrite" : undefined; // les autres ne font que des images
    return AGENTS.find((a) => a.job === j.type && !a.vision)?.key;
  };
  for (const j of [...((recent.data ?? []) as unknown as JobRow[]), ...((live.data ?? []) as unknown as JobRow[])]) {
    const key = agentOf(j);
    if (!key) continue;
    // le relecteur et le réalisateur passent dans chaque tâche du conteur des histoires (worker/steps/script.py, docs/37)
    for (const k of key === "script" ? [key, "script_review", "script_shots"] : [key]) {
      const e = entry(k);
      if (j.status === "done") e.done += 1;
      else if (j.status === "failed") e.failed += 1;
      else if (j.status === "running") e.running += 1;
      else if (j.status === "queued") e.queued += 1;
      if (j.finished_at && (!e.lastAt || j.finished_at > e.lastAt)) e.lastAt = j.finished_at;
    }
  }
  for (const a of (qc.data ?? []) as { kind: string; created_at: string; ok: string | null }[]) {
    const e = entry(a.kind === "clip" ? "clip_qc" : "keyframe_qc");
    e.checked = (e.checked ?? 0) + 1;
    if (a.ok === "false") e.refused = (e.refused ?? 0) + 1;
    if (!e.lastAt || a.created_at > e.lastAt) e.lastAt = a.created_at;
  }
  return out;
}

// ---------------------------------------------------------------------------------------------------------------
// Chaîne de production en direct
// ---------------------------------------------------------------------------------------------------------------

export const PROVIDER_LABELS: Record<Provider, string> = { gemini: "Gemini", anthropic: "Claude", mistral: "Mistral", ollama: "Ollama" };
// Même règle que le worker (providers/llm.py, sees_images) : qui peut regarder une image
const OLLAMA_VISION = /(llava|vision|[-_.]vl|minicpm-v|gemma3|moondream|bakllava|granite3\.2-vision|mistral-small3)/i;

function seesImages(provider: Provider, model: string): boolean {
  if (provider === "gemini" || provider === "anthropic") return true;
  if (provider === "mistral") return /(pixtral|small|medium)/i.test(model);
  return OLLAMA_VISION.test(model);
}

/** Les 1ers choix des chaînes de modèles (Réglages → IA) dont le fournisseur a une clé, et celui qui regarde les images. */
export async function getLlmLabels(): Promise<{ llm: string; vision: string }> {
  const [llm, hints] = await Promise.all([getLlmSettings(), getSecretHints()]);
  const configured = (p: Provider) => p === "ollama" || (hints[p]?.length ?? 0) > 0;
  const general = llm.chains.default.filter((e) => configured(e.provider));
  const writer = llm.chains.writer.filter((e) => configured(e.provider));
  const label = (e: { provider: Provider; model: string }) => `${PROVIDER_LABELS[e.provider]} · ${e.model}`;
  const vision = general.find((e) => seesImages(e.provider, e.model));
  const more = general.length > 1 ? ` (+ ${general.length - 1} en secours)` : "";
  return {
    llm: general[0]
      ? label(general[0]) + (writer[0] && writer[0].model !== general[0].model ? ` · écriture : ${writer[0].model}` : "") + more
      : "aucun modèle configuré",
    vision: vision ? label(vision) : "aucun modèle qui voit les images",
  };
}

// Le dashboard tourne dans apps/dashboard : le catalogue des modèles du worker est deux dossiers plus haut (même
// chemin que lib/generation-data.ts, qui interroge en plus ComfyUI ; ici seuls les noms comptent).
const WORKFLOW_DIR = process.env.COMFY_WORKFLOW_DIR ?? path.join(process.cwd(), "..", "..", "services", "worker", "workflows");

type CatalogLabels = {
  image?: Record<string, { label?: string }>;
  video?: Record<string, { label?: string }>;
  tts?: Record<string, { label?: string }>;
  voices?: Record<string, (string | { id: string; label?: string })[]>;
};

async function modelLabels(): Promise<Pick<Record<ModelSlot, string>, "image" | "video" | "voice">> {
  const gen = await getGenerationSettings();
  let catalog: CatalogLabels = {};
  try {
    catalog = JSON.parse(await fs.readFile(path.join(WORKFLOW_DIR, "catalog.json"), "utf8")) as CatalogLabels;
  } catch {
    // catalogue illisible : les noms techniques suffisent
  }
  const voiceId = gen.voices.fr;
  const [engine] = voiceId.split(":");
  const voice = (catalog.voices?.fr ?? []).map((v) => (typeof v === "string" ? { id: v } : v)).find((v) => v.id === voiceId);
  const candidates = gen.storyboard_candidates;
  return {
    image: `${catalog.image?.[gen.image_workflow]?.label ?? gen.image_workflow} · ${candidates} image${candidates > 1 ? "s" : ""} par scène`,
    video: catalog.video?.[gen.video_workflow]?.label ?? gen.video_workflow,
    voice: `${voice?.label ?? voiceId} · ${catalog.tts?.[engine]?.label ?? engine}`,
  };
}

async function countRows(table: string, column: string, value: string): Promise<number> {
  const { count } = await supabaseAdmin().from(table).select("id", { count: "exact", head: true }).eq(column, value);
  return count ?? 0;
}

export async function getPipelineLive(): Promise<PipelineLive> {
  const empty: Record<WaitingKey, number> = { concepts: 0, storyboards: 0, videos_review: 0, scheduled: 0, published: 0 };
  const [llm, models] = await Promise.all([getLlmLabels(), modelLabels()]);
  if (IS_MOCK) return { models: { ...llm, ...models }, jobs: {}, waiting: empty };
  const [jobs, concepts, storyboards, review, scheduled, published] = await Promise.all([
    supabaseAdmin().from("jobs").select("type, status").in("status", ["queued", "running"]).limit(2000),
    countRows("concepts", "status", "proposed"),
    countRows("productions", "status", "storyboard_review"),
    countRows("videos", "status", "review"),
    countRows("videos", "status", "scheduled"),
    countRows("videos", "status", "published"),
  ]);
  const byType: PipelineLive["jobs"] = {};
  for (const j of (jobs.data ?? []) as { type: JobType; status: string }[]) {
    const e = (byType[j.type] ??= { running: 0, queued: 0 });
    if (j.status === "running") e.running += 1;
    else e.queued += 1;
  }
  return {
    models: { ...llm, ...models },
    jobs: byType,
    waiting: { concepts, storyboards, videos_review: review, scheduled, published },
  };
}
