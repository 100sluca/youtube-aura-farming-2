"use server";

/**
 * Page Recherche (docs/60-recherche-niches.md) : chaque bouton met une tâche « research » en file (payload.action), prise
 * dans la seconde par le fil « stats » du worker, ou change une ligne (niche suivie, vidéo écartée, réglages).
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { parseResearchSettings, type NicheStatus, type ReproduceMode, type ResearchAction, type ResearchSettings } from "@/lib/research-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

const PATH = "/research";

function fail(error: unknown): ActionResult {
  return { ok: false, message: error instanceof Error ? error.message : String((error as { message?: string })?.message ?? error) };
}

/** Met la tâche en file, sauf si la même attend ou tourne déjà (même action, même vidéo). */
async function enqueue(action: ResearchAction, payload: Record<string, unknown> = {}): Promise<{ queued: boolean; error?: string }> {
  const db = supabaseAdmin();
  let q = db.from("jobs").select("id, status").eq("type", "research").in("status", ["queued", "running"]).eq("payload->>action", action);
  if (payload.video_id) q = q.eq("payload->>video_id", String(payload.video_id));
  const pending = await q.limit(1);
  if (pending.error) return { queued: false, error: pending.error.message };
  if (pending.data?.length) {
    if (pending.data[0].status === "queued") {
      await db.from("jobs").update({ priority: 10, run_after: new Date().toISOString() }).eq("id", pending.data[0].id);
    }
    return { queued: false };
  }
  const res = await db.from("jobs").insert({ type: "research", priority: 10, max_attempts: 2, payload: { action, source: "dashboard", ...payload } });
  return res.error ? { queued: false, error: res.error.message } : { queued: true };
}

export async function scanNow(): Promise<ActionResult> {
  try {
    const r = await enqueue("scan");
    if (r.error) return { ok: false, message: r.error };
    revalidatePath(PATH);
    return {
      ok: true,
      message: r.queued
        ? "Relevé lancé : recherches YouTube, chiffres, classement (2 à 5 minutes)."
        : "Un relevé est déjà en cours.",
    };
  } catch (e) {
    return fail(e);
  }
}

export async function exploreTopic(q: string, lang: string): Promise<ActionResult> {
  const topic = q.trim();
  if (topic.length < 3) return { ok: false, message: "Écris un sujet (3 lettres au moins)." };
  try {
    const r = await enqueue("explore", { q: topic.slice(0, 120), lang: lang === "fr" ? "fr" : "en" });
    if (r.error) return { ok: false, message: r.error };
    revalidatePath(PATH);
    return { ok: true, message: `« ${topic} » : 7 recherches (la semaine, puis 6 mois), résultat dans une minute ou deux.` };
  } catch (e) {
    return fail(e);
  }
}

export async function watchVideo(videoId: string): Promise<ActionResult> {
  try {
    const r = await enqueue("watch", { video_id: videoId });
    if (r.error) return { ok: false, message: r.error };
    revalidatePath(PATH);
    return { ok: true, message: r.queued ? "Gemini regarde la vidéo (une minute environ)." : "Gemini la regarde déjà." };
  } catch (e) {
    return fail(e);
  }
}

/** « fidele » (par défaut, docs/64 §3) : même sujet, même déroulé, nos mots en français ; « mecanique » : histoire nouvelle. */
export async function reproduceVideo(videoId: string, mode: ReproduceMode = "fidele"): Promise<ActionResult> {
  try {
    const r = await enqueue("reproduce", { video_id: videoId, mode: mode === "mecanique" ? "mecanique" : "fidele" });
    if (r.error) return { ok: false, message: r.error };
    await supabaseAdmin().from("research_videos").update({ status: "shortlisted" }).eq("id", videoId).eq("status", "new");
    revalidatePath(PATH);
    return {
      ok: true,
      message: r.queued
        ? mode === "fidele"
          ? "Version fidèle en route : Gemini la réécrit en français, puis elle part en fabrication ; le storyboard arrivera dans Création, à valider."
          : "Notre version part en fabrication : son storyboard arrivera dans Création, à valider."
        : "Déjà en route vers la fabrication.",
    };
  } catch (e) {
    return fail(e);
  }
}

/** La version fidèle en français, écrite sans rien lancer (à lire avant de refaire). */
export async function adaptVideo(videoId: string): Promise<ActionResult> {
  try {
    const r = await enqueue("adapt", { video_id: videoId });
    if (r.error) return { ok: false, message: r.error };
    revalidatePath(PATH);
    return { ok: true, message: r.queued ? "Gemini regarde la vidéo et l’écrit en français (une minute environ)." : "Déjà en cours." };
  } catch (e) {
    return fail(e);
  }
}

