"use server";

/**
 * Gestes du gestionnaire de tâches (panneau de droite) : lire la file, arrêter / reprendre / supprimer une vidéo en
 * fabrication, relancer ou masquer une tâche hors vidéo. L'arrêt passe par SQL cancel_production : le worker voit
 * l'arrêt au plus tard 5 s après et annule aussi le calcul en cours dans ComfyUI (worker/cancel.py).
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { getProductionCard } from "@/lib/data";
import { deleteProduction } from "@/lib/deletion";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { getTaskBoard } from "@/lib/tasks";
import type { TaskBoard } from "@/lib/task-types";
import type { ProductionCard } from "@/lib/types";

function fail(error: unknown): ActionResult {
  return { ok: false, message: error instanceof Error ? error.message : String((error as { message?: string })?.message ?? error) };
}

function refresh() {
  revalidatePath("/", "layout");
}

export async function fetchTaskBoard(): Promise<TaskBoard> {
  return getTaskBoard();
}

export async function fetchProductionCard(productionId: string): Promise<ProductionCard | null> {
  return getProductionCard(productionId);
}

export async function stopProduction(productionId: string): Promise<ActionResult> {
  const { error } = await supabaseAdmin().rpc("cancel_production", { p_production: productionId });
  if (error) return fail(error);
  refresh();
  return { ok: true, message: "Arrêtée : le calcul en cours s’interrompt dans quelques secondes" };
}

export async function resumeProduction(productionId: string): Promise<ActionResult> {
  const { error } = await supabaseAdmin().rpc("resume_production", { p_production: productionId });
  if (error) return fail(error);
  refresh();
  return { ok: true, message: "Reprise : elle repart dans la file" };
}

/** Supprimer une vidéo arrêtée ou en échec : fichiers et production ; l'idée revient dans Création. */
export async function removeProduction(productionId: string): Promise<ActionResult> {
  const res = await deleteProduction(productionId, "proposed");
  if (res.ok) refresh();
  return res.ok ? { ok: true, message: `${res.message} · l’idée revient dans Création` } : res;
}

export async function cancelJob(jobId: string): Promise<ActionResult> {
  const { error } = await supabaseAdmin()
    .from("jobs")
    .update({ status: "cancelled", finished_at: new Date().toISOString(), error: "Arrêtée par l'utilisateur" })
    .eq("id", jobId)
    .in("status", ["queued", "running"]);
  if (error) return fail(error);
  refresh();
  return { ok: true, message: "Tâche arrêtée" };
}

export async function retryJob(jobId: string): Promise<ActionResult> {
  const { error } = await supabaseAdmin()
    .from("jobs")
    .update({ status: "queued", attempts: 0, error: null, locked_by: null, locked_at: null, finished_at: null, run_after: new Date().toISOString() })
    .eq("id", jobId)
    .eq("status", "failed");
  if (error) return fail(error);
  refresh();
  return { ok: true, message: "Tâche remise en file" };
}

/** Masquer une tâche en échec (elle passe « annulée » et quitte le panneau). */
export async function dismissJob(jobId: string): Promise<ActionResult> {
  const { error } = await supabaseAdmin().from("jobs").update({ status: "cancelled" }).eq("id", jobId).eq("status", "failed");
  if (error) return fail(error);
  refresh();
  return { ok: true, message: "Masquée" };
}
