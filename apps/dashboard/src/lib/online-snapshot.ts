/**
 * Instantané pour le site en ligne (docs/65-site-en-ligne.md) : les chiffres de toutes les chaînes et de tous les comptes
 * (YouTube, TikTok, Instagram), les dernières vidéos sorties avec leurs vues sur chaque réseau, la fabrication en cours
 * (avancement, fin estimée) et l'état de la machine, en un seul JSON. Le dashboard le pousse toutes les 5 minutes vers
 * le Worker Cloudflare d'apps/online (lib/online-push.ts), qui le sert derrière un mot de passe. Serveur uniquement.
 *
 * Rien de secret ici : pas de clé, pas d'e-mail, pas de fichier du PC (les vignettes sont celles de YouTube, TikTok et
 * Instagram). Les erreurs d'une partie n'empêchent pas les autres de partir (`safe`).
 */
import { getChannels, getOverviewKpis, getSchedule } from "@/lib/data";
import { now } from "@/lib/format";
import { getInstagramStatsPage } from "@/lib/instagram-stats";
import type { InstagramStatsVideo } from "@/lib/instagram-stats-types";
import type { NetworkAccount } from "@/lib/network-types";
import { getNetworkAccounts } from "@/lib/networks";
import { getResearchOverview } from "@/lib/research";
import { getDiscovery, type DiscoveryData } from "@/lib/research-discovery";
import { thumbUrl, type ResearchOverview, type ResearchReport, type ResearchVideo } from "@/lib/research-types";
import { getStatsPage } from "@/lib/stats";
import type { StatsVideo, Verdict } from "@/lib/stats-types";
import { getSystemStatus } from "@/lib/system";
import { getTaskBoard } from "@/lib/tasks";
import type { TaskProduction } from "@/lib/task-types";
import { getTikTokStatsPage } from "@/lib/tiktok-stats";
import type { TikTokStatsVideo } from "@/lib/tiktok-stats-types";
import type { OverviewKpis } from "@/lib/types";
import type { DayViews } from "@/lib/views-series";

export const ONLINE_SNAPSHOT_VERSION = 1;
const VIDEO_LIMIT = 40;

type Day = { day: string; views: number | null };

export interface OnlinePlatformStats {
  views: number | null;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  /** Durée moyenne regardée ÷ durée (YouTube : rétention moyenne ; TikTok, Instagram : peut dépasser 100 %). */
  watched_pct: number | null;
  /** Encore là à 3 s (YouTube, Instagram). */
  hook_pct: number | null;
  /** Vue jusqu'au bout (YouTube : encore là à la fin ; TikTok : part terminée). */
  end_pct: number | null;
  avg_watch_s: number | null;
  views_24h: number | null;
  views_7d: number | null;
  subscribers_gained: number | null;
  verdict: Verdict;
  score: number | null;
  url: string | null;
  pending: boolean;
}

export interface OnlineVideo {
  key: string;
  title: string;
  published_at: string;
  channel: string | null;
  recipe: string | null;
  series: string | null;
  duration_s: number | null;
  thumbnail: string | null;
  youtube: OnlinePlatformStats | null;
  tiktok: OnlinePlatformStats | null;
  instagram: OnlinePlatformStats | null;
  /** Avis de l'agent analyste (YouTube). */
  insight: string | null;
}

export interface OnlineProduction {
  id: string;
  title: string;
  channel: string | null;
  series: string | null;
  group: "running" | "queued" | "preparing" | "paused" | "waiting" | "failed";
  stage: string;
  progress_pct: number;
  step_progress: number | null;
  step_started_at: string | null;
  eta_at: string | null;
  queue_position: number | null;
  clips_done: number;
  clips_total: number;
  error: string | null;
  updated_at: string;
}

