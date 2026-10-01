/**
 * « Paf, j'achète » côté serveur du dashboard (docs/50-paf-j-achete.md) : réglages, clé du second compte Zernio,
 * vidéo du dossier <DATA_DIR>/paf-j-achete et historique des vendredis (paf_posts, tenu par le worker).
 */
import { mkdir, readdir, stat } from "node:fs/promises";
import { extname, join } from "node:path";

import { IS_MOCK } from "@/lib/data";
import { decryptSecret } from "@/lib/crypto";
import { dataRoot } from "@/lib/files";
import { now, parisAddDays, parisSlot, parisStartOfWeek } from "@/lib/format";
import {
  DEFAULT_PAF,
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
import { ZERNIO_API } from "@/lib/tiktok";

const LATE_MS = 12 * 3600_000; // vendredi raté : encore publié jusqu'à 19 h (worker/paf.py)

/** Le vendredi 7 h visé : celui de cette semaine tant qu'il n'a pas plus de 12 h de retard, sinon le suivant. */
export function nextPafSlot(base: Date = now()): Date {
  const slot = parisSlot(parisAddDays(parisStartOfWeek(base), 4), "07:00");
  return slot.getTime() + LATE_MS < base.getTime() ? parisSlot(parisAddDays(slot, 7), "07:00") : slot;
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
  const nextSlot = nextPafSlot().toISOString();
  if (IS_MOCK) return { settings: DEFAULT_PAF, keyHint: null, folder: null, video: null, nextSlot, posts: [], job: null };
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
  return {
    settings,
    keyHint: secret.data ? ((secret.data.hint as string | null) ?? "…") : null,
    folder,
    video: video ? { name: video.name, size: video.size, modified: video.modified } : null,
    nextSlot,
    posts: (posts.data ?? []) as PafPost[],
    job: job ? { status: job.status as string, label: (job.progress_label as string | null) ?? null, error: (job.error as string | null) ?? null } : null,
  };
}

/** Comptes Instagram du second compte Zernio. */
export async function listPafAccounts(key?: string): Promise<{ ok: boolean; accounts: PafAccount[]; message: string }> {
  const secret = key ?? (await pafKey());
  if (!secret) return { ok: false, accounts: [], message: "Coller d’abord la clé Zernio de ce compte" };
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
      message: accounts.length ? `${accounts.length} compte${accounts.length > 1 ? "s" : ""} Instagram sur ce compte Zernio` : "Aucun compte Instagram connecté à ce compte Zernio : zernio.com → Accounts → Instagram",
    };
  } catch (error) {
    return { ok: false, accounts: [], message: `Zernio injoignable : ${error instanceof Error ? error.message : String(error)}` };
  }
}
