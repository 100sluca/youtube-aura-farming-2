"use server";

/**
 * Gestes sur une production, partagés par Création (storyboard : choisir, refaire, valider), la Bibliothèque
 * (autoriser la publication au prochain créneau libre, programmer à une date, refuser) et le gestionnaire de
 * tâches (relancer une production en échec, refaire avec les réglages actuels).
 * La logique partagée avec la commande `yt2` vit en SQL (migration 0004 : approve_video, schedule_video,
 * reject_video) ; le rendu passe par un job `render` (le plan de continuité est calculé par le worker).
 */
import { revalidatePath } from "next/cache";

import { syncFavorite } from "@/lib/favorites";
import { formatDateTime } from "@/lib/format";
import { GEMINI_PROVIDER, geminiEtaHours } from "@/lib/gemini-types";
import { supabaseAdmin } from "@/lib/supabase-admin";
import type { ScriptV1 } from "@/lib/types";

export type ActionResult = { ok: true; message: string; at?: string } | { ok: false; message: string };

function fail(error: unknown): ActionResult {
  const message = error instanceof Error ? error.message : typeof error === "object" && error && "message" in error ? String((error as { message: unknown }).message) : String(error);
  return { ok: false, message };
}

function refresh() {
  revalidatePath("/", "layout"); // Création, Bibliothèque, Calendrier, Vue d'ensemble
}

export async function pickStoryboard(productionId: string, sceneIndex: number, assetId: string): Promise<ActionResult> {
  const db = supabaseAdmin();
  const off = await db.from("assets").update({ selected: false }).eq("production_id", productionId).eq("kind", "storyboard").eq("scene_index", sceneIndex);
  if (off.error) return fail(off.error);
  const on = await db.from("assets").update({ selected: true }).eq("id", assetId);
  if (on.error) return fail(on.error);
  await syncFavorite(productionId); // un storyboard en favori garde le dernier choix d'images (docs/19)
  refresh();
  return { ok: true, message: "Image retenue" };
}

export async function redoStoryboard(productionId: string, scenes: number[]): Promise<ActionResult> {
  const { error } = await supabaseAdmin().from("jobs").insert({ type: "storyboard", production_id: productionId, priority: 80, payload: { scenes } });
  if (error) return fail(error);
  refresh();
  return { ok: true, message: "Nouvelles images demandées : elles arrivent dans quelques minutes" };
}

/** Refaire la fiche d'un personnage de drame (docs/35) : sa fiche et tous les plans où il apparaît (ils la prennent en
 * référence) sont refaits ; payload characters pour le worker, scenes pour que Création montre ces plans en cours. */
export async function redoCharacter(productionId: string, key: string): Promise<ActionResult> {
  const db = supabaseAdmin();
  const prod = await db.from("productions").select("status, script").eq("id", productionId).maybeSingle();
  if (prod.error) return fail(prod.error);
  if (prod.data?.status !== "storyboard_review") return { ok: false, message: "Ce storyboard n’est plus à valider : sa fabrication est lancée" };
  const script = prod.data.script as ScriptV1 | null;
  const scenes = (script?.scenes ?? []).filter((s) => (s.characters ?? []).includes(key)).map((s) => s.index);
  const { error } = await db.from("jobs").insert({ type: "storyboard", production_id: productionId, priority: 80, payload: { characters: [key], scenes } });
  if (error) return fail(error);
  refresh();
  return { ok: true, message: `Nouvelle fiche demandée, puis les ${scenes.length} plans où ce personnage apparaît` };
}

/** « Arrêter » un Refaire pendant la revue (docs/16 §3) : les images affichées restent et le storyboard se valide tout de
 * suite. Le worker voit l'arrêt en 5 s au plus, annule le calcul ComfyUI en cours et ne change plus l'image retenue
 * d'aucune scène (worker/steps/storyboard.py : _select). Un Réinventer n'est arrêté que s'il est encore en file : une
 * fois commencé, ses anciennes images sont effacées et la scène resterait sans image. `jobId` : ce job, sinon tous. */
