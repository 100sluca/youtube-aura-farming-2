/**
 * Reels Instagram par Zernio, côté serveur du dashboard (docs/48-publication-instagram.md) : réglages (app_settings
 * « instagram »), comptes Instagram connectés à Zernio et Reel de chaque vidéo. La clé Zernio est celle de TikTok
 * (lib/tiktok.ts).
 */
import { IS_MOCK } from "@/lib/data";
import {
  DEFAULT_INSTAGRAM,
  parseInstagramSettings,
  parseVideoInstagram,
  type InstagramAccount,
  type InstagramSettings,
  type LibraryInstagram,
} from "@/lib/instagram-types";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { ZERNIO_API, zernioKey } from "@/lib/tiktok";

export async function getInstagramSettings(): Promise<InstagramSettings> {
  if (IS_MOCK) return DEFAULT_INSTAGRAM;
  const { data } = await supabaseAdmin().from("app_settings").select("value").eq("key", "instagram").maybeSingle();
  return parseInstagramSettings(data?.value);
}

/** Comptes Instagram connectés à Zernio (zernio.com → Accounts). */
export async function listZernioInstagramAccounts(): Promise<{ ok: boolean; accounts: InstagramAccount[]; message: string }> {
  const secret = await zernioKey();
  if (!secret) return { ok: false, accounts: [], message: "Enregistrer d’abord la clé Zernio (Réglages → TikTok)" };
  try {
    const res = await fetch(`${ZERNIO_API}/accounts`, { headers: { Authorization: `Bearer ${secret}` }, cache: "no-store", signal: AbortSignal.timeout(15_000) });
    if (!res.ok) return { ok: false, accounts: [], message: `Zernio répond ${res.status} : ${(await res.text()).slice(0, 200)}` };
    const body = (await res.json()) as { accounts?: Record<string, unknown>[] };
    const accounts = (body.accounts ?? [])
      .filter((a) => a.platform === "instagram")
      .map((a) => {
        const profile = ((a.metadata as Record<string, unknown> | undefined)?.profileData ?? {}) as Record<string, unknown>;
        const kind = (profile.extraData as Record<string, unknown> | undefined)?.accountType;
        return {
          id: String(a._id),
          username: String(a.username ?? ""),
          displayName: String(a.displayName ?? a.username ?? ""),
          avatar: typeof a.profilePicture === "string" ? a.profilePicture : null,
          active: a.isActive !== false && a.needsReconnection !== true,
          kind: typeof kind === "string" ? kind : null,
        };
      });
    return {
      ok: true,
      accounts,
      message: accounts.length
        ? `${accounts.length} compte${accounts.length > 1 ? "s" : ""} Instagram connecté${accounts.length > 1 ? "s" : ""} à Zernio`
        : "Aucun compte Instagram connecté à Zernio : zernio.com → Accounts → Instagram",
    };
  } catch (error) {
    return { ok: false, accounts: [], message: `Zernio injoignable : ${error instanceof Error ? error.message : String(error)}` };
  }
}

/** Reel d'une vidéo, pour sa fiche dans la Bibliothèque. */
export async function getLibraryInstagram(videoId: string, channelId: string): Promise<LibraryInstagram> {
  if (IS_MOCK) return { state: null, username: null, pending: false };
  const db = supabaseAdmin();
  const [video, settings, jobs] = await Promise.all([
    db.from("videos").select("instagram").eq("id", videoId).maybeSingle(),
    getInstagramSettings(),
    db.from("jobs").select("id").eq("video_id", videoId).eq("type", "instagram_publish").in("status", ["queued", "running"]).limit(1),
  ]);
  const link = settings.channels[channelId];
  return { state: parseVideoInstagram(video.data?.instagram), username: link?.username || null, pending: (jobs.data ?? []).length > 0 };
}
