/**
 * « Paf, j'achète » côté serveur du dashboard (docs/50-paf-j-achete.md) : réglages, clé du second compte Zernio,
 * vidéo du dossier <DATA_DIR>/paf-j-achete et historique des vendredis (paf_posts, tenu par le worker).
 */
import { mkdir, readdir, stat } from "node:fs/promises";
import { extname, join } from "node:path";

import { IS_MOCK } from "@/lib/data";
import { decryptSecret } from "@/lib/crypto";
import { dataRoot } from "@/lib/files";
import { now, parisAddDays, parisDayKey, parisSlot, parisStartOfWeek } from "@/lib/format";
import {
  DEFAULT_PAF,
  PAF_DEFAULT_HOUR,
  PAF_FOLDER,
  PAF_SECRET,
  PAF_SETTINGS_KEY,
  parsePafSettings,
  type PafAccount,
  type PafOverview,
  type PafPost,
  type PafSettings,
  type PafVideo,
} from "@/lib/paf-types";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { ZERNIO_API, zernioKey } from "@/lib/tiktok";

const LATE_MS = 12 * 3600_000; // vendredi raté : encore publié 12 h après l'heure prévue, jamais après minuit (worker/paf.py)

/** Fin du rattrapage d'un vendredi raté : 12 h après l'heure prévue, au plus tard minuit (heure de Paris). */
function lateLimit(slot: Date): number {
  return Math.min(slot.getTime() + LATE_MS, parisSlot(parisAddDays(slot, 1), "00:00").getTime());
}

/** Le vendredi visé, à l'heure choisie : celui de cette semaine tant qu'il n'est pas trop en retard, sinon le suivant. */
export function nextPafSlot(base: Date = now(), hour: string = PAF_DEFAULT_HOUR): Date {
  const slot = parisSlot(parisAddDays(parisStartOfWeek(base), 4), hour);
  return lateLimit(slot) < base.getTime() ? parisSlot(parisAddDays(slot, 7), hour) : slot;
}

export async function getPafSettings(): Promise<PafSettings> {
  if (IS_MOCK) return DEFAULT_PAF;
  const { data } = await supabaseAdmin().from("app_settings").select("value").eq("key", PAF_SETTINGS_KEY).maybeSingle();
  return parsePafSettings(data?.value);
}

export async function pafKey(): Promise<string | null> {
  const { data } = await supabaseAdmin().from("app_secrets").select("value_encrypted").eq("name", PAF_SECRET).maybeSingle();
  return data?.value_encrypted ? decryptSecret(data.value_encrypted as string) : null;
}

/** Dossier où Luca dépose la vidéo ; créé s'il manque. */
export async function pafFolder(): Promise<string | null> {
  const root = (await dataRoot()) ?? process.env.DATA_DIR ?? null;
  if (!root) return null;
  const dir = join(root, PAF_FOLDER);
  await mkdir(dir, { recursive: true }).catch(() => undefined);
  return dir;
}

/** Le .mp4 le plus récent du dossier : celui que le worker enverra (même règle que worker/paf.py). */
export async function pafVideo(dir: string | null): Promise<(PafVideo & { path: string }) | null> {
  if (!dir) return null;
  const names = await readdir(dir).catch(() => [] as string[]);
  let best: (PafVideo & { path: string; mtime: number }) | null = null;
  for (const name of names) {
    if (extname(name).toLowerCase() !== ".mp4" || name.startsWith(".")) continue;
    const path = join(dir, name);
    const s = await stat(path).catch(() => null);
    if (!s?.isFile()) continue;
    if (!best || s.mtimeMs > best.mtime) best = { name, path, size: s.size, modified: s.mtime.toISOString(), mtime: s.mtimeMs };
  }
  if (!best) return null;
  return { name: best.name, path: best.path, size: best.size, modified: best.modified };
}