export async function stopRework(productionId: string, jobId?: string): Promise<ActionResult> {
  const db = supabaseAdmin();
  const found = await db.from("jobs").select("id, status, payload").eq("production_id", productionId).eq("type", "storyboard").in("status", ["queued", "running"]);
  if (found.error) return fail(found.error);
  const jobs = (found.data ?? []).filter((j) => Array.isArray(j.payload?.scenes) && (!jobId || j.id === jobId));
  const rewrite = (j: { payload: Record<string, unknown> | null }) => Boolean(j.payload?.reinvent || j.payload?.reinvented);
  const redo = jobs.filter((j) => !rewrite(j)).map((j) => j.id as string);
  const waiting = jobs.filter((j) => rewrite(j) && j.status === "queued").map((j) => j.id as string);
  if (redo.length + waiting.length === 0) {
    return jobs.length
      ? { ok: false, message: "La scène est en train d’être réinventée : ses anciennes images sont déjà effacées, attendre les nouvelles" }
      : { ok: true, message: "Plus rien en cours sur ce storyboard" };
  }
  const stop = { status: "cancelled", finished_at: new Date().toISOString(), error: "Arrêtée par l'utilisateur" };
  if (redo.length) {
    const { error } = await db.from("jobs").update(stop).in("id", redo).in("status", ["queued", "running"]);
    if (error) return fail(error);
  }
  if (waiting.length) {
    const { error } = await db.from("jobs").update(stop).in("id", waiting).eq("status", "queued");
    if (error) return fail(error);
  }
  refresh();
  const left = jobs.length - redo.length - waiting.length;
  return { ok: true, message: `Arrêté : les images affichées restent${left ? " (une scène finit d’être réinventée)" : ", tu peux valider"}` };
}

/** Travail d'images en file ou en cours sur ce storyboard (Refaire, Réinventer) : jobs storyboard non terminés. */
async function storyboardJobs(productionId: string) {
  return supabaseAdmin().from("jobs").select("payload").eq("production_id", productionId).eq("type", "storyboard").in("status", ["queued", "running"]);
}

/** Réinventer une scène (docs/27) : le scénariste réécrit son plan, son mouvement, sa narration et son texte à l'écran,
 * raccord avec les scènes voisines qui ne changent pas, puis de nouvelles images sont faites à la place des anciennes
 * (job storyboard, payload reinvent). `note` : ce qui ne va pas, dit par Luca (facultatif). */
export async function reinventScene(productionId: string, sceneIndex: number, note = ""): Promise<ActionResult> {
  const db = supabaseAdmin();
  const prod = await db.from("productions").select("status").eq("id", productionId).maybeSingle();
  if (prod.error) return fail(prod.error);
  if (prod.data?.status !== "storyboard_review") return { ok: false, message: "Ce storyboard n’est plus à valider : sa fabrication est lancée" };
  const busy = await storyboardJobs(productionId);
  if (busy.error) return fail(busy.error);
  if ((busy.data ?? []).some((j) => ((j.payload?.scenes ?? []) as unknown[]).map(Number).includes(sceneIndex))) {
    return { ok: false, message: "Cette scène est déjà en cours : attendre ses nouvelles images" };
  }
  const text = note.trim().slice(0, 500);
  const payload = { scenes: [sceneIndex], reinvent: true, ...(text ? { note: text } : {}) };
  const { error } = await db.from("jobs").insert({ type: "storyboard", production_id: productionId, priority: 80, payload });
  if (error) return fail(error);
  refresh();
  return { ok: true, message: "Le scénariste réinvente la scène, puis ses nouvelles images arrivent (quelques minutes)" };
}

/** Valider le storyboard : clips, voix et montage d'une traite. engine « gemini » (bouton Gemini) : les clips sont
 * fabriqués par l'appli Gemini en ligne (productions.video_provider = gemini_web, docs/17) au lieu du modèle local
 * figé au script ; voix et montage restent sur le PC. */
export async function approveStoryboard(productionId: string, engine: "local" | "gemini" = "local"): Promise<ActionResult> {
  const db = supabaseAdmin();
  const sbJobs = await db.from("jobs").select("status, payload").eq("production_id", productionId).eq("type", "storyboard");
  if (sbJobs.error) return fail(sbJobs.error);
  // Une scène refaite ou réinventée pendant la fabrication mélangerait l'ancien et le nouveau script
  if ((sbJobs.data ?? []).some((j) => j.status === "queued" || j.status === "running")) {
    return { ok: false, message: "Des images sont en cours pour ce storyboard : valider quand elles sont arrivées" };
  }
  const { data, error } = await db.from("assets").select("scene_index, selected").eq("production_id", productionId).eq("kind", "storyboard");
  if (error) return fail(error);
  const scenes = new Map<number, boolean>();
  for (const a of data ?? []) scenes.set(a.scene_index, (scenes.get(a.scene_index) ?? false) || Boolean(a.selected));
  // Une scène réinventée a toujours sa propre image, même si ses nouvelles images n'ont pas pu se faire (docs/27)
  for (const j of sbJobs.data ?? []) {
    for (const e of (j.payload?.reinvented ?? []) as { scene?: unknown }[]) if (!scenes.has(Number(e.scene))) scenes.set(Number(e.scene), false);
  }
  const missing = [...scenes.values()].filter((ok) => !ok).length;
  if (missing) return { ok: false, message: `Choisir une image pour chaque scène (${missing} sans image retenue)` };
  await syncFavorite(productionId); // choix définitif (une scène refaite a pu changer d'image retenue)
  let clips = 0;
  if (engine === "gemini") {
    const prod = await db.from("productions").select("status, script").eq("id", productionId).maybeSingle();
    if (prod.error) return fail(prod.error);
    if (prod.data?.status !== "storyboard_review") return { ok: false, message: "La fabrication de cette vidéo est déjà lancée" };
    const script = (prod.data?.script ?? null) as ScriptV1 | null;
    clips = script?.scenes.length ?? 0;
    // Chantier en accéléré, passages d'une visite (première + dernière image) : essai, Gemini reçoit les deux images
    const up = await db.from("productions").update({ video_provider: GEMINI_PROVIDER }).eq("id", productionId);
    if (up.error) return fail(up.error);
  }
  const pending = await db.from("jobs").select("id").eq("production_id", productionId).eq("type", "render").in("status", ["queued", "running"]).limit(1);
  if (pending.error) return fail(pending.error);
  if ((pending.data ?? []).length === 0) {
    const ins = await db.from("jobs").insert({ type: "render", production_id: productionId, priority: 90 });
    if (ins.error) return fail(ins.error);
  }
  await db.from("productions").update({ status: "generating" }).eq("id", productionId).eq("status", "storyboard_review");
  refresh();
  if (engine === "gemini") {
    const eta = geminiEtaHours(clips);
    return { ok: true, message: `Storyboard validé : ${clips} clips demandés à Gemini${eta ? ` (≈ ${eta} h avec le quota Pro)` : ""}, puis voix et montage sur le PC` };
  }
  return { ok: true, message: "Storyboard validé : clips, voix et montage en file" };
}

