/**
 * Onglet Instagram du Dashboard (docs/62-reseaux-et-comptes.md) : les Reels sortis sur chaque compte Instagram relevé
 * (job sync_instagram, tables instagram_* de la migration 0052), leur note par rapport aux autres Reels du compte (mêmes
 * règles que YouTube : lib/stats.ts), les vues par jour d'après les relevés, les Reels déjà programmés. Deux rôles :
 * le compte où partent les Shorts (Réglages → Instagram) et celui de « Paf, j'achète » (docs/50). Serveur uniquement.
 */
import { IS_MOCK } from "@/lib/data";
import { formatDate, now, parisDayKey } from "@/lib/format";
import { getInstagramSettings } from "@/lib/instagram";
import { PAF_ACCOUNT, type InstagramAccountStats, type InstagramStatsPage, type InstagramStatsVideo, type InstagramTotals, type InstagramUpcoming } from "@/lib/instagram-stats-types";
import { parseVideoInstagram } from "@/lib/instagram-types";
import { getLibrary } from "@/lib/library";
import type { LibraryItem } from "@/lib/library-types";
import { getPafSettings, nextPafSlot } from "@/lib/paf";
import { PAF_SECRET } from "@/lib/paf-types";
import { postDailyViews } from "@/lib/post-daily-views";
import { rankVideos } from "@/lib/stats";
import { FLOP_SCORE, STATS_PERIODS, TOP_SCORE, type StatsPeriod } from "@/lib/stats-types";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { ZERNIO_SECRET } from "@/lib/tiktok";
import type { Channel } from "@/lib/types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;
type Query = PromiseLike<{ data: unknown; error: { message?: string } | null }>;

async function rows(q: Query): Promise<Row[]> {
  const { data, error } = await q;
  if (error) throw new Error(error.message ?? String(error));
  return (data as Row[] | null) ?? [];
}

const RANK_WINDOW_DAYS = 90; // comme l'onglet YouTube et l'agent analyste
const WAITING = new Set(["sending", "scheduled", "pending", "publishing", "processing", "uploading", "queued"]);
const num = (v: unknown): number | null => (v === null || v === undefined || v === "" ? null : Number(v));
const pct = (part: number, whole: number): number | null => (whole > 0 ? Math.round((part / whole) * 10000) / 100 : null);

