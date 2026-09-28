"use server";

/**
 * Réglages → Notifications (docs/32-notifications-mail.md) : adresse qui reçoit, case « Vidéo terminée », compte Gmail
 * qui envoie (app_settings « notifications ») et son mot de passe d'application (app_secrets « smtp_password », chiffré
 * comme les clés d'IA ; le navigateur n'en voit que les 4 derniers caractères). Le mail d'essai passe par le worker,
 * comme les vrais : une alerte « test » qu'il envoie dans les 20 s.
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { encryptSecret } from "@/lib/crypto";
import { SMTP_SECRET, getNotificationSettings } from "@/lib/notify";
import type { NotificationSettings, TestMailState } from "@/lib/notify-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const GMAIL_APP_PASSWORD = /^[a-z]{4}( [a-z]{4}){3}$/i; // affiché par Google en 4 groupes de 4 lettres

function fail(error: unknown): ActionResult {
  return { ok: false, message: error instanceof Error ? error.message : String((error as { message?: string })?.message ?? error) };
}

export async function saveNotificationSettings(input: NotificationSettings): Promise<ActionResult> {
  const email_to = String(input.email_to ?? "").trim();
  const sender = String(input.sender ?? "").trim();
  if (!EMAIL.test(email_to)) return { ok: false, message: "Adresse qui reçoit invalide" };
  if (sender && !EMAIL.test(sender)) return { ok: false, message: "Adresse du compte qui envoie invalide" };
  const value: NotificationSettings = { email_to, on_video_ready: Boolean(input.on_video_ready), sender };
  const { error } = await supabaseAdmin().from("app_settings").upsert({ key: "notifications", value, updated_at: new Date().toISOString() });
  if (error) return fail(error);
  revalidatePath("/settings");
  return {
    ok: true,
    message: value.on_video_ready ? `Enregistré : un mail à ${email_to} dès qu’une vidéo est terminée` : "Enregistré : plus de mail à la fin des vidéos",
  };
}

export async function saveSmtpPassword(value: string): Promise<ActionResult & { hint?: string }> {
  let secret = String(value ?? "").trim();
  if (GMAIL_APP_PASSWORD.test(secret)) secret = secret.replace(/ /g, "");
  if (secret.length < 8) return { ok: false, message: "Mot de passe trop court (Gmail : 16 lettres)" };
  try {
    const { error } = await supabaseAdmin()
      .from("app_secrets")
      .upsert({ name: SMTP_SECRET, value_encrypted: await encryptSecret(secret), hint: secret.slice(-4), updated_at: new Date().toISOString() });
    if (error) return fail(error);
    revalidatePath("/settings");
    return { ok: true, message: `Mot de passe enregistré (…${secret.slice(-4)}) : envoie un mail d’essai pour vérifier`, hint: secret.slice(-4) };
  } catch (error) {
    return fail(error);
  }
}

export async function deleteSmtpPassword(): Promise<ActionResult> {
  const { error } = await supabaseAdmin().from("app_secrets").delete().eq("name", SMTP_SECRET);
  if (error) return fail(error);
  revalidatePath("/settings");
  return { ok: true, message: "Mot de passe retiré : plus aucun mail ne part" };
}

/** Mail d'essai : une alerte « test » que le worker envoie dans les 20 s, exactement comme un vrai mail. */
export async function sendTestMail(): Promise<ActionResult & { alertId?: string }> {
  const { email_to } = await getNotificationSettings();
  const { data, error } = await supabaseAdmin()
    .from("alerts")
    .insert({ severity: "info", kind: "test", title: "Mail d’essai", body: `Demandé depuis Réglages → Notifications, vers ${email_to}` })
    .select("id")
    .single();
  if (error) {
    const stale = /kind|schema cache/i.test(error.message);
    return { ok: false, message: stale ? "Base pas à jour : migration 0019 à appliquer (relancer le lanceur)" : error.message };
  }
  return { ok: true, message: `Mail d’essai en file : le worker l’envoie à ${email_to} dans les 20 s…`, alertId: data.id as string };
}

export async function getTestMailState(alertId: string): Promise<TestMailState> {
  if (!/^[0-9a-f-]{36}$/i.test(alertId)) return { state: "unknown", message: "" };
  const { data } = await supabaseAdmin().from("alerts").select("emailed_at, email_error, acknowledged_at").eq("id", alertId).maybeSingle();
  if (!data) return { state: "unknown", message: "Essai introuvable" };
  if (data.emailed_at) return { state: "sent", message: "Mail d’essai parti : regarde ta boîte (et les spams, la première fois)" };
  if (data.email_error || data.acknowledged_at) return { state: "failed", message: (data.email_error as string | null) ?? "Essai abandonné" };
  return { state: "pending", message: "Le worker va l’envoyer…" };
}
