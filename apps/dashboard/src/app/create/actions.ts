"use server";

/**
 * Gestes de la page Création : demander des idées pour une chaîne et un thème, garder (✓ : la production part tout
 * de suite, SQL create_production) ou écarter (✗) une idée, abandonner un storyboard. Choisir, refaire et valider
 * les images d'un storyboard passent par app/production/actions.ts.
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { deleteProduction } from "@/lib/deletion";
import { supabaseAdmin } from "@/lib/supabase-admin";

function fail(error: unknown): ActionResult {
  return { ok: false, message: error instanceof Error ? error.message : String((error as { message?: string })?.message ?? error) };
}

function refresh() {
  revalidatePath("/", "layout");
}

export async function generateIdeas(channelId: string, seriesSlug: string, count: number): Promise<ActionResult> {
  const n = Math.max(1, Math.min(20, Math.round(count)));
  const db = supabaseAdmin();
  const { data: series, error: sErr } = await db.from("series").select("id, name").eq("slug", seriesSlug).maybeSingle();
  if (sErr) return fail(sErr);
  if (!series) return { ok: false, message: "Thème inconnu" };
  const { error } = await db.from("jobs").insert({ type: "ideate", priority: 60, channel_id: channelId, payload: { series: seriesSlug, count: n, channel_id: channelId } });
  if (error) return fail(error);
  await db.from("channels").update({ last_series_id: series.id }).eq("id", channelId);
  refresh();
  return { ok: true, message: `L’agent écrit ${n} idées pour « ${series.name} » : elles arrivent ici dans une minute ou deux.` };
}

/** ✓ : la production démarre pour la chaîne choisie (script, puis images du storyboard à regarder ici). */
export async function acceptIdea(conceptId: string, channelId: string): Promise<ActionResult> {
  const { error } = await supabaseAdmin().rpc("create_production", { p_concept: conceptId, p_priority: 50, p_channel: channelId });
  if (error) return fail(error);
  refresh();
  return { ok: true, message: "En fabrication : script, puis storyboard à regarder ici (≈ 10 min)." };
}

/** ✗ : l'idée est écartée (elle reste dans « Écartées récemment » pour la remettre). */
export async function rejectIdea(conceptId: string): Promise<ActionResult> {
  const { error } = await supabaseAdmin().from("concepts").update({ status: "rejected" }).eq("id", conceptId).in("status", ["proposed", "approved"]);
  if (error) return fail(error);
  refresh();
  return { ok: true, message: "Idée écartée" };
}

export async function restoreIdea(conceptId: string): Promise<ActionResult> {
  const { error } = await supabaseAdmin().from("concepts").update({ status: "proposed" }).eq("id", conceptId).eq("status", "rejected");
  if (error) return fail(error);
  refresh();
  return { ok: true, message: "Idée remise dans la liste" };
}

/** ✗ sur un storyboard : la vidéo est abandonnée (images supprimées), l'idée passe en écartée. */
export async function abandonStoryboard(productionId: string): Promise<ActionResult> {
  const res = await deleteProduction(productionId, "rejected");
  if (res.ok) refresh();
  return res.ok ? { ok: true, message: `Vidéo abandonnée · ${res.message.replace(/^Supprimée · /, "")}` } : res;
}
