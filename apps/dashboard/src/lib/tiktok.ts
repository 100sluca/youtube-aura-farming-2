/**
 * TikTok par Zernio, côté serveur du dashboard (docs/36-publication-tiktok.md) : réglages (app_settings « tiktok »),
 * clé API (app_secrets « zernio_api_key », chiffrée comme les clés des LLM, jamais renvoyée au navigateur) et comptes
 * TikTok connectés à Zernio. Zernio ne sert qu'à TikTok : YouTube garde son propre envoi.
 */
import { decryptSecret } from "@/lib/crypto";
import { IS_MOCK, getSchedule } from "@/lib/data";
import { now } from "@/lib/format";
import { supabaseAdmin } from "@/lib/supabase-admin";
import {
  DEFAULT_TIKTOK,
  parseTikTokSettings,
  parseVideoTikTok,
  type LibraryTikTok,
  type TikTokAccount,
  type TikTokBacklogVideo,
  type TikTokBrief,
  type TikTokCalendarItem,
  type TikTokSettings,
  type VideoTikTok,
} from "@/lib/tiktok-types";

export const ZERNIO_API = "https://zernio.com/api/v1";
export const ZERNIO_SECRET = "zernio_api_key";

export async function getTikTokSettings(): Promise<TikTokSettings> {
  if (IS_MOCK) return DEFAULT_TIKTOK;
  const { data } = await supabaseAdmin().from("app_settings").select("value").eq("key", "tiktok").maybeSingle();
  return parseTikTokSettings(data?.value);
}

/** 4 derniers caractères de la clé Zernio enregistrée, sinon null. */
export async function getZernioKeyHint(): Promise<string | null> {
  if (IS_MOCK) return null;
  const { data } = await supabaseAdmin().from("app_secrets").select("hint").eq("name", ZERNIO_SECRET).maybeSingle();
  return data ? ((data.hint as string | null) ?? "…") : null;
}

export async function zernioKey(): Promise<string | null> {
  const { data } = await supabaseAdmin().from("app_secrets").select("value_encrypted").eq("name", ZERNIO_SECRET).maybeSingle();
  return data?.value_encrypted ? decryptSecret(data.value_encrypted as string) : null;
}

/** Comptes TikTok connectés à Zernio (zernio.com → Accounts). */
export async function listZernioTikTokAccounts(key?: string): Promise<{ ok: boolean; accounts: TikTokAccount[]; message: string }> {
  const secret = key ?? (await zernioKey());
  if (!secret) return { ok: false, accounts: [], message: "Enregistrer d’abord la clé Zernio" };
  try {
    const res = await fetch(`${ZERNIO_API}/accounts`, { headers: { Authorization: `Bearer ${secret}` }, cache: "no-store", signal: AbortSignal.timeout(15_000) });
    if (!res.ok) return { ok: false, accounts: [], message: `Zernio répond ${res.status} : ${(await res.text()).slice(0, 200)}` };
    const body = (await res.json()) as { accounts?: Record<string, unknown>[] };
    const accounts = (body.accounts ?? [])
      .filter((a) => a.platform === "tiktok")
      .map((a) => ({
        id: String(a._id),
        username: String(a.username ?? ""),
        displayName: String(a.displayName ?? a.username ?? ""),
        avatar: typeof a.profilePicture === "string" ? a.profilePicture : null,
        active: a.isActive !== false && a.needsReconnection !== true,
      }));
    return {
      ok: true,
      accounts,
      message: accounts.length
        ? `${accounts.length} compte${accounts.length > 1 ? "s" : ""} TikTok connecté${accounts.length > 1 ? "s" : ""} à Zernio`
        : "Aucun compte TikTok connecté à Zernio : zernio.com → Accounts → TikTok",
    };
  } catch (error) {
    return { ok: false, accounts: [], message: `Zernio injoignable : ${error instanceof Error ? error.message : String(error)}` };
  }
}

/** Rattrapage (docs/39) : par chaîne, les vidéos déjà sorties sur YouTube et jamais envoyées sur TikTok, dans l'ordre où
 * elles partiront (la plus ancienne d'abord, une par créneau resté vide). */
export async function getTikTokBacklog(): Promise<Record<string, TikTokBacklogVideo[]>> {
  if (IS_MOCK) return {};
  const { data, error } = await supabaseAdmin()
    .from("v_tiktok_backlog")
    .select("id, channel_id, title, published_at")
    .order("published_at", { ascending: true })
    .order("id", { ascending: true });
  if (error) return {}; // migration 0026 pas encore appliquée
  const out: Record<string, TikTokBacklogVideo[]> = {};
  for (const r of data ?? []) {
    (out[r.channel_id as string] ??= []).push({
      id: r.id as string,
      channel_id: r.channel_id as string,
      title: (r.title as string | null) ?? null,
      published_at: (r.published_at as string | null) ?? null,
    });
  }
  return out;
}

/** État TikTok de chaque vidéo qui en a un, avec ses vues TikTok au dernier relevé (vignettes, tableau YouTube). */
export async function getTikTokBriefs(): Promise<Map<string, TikTokBrief>> {
  const out = new Map<string, TikTokBrief>();
  if (IS_MOCK) return out;
  const db = supabaseAdmin();
  const [videos, posts] = await Promise.all([
    db.from("videos").select("id, tiktok").not("tiktok", "is", null),
    db.from("tiktok_posts").select("video_id, views, url").not("video_id", "is", null),
  ]);
  const views = new Map((posts.data ?? []).map((p) => [p.video_id as string, { views: Number(p.views ?? 0), url: (p.url as string | null) ?? null }]));
  for (const v of videos.data ?? []) {
    const t = parseVideoTikTok(v.tiktok);
    if (!t) continue;
    const post = views.get(v.id as string);
    out.set(v.id as string, {
      status: t.status,
      draft: t.draft,
      source: t.source,
      scheduled_for: t.scheduled_for,
      url: t.url ?? post?.url ?? null,
      views: post ? post.views : null,
    });
  }
  return out;
}

