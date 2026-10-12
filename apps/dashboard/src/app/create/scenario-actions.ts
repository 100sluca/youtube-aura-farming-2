"use server";

/**
 * Gestes de la carte « Mon scénario » de Création (docs/59) : confier un scénario libre à l'équipe d'agents (SQL
 * submit_scenario : l'idée et sa production en une fois, le script part aussitôt) et relancer un scénario dont la
 * production a échoué ou a été arrêtée.
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import type { ScenarioSpeech, ScenarioStyle } from "@/lib/scenario-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

function fail(error: unknown): ActionResult {
  return { ok: false, message: error instanceof Error ? error.message : String((error as { message?: string })?.message ?? error) };
}

export type ScenarioInput = { text: string; title?: string; style: ScenarioStyle; speech: ScenarioSpeech; durationS: number };

export async function submitScenario(channelId: string, input: ScenarioInput): Promise<ActionResult> {
  const text = input.text.trim();
  if (text.length < 20) return { ok: false, message: "Décris au moins une action : qui fait quoi, où." };
  const { error } = await supabaseAdmin().rpc("submit_scenario", {
    p_channel: channelId,
    p_text: text,
    p_title: input.title?.trim() || null,
    p_style: input.style === "auto" ? null : input.style,
    p_speech: input.speech === "auto" ? null : input.speech,
    p_duration: input.durationS > 0 ? Math.round(input.durationS) : null,
  });
  if (error) return fail(error);
  revalidatePath("/", "layout");
  return {
    ok: true,
    message: "Confié à l’équipe : mise en scène, plans et relecture (≈ 5 min), puis le storyboard arrive ici à valider.",
  };
}

/** Production ratée ou arrêtée : une nouvelle part avec le même scénario (l'équipe le relit depuis le début). */
export async function relaunchScenario(conceptId: string, channelId: string): Promise<ActionResult> {
  const { error } = await supabaseAdmin().rpc("create_production", { p_concept: conceptId, p_priority: 50, p_channel: channelId });
  if (error) return fail(error);
  revalidatePath("/", "layout");
  return { ok: true, message: "Relancé : l’équipe relit ton scénario depuis le début." };
}