export interface OnlineSnapshot {
  version: number;
  generated_at: string;
  errors: string[];
  machine: {
    worker: string;
    worker_beat_s: number | null;
    comfy: string;
    comfy_queue: number | null;
    ram_free_gb: number;
    ram_total_gb: number;
    vram_used_mb: number | null;
    vram_total_mb: number | null;
    gpu_job: { label: string; started_at: string | null } | null;
    warnings: string[];
  } | null;
  youtube: {
    kpis: OverviewKpis | null;
    subscribers: number | null;
    subscribers_delta_7d: number | null;
    totals: Record<string, number | null> | null;
    median_views: number | null;
    scheduled: number;
    analytics_through: string | null;
    counters_at: string | null;
    daily: Day[];
    analysis: { created_at: string; summary: string | null; findings: string[]; proposed: number; active: number } | null;
  } | null;
  tiktok: { configured: boolean; totals: Record<string, number | null> | null; daily: Day[]; followers: number | null; synced_at: string | null } | null;
  instagram: { configured: boolean; totals: Record<string, number | null> | null; daily: Day[]; followers: number | null; synced_at: string | null } | null;
  networks: NetworkAccount[];
  videos: OnlineVideo[];
  production: {
    items: OnlineProduction[];
    review_videos: number;
    queue_end_at: string | null;
    other_jobs: { label: string; status: string; progress: number; detail: string | null; started_at: string | null }[];
    retouches: { title: string; what: string; stage: string; status: string; progress_pct: number; eta_at: string | null }[];
    failed_jobs: number;
  } | null;
  upcoming: { at: string; title: string; channel: string | null; platforms: string[] }[];
  research: OnlineResearch | null;
}

/** Page Recherche (docs/60, 63, 64), en lecture : le rapport du stratège, les 40 meilleures niches et leur courbe, les 30
 * vidéos à reproduire avec ce que Gemini en a vu, les chaînes qui percent (Découverte) et les questions posées au stratège. */
export interface OnlineResearch {
  report: (ResearchReport["report"] & { created_at: string }) | null;
  niches: {
    id: string;
    slug: string;
    label: string;
    description: string | null;
    status: string;
    origin: string;
    phase: string | null;
    phase_reason: string | null;
    score: number | null;
    effort: number | null;
    formats: string[];
    median_views_month: number | null;
    hits_month: number | null;
    open_share_month: number | null;
    curve: { month: string; median_views: number | null; hits: number }[];
  }[];
  videos: {
    id: string;
    url: string;
    thumbnail: string;
    title: string;
    lang: string | null;
    channel: string | null;
    channel_subs: number | null;
    published_at: string | null;
    duration_s: number | null;
    views: number;
    views_per_day: number;
    outlier: number | null;
    remake_score: number;
    niche: string | null;
    status: string;
    format: string | null;
    effort: number | null;
    summary: string | null;
    hook: string | null;
    why: string[];
    remake: { title: string; premise: string; hook: string } | null;
    adaptation: string | null;
  }[];
  discovery: {
    niche: string;
    category: string;
    revenue: number;
    langs: string[];
    channels: { title: string; lang: string | null; months: number | null; subs: number | null; monthly_views: number | null; revenue: number | null; rpm: number | null; format: string; why: string; url: string }[];
  }[];
  asks: { question: string; status: string; answer: string | null; at: string }[];
  running: string[];
}

async function safe<T>(errors: string[], label: string, fn: () => Promise<T>): Promise<T | null> {
  try {
    return await fn();
  } catch (e) {
    errors.push(`${label} : ${e instanceof Error ? e.message : String(e)}`);
    return null;
  }
}

