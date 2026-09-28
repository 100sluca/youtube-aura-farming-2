/**
 * TikTok par Zernio, côté serveur du dashboard (docs/36-publication-tiktok.md) : réglages (app_settings « tiktok »),
 * clé API (app_secrets « zernio_api_key », chiffrée comme les clés des LLM, jamais renvoyée au navigateur) et comptes
 * TikTok connectés à Zernio. Zernio ne sert qu'à TikTok : YouTube garde son propre envoi.
 */
import { decryptSecret } from "@/lib/crypto";
import { IS_MOCK } from "@/lib/data";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { DEFAULT_TIKTOK, parseTikTokSettings, parseVideoTikTok, type LibraryTikTok, type TikTokAccount, type TikTokSettings } from "@/lib/tiktok-types";

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