export async function getPafOverview(): Promise<PafOverview> {
  if (IS_MOCK) {
    const slot = nextPafSlot();
    return { settings: DEFAULT_PAF, keyHint: null, folder: null, video: null, nextSlot: slot.toISOString(), nextFriday: parisDayKey(slot), posts: [], job: null };
  }
  const db = supabaseAdmin();
  const [settings, secret, posts, jobs, folder] = await Promise.all([
    getPafSettings(),
    db.from("app_secrets").select("hint").eq("name", PAF_SECRET).maybeSingle(),
    db.from("paf_posts").select("friday, status, scheduled_for, url, error, file_name, caption, username, published_at").order("friday", { ascending: false }).limit(30),
    db.from("jobs").select("status, progress_label, error").eq("type", "paf_publish").in("status", ["queued", "running"]).order("created_at", { ascending: false }).limit(1),
    pafFolder(),
  ]);
  const video = await pafVideo(folder);
  const job = jobs.data?.[0];
  const slot = nextPafSlot(now(), settings.hour);
  return {
    settings,
    keyHint: secret.data ? ((secret.data.hint as string | null) ?? "…") : null,
    folder,
    video: video ? { name: video.name, size: video.size, modified: video.modified } : null,
    nextSlot: slot.toISOString(),
    nextFriday: parisDayKey(slot),
    posts: (posts.data ?? []) as PafPost[],
    job: job ? { status: job.status as string, label: (job.progress_label as string | null) ?? null, error: (job.error as string | null) ?? null } : null,
  };
}

/** Instagram du compte Zernio principal (clé de TikTok / @arzakparker) : identifiants et noms, pour les repérer. */
async function mainInstagram(): Promise<{ ids: Set<string>; names: Set<string> }> {
  const found = { ids: new Set<string>(), names: new Set<string>() };
  const secret = await zernioKey().catch(() => null);
  if (!secret) return found;
  try {
    const res = await fetch(`${ZERNIO_API}/accounts`, { headers: { Authorization: `Bearer ${secret}` }, cache: "no-store", signal: AbortSignal.timeout(15_000) });
    if (!res.ok) return found;
    for (const a of ((await res.json()) as { accounts?: Record<string, unknown>[] }).accounts ?? []) {
      if (a.platform !== "instagram") continue;
      if (a.platformUserId) found.ids.add(String(a.platformUserId));
      if (a.username) found.names.add(String(a.username).toLowerCase());
    }
  } catch {
    // compte principal injoignable : rien à comparer
  }
  return found;
}

/** Comptes Instagram du second compte Zernio ; celui qui est aussi sur le compte principal est marqué `sameAsMain`. */
export async function listPafAccounts(key?: string): Promise<{ ok: boolean; accounts: PafAccount[]; message: string }> {
  const secret = key ?? (await pafKey());
  if (!secret) return { ok: false, accounts: [], message: "Coller d’abord la clé Zernio de ce compte" };
  try {
    const [res, main] = await Promise.all([
      fetch(`${ZERNIO_API}/accounts`, { headers: { Authorization: `Bearer ${secret}` }, cache: "no-store", signal: AbortSignal.timeout(15_000) }),
      mainInstagram(),
    ]);
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
          sameAsMain: main.ids.has(String(a.platformUserId ?? "")) || main.names.has(String(a.username ?? "").toLowerCase()),
        };
      });
    const own = accounts.filter((a) => !a.sameAsMain);
    const twin = accounts.find((a) => a.sameAsMain);
    return {
      ok: true,
      accounts,
      message: own.length
        ? `${own.length} compte${own.length > 1 ? "s" : ""} Instagram sur ce compte Zernio`
        : twin
          ? `Ce compte Zernio n’a que @${twin.username}, le même Instagram que le compte principal : y brancher @paf.jachete`
          : "Aucun compte Instagram connecté à ce compte Zernio : zernio.com → Accounts → Instagram",
    };
  } catch (error) {
    return { ok: false, accounts: [], message: `Zernio injoignable : ${error instanceof Error ? error.message : String(error)}` };
  }
}
