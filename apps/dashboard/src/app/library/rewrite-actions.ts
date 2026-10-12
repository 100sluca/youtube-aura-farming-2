"use server";

/**
 * Retoucher → Récit (docs/53-reecrire-le-recit.md) : demander au conteur un nouveau texte pour une vidéo faite (job
 * « rewrite », action « propose »), puis en faire une nouvelle vidéo sur les mêmes plans (action « make »). La vidéo
 * d'origine ne change pas ; la nouvelle arrive à valider dans la Bibliothèque.
 */
import { revalidatePath } from "next/cache";
import { z } from "zod";

import type { ActionResult } from "@/app/production/actions";
import { getRewriteData } from "@/lib/rewrite-story";
import { supabaseAdmin } from "@/lib/supabase-admin";

const UUID = /^[0-9a-f-]{36}$/i;
const text = (max: number) => z.string().max(max);

const askSchema = z.object({
  mode: z.enum(["story", "hook"]),
  note: text(3000),
  page: text(200),
});

const storySchema = z.object({
  central_idea: text(2000).default(""),
  engine: text(500).default(""),
  protagonist: text(500).default(""),
  stakes: text(1000).default(""),
  ending: text(500).default(""),
  scenes: z
    .array(z.object({ index: z.number().int().min(0).max(200), part: text(20), text: text(600), on_screen: text(80).default("") }))
    .min(1)
    .max(60),
  hook_title: z.record(z.string(), text(140)).default({}),
  title: text(100).default(""),
});

const hookSchema = z.object({
  angle: text(1000).default(""),
  hook: text(300).min(1, "accroche vide"),
  promise: text(300).min(1, "promesse vide"),
  on_screen: text(80).default(""),
  hook_title: z.record(z.string(), text(140)).default({}),
  title: text(100).default(""),
});

async function check(videoId: string, mode: "story" | "hook"): Promise<{ productionId: string } | ActionResult> {
  if (!UUID.test(videoId)) return { ok: false, message: "Vidéo inconnue" };
  const data = await getRewriteData(videoId);
  if (!data) return { ok: false, message: "Cette vidéo n’a pas de récit en voix off à réécrire" };
  if (data.blocked) return { ok: false, message: data.blocked };
  if (mode === "hook" && data.hookBlocked) return { ok: false, message: data.hookBlocked };
  const busy = data.state.current && (data.state.current.status === "queued" || data.state.current.status === "running");
  if (busy) return { ok: false, message: "Une réécriture est déjà en cours pour cette vidéo" };
  const { data: v } = await supabaseAdmin().from("videos").select("production_id").eq("id", videoId).maybeSingle();
  return { productionId: v?.production_id as string };
}

/** Le conteur propose un texte (rien n'est créé) : 5 à 15 minutes pour un récit, 2 à 5 pour une accroche. */
export async function proposeRewrite(videoId: string, input: { mode: "story" | "hook"; note: string; page: string }): Promise<ActionResult> {
  const parsed = askSchema.safeParse(input);
  if (!parsed.success) return { ok: false, message: parsed.error.issues[0]?.message ?? "Demande invalide" };
  const r = parsed.data;
  const ok = await check(videoId, r.mode);
  if ("ok" in ok) return ok;
  const pages = r.page.trim() ? [r.page.trim()] : [];
  const { error } = await supabaseAdmin()
    .from("jobs")
    .insert({
      type: "rewrite",
      video_id: videoId,
      production_id: ok.productionId,
      priority: 15,
      max_attempts: 2,
      payload: { action: "propose", mode: r.mode, note: r.note.trim(), pages, source: "retouche" },
    });
  if (error) return { ok: false, message: error.message };
  return { ok: true, message: r.mode === "hook" ? "Le conteur réécrit l’accroche" : "Le conteur réécrit le récit" };
}

/** Le texte relu devient une nouvelle vidéo : copie des plans, voix, montage, contrôle (et SEO pour un récit entier). */
export async function makeRewrite(videoId: string, input: { mode: "story" | "hook"; proposal: unknown; note?: string }): Promise<ActionResult> {
  const mode = input.mode === "hook" ? "hook" : "story";
  const parsed = mode === "hook" ? hookSchema.safeParse(input.proposal) : storySchema.safeParse(input.proposal);
  if (!parsed.success) return { ok: false, message: `Texte refusé : ${parsed.error.issues[0]?.message ?? "valeurs invalides"}` };
  if (mode === "story" && (parsed.data as z.infer<typeof storySchema>).scenes.some((s) => !s.text.trim())) {
    return { ok: false, message: "Chaque plan a sa phrase : un texte est vide" };
  }
  const ok = await check(videoId, mode);
  if ("ok" in ok) return ok;
  const { error } = await supabaseAdmin()
    .from("jobs")
    .insert({
      type: "rewrite",
      video_id: videoId,
      production_id: ok.productionId,
      priority: 15,
      max_attempts: 1, // une copie de production à moitié faite ne se refait pas seule
      payload: { action: "make", mode, proposal: parsed.data, note: input.note ?? "", source: "retouche" },
    });
  if (error) return { ok: false, message: error.message };
  revalidatePath("/library");
  return { ok: true, message: "Nouvelle vidéo lancée : voix, montage, contrôle" };
}

/** Arrêter la réécriture en cours : le worker s'arrête dès que l'appel au modèle en cours est fini (worker/cancel.py). */
export async function stopRewrite(videoId: string): Promise<ActionResult> {
  if (!UUID.test(videoId)) return { ok: false, message: "Vidéo inconnue" };
  const { error } = await supabaseAdmin()
    .from("jobs")
    .update({ status: "cancelled", finished_at: new Date().toISOString(), error: "Arrêtée par l'utilisateur" })
    .eq("video_id", videoId)
    .eq("type", "rewrite")
    .in("status", ["queued", "running"]);
  if (error) return { ok: false, message: error.message };
  return { ok: true, message: "Réécriture arrêtée" };
}