export async function approveVideo(videoId: string): Promise<ActionResult> {
  const { data, error } = await supabaseAdmin().rpc("approve_video", { p_video: videoId });
  if (error) return fail(error);
  refresh();
  const at = String(data);
  return { ok: true, message: `Publication autorisée : programmée le ${formatDateTime(at)}`, at };
}

export async function scheduleVideo(videoId: string, atIso: string): Promise<ActionResult> {
  const at = new Date(atIso);
  if (Number.isNaN(at.getTime())) return { ok: false, message: "Date invalide" };
  const { data, error } = await supabaseAdmin().rpc("schedule_video", { p_video: videoId, p_at: at.toISOString() });
  if (error) return fail(error);
  refresh();
  return { ok: true, message: `Programmée le ${formatDateTime(String(data))}`, at: String(data) };
}

export async function rejectVideo(videoId: string, reason: string): Promise<ActionResult> {
  const { error } = await supabaseAdmin().rpc("reject_video", { p_video: videoId, p_reason: reason || null });
  if (error) return fail(error);
  refresh();
  return { ok: true, message: "Vidéo refusée : rien ne partira sur YouTube" };
}

/** Refaire le montage d'une vidéo pas encore envoyée sur YouTube avec le modèle de montage actuel (onglet Montage,
 * SQL remount_video, migration 0013) : mêmes clips et même voix ; une vidéo déjà autorisée repasse en validation. */
export async function remountVideo(videoId: string): Promise<ActionResult> {
  const { error } = await supabaseAdmin().rpc("remount_video", { p_video: videoId });
  if (error) return fail(error);
  refresh();
  return { ok: true, message: "Montage relancé avec le modèle actuel : la vidéo revient à valider dans une minute environ" };
}

/** Refaire une production avec les modèles des réglages actuels : même script, nouveau storyboard, nouveaux clips
 * (SQL remake_production, migration 0005). L'originale reste intacte, pour comparer. */
export async function remakeProduction(productionId: string): Promise<ActionResult> {
  const { data, error } = await supabaseAdmin().rpc("remake_production", { p_production: productionId });
  if (error) return fail(error);
  refresh();
  return { ok: true, message: `Nouvelle production ${String(data).slice(0, 8)} créée avec les réglages actuels : storyboard en préparation` };
}

export async function retryProduction(productionId: string): Promise<ActionResult> {
  const db = supabaseAdmin();
  const { data: videos, error } = await db.from("videos").select("id").eq("production_id", productionId);
  if (error) return fail(error);
  const videoIds = (videos ?? []).map((v) => v.id as string);
  const reset = { status: "queued", attempts: 0, error: null, locked_by: null, locked_at: null, finished_at: null, run_after: new Date().toISOString() };
  const a = await db.from("jobs").update(reset).eq("production_id", productionId).eq("status", "failed");
  if (a.error) return fail(a.error);
  if (videoIds.length) {
    const b = await db.from("jobs").update(reset).in("video_id", videoIds).eq("status", "failed");
    if (b.error) return fail(b.error);
    await db.from("videos").update({ status: "pending", error: null }).in("id", videoIds).eq("status", "failed");
  }
  await db.from("productions").update({ status: "generating", error: null }).eq("id", productionId).eq("status", "failed");
  refresh();
  return { ok: true, message: "Jobs en échec remis en file" };
}