const SAME_SLOT_MS = 10 * 60_000; // une publication à ±10 min occupe le créneau (tiktok/backlog.py)
const BACKLOG_LEAD_MS = 5 * 60_000; // le rattrapage choisit sa vidéo au plus tard 5 min avant l'heure

/** Heure de sortie sur TikTok d'une publication : sortie réelle, sinon heure programmée. */
function tiktokAt(t: VideoTikTok): string | null {
  return t.published_at ?? t.scheduled_for;
}

/** Calendrier (docs/39) : les publications TikTok des vidéos de l'appli entre deux instants, et le rattrapage prévu dans
 * les créneaux vides à venir des chaînes qui l'ont activé (la plus ancienne vidéo d'abord, une par créneau, comme
 * scheduler.plan_tiktok_backlog) : ce qu'il fera si aucune nouvelle vidéo ne prend ces créneaux d'ici là. */
export async function getTikTokCalendar(fromISO: string, toISO: string): Promise<TikTokCalendarItem[]> {
  if (IS_MOCK) return [];
  const db = supabaseAdmin();
  const [videos, settings, backlog] = await Promise.all([
    db.from("videos").select("id, channel_id, title, tiktok").not("tiktok", "is", null),
    getTikTokSettings(),
    getTikTokBacklog(),
  ]);
  const fromMs = new Date(fromISO).getTime();
  const toMs = new Date(toISO).getTime();
  const items: TikTokCalendarItem[] = [];
  const takenByAccount = new Map<string, number[]>(); // compte TikTok → heures déjà prises (hors échecs)
  for (const v of videos.data ?? []) {
    const t = parseVideoTikTok(v.tiktok);
    const at = t ? tiktokAt(t) : null;
    if (!t || !at) continue;
    const account = String((v.tiktok as Record<string, unknown>).account_id ?? "");
    if (t.status !== "failed" && t.status !== "cancelled") takenByAccount.set(account, [...(takenByAccount.get(account) ?? []), new Date(at).getTime()]);
    const ms = new Date(at).getTime();
    if (ms < fromMs || ms >= toMs) continue;
    items.push({
      video_id: v.id as string,
      channel_id: v.channel_id as string,
      title: (v.title as string | null) ?? null,
      at,
      status: t.status,
      draft: t.draft,
      source: t.source,
      url: t.url,
      error: t.error,
    });
  }

  // Rattrapage prévu, depuis maintenant : les créneaux de cette semaine consomment la file avant ceux de la suivante
  const nowMs = now().getTime();
  const channelsWithBacklog = Object.entries(settings.channels).filter(([cid, c]) => c.backlog && c.account_id && (backlog[cid]?.length ?? 0) > 0);
  if (channelsWithBacklog.length && toMs > nowMs + BACKLOG_LEAD_MS) {
    const days = Math.ceil((toMs - nowMs) / 86_400_000) + 1;
    const [schedule, channelRows] = await Promise.all([getSchedule(new Date(nowMs).toISOString(), days), db.from("channels").select("id, slug")]);
    const idOf = new Map((channelRows.data ?? []).map((c) => [c.slug as string, c.id as string]));
    for (const [cid, link] of channelsWithBacklog) {
      const queue = [...(backlog[cid] ?? [])];
      const taken = takenByAccount.get(link.account_id) ?? [];
      const slots = schedule.filter((s) => idOf.get(s.channel_slug) === cid).sort((a, b) => a.at.localeCompare(b.at));
      for (const s of slots) {
        const at = new Date(s.at).getTime();
        if (at <= nowMs + BACKLOG_LEAD_MS || at >= toMs) continue;
        if (link.enabled && s.video) continue; // la nouvelle vidéo YouTube du créneau part aussi sur TikTok
        if (taken.some((t) => Math.abs(t - at) < SAME_SLOT_MS)) continue;
        const next = queue.shift();
        if (!next) break;
        if (at >= fromMs) {
          items.push({ video_id: next.id, channel_id: cid, title: next.title, at: s.at, status: "scheduled", draft: false, source: "rattrapage", url: null, error: null, forecast: true });
        }
      }
    }
  }
  return items.sort((a, b) => a.at.localeCompare(b.at));
}

/** Publication TikTok d'une vidéo, pour sa fiche dans la Bibliothèque. */
export async function getLibraryTikTok(videoId: string, channelId: string): Promise<LibraryTikTok> {
  if (IS_MOCK) return { state: null, username: null, pending: false };
  const db = supabaseAdmin();
  const [video, settings, jobs] = await Promise.all([
    db.from("videos").select("tiktok").eq("id", videoId).maybeSingle(),
    getTikTokSettings(),
    db.from("jobs").select("id").eq("video_id", videoId).eq("type", "tiktok_publish").in("status", ["queued", "running"]).limit(1),
  ]);
  const link = settings.channels[channelId];
  return { state: parseVideoTikTok(video.data?.tiktok), username: link?.username || null, pending: (jobs.data ?? []).length > 0 };
}
