/** Lectures serveur de Réglages → Notifications (docs/32) : réglages, mot de passe (ses 4 derniers caractères seulement),
 * dernier mail et mails en attente. À n'importer que depuis des Server Components ou des actions serveur. */
import { IS_MOCK } from "@/lib/data";
import { DEFAULT_ALERT_EMAIL, OUTBOX_HOURS, type NotificationSettings, type NotifyStatus } from "@/lib/notify-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

export const SMTP_SECRET = "smtp_password";

export async function getNotificationSettings(): Promise<NotificationSettings> {
  const fallback: NotificationSettings = { email_to: process.env.ALERT_EMAIL_TO?.trim() || DEFAULT_ALERT_EMAIL, on_video_ready: true, sender: "" };
  if (IS_MOCK) return fallback;
  const { data } = await supabaseAdmin().from("app_settings").select("value").eq("key", "notifications").maybeSingle();
  const v = (data?.value ?? {}) as Partial<NotificationSettings>;
  return {
    email_to: typeof v.email_to === "string" && v.email_to.trim() ? v.email_to.trim() : fallback.email_to,
    on_video_ready: typeof v.on_video_ready === "boolean" ? v.on_video_ready : fallback.on_video_ready,
    sender: typeof v.sender === "string" ? v.sender.trim() : "",
  };
}

type AlertRow = { kind: string; title: string; emailed_at: string | null; email_error: string | null; created_at: string };

export async function getNotifyStatus(): Promise<NotifyStatus> {
  if (IS_MOCK) return { passwordHint: null, last: null, pending: 0 };
  const db = supabaseAdmin();
  const since = new Date(Date.now() - OUTBOX_HOURS * 3_600_000).toISOString();
  const [secret, last, pending] = await Promise.all([
    db.from("app_secrets").select("hint").eq("name", SMTP_SECRET).maybeSingle(),
    db
      .from("alerts")
      .select("kind, title, emailed_at, email_error, created_at")
      .in("kind", ["video_ready", "test"])
      .or("emailed_at.not.is.null,email_error.not.is.null")
      .order("created_at", { ascending: false })
      .limit(1)
      .maybeSingle(),
    db
      .from("alerts")
      .select("id", { count: "exact", head: true })
      .eq("kind", "video_ready")
      .is("emailed_at", null)
      .is("acknowledged_at", null)
      .gte("created_at", since),
  ]);
  const row = (last.data ?? null) as AlertRow | null;
  return {
    passwordHint: secret.data ? ((secret.data.hint as string | null) ?? "…") : null,
    last: row
      ? {
          kind: row.kind === "test" ? "test" : "video_ready",
          title: row.title,
          ok: Boolean(row.emailed_at),
          at: row.emailed_at ?? row.created_at,
          error: row.emailed_at ? null : row.email_error,
        }
      : null,
    pending: pending.error ? 0 : (pending.count ?? 0),
  };
}
