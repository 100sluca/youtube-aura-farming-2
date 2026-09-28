"use server";

/**
 * Gestes du Dashboard (docs/25-dashboard-statistiques.md) : actualiser les stats YouTube tout de suite, lancer l'agent
 * analyste, valider ou écarter ses leçons. Tout passe par la file de jobs du worker (sync_metrics, analyze) ; une leçon
 * validée est lue par les agents idées, scénaristes et SEO dès leur tâche suivante (worker/lessons.py).
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { getChannelContext } from "@/lib/channel-server";
import type { LessonStatus } from "@/lib/stats-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

const errorText = (error: unknown): string =>
  error && typeof error === "object" && "message" in error ? String((error as { message: unknown }).message) : String(error);

/** Synchro complète maintenant (compteurs, YouTube Analytics, courbes de rétention), devant les autres tâches. */
export async function refreshStats(): Promise<ActionResult> {
  const { channels, selected } = await getChannelContext();
  const targets = (selected ? [selected] : channels).filter((c) => c.is_active && c.youtube_channel_id);
  if (!targets.length) return { ok: false, message: "Aucune chaîne connectée à YouTube : Réglages → Chaînes." };
  const db = supabaseAdmin();
  const payload = { days: 7, source: "dashboard" };
  for (const c of targets) {
    const pending = await db.from("jobs").select("id").eq("type", "sync_metrics").eq("channel_id", c.id).eq("status", "queued").limit(1);
    if (pending.error) return { ok: false, message: errorText(pending.error) };
    // une synchro attend déjà (compteurs de l'heure) : elle devient complète et passe devant
    const res = pending.data?.length
      ? await db.from("jobs").update({ priority: 10, payload, run_after: new Date().toISOString() }).eq("id", pending.data[0].id)
      : await db.from("jobs").insert({ type: "sync_metrics", channel_id: c.id, priority: 10, payload });
    if (res.error) return { ok: false, message: errorText(res.error) };
  }
  revalidatePath("/dashboard");
  return { ok: true, message: "Actualisation lancée : compteurs, YouTube Analytics et courbes de rétention (une minute environ)." };
}

/** L'agent analyste compare maintenant les vidéos qui marchent et les autres. */
export async function runAnalysis(channelId: string): Promise<ActionResult> {
  const db = supabaseAdmin();
  const pending = await db.from("jobs").select("id").eq("type", "analyze").eq("channel_id", channelId).in("status", ["queued", "running"]).limit(1);
  if (pending.error) return { ok: false, message: errorText(pending.error) };
  if (pending.data?.length) return { ok: true, message: "L’analyse est déjà en cours." };
  const { error } = await db.from("jobs").insert({ type: "analyze", channel_id: channelId, priority: 20, payload: { source: "dashboard" } });
  if (error) return { ok: false, message: errorText(error) };
  revalidatePath("/dashboard");
  return { ok: true, message: "Analyse lancée : l’agent lit les chiffres et la fiche de chaque vidéo (une à deux minutes)." };
}

const DECISION_MESSAGES: Partial<Record<LessonStatus, string>> = {
  active: "Leçon validée : les agents la reçoivent dès leur prochaine tâche.",
  rejected: "Leçon écartée.",
  retired: "Leçon retirée : les agents ne la reçoivent plus.",
};

/** ✓ (active), ✗ (rejected) ou retrait d'une leçon déjà validée (retired) ; le texte peut être corrigé en validant. */
export async function decideLesson(id: string, decision: "active" | "rejected" | "retired", rule?: string): Promise<ActionResult> {
  const update: Record<string, unknown> = { status: decision, decided_at: new Date().toISOString() };
  if (rule !== undefined) {
    const clean = rule.replace(/\s+/g, " ").trim();
    if (clean.length < 3 || clean.length > 600) return { ok: false, message: "Une leçon fait entre 3 et 600 caractères." };
    update.rule = clean;
  }
  const { data, error } = await supabaseAdmin().from("performance_lessons").update(update).eq("id", id).select("target").maybeSingle();
  if (error) return { ok: false, message: errorText(error) };
  if (!data) return { ok: false, message: "Leçon introuvable." };
  revalidatePath("/dashboard");
  if (decision === "active" && data.target === "production") return { ok: true, message: "Notée : c’est un réglage à faire toi-même, aucun agent ne la reçoit." };
  return { ok: true, message: DECISION_MESSAGES[decision] ?? "C’est noté." };
}
