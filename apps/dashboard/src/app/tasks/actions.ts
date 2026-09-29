"use server";

/**
 * Gestes du gestionnaire de tâches (panneau de droite) : lire la file, mettre en pause / reprendre, changer l'ordre de
 * la file, arrêter / reprendre / supprimer une vidéo en fabrication, relancer ou masquer une tâche hors vidéo. L'arrêt
 * et la pause « tout de suite » passent par SQL (cancel_production, pause_productions) : le worker les voit au plus
 * tard 5 s après et annule aussi le calcul en cours dans ComfyUI (worker/cancel.py). Pause et ordre : docs/40.
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

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Identifiants de productions reçus du navigateur : des uuid, sans doublon. */
function ids(list: string[]): string[] {
  return [...new Set((Array.isArray(list) ? list : []).filter((id) => typeof id === "string" && UUID.test(id)))];
}

/**
 * Mettre en pause : la vidéo garde sa place et tout ce qui est fait. now : le calcul en cours sur la carte graphique
 * (clip, images, voix) s'arrête tout de suite et sera refait à la reprise ; sinon il se termine d'abord.
 */
export async function pauseProductions(productionIds: string[], now: boolean): Promise<ActionResult> {
  const list = ids(productionIds);
  if (!list.length) return { ok: false, message: "Rien à mettre en pause" };
  const { data, error } = await supabaseAdmin().rpc("pause_productions", { p_ids: list, p_now: now });
  if (error) return fail(error);
  refresh();
  const n = Number(data ?? 0);
  return { ok: true, message: n > 1 ? `${n} vidéos en pause : ce qui est fait est gardé` : "En pause : ce qui est fait est gardé" };
}

/**
 * Reprendre après une pause : elle retrouve sa place dans la file, sans passer devant la vidéo en cours. order
 * (facultatif) : nouvel ordre de la file juste après (« Reprendre en premier »).
 */
export async function unpauseProductions(productionIds: string[], order?: string[]): Promise<ActionResult> {
  const list = ids(productionIds);
  if (!list.length) return { ok: false, message: "Rien à reprendre" };
  const db = supabaseAdmin();
  const { data, error } = await db.rpc("unpause_productions", { p_ids: list });
  if (error) return fail(error);
  if (order?.length) {
    const reordered = await db.rpc("reorder_queue", { p_ids: ids(order) });
    if (reordered.error) return fail(reordered.error);
  }
  refresh();
  const n = Number(data ?? 0);
  return { ok: true, message: n > 1 ? `${n} vidéos reprises` : "Reprise : elle retrouve sa place dans la file" };
}

/** Nouvel ordre de la file d'attente (glisser, « Passer en premier », monter, descendre) : la vidéo en cours reste devant. */
export async function reorderQueue(order: string[]): Promise<ActionResult> {
  const list = ids(order);
  if (list.length < 2) return { ok: false, message: "Rien à réordonner" };
  const { error } = await supabaseAdmin().rpc("reorder_queue", { p_ids: list });
  if (error) return fail(error);
  refresh();
  return { ok: true, message: "Nouvel ordre de la file enregistré" };
}

/** « Tout mettre en pause sauf celle-ci » : les autres vidéos se mettent en pause, celle-ci passe en tête de la file. */
export async function focusProduction(productionId: string, now: boolean): Promise<ActionResult> {
  if (!UUID.test(productionId)) return { ok: false, message: "Vidéo inconnue" };
  const { data, error } = await supabaseAdmin().rpc("focus_production", { p_production: productionId, p_now: now });
  if (error) return fail(error);
  refresh();
  const n = Number(data ?? 0);
  return { ok: true, message: n > 0 ? `${n} autre${n > 1 ? "s" : ""} vidéo${n > 1 ? "s" : ""} en pause : celle-ci passe seule` : "Elle passe seule, en premier" };
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