/** Les vignettes servies par le PC (/api/media/…) ne s'ouvrent pas en ligne : seules celles des plateformes restent. */
const remote = (url: string | null | undefined): string | null => (url && /^https?:\/\//.test(url) ? url : null);

const days = (list: DayViews[] | undefined): Day[] => (list ?? []).map((d) => ({ day: d.day, views: d.views }));

function numbers(obj: object | null | undefined): Record<string, number | null> | null {
  if (!obj) return null;
  const out: Record<string, number | null> = {};
  for (const [k, v] of Object.entries(obj)) if (typeof v === "number" || v === null) out[k] = v;
  return out;
}

function fromYouTube(v: StatsVideo): OnlinePlatformStats {
  return {
    views: v.views,
    likes: v.likes,
    comments: v.comments,
    shares: v.shares ?? null,
    watched_pct: v.average_view_pct ?? null,
    hook_pct: v.hook_retention_pct ?? null,
    end_pct: v.end_retention_pct ?? null,
    avg_watch_s: v.average_view_duration_s ?? null,
    views_24h: v.views_24h ?? null,
    views_7d: v.views_7d ?? null,
    subscribers_gained: v.subscribers_gained ?? null,
    verdict: v.verdict,
    score: v.score,
    url: v.youtube_video_id ? `https://www.youtube.com/shorts/${v.youtube_video_id}` : null,
    pending: false,
  };
}

function fromTikTok(v: TikTokStatsVideo): OnlinePlatformStats {
  return {
    views: v.views_pending ? null : v.views,
    likes: v.likes,
    comments: v.comments,
    shares: v.shares,
    watched_pct: v.watched_pct,
    hook_pct: null,
    end_pct: v.completion_pct,
    avg_watch_s: v.avg_watch_s,
    views_24h: v.views_24h,
    views_7d: v.views_7d,
    subscribers_gained: v.follows,
    verdict: v.verdict,
    score: v.score,
    url: v.url,
    pending: v.views_pending,
  };
}

function fromInstagram(v: InstagramStatsVideo): OnlinePlatformStats {
  return {
    views: v.views_pending ? null : v.views,
    likes: v.likes,
    comments: v.comments,
    shares: v.shares,
    watched_pct: v.watched_pct,
    hook_pct: v.hook_pct,
    end_pct: null,
    avg_watch_s: v.avg_watch_s,
    views_24h: v.views_24h,
    views_7d: v.views_7d,
    subscribers_gained: null,
    verdict: v.verdict,
    score: v.score,
    url: v.url,
    pending: v.views_pending,
  };
}

/** Une ligne par vidéo : la même vidéo de l'appli sur YouTube, TikTok et Instagram réunie ; une publication faite à la
 * main (sans vidéo de l'appli) garde sa ligne à elle. Plus récentes d'abord. */
function mergeVideos(yt: StatsVideo[], tt: TikTokStatsVideo[], ig: InstagramStatsVideo[]): OnlineVideo[] {
  const byKey = new Map<string, OnlineVideo>();
  const base = (key: string, title: string, published_at: string): OnlineVideo => ({
    key,
    title,
    published_at,
    channel: null,
    recipe: null,
    series: null,
    duration_s: null,
    thumbnail: null,
    youtube: null,
    tiktok: null,
    instagram: null,
    insight: null,
  });
  for (const v of yt) {
    const row = base(v.id, v.title ?? "Sans titre", v.published_at ?? "");
    row.channel = v.channel_name ?? null;
    row.recipe = v.recipe ?? null;
    row.series = v.series_name ?? null;
    row.duration_s = v.duration_s;
    row.thumbnail = remote(v.thumbnail_url) ?? (v.youtube_video_id ? `https://i.ytimg.com/vi/${v.youtube_video_id}/hqdefault.jpg` : null);
    row.youtube = fromYouTube(v);
    row.insight = v.insight?.why ?? null;
    byKey.set(v.id, row);
  }
  const attach = (key: string, title: string, published_at: string, extra: Partial<OnlineVideo>) => {
    const row = byKey.get(key) ?? base(key, title, published_at);
    for (const [k, val] of Object.entries(extra)) {
      const field = k as keyof OnlineVideo;
      if (val !== null && val !== undefined && (row[field] === null || row[field] === undefined)) (row as unknown as Record<string, unknown>)[field] = val;
    }
    if (published_at && (!row.published_at || published_at < row.published_at)) row.published_at = published_at;
    byKey.set(key, row);
  };
  for (const v of tt) {
    attach(v.video_id ?? `tiktok:${v.id}`, v.title, v.published_at, {
      tiktok: fromTikTok(v),
      recipe: v.recipe,
      series: v.series_name,
      duration_s: v.duration_s,
      thumbnail: remote(v.thumbnail),
    });
  }
  for (const v of ig) {
    attach(v.video_id ?? `instagram:${v.id}`, v.title, v.published_at, {
      instagram: fromInstagram(v),
      recipe: v.recipe,
      series: v.series_name,
      duration_s: v.duration_s,
      thumbnail: remote(v.thumbnail),
    });
  }
  return [...byKey.values()].filter((v) => v.published_at).sort((a, b) => b.published_at.localeCompare(a.published_at)).slice(0, VIDEO_LIMIT);
}

function research(data: ResearchOverview | null, discovery: DiscoveryData | null): OnlineResearch | null {
  if (!data) return null;
  const nicheLabel = new Map(data.niches.map((n) => [n.id, n.label]));
  const video = (v: ResearchVideo): OnlineResearch["videos"][number] => ({
    id: v.id,
    url: v.url,
    thumbnail: thumbUrl(v.external_id),
    title: v.title,
    lang: v.lang,
    channel: v.channel_title,
    channel_subs: v.channel_subs,
    published_at: v.published_at,
    duration_s: v.duration_s,
    views: v.views,
    views_per_day: Math.round(v.views_per_day),
    outlier: v.outlier,
    remake_score: v.remake_score,
    niche: v.niche_id ? (nicheLabel.get(v.niche_id) ?? null) : null,
    status: v.status,
    format: v.classification?.format ?? v.analysis?.format ?? null,
    effort: v.classification?.effort ?? v.analysis?.effort ?? null,
    summary: v.analysis?.summary ?? null,
    hook: v.analysis?.hook_text || v.analysis?.hook_visual || null,
    why: v.analysis?.why_it_works?.slice(0, 4) ?? [],
    remake: v.analysis?.remake ? { title: v.analysis.remake.title, premise: v.analysis.remake.premise, hook: v.analysis.remake.hook } : null,
    adaptation: v.adaptation?.title ?? null,
  });
  // Les vidéos citées par le stratège d'abord, puis les meilleures ; les plus vues de chaque niche à part
  const cited = new Set([data.report?.report.next_video?.video_id, ...(data.report?.report.remakes ?? []).map((r) => r.video_id)].filter(Boolean));
  const videos = [...data.videos.filter((v) => cited.has(v.id)), ...data.videos.filter((v) => !cited.has(v.id))].slice(0, 30);
  return {
    report: data.report ? { ...data.report.report, created_at: data.report.created_at } : null,
    niches: data.niches
      .filter((n) => n.status !== "archived")
      .map((n) => ({
        id: n.id,
        slug: n.slug,
        label: n.label,
        description: n.description,
        status: n.status,
        origin: n.origin,
        phase: n.summary?.phase ?? null,
        phase_reason: n.summary?.phase_reason ?? null,
        score: n.summary?.score_parts.score ?? null,
        effort: n.summary?.effort ?? null,
        formats: n.summary?.formats ?? [],
        median_views_month: n.summary?.median_views_month ?? null,
        hits_month: n.summary?.hits_month ?? null,
        open_share_month: n.summary?.open_share_month ?? null,
        curve: (n.summary?.curve ?? []).slice(-12).map((c) => ({ month: c.month, median_views: c.median_views, hits: c.hits })),
      }))
      .sort((a, b) => Number(b.status === "active") - Number(a.status === "active") || (b.score ?? -1) - (a.score ?? -1))
      .slice(0, 40),
    videos: videos.map(video),
    discovery: (discovery?.niches ?? []).slice(0, 12).map((n) => ({
      niche: n.niche,
      category: n.category,
      revenue: n.revenue,
      langs: n.langs,
      channels: n.channels.slice(0, 5).map((c) => ({
        title: c.title,
        lang: c.lang,
        months: c.months !== null ? Math.round(c.months * 10) / 10 : null,
        subs: c.subs,
        monthly_views: c.monthlyViews,
        revenue: c.revenue,
        rpm: c.rpm,
        format: c.formatName,
        why: c.why,
        url: `https://www.youtube.com/channel/${c.id}`,
      })),
    })),
    asks: data.asks.slice(0, 8).map((a) => ({ question: a.question, status: a.status, answer: a.answer, at: a.at })),
    running: [...data.jobs.map((j) => j.label ?? j.action), ...(discovery?.running ? [discovery.running.label ?? "Découverte"] : [])],
  };
}

function production(p: TaskProduction, group: OnlineProduction["group"]): OnlineProduction {
  return {
    id: p.id,
    title: p.title,
    channel: p.channel_name,
    series: p.series_name,
    group,
    stage: p.stage,
    progress_pct: p.progress_pct,
    step_progress: p.step_progress,
    step_started_at: p.step_started_at,
    eta_at: p.eta_at,
    queue_position: p.queue_position,
    clips_done: p.clips_done,
    clips_total: p.clips_total,
    error: p.error,
    updated_at: p.updated_at,
  };
}

export async function buildOnlineSnapshot(): Promise<OnlineSnapshot> {
  const errors: string[] = [];
  const channels = (await safe(errors, "chaînes", getChannels)) ?? [];
  const nowIso = now().toISOString();

  const [system, kpis, stats, tiktok, instagram, networks, board, schedule, researchData, discovery] = await Promise.all([
    safe(errors, "machine", getSystemStatus),
    safe(errors, "vue d'ensemble", () => getOverviewKpis()),
    safe(errors, "YouTube", () => getStatsPage(channels, undefined, "all")),
    safe(errors, "TikTok", () => getTikTokStatsPage(channels, undefined, "all")),
    safe(errors, "Instagram", () => getInstagramStatsPage(channels, undefined, "all")),
    safe(errors, "comptes", () => getNetworkAccounts(channels, undefined)),
    safe(errors, "fabrication", getTaskBoard),
    safe(errors, "calendrier", () => getSchedule(nowIso, 7)),
    safe(errors, "recherche", getResearchOverview),
    safe(errors, "découverte", getDiscovery),
  ]);

  const channelName = new Map(channels.map((c) => [c.slug, c.name]));
  const upcoming = new Map<string, { at: string; title: string; channel: string | null; platforms: Set<string> }>();
  const plan = (key: string, at: string | null, title: string | null, channel: string | null, platform: string) => {
    if (!at || at < nowIso) return;
    const row = upcoming.get(key) ?? { at, title: title ?? "Sans titre", channel, platforms: new Set<string>() };
    row.platforms.add(platform);
    if (at < row.at) row.at = at;
    upcoming.set(key, row);
  };
  for (const s of schedule ?? []) if (s.video) plan(s.video.id, s.at, s.video.title, channelName.get(s.channel_slug) ?? null, "youtube");
  for (const u of tiktok?.upcoming ?? []) plan(u.video_id, u.scheduled_for, u.title, null, "tiktok");
  for (const u of instagram?.upcoming ?? []) plan(u.video_id ?? u.key, u.scheduled_for, u.title, null, "instagram");

  const followers = (list: { followers: number | null }[] | undefined) =>
    list?.some((a) => a.followers !== null) ? list.reduce((s, a) => s + (a.followers ?? 0), 0) : null;
  const lastSync = (sync: { last_done_at: string | null } | undefined) => sync?.last_done_at ?? null;

  return {
    version: ONLINE_SNAPSHOT_VERSION,
    generated_at: new Date().toISOString(),
    errors,
    machine: system
      ? {
          worker: system.worker.state,
          worker_beat_s: system.worker.lastBeatS,
          comfy: system.comfy.state,
          comfy_queue: system.comfy.queue,
          ram_free_gb: system.ram.freeGb,
          ram_total_gb: system.ram.totalGb,
          vram_used_mb: system.vram?.usedMb ?? null,
          vram_total_mb: system.vram?.totalMb ?? null,
          gpu_job: system.gpuJob ? { label: system.gpuJob.label ?? system.gpuJob.type, started_at: system.gpuJob.startedAt } : null,
          warnings: system.warnings,
        }
      : null,
    youtube: stats
      ? {
          kpis,
          subscribers: stats.subscribers,
          subscribers_delta_7d: stats.subscribers_delta_7d,
          totals: numbers(stats.totals),
          median_views: stats.median_views,
          scheduled: stats.scheduled,
          analytics_through: stats.analytics_through,
          counters_at: stats.counters_at,
          daily: days(stats.daily).slice(-90),
          analysis: stats.analysis.report
            ? {
                created_at: stats.analysis.report.created_at,
                summary: stats.analysis.report.summary,
                findings: stats.analysis.report.patterns.slice(0, 4).map((p) => p.finding),
                proposed: stats.analysis.proposed.length,
                active: stats.analysis.active.length,
              }
            : null,
        }
      : null,
    tiktok: tiktok
      ? { configured: tiktok.configured, totals: numbers(tiktok.totals), daily: days(tiktok.daily).slice(-90), followers: followers(tiktok.accounts), synced_at: lastSync(tiktok.sync) }
      : null,
    instagram: instagram
      ? {
          configured: instagram.configured,
          totals: numbers(instagram.totals),
          daily: days(instagram.daily).slice(-90),
          followers: followers(instagram.accounts.filter((a) => a.connected)),
          synced_at: lastSync(instagram.sync),
        }
      : null,
    networks: networks ?? [],
    videos: mergeVideos(stats?.videos ?? [], tiktok?.videos ?? [], instagram?.videos ?? []),
    production: board
      ? {
          items: [
            ...board.running.map((p) => production(p, "running")),
            ...board.preparing.map((p) => production(p, "preparing")),
            ...board.queued.map((p) => production(p, "queued")),
            ...board.waiting.map((p) => production(p, "waiting")),
            ...board.paused.map((p) => production(p, "paused")),
            ...board.failed.slice(0, 5).map((p) => production(p, "failed")),
          ],
          review_videos: board.review_videos,
          queue_end_at: board.queue_end_at,
          other_jobs: board.other_jobs.slice(0, 10).map((j) => ({ label: j.label, status: j.status, progress: j.progress, detail: j.detail, started_at: j.started_at })),
          retouches: board.retouches
            .filter((r) => r.status === "queued" || r.status === "running")
            .map((r) => ({ title: r.title, what: r.what, stage: r.stage, status: r.status, progress_pct: r.progress_pct, eta_at: r.eta_at })),
          failed_jobs: board.failed_jobs.length,
        }
      : null,
    upcoming: [...upcoming.values()]
      .sort((a, b) => a.at.localeCompare(b.at))
      .slice(0, 20)
      .map((u) => ({ at: u.at, title: u.title, channel: u.channel, platforms: [...u.platforms] })),
    research: research(researchData, discovery),
  };
}
