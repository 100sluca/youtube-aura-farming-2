/**
 * Onglet TikTok du Dashboard (docs/39-tiktok-partout.md) : les vidéos sorties sur chaque compte TikTok relié, avec leurs
 * chiffres relevés chaque heure par le worker (job sync_tiktok, tables tiktok_* de la migration 0026), leur note par
 * rapport aux autres vidéos du compte (mêmes règles que YouTube : lib/stats.ts), les vues par jour d'après les relevés,
 * les publications déjà programmées. Serveur uniquement.
 */
import { IS_MOCK } from "@/lib/data";
import { now, parisAddDays, parisDayKey } from "@/lib/format";
import { getLibrary } from "@/lib/library";
import type { LibraryItem } from "@/lib/library-types";
import { rankVideos } from "@/lib/stats";
import { FLOP_SCORE, STATS_PERIODS, TOP_SCORE, type StatsPeriod } from "@/lib/stats-types";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { getTikTokSettings, getZernioKeyHint } from "@/lib/tiktok";
import type { TikTokAccountStats, TikTokStatsPage, TikTokStatsVideo, TikTokTotals, TikTokUpcoming } from "@/lib/tiktok-stats-types";
import { parseVideoTikTok } from "@/lib/tiktok-types";
import type { Channel } from "@/lib/types";
import { lastDays, type DayViews } from "@/lib/views-series";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;
type Query = PromiseLike<{ data: unknown; error: { message?: string } | null }>;

async function rows(q: Query): Promise<Row[]> {
  const { data, error } = await q;
  if (error) throw new Error(error.message ?? String(error));
  return (data as Row[] | null) ?? [];
}

/** Toutes les lignes d'une requête, par pages de 1 000 (limite de PostgREST). */
async function allRows(page: (from: number, to: number) => Query): Promise<Row[]> {
  const out: Row[] = [];
  for (let from = 0; ; from += 1000) {
    const chunk = await rows(page(from, from + 999));
    out.push(...chunk);
    if (chunk.length < 1000) return out;
  }
}

const RANK_WINDOW_DAYS = 90; // comme l'onglet YouTube et l'agent analyste
const WAITING = new Set(["sending", "scheduled", "pending", "publishing", "processing", "uploading"]);
const num = (v: unknown): number | null => (v === null || v === undefined || v === "" ? null : Number(v));
const pct = (part: number, whole: number): number | null => (whole > 0 ? Math.round((part / whole) * 10000) / 100 : null);
const previousDay = (day: string): string => parisDayKey(parisAddDays(`${day}T12:00:00Z`, -1));