function captionTitle(caption: string | null): string {
  const line = (caption ?? "").split("\n").map((l) => l.replace(/#[\p{L}\p{N}_]+/gu, "").trim()).find(Boolean) ?? "";
  return line ? (line.length > 90 ? `${line.slice(0, 89)}…` : line) : "Reel Instagram";
}

function thumbnailOf(item: LibraryItem | null, fallback: string | null): string | null {
  if (item?.poster_asset_id && !item.files_deleted_at) return `/api/media/${item.poster_asset_id}`;
  if (item?.thumbnail_url) return item.thumbnail_url;
  if (item?.youtube_video_id) return `https://i.ytimg.com/vi/${item.youtube_video_id}/hqdefault.jpg`;
  return fallback;
}

export const pafTitle = (friday: string): string => `Paf, j’achète · ${formatDate(`${friday}T12:00:00Z`, "EEEE d MMMM")}`;

function totalsOf(videos: InstagramStatsVideo[]): InstagramTotals {
  const sum = (f: (v: InstagramStatsVideo) => number | null | undefined) => videos.reduce((s, v) => s + (f(v) ?? 0), 0);
  const known = (f: (v: InstagramStatsVideo) => number | null | undefined) => videos.filter((v) => f(v) !== null && f(v) !== undefined);
  const weighted = (f: (v: InstagramStatsVideo) => number | null | undefined, digits = 1) => {
    const list = known(f);
    const w = list.reduce((s, v) => s + v.views, 0);
    const k = 10 ** digits;
    return w > 0 ? Math.round((list.reduce((s, v) => s + (f(v) ?? 0) * v.views, 0) / w) * k) / k : null;
  };
  const views = sum((v) => v.views);
  const likes = sum((v) => v.likes);
  return {
    videos: videos.length,
    views,
    reach: known((v) => v.reach).length ? sum((v) => v.reach) : null,
    likes,
    comments: sum((v) => v.comments),
    shares: sum((v) => v.shares),
    saves: known((v) => v.saves).length ? sum((v) => v.saves) : null,
    watched_pct: weighted((v) => v.watched_pct),
    hook_pct: weighted((v) => v.hook_pct),
    avg_watch_s: weighted((v) => v.avg_watch_s),
    watch_hours: known((v) => v.total_watch_s).length ? Math.round((sum((v) => v.total_watch_s) / 3600) * 10) / 10 : null,
    like_rate_pct: pct(likes, views),
  };
}

/** Comptes Instagram relevés, avec leur rôle (Shorts d'une chaîne, « Paf, j'achète ») ; le compte de « Paf, j'achète »
 * apparaît même s'il n'est pas encore relevé, avec ce qu'il manque. Sert aussi à la Vue d'ensemble (lib/networks.ts). */
export async function getInstagramAccounts(channels: Channel[]): Promise<{ accounts: InstagramAccountStats[]; configured: boolean; pafEnabled: boolean }> {
  if (IS_MOCK) return { accounts: [], configured: false, pafEnabled: false };
  const db = supabaseAdmin();
  const weekAgo = new Date(now().getTime() - 7 * 86_400_000).toISOString();
  const [settings, paf, secrets, accountRows] = await Promise.all([
    getInstagramSettings(),
    getPafSettings(),
    rows(db.from("app_secrets").select("name").in("name", [ZERNIO_SECRET, PAF_SECRET])).catch(() => [] as Row[]),
    rows(db.from("instagram_accounts").select("*").order("username")).catch(() => [] as Row[]),
  ]);
  const channelName = new Map(channels.map((c) => [c.id, c.name]));
  // id Zernio (de l'un ou l'autre compte Zernio) → id Instagram du compte
  const byZernio = new Map<string, string>();
  for (const a of accountRows) for (const zid of Object.values((a.zernio_ids ?? {}) as Record<string, string>)) byZernio.set(zid, a.id as string);
  const linked = new Map<string, string[]>();
  for (const [cid, link] of Object.entries(settings.channels)) {
    const ig = byZernio.get(link.account_id);
    if (ig) linked.set(ig, [...(linked.get(ig) ?? []), channelName.get(cid) ?? cid]);
  }
  const pafIg = paf.account_id ? (byZernio.get(paf.account_id) ?? null) : null;
  const followersWeekAgo = new Map<string, number>();
  await Promise.all(
    accountRows.map(async (a) => {
      const old = await rows(
        db.from("instagram_account_snapshots").select("followers").eq("account_id", a.id).lte("taken_at", weekAgo).order("taken_at", { ascending: false }).limit(1),
      ).catch(() => [] as Row[]);
      if (old[0] && num(old[0].followers) !== null) followersWeekAgo.set(a.id as string, num(old[0].followers) ?? 0);
    }),
  );

  const accounts: InstagramAccountStats[] = accountRows.map((a) => {
    const id = a.id as string;
    const followers = num(a.followers);
    const isPaf = id === pafIg;
    const channelsOf = linked.get(id) ?? [];
    return {
      id,
      username: (a.username as string) || "?",
      display_name: (a.display_name as string | null) ?? null,
      avatar_url: (a.avatar_url as string | null) ?? null,
      profile_url: (a.profile_url as string | null) ?? `https://www.instagram.com/${a.username}`,
      account_type: (a.account_type as string | null) ?? null,
      followers,
      followers_delta_7d: followers !== null && followersWeekAgo.has(id) ? followers - (followersWeekAgo.get(id) ?? 0) : null,
      media_count: num(a.media_count),
      views_28d: num(a.views_28d),
      reach_28d: num(a.reach_28d),
      interactions_28d: num(a.interactions_28d),
      fetched_at: (a.fetched_at as string | null) ?? null,
      channels: channelsOf,
      paf: isPaf,
      connected: true,
      warning:
        isPaf && channelsOf.length
          ? paf.enabled
            ? "« Paf, j’achète » vise aussi ce compte, interrupteur allumé : vendredi, la vidéo du vendredi partira ici."
            : "L’onglet Paf, j’achète vise aussi ce compte (interrupteur coupé)."
          : null,
    };
  });

  // « Paf, j'achète » sans compte à lui : une place réservée qui dit quoi faire
  if (!pafIg || linked.has(pafIg)) {
    accounts.push({
      id: PAF_ACCOUNT,
      username: pafIg ? "" : paf.username,
      display_name: null,
      avatar_url: null,
      profile_url: null,
      account_type: null,
      followers: null,
      followers_delta_7d: null,
      media_count: null,
      views_28d: null,
      reach_28d: null,
      interactions_28d: null,
      fetched_at: null,
      channels: [],
      paf: true,
      connected: false,
      warning: !paf.account_id
        ? "Pas encore de compte : dans l’onglet Paf, j’achète, colle la clé du second compte Zernio et choisis le compte Instagram."
        : pafIg
          ? `L’onglet Paf, j’achète vise encore @${paf.username || "?"}, le compte des Shorts. Connecte le compte de « Paf, j’achète » au second compte Zernio (zernio.com → Accounts), puis choisis-le dans l’onglet.`
          : `@${paf.username || "?"} n’a pas encore été relevé : ses chiffres arrivent dans l’heure.`,
    });
  }
  return { accounts, configured: secrets.length > 0, pafEnabled: paf.enabled };
}

/** Toute la page pour la chaîne choisie en haut (ses comptes Instagram, plus « Paf, j'achète » qui ne dépend d'aucune
 * chaîne) ou toutes les chaînes (tous les comptes). */
export async function getInstagramStatsPage(channels: Channel[], selected: Channel | undefined, period: StatsPeriod, accountParam?: string): Promise<InstagramStatsPage> {
  const days = STATS_PERIODS.find((p) => p.id === period)?.days ?? null;
  const empty: InstagramStatsPage = {
    period,
    configured: false,
    accounts: [],
    account_id: null,
    videos: [],
    totals: totalsOf([]),
    median_views: null,
    upcoming: [],
    daily: [],
    snapshots_since: null,
    sync: { active: false, since: null, last_done_at: null, last_error: null },
  };
  if (IS_MOCK) return empty;

  const db = supabaseAdmin();
  const [{ accounts: all, configured }, syncJobs, lastFinished, paf, settings] = await Promise.all([
    getInstagramAccounts(channels),
    rows(db.from("jobs").select("status, created_at, started_at").eq("type", "sync_instagram").in("status", ["queued", "running"]).order("created_at")).catch(() => [] as Row[]),
    rows(db.from("jobs").select("status, finished_at, error").eq("type", "sync_instagram").in("status", ["done", "failed"]).order("finished_at", { ascending: false }).limit(1)).catch(
      () => [] as Row[],
    ),
    getPafSettings(),
    getInstagramSettings(),
  ]);
  const sync = {
    active: syncJobs.length > 0,
    since: syncJobs[0]?.started_at ?? syncJobs[0]?.created_at ?? null,
    last_done_at: lastFinished[0]?.status === "done" ? (lastFinished[0].finished_at ?? null) : null,
    last_error: lastFinished[0]?.status === "failed" ? String(lastFinished[0].error ?? "échec") : null,
  };
  const accounts = selected ? all.filter((a) => a.paf || a.channels.includes(selected.name)) : all;
  const pafAccount = accounts.find((a) => a.paf && a.connected) ?? accounts.find((a) => a.paf);
  const accountId = accountParam === PAF_ACCOUNT ? (pafAccount?.id ?? null) : accountParam && accounts.some((a) => a.id === accountParam) ? accountParam : null;
  const scope = (accountId ? [accountId] : accounts.map((a) => a.id)).filter((id) => id !== PAF_ACCOUNT);
  const base = { ...empty, configured, accounts, account_id: accountId, sync };

  // Reels programmés : vidéos de l'appli (videos.instagram) et vendredis de « Paf, j'achète » (paf_posts)
  const [accountRows, igVideos, pafRows] = await Promise.all([
    rows(db.from("instagram_accounts").select("id, zernio_ids")).catch(() => [] as Row[]),
    rows(db.from("videos").select("id, title, instagram").not("instagram", "is", null)).catch(() => [] as Row[]),
    rows(db.from("paf_posts").select("friday, status, scheduled_for, account_id, username").order("friday")).catch(() => [] as Row[]),
  ]);
  const igOfZernio = new Map<string, string>();
  for (const a of accountRows) for (const zid of Object.values((a.zernio_ids ?? {}) as Record<string, string>)) igOfZernio.set(zid, a.id as string);
  const inScope = (zid: unknown) => {
    const ig = igOfZernio.get(String(zid ?? ""));
    return ig ? scope.includes(ig) : !accountId; // compte pas encore relevé : montré avec « tous les comptes »
  };
  const showPaf = !accountId || accountId === pafAccount?.id;
  const upcoming: InstagramUpcoming[] = [
    ...igVideos
      .map((v): InstagramUpcoming | null => {
        const raw = (v.instagram ?? {}) as Record<string, unknown>;
        const t = parseVideoInstagram(raw);
        if (!t || !WAITING.has(t.status) || !inScope(raw.account_id)) return null;
        if (selected && !Object.entries(settings.channels).some(([cid, l]) => cid === selected.id && l.account_id === raw.account_id)) return null;
        return { key: v.id as string, video_id: v.id as string, title: (v.title as string | null) ?? "Sans titre", scheduled_for: t.scheduled_for, username: t.username, paf: false };
      })
      .filter((u): u is InstagramUpcoming => u !== null),
    ...(showPaf
      ? pafRows
          .filter((p) => WAITING.has(String(p.status)) && new Date(String(p.scheduled_for ?? `${p.friday}T23:59:00+02:00`)).getTime() > now().getTime() - 3600_000)
          .map((p): InstagramUpcoming => ({ key: `paf-${p.friday}`, video_id: null, title: pafTitle(String(p.friday)), scheduled_for: (p.scheduled_for as string | null) ?? null, username: (p.username as string | null) ?? null, paf: true }))
      : []),
  ];
  // « Paf, j'achète » allumé : le prochain vendredi est prévu même si sa ligne n'existe pas encore (créée 48 h avant)
  const slot = nextPafSlot(now(), paf.hour);
  const slotDay = parisDayKey(slot);
  if (showPaf && paf.enabled && paf.account_id && !upcoming.some((u) => u.paf && u.key.startsWith(`paf-${slotDay}`)) && !pafRows.some((p) => String(p.friday) === slotDay)) {
    upcoming.push({ key: `paf-${slotDay}`, video_id: null, title: pafTitle(slotDay), scheduled_for: slot.toISOString(), username: paf.username || null, paf: true });
  }
  upcoming.sort((a, b) => (a.scheduled_for ?? "").localeCompare(b.scheduled_for ?? ""));
  if (!scope.length) return { ...base, upcoming };

  const [postRows, { items }, tiktokRows] = await Promise.all([
    rows(db.from("instagram_posts").select("*").in("account_id", scope).not("published_at", "is", null)),
    getLibrary(), // toutes les chaînes : un compte Instagram peut servir à plusieurs chaînes YouTube
    rows(db.from("tiktok_posts").select("video_id, views").not("video_id", "is", null)).catch(() => [] as Row[]),
  ]);
  const byId = new Map(items.map((v) => [v.id, v]));
  const tiktokViews = new Map<string, number>();
  for (const t of tiktokRows) tiktokViews.set(t.video_id as string, (tiktokViews.get(t.video_id as string) ?? 0) + Number(t.views ?? 0));
  const username = new Map(accounts.map((a) => [a.id, a.username]));
  const nowMs = now().getTime();

  const list = postRows.map((p) => {
    const item = p.video_id ? (byId.get(p.video_id as string) ?? null) : null;
    const duration = item?.duration_s ?? num(p.duration_s);
    const avgWatch = num(p.avg_watch_s);
    const skip = num(p.skip_rate_pct);
    const friday = (p.paf_friday as string | null) ?? null;
    return {
      id: p.id as string,
      account_id: p.account_id as string,
      username: username.get(p.account_id as string) ?? "?",
      video_id: (p.video_id as string | null) ?? null,
      item,
      paf_friday: friday,
      title: item?.title ?? (friday ? pafTitle(friday) : captionTitle((p.caption as string | null) ?? null)),
      url: (p.url as string | null) ?? null,
      thumbnail: thumbnailOf(item, (p.thumbnail_url as string | null) ?? null),
      published_at: p.published_at as string,
      age_h: Math.max(0, (nowMs - new Date(p.published_at as string).getTime()) / 3_600_000),
      duration_s: duration,
      origin: (item ? item.origin : "imported") as "app" | "imported",
      recipe: item?.recipe ?? null,
      series_name: item?.series_name ?? null,
      views: Number(p.views ?? 0),
      views_pending: p.sync_status === "live",
      reach: num(p.reach),
      likes: Number(p.likes ?? 0),
      comments: Number(p.comments ?? 0),
      shares: Number(p.shares ?? 0),
      saves: num(p.saves),
      avg_watch_s: avgWatch,
      total_watch_s: num(p.total_watch_s),
      watched_pct: avgWatch !== null && duration ? Math.round((avgWatch / duration) * 1000) / 10 : null,
      hook_pct: skip !== null ? Math.round((100 - skip) * 10) / 10 : null,
      views_24h: num(p.views_24h),
      views_7d: num(p.views_7d),
      youtube_views: item?.youtube_video_id ? item.views : null,
      tiktok_views: p.video_id ? (tiktokViews.get(p.video_id as string) ?? null) : null,
    };
  });

  // Note sur les 90 derniers jours du périmètre (comme les autres onglets), affichage sur la période choisie
  const ranks = rankVideos(list.filter((v) => v.age_h <= RANK_WINDOW_DAYS * 24 && !v.views_pending));
  const med = [...ranks.values()][0]?.median ?? null;
  const videos: InstagramStatsVideo[] = list
    .filter((v) => days === null || v.age_h <= days * 24)
    .map((v) => {
      const r = ranks.get(v.id);
      const comparable = r?.comparable ?? (v.views_7d !== null && v.age_h >= 7 * 24 ? v.views_7d : v.views);
      const score = v.views_pending ? null : (r?.score ?? (med !== null ? Math.round((comparable / Math.max(med, 1)) * 100) / 100 : null));
      if (v.views_pending) return { ...v, comparable_views: comparable, score, verdict: "trop récente" as const, like_rate_pct: null, engagement_pct: null };
      return {
        ...v,
        comparable_views: comparable,
        score,
        verdict: r?.verdict ?? (score === null ? "moyen" : score >= TOP_SCORE ? "top" : score <= FLOP_SCORE ? "flop" : "moyen"),
        like_rate_pct: pct(v.likes, v.views),
        engagement_pct: pct(v.likes + v.comments + v.shares + (v.saves ?? 0), v.views),
      };
    })
    .sort((a, b) => b.published_at.localeCompare(a.published_at));

  const { daily, since } = await postDailyViews(
    "instagram",
    list.map((v) => ({ id: v.id, published_at: v.published_at })),
    days ?? 90,
  );
  return { ...base, upcoming, videos, totals: totalsOf(videos), median_views: med, daily, snapshots_since: since };
}
