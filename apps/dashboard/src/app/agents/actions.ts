"use server";

/**
 * Onglet Agents (docs/22-agents.md) : écrire une nouvelle version d'un prompt, ou remettre en service une version de
 * l'historique (texte du code, ancienne version, proposition de l'agent d'amélioration). La logique vit en SQL
 * (migration 0012 : save_prompt, activate_prompt) ; le worker lit la version active à chaque appel d'agent, une
 * modification sert donc dès la tâche suivante, sans le relancer.
 */
import { revalidatePath } from "next/cache";

import { promptName } from "@/lib/agent-catalog";
import { supabaseAdmin } from "@/lib/supabase-admin";

import type { ActionResult } from "@/app/production/actions";

const KEY = /^[a-z][a-z0-9_]{1,39}$/; // contrainte prompt_templates_agent_check
const MAX_CHARS = 40_000; // le plus long prompt du code en fait 4 600

function fail(error: unknown): ActionResult {
  return { ok: false, message: error instanceof Error ? error.message : String((error as { message?: string })?.message ?? error) };
}

function refresh(key: string) {
  revalidatePath("/agents");
  revalidatePath(`/agents/${key}`);
}

async function knownKey(key: string): Promise<boolean> {
  if (!KEY.test(key)) return false;
  const { count } = await supabaseAdmin().from("prompt_templates").select("id", { count: "exact", head: true }).eq("agent", key);
  return (count ?? 0) > 0;
}

export async function savePrompt(input: { key: string; content: string; notes?: string; parentId?: string | null }): Promise<ActionResult> {
  const content = input.content.replace(/\r\n?/g, "\n").replace(/\s+$/, "");
  if (!(await knownKey(input.key))) return { ok: false, message: "Agent inconnu" };
  if (!content.trim()) return { ok: false, message: "Le prompt est vide" };
  if (content.length > MAX_CHARS) return { ok: false, message: `Prompt trop long (${content.length} caractères, ${MAX_CHARS} au plus)` };
  const { data, error } = await supabaseAdmin().rpc("save_prompt", {
    p_agent: input.key,
    p_content: content,
    p_notes: (input.notes ?? "").trim().slice(0, 500) || null,
    p_parent: input.parentId ?? null,
  });
  if (error) return fail(error);
  refresh(input.key);
  return { ok: true, message: `${promptName(input.key)} : version ${data as number} enregistrée et active. Elle sert dès la prochaine tâche.` };
}

export async function activatePrompt(key: string, version: number): Promise<ActionResult> {
  if (!(await knownKey(key)) || !Number.isInteger(version)) return { ok: false, message: "Version inconnue" };
  const { error } = await supabaseAdmin().rpc("activate_prompt", { p_agent: key, p_version: version });
  if (error) return fail(error);
  refresh(key);
  return { ok: true, message: `${promptName(key)} : la version ${version} est de nouveau active. Elle sert dès la prochaine tâche.` };
}