/** Titre d'une vidéo publiée à la main dans TikTok : la première ligne de sa légende, sans les hashtags. */
function captionTitle(caption: string | null): string {
  const line = (caption ?? "").split("\n").map((l) => l.replace(/#[\p{L}\p{N}_]+/gu, "").trim()).find(Boolean) ?? "";
  return line ? (line.length > 90 ? `${line.slice(0, 89)}…` : line) : "Vidéo TikTok";
}

function thumbnailOf(item: LibraryItem | null, fallback: string | null): string | null {
  if (item?.poster_asset_id && !item.files_deleted_at) return `/api/media/${item.poster_asset_id}`;
  if (item?.thumbnail_url) return item.thumbnail_url;
  if (item?.youtube_video_id) return `https://i.ytimg.com/vi/${item.youtube_video_id}/hqdefault.jpg`;
  return fallback;
}

function totalsOf(videos: TikTokStatsVideo[]): TikTokTotals {
  const sum = (f: (v: TikTokStatsVideo) => number | null | undefined) => videos.reduce((s, v) => s + (f(v) ?? 0), 0);
  const known = (f: (v: TikTokStatsVideo) => number | null | undefined) => videos.filter((v) => f(v) !== null && f(v) !== undefined);
  const weighted = (f: (v: TikTokStatsVideo) => number | null | undefined, digits = 1) => {
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
    likes,
    comments: sum((v) => v.comments),
    shares: sum((v) => v.shares),
    saves: known((v) => v.saves).length ? sum((v) => v.saves) : null,
    follows: known((v) => v.follows).length ? sum((v) => v.follows) : null,
    watched_pct: weighted((v) => v.watched_pct),
    completion_pct: weighted((v) => v.completion_pct),
    avg_watch_s: weighted((v) => v.avg_watch_s),
    for_you_pct: weighted((v) => v.for_you_pct, 0),
    watch_hours: known((v) => v.total_watch_s).length ? Math.round((sum((v) => v.total_watch_s) / 3600) * 10) / 10 : null,
    like_rate_pct: pct(likes, views),
    youtube_views: known((v) => v.youtube_views).length ? sum((v) => v.youtube_views) : null,
  };
}

/** Vues par jour (heure de Paris) d'après les relevés horaires : différence entre deux fins de journée. Un jour reste
 * « inconnu » s'il manque un relevé pour une vidéo déjà en ligne ; une vidéo retirée de TikTok (plus relevée) ne compte
 * plus. Pas d'équivalent de YouTube Analytics : tout est estimé d'après les relevés. */
async function dailyViews(posts: { id: string; published_at: string }[], days: number): Promise<{ daily: DayViews[]; since: string | null }> {
  const keys = lastDays(days);
  if (!posts.length) return { daily: keys.map((day) => ({ day, views: 0, source: "estimate" as const })), since: null };
  const db = supabaseAdmin();
  const ids = posts.map((p) => p.id);
  const [snaps, first] = await Promise.all([
    allRows((a, b) => db.from("v_tiktok_post_daily_snapshots").select("post_id, day, views").in("post_id", ids).gte("day", previousDay(keys[0])).range(a, b)),
    rows(db.from("tiktok_post_snapshots").select("taken_at").in("post_id", ids).order("taken_at").limit(1)),
  ]);
  const endOfDay = new Map<string, number>();
  const lastSeen = new Map<string, string>();
  let latest = "";
  for (const s of snaps) {
    endOfDay.set(`${s.post_id}|${s.day}`, Number(s.views ?? 0));
    if ((lastSeen.get(s.post_id) ?? "") < s.day) lastSeen.set(s.post_id, s.day);
    if (s.day > latest) latest = s.day;
  }
  const vids = posts.map((p) => ({ id: p.id, pubDay: parisDayKey(p.published_at) }));
  const daily = keys.map((day): DayViews => {
    if (!latest || day > latest) return { day, views: null, source: "unknown" }; // pas encore de relevé ce jour-là
    let total = 0;
    for (const v of vids) {
      if (v.pubDay > day) continue;
      const end = endOfDay.get(`${v.id}|${day}`);
      if (end === undefined && (lastSeen.get(v.id) ?? "") < day) continue; // plus relevée : retirée de TikTok
      const start = v.pubDay === day ? 0 : endOfDay.get(`${v.id}|${previousDay(day)}`);
      if (end === undefined || start === undefined) return { day, views: null, source: "unknown" };
      total += Math.max(0, end - start); // les compteurs publics redescendent parfois
    }
    return { day, views: total, source: "estimate" };
  });
  return { daily, since: (first[0]?.taken_at as string | undefined) ?? null };
}

/** Toute la page pour la chaîne choisie en haut (son compte TikTok relié) ou toutes les chaînes (tous les comptes). */
export async function getTikTokStatsPage(channels: Channel[], selected: Channel | undefined, period: StatsPeriod, accountParam?: string): Promise<TikTokStatsPage> {
  const days = STATS_PERIODS.find((p) => p.id === period)?.days ?? null;
  const empty: TikTokStatsPage = {
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
  const [hint, settings, accountRows, syncJobs, lastFinished] = await Promise.all([
    getZernioKeyHint(),
    getTikTokSettings(),
    rows(db.from("tiktok_accounts").select("*").order("username")).catch(() => [] as Row[]),
    rows(db.from("jobs").select("status, created_at, started_at").eq("type", "sync_tiktok").in("status", ["queued", "running"]).order("created_at")).catch(() => [] as Row[]),
    rows(db.from("jobs").select("status, finished_at, error").eq("type", "sync_tiktok").in("status", ["done", "failed"]).order("finished_at", { ascending: false }).limit(1)).catch(
      () => [] as Row[],
    ),
  ]);
  const sync = {
    active: syncJobs.length > 0,
    since: syncJobs[0]?.started_at ?? syncJobs[0]?.created_at ?? null,
    last_done_at: lastFinished[0]?.status === "done" ? (lastFinished[0].finished_at ?? null) : null,
    last_error: lastFinished[0]?.status === "failed" ? String(lastFinished[0].error ?? "échec") : null,
  };

  // Comptes du périmètre : celui relié à la chaîne choisie, sinon tous les comptes relevés (et ceux reliés pas encore relevés)
  const channelName = new Map(channels.map((c) => [c.id, c.name]));
  const linkedTo = new Map<string, string[]>();
  for (const [cid, link] of Object.entries(settings.channels)) {
    if (link.account_id) linkedTo.set(link.account_id, [...(linkedTo.get(link.account_id) ?? []), channelName.get(cid) ?? cid]);
  }
  const wanted = selected ? [settings.channels[selected.id]?.account_id].filter((id): id is string => Boolean(id)) : [...new Set([...accountRows.map((a) => a.id as string), ...linkedTo.keys()])];
  const weekAgo = new Date(now().getTime() - 7 * 86_400_000).toISOString();
  const accounts: TikTokAccountStats[] = await Promise.all(
    wanted.map(async (id): Promise<TikTokAccountStats> => {
      const a = accountRows.find((r) => r.id === id);
      const old = await rows(
        db.from("tiktok_account_snapshots").select("followers").eq("account_id", id).lte("taken_at", weekAgo).order("taken_at", { ascending: false }).limit(1),
      ).catch(() => [] as Row[]);
      const followers = num(a?.followers);
      const username = (a?.username as string | undefined) || Object.values(settings.channels).find((c) => c.account_id === id)?.username || "?";
      return {
        id,
        username,
        display_name: (a?.display_name as string | null) ?? null,
        avatar_url: (a?.avatar_url as string | null) ?? null,
        profile_url: (a?.profile_url as string | null) ?? `https://www.tiktok.com/@${username}`,
        business: (a?.business as boolean | null) ?? null,
        followers,
        followers_delta_7d: followers !== null && old[0] && num(old[0].followers) !== null ? followers - (num(old[0].followers) ?? 0) : null,
        likes: num(a?.likes),
        videos: num(a?.videos),
        fetched_at: (a?.fetched_at as string | null) ?? null,
        zernio_synced_at: (a?.zernio_synced_at as string | null) ?? null,
        channels: linkedTo.get(id) ?? [],
      };
    }),
  );
  const accountId = accountParam && accounts.some((a) => a.id === accountParam) ? accountParam : null;
  const scope = accountId ? [accountId] : accounts.map((a) => a.id);
  const base = { ...empty, configured: Boolean(hint), accounts, account_id: accountId, sync };
  if (!scope.length) return base;

  const [postRows, { items }, tiktokVideos] = await Promise.all([
    rows(db.from("tiktok_posts").select("*").in("account_id", scope).not("published_at", "is", null)),
    getLibrary(), // toutes les chaînes : un compte TikTok peut servir à plusieurs chaînes YouTube
    rows(db.from("videos").select("id, title, tiktok").not("tiktok", "is", null)),
  ]);
  const byId = new Map(items.map((v) => [v.id, v]));
  const username = new Map(accounts.map((a) => [a.id, a.username]));
  const nowMs = now().getTime();

  const all = postRows.map((p) => {
    const item = p.video_id ? (byId.get(p.video_id as string) ?? null) : null;
    const duration = item?.duration_s ?? null;
    const avgWatch = num(p.avg_watch_s);
    const views = Number(p.views ?? 0);
    const sources = (p.impression_sources ?? null) as Record<string, number> | null;
    return {
      id: p.id as string,
      account_id: p.account_id as string,
      username: username.get(p.account_id as string) ?? "?",
      video_id: (p.video_id as string | null) ?? null,
      item,
      title: item?.title ?? captionTitle((p.caption as string | null) ?? null),
      url: (p.url as string | null) ?? null,
      thumbnail: thumbnailOf(item, (p.thumbnail_url as string | null) ?? null),
      published_at: p.published_at as string,
      age_h: Math.max(0, (nowMs - new Date(p.published_at as string).getTime()) / 3_600_000),
      duration_s: duration,
      origin: (item ? item.origin : "imported") as "app" | "imported",
      recipe: item?.recipe ?? null,
      series_name: item?.series_name ?? null,
      views,
      views_pending: p.sync_status === "live",
      likes: Number(p.likes ?? 0),
      comments: Number(p.comments ?? 0),
      shares: Number(p.shares ?? 0),
      saves: num(p.saves),
      reach: num(p.reach),
      follows: num(p.follows),
      profile_views: num(p.profile_views),
      avg_watch_s: avgWatch,
      total_watch_s: num(p.total_watch_s),
      completion_pct: num(p.completion_pct),
      watched_pct: avgWatch !== null && duration ? Math.round((avgWatch / duration) * 1000) / 10 : null,
      for_you_pct: sources && typeof sources.forYou === "number" ? Math.round(sources.forYou * 1000) / 10 : null,
      views_24h: num(p.views_24h),
      views_7d: num(p.views_7d),
      youtube_views: item?.youtube_video_id ? item.views : null,
      business_pending: p.completion_pct === null && p.avg_watch_s === null && !sources,
    };
  });

  // Note sur les 90 derniers jours du périmètre (comme l'onglet YouTube), affichage sur la période choisie ; une vidéo dont
  // Zernio n'a pas encore relevé les vues n'est pas notée
  const ranks = rankVideos(all.filter((v) => v.age_h <= RANK_WINDOW_DAYS * 24 && !v.views_pending));
  const med = [...ranks.values()][0]?.median ?? null;
  const videos: TikTokStatsVideo[] = all
    .filter((v) => days === null || v.age_h <= days * 24)
    .map((v) => {
      const r = ranks.get(v.id);
      const comparable = r?.comparable ?? (v.views_7d !== null && v.age_h >= 7 * 24 ? v.views_7d : v.views);
      const score = v.views_pending ? null : (r?.score ?? (med !== null ? Math.round((comparable / Math.max(med, 1)) * 100) / 100 : null));
      if (v.views_pending) {
        return { ...v, comparable_views: comparable, score, verdict: "trop récente" as const, like_rate_pct: null, engagement_pct: null };
      }
      return {
        ...v,
        comparable_views: comparable,
        score,
        // hors de la fenêtre de 90 jours (période « Tout ») : verdict aux seuils, comme l'onglet YouTube
        verdict: r?.verdict ?? (score === null ? "moyen" : score >= TOP_SCORE ? "top" : score <= FLOP_SCORE ? "flop" : "moyen"),
        like_rate_pct: pct(v.likes, v.views),
        engagement_pct: pct(v.likes + v.comments + v.shares, v.views),
      };
    })
    .sort((a, b) => b.published_at.localeCompare(a.published_at));

  // Publications prévues sur les comptes du périmètre, pas encore sorties
  const upcoming: TikTokUpcoming[] = tiktokVideos
    .map((v) => {
      const raw = (v.tiktok ?? {}) as Record<string, unknown>;
      const t = parseVideoTikTok(raw);
      return t && WAITING.has(t.status) && scope.includes(String(raw.account_id ?? ""))
        ? { video_id: v.id as string, title: (v.title as string | null) ?? null, scheduled_for: t.scheduled_for, source: t.source, username: t.username, status: t.status }
        : null;
    })
    .filter((u): u is TikTokUpcoming => u !== null)
    .sort((a, b) => (a.scheduled_for ?? "").localeCompare(b.scheduled_for ?? ""));

  const { daily, since } = await dailyViews(
    all.map((v) => ({ id: v.id, published_at: v.published_at })),
    days ?? 90,
  );

  return {
    ...base,
    videos,
    totals: totalsOf(videos),
    median_views: med,
    upcoming,
    daily,
    snapshots_since: since,
  };
}

