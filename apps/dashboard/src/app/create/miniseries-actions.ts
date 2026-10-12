"use server";

/**
 * Gestes de la carte « Mini-séries » de Création (docs/52) : lancer la partie suivante (le worker la crée au tick
 * suivant, worker/arcs.py), arrêter une mini-série, allumer le pilote des mini-séries et régler le seuil.
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { supabaseAdmin } from "@/lib/supabase-admin";

function fail(error: unknown): ActionResult {
  return { ok: false, message: error instanceof Error ? error.message : String((error as { message?: string })?.message ?? error) };
}

export async function launchArcPart(arcId: string, part: number): Promise<ActionResult> {
  if (part < 2 || part > 3) return { ok: false, message: "Partie inconnue" };
  const db = supabaseAdmin();
  const { error } = await db.from("story_arcs").update({ launch_request: part, status: "active", updated_at: new Date().toISOString() }).eq("id", arcId);
  if (error) return fail(error);
  revalidatePath("/create");
  return { ok: true, message: `Partie ${part} demandée : son script part dans 2 min, puis son storyboard arrive ici à valider.` };
}

export async function stopArc(arcId: string): Promise<ActionResult> {
  const db = supabaseAdmin();
  const { error } = await db.from("story_arcs").update({ status: "stopped", launch_request: null, updated_at: new Date().toISOString() }).eq("id", arcId);
  if (error) return fail(error);
  revalidatePath("/create");
  return { ok: true, message: "Mini-série arrêtée : aucune autre partie ne sera proposée." };
}

export async function saveMiniseriesSettings(change: { autopilot?: boolean; threshold?: number }): Promise<ActionResult> {
  const db = supabaseAdmin();
  const { data } = await db.from("app_settings").select("value").eq("key", "miniseries").maybeSingle();
  const value = { autopilot: false, threshold: 1, eval_hours: 48, parts: 3, ...((data?.value ?? {}) as Record<string, unknown>), ...change };
  const { error } = await db.from("app_settings").upsert({ key: "miniseries", value, updated_at: new Date().toISOString() });
  if (error) return fail(error);
  revalidatePath("/create");
  if (change.autopilot !== undefined) {
    return {
      ok: true,
      message: change.autopilot
        ? "Pilote des mini-séries allumé : une suite au-dessus du seuil est fabriquée et programmée sans toi."
        : "Pilote des mini-séries coupé : les suites te sont proposées ici.",
    };
  }
  return { ok: true, message: "Seuil enregistré." };
}
