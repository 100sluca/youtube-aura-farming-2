"use server";

/**
 * Recherche → Découverte (docs/63 §9) : lancer un balayage, écarter une chaîne, demander des sujets de vidéos longues
 * dans une niche découverte.
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { creationChannel, getChannelContext } from "@/lib/channel-server";
import { supabaseAdmin } from "@/lib/supabase-admin";

function fail(error: unknown): ActionResult {
  return { ok: false, message: error instanceof Error ? error.message : String(error) };
}

export async function discoverNow(): Promise<ActionResult> {
  try {
    const db = supabaseAdmin();
    const { data } = await db
      .from("jobs")
      .select("id")
      .eq("type", "research")
      .eq("payload->>action", "discover")
      .in("status", ["queued", "running"])
      .limit(1);
    if (data?.length) return { ok: false, message: "La découverte tourne déjà" };
    const res = await db.from("jobs").insert({ type: "research", priority: 10, max_attempts: 2, payload: { action: "discover", source: "dashboard" } });
    if (res.error) return { ok: false, message: res.error.message };
    revalidatePath("/research");
    return { ok: true, message: "Découverte lancée : 25 recherches au plus, quelques minutes" };
  } catch (e) {
    return fail(e);
  }
}

export async function dismissChannel(id: string): Promise<ActionResult> {
  try {
    const res = await supabaseAdmin().from("research_channels").update({ status: "dismissed" }).eq("channel_ext_id", id);
    if (res.error) return { ok: false, message: res.error.message };
    revalidatePath("/research");
    return { ok: true, message: "Chaîne écartée" };
  } catch (e) {
    return fail(e);
  }
}

/** Sujets de vidéos longues inspirés d'une niche découverte : l'agent des vidéos longues reçoit la niche et ses titres. */
export async function longIdeasFromNiche(niche: string, examples: string[]): Promise<ActionResult> {
  try {
    const channel = creationChannel(await getChannelContext());
    if (!channel) return { ok: false, message: "Aucune chaîne" };
    const note = `Niche découverte qui rapporte : « ${niche} ». Exemples de vidéos qui marchent : ${examples.slice(0, 6).join(" | ")}. Propose des sujets de cette niche, adaptés à notre chaîne histoire et mystères, avec nos formats.`;
    const res = await supabaseAdmin()
      .from("jobs")
      .insert({
        type: "long_write",
        channel_id: channel.id,
        priority: 20,
        max_attempts: 2,
        payload: { action: "ideas", count: 4, note: note.slice(0, 900), channel_id: channel.id, source: "decouverte" },
      });
    if (res.error) return { ok: false, message: res.error.message };
    revalidatePath("/long");
    return { ok: true, message: "4 sujets demandés : ils arrivent dans Vidéos longues" };
  } catch (e) {
    return fail(e);
  }
}