/** Une question au stratège : la réponse arrive sous la question, dans une minute environ. */
export async function askStrategist(question: string): Promise<ActionResult> {
  const q = question.trim();
  if (q.length < 4) return { ok: false, message: "Écris ta question." };
  try {
    const res = await supabaseAdmin()
      .from("jobs")
      .insert({ type: "research", priority: 10, max_attempts: 2, payload: { action: "ask", source: "dashboard", question: q.slice(0, 1000) } });
    if (res.error) return { ok: false, message: res.error.message };
    revalidatePath(PATH);
    return { ok: true, message: "Question envoyée : le stratège lit la veille et répond (une minute environ)." };
  } catch (e) {
    return fail(e);
  }
}

/** Découverte des niches Shorts hors des nôtres (docs/64 §2) : `budget` recherches YouTube au plus. */
export async function discoverShortsNow(budget = 40): Promise<ActionResult> {
  try {
    const r = await enqueue("discover_shorts", { budget: Math.max(1, Math.min(80, Math.round(budget))) });
    if (r.error) return { ok: false, message: r.error };
    revalidatePath(PATH);
    return {
      ok: true,
      message: r.queued ? "Découverte lancée : une recherche par sujet, puis le classement (5 à 10 minutes)." : "Une découverte est déjà en cours.",
    };
  } catch (e) {
    return fail(e);
  }
}

export async function setVideoStatus(videoId: string, status: "new" | "shortlisted" | "dismissed"): Promise<ActionResult> {
  try {
    const { error } = await supabaseAdmin().from("research_videos").update({ status }).eq("id", videoId).neq("status", "reproduced");
    if (error) return { ok: false, message: error.message };
    revalidatePath(PATH);
    return { ok: true, message: status === "dismissed" ? "Écartée." : status === "shortlisted" ? "Gardée en tête de liste." : "Remise dans la liste." };
  } catch (e) {
    return fail(e);
  }
}

export async function setNicheStatus(nicheId: string, status: NicheStatus): Promise<ActionResult> {
  try {
    const { error } = await supabaseAdmin().from("research_niches").update({ status }).eq("id", nicheId);
    if (error) return { ok: false, message: error.message };
    revalidatePath(PATH);
    const label = { active: "Suivie chaque jour.", paused: "En pause.", archived: "Retirée de la veille.", proposed: "Proposée." }[status];
    return { ok: true, message: label };
  } catch (e) {
    return fail(e);
  }
}

/** Une niche proposée par le stratège (ou tapée à la main) : suivie tout de suite, et relevée au prochain relevé. */
export async function addNiche(label: string, queries: string[]): Promise<ActionResult> {
  const name = label.trim();
  const qs = queries.map((q) => q.trim()).filter(Boolean).slice(0, 3);
  if (!name || !qs.length) return { ok: false, message: "Il faut un nom et au moins une recherche." };
  const slug =
    "manual_" +
    name
      .normalize("NFKD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_|_$/g, "")
      .slice(0, 40);
  try {
    const { error } = await supabaseAdmin()
      .from("research_niches")
      .upsert(
        {
          slug,
          label: name.slice(0, 80),
          queries: qs.map((q, i) => (i === 0 ? { q, lang: "en", region: "US" } : { q, lang: "fr", region: "FR" })),
          status: "active",
          origin: "manual",
        },
        { onConflict: "slug" },
      );
    if (error) return { ok: false, message: error.message };
    revalidatePath(PATH);
    return { ok: true, message: `« ${name} » suivie : elle sera relevée au prochain relevé.` };
  } catch (e) {
    return fail(e);
  }
}

export async function requestBrief(): Promise<ActionResult> {
  try {
    const r = await enqueue("brief");
    if (r.error) return { ok: false, message: r.error };
    revalidatePath(PATH);
    return { ok: true, message: r.queued ? "Le stratège lit la veille (une à deux minutes)." : "Le stratège y travaille déjà." };
  } catch (e) {
    return fail(e);
  }
}

export async function saveResearchSettings(patch: Partial<ResearchSettings>): Promise<ActionResult> {
  try {
    const db = supabaseAdmin();
    const { data } = await db.from("app_settings").select("value").eq("key", "research").maybeSingle();
    const next = parseResearchSettings({ ...parseResearchSettings(data?.value), ...patch });
    next.daily_searches = Math.max(10, Math.min(95, Math.round(next.daily_searches)));
    next.auto_watch = Math.max(0, Math.min(15, Math.round(next.auto_watch)));
    next.min_views = Math.max(5_000, Math.round(next.min_views));
    const { error } = await db.from("app_settings").upsert({ key: "research", value: next, updated_at: new Date().toISOString() });
    if (error) return { ok: false, message: error.message };
    revalidatePath(PATH);
    return { ok: true, message: "Réglages enregistrés." };
  } catch (e) {
    return fail(e);
  }
}
