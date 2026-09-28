/**
 * Dashboard des statistiques (docs/25-dashboard-statistiques.md) : les vidéos publiées avec tous leurs chiffres, leur
 * note par rapport aux autres, les vues par jour, l'état de la synchro YouTube et le dernier rapport de l'agent
 * analyste avec ses leçons. Serveur uniquement.
 */
import { IS_MOCK } from "@/lib/data";
import { now } from "@/lib/format";
import { insightFrom, recentReports } from "@/lib/insights";
import { getLibrary } from "@/lib/library";
import type { LibraryItem } from "@/lib/library-types";
import {
  FLOP_SCORE,
  MIN_AGE_H,
  STATS_PERIODS,
  TOP_SCORE,
  type AnalysisReport,
  type Lesson,
  type StatsPage,
  type StatsPeriod,
  type StatsTotals,
  type StatsVideo,
  type Verdict,
} from "@/lib/stats-types";
import { supabaseAdmin } from "@/lib/supabase-admin";
import type { Channel } from "@/lib/types";
import { channelCounters, channelViews } from "@/lib/views-series";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;

async function rows(q: PromiseLike<{ data: unknown; error: { message?: string } | null }>): Promise<Row[]> {
  const { data, error } = await q;
  if (error) throw new Error(error.message ?? String(error));
  return (data as Row[] | null) ?? [];
}

const RANK_WINDOW_DAYS = 90; // comme l'agent analyste
const pct = (part: number, whole: number): number | null => (whole > 0 ? Math.round((part / whole) * 10000) / 100 : null);

function median(values: number[]): number | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

type Rankable = { id: string; views: number; views_7d?: number | null; age_h: number };
type Rank = { comparable: number; score: number | null; verdict: Verdict; median: number | null };

/** Vues à 7 jours pour une vidéo de plus de 7 jours (si connues), sinon vues du moment. */
const comparable = (v: Rankable): number => (v.views_7d !== null && v.views_7d !== undefined && v.age_h >= 7 * 24 ? v.views_7d : v.views);

/** Vidéo hors de la fenêtre de 90 jours (période « Tout ») : notée sur la médiane de la fenêtre, verdict aux seuils. */
function outsideRank(v: Rankable, med: number | null): Rank {
  const score = med === null ? null : Math.round((comparable(v) / Math.max(med, 1)) * 100) / 100;
  const verdict: Verdict = score === null ? "moyen" : score >= TOP_SCORE ? "top" : score <= FLOP_SCORE ? "flop" : "moyen";
  return { comparable: comparable(v), score, verdict, median: med };
}

/** Note et verdict de chaque vidéo : mêmes règles que worker/performance.py (rank). */
export function rankVideos<T extends Rankable>(videos: T[]): Map<string, Rank> {
  const judged = videos.filter((v) => v.age_h >= MIN_AGE_H).sort((a, b) => comparable(b) - comparable(a));
  const med = median(judged.map(comparable));
  const base = Math.max(med ?? 0, 1);
  const third = Math.max(1, Math.round(judged.length / 3));
  const out = new Map<string, Rank>();
  judged.forEach((v, i) => {
    const score = Math.round((comparable(v) / base) * 100) / 100;
    let verdict: Verdict = "moyen";
    if (judged.length >= 2 && i < third && score >= TOP_SCORE) verdict = "top";
    else if (judged.length >= 2 && i >= judged.length - third && score <= FLOP_SCORE) verdict = "flop";
    out.set(v.id, { comparable: comparable(v), score, verdict, median: med });
  });
  for (const v of videos) {
    if (out.has(v.id)) continue;
    out.set(v.id, { comparable: comparable(v), score: judged.length ? Math.round((comparable(v) / base) * 100) / 100 : null, verdict: "trop récente", median: med });
  }
  return out;
}

function totalsOf(videos: StatsVideo[]): StatsTotals {
  const sum = (f: (v: StatsVideo) => number | null | undefined) => videos.reduce((s, v) => s + (f(v) ?? 0), 0);
  const known = (f: (v: StatsVideo) => number | null | undefined) => videos.filter((v) => f(v) !== null && f(v) !== undefined);
  const weighted = (f: (v: StatsVideo) => number | null | undefined) => {
    const list = known(f);
    const w = list.reduce((s, v) => s + v.views, 0);
    return w > 0 ? Math.round((list.reduce((s, v) => s + (f(v) ?? 0) * v.views, 0) / w) * 10) / 10 : null;
  };
  const views = sum((v) => v.views);
  const likes = sum((v) => v.likes);
  return {
    videos: videos.length,
    views,
    likes,
    comments: sum((v) => v.comments),
    shares: known((v) => v.shares).length ? sum((v) => v.shares) : null,
    subscribers_gained: known((v) => v.subscribers_gained).length ? sum((v) => v.subscribers_gained) : null,
    average_view_pct: weighted((v) => v.average_view_pct),
    hook_retention_pct: weighted((v) => v.hook_retention_pct),
    average_view_duration_s: weighted((v) => v.average_view_duration_s),
    watch_hours: known((v) => v.estimated_minutes_watched).length ? Math.round((sum((v) => v.estimated_minutes_watched) / 60) * 10) / 10 : null,
    like_rate_pct: pct(likes, views),
  };
}

function mapLesson(r: Row): Lesson {
  return {
    id: r.id,
    target: r.target,
    recipe: r.recipe ?? null,
    rule: r.rule,
    why: r.why ?? null,
    confidence: r.confidence,
    status: r.status,
    created_at: r.created_at,
    decided_at: r.decided_at ?? null,
  };
}

/** Toute la page Dashboard pour la chaîne choisie en haut (ou toutes les chaînes). */
export async function getStatsPage(channels: Channel[], selected: Channel | undefined, period: StatsPeriod): Promise<StatsPage> {
  const scope = selected ? [selected] : channels;
  const ids = scope.map((c) => c.id);
  const connected = scope.filter((c) => c.youtube_channel_id);
  const analysisChannel = selected?.youtube_channel_id ? selected : connected[0];
  const days = STATS_PERIODS.find((p) => p.id === period)?.days ?? null;
  const empty: StatsPage = {
    period,
    videos: [],
    totals: totalsOf([]),
    scheduled: 0,
    median_views: null,
    subscribers: null,
    subscribers_delta_7d: null,
    daily: [],
    unattributed: 0,
    analytics_through: null,
    counters_at: null,
    sync: { active: false, since: null, last_done_at: null, last_error: null },
    connected: connected.length > 0,
    analysis: { channel_id: analysisChannel?.id ?? null, running: false, report: null, proposed: [], active: [] },
  };
  if (IS_MOCK || ids.length === 0) return empty;

  const db = supabaseAdmin();
  const nowMs = now().getTime();
  const [{ items }, counters, series, syncJobs, lastFinished, reports, lessons, analyzeJobs] = await Promise.all([
    getLibrary(selected?.id),
    channelCounters(ids),
    channelViews(ids, days ?? 90),
    rows(db.from("jobs").select("status, created_at, started_at").eq("type", "sync_metrics").in("channel_id", ids).in("status", ["queued", "running"]).order("created_at")),
    rows(
      db.from("jobs").select("status, finished_at, error").eq("type", "sync_metrics").in("channel_id", ids).in("status", ["done", "failed"])
        .order("finished_at", { ascending: false }).limit(1),
    ),
    recentReports(analysisChannel?.id ?? null).catch(() => [] as AnalysisReport[]),
    analysisChannel
      ? rows(
          db.from("performance_lessons").select("*").in("status", ["proposed", "active"])
            .or(`channel_id.is.null,channel_id.eq.${analysisChannel.id}`).order("created_at", { ascending: false }),
        ).catch(() => [] as Row[])
      : Promise.resolve([] as Row[]),
    analysisChannel
      ? rows(db.from("jobs").select("id").eq("type", "analyze").eq("channel_id", analysisChannel.id).in("status", ["queued", "running"]).limit(1)).catch(() => [] as Row[])
      : Promise.resolve([] as Row[]),
  ]);

  // Vidéos publiées : note calculée sur les 90 derniers jours (comme l'agent), affichage sur la période choisie
  const published = items
    .filter((v): v is LibraryItem & { published_at: string } => v.status === "published" && Boolean(v.youtube_video_id) && Boolean(v.published_at))
    .map((v) => ({ ...v, age_h: Math.max(0, (nowMs - new Date(v.published_at).getTime()) / 3_600_000) }));
  const ranks = rankVideos(published.filter((v) => v.age_h <= RANK_WINDOW_DAYS * 24));
  const med = [...ranks.values()][0]?.median ?? null;
  const videos: StatsVideo[] = published
    .filter((v) => days === null || v.age_h <= days * 24)
    .map((v) => {
      const r = ranks.get(v.id) ?? outsideRank(v, med);
      return {
        ...v,
        comparable_views: r.comparable,
        score: r.score,
        verdict: r.verdict,
        like_rate_pct: pct(v.likes, v.views),
        engagement_pct: pct(v.likes + v.comments + (v.shares ?? 0), v.views),
        engaged_pct: v.engaged_views !== null && v.engaged_views !== undefined ? pct(v.engaged_views, v.views) : null,
        insight: insightFrom(reports, v.id),
      };
    })
    .sort((a, b) => b.published_at!.localeCompare(a.published_at!));

  // Vues par jour : toutes les chaînes du périmètre additionnées
  const all = [...series.values()];
  const daily = all.length
    ? all[0].days.map((d, i) => {
        const parts = all.map((c) => c.days[i]);
        const unknown = parts.some((p) => p.source === "unknown");
        return {
          day: d.day,
          views: unknown ? null : parts.reduce((s, p) => s + (p.views ?? 0), 0),
          source: unknown ? ("unknown" as const) : parts.some((p) => p.source === "estimate") ? ("estimate" as const) : ("analytics" as const),
        };
      })
    : [];
  const throughs = all.map((c) => c.through);
  const counterList = [...counters.values()];
  const takenAt = counterList.map((c) => c.taken_at).filter((t): t is string => Boolean(t)).sort();
  const lessonRows = lessons.map(mapLesson);

  return {
    ...empty,
    videos,
    totals: totalsOf(videos),
    scheduled: items.filter((v) => v.status === "scheduled" || v.status === "uploading" || v.status === "ready").length,
    median_views: med,
    subscribers: counterList.some((c) => c.subscribers !== null) ? counterList.reduce((s, c) => s + (c.subscribers ?? 0), 0) : null,
    subscribers_delta_7d: counterList.every((c) => c.delta_7d !== null) ? counterList.reduce((s, c) => s + (c.delta_7d ?? 0), 0) : null,
    daily,
    unattributed: all.reduce((s, c) => s + c.unattributed, 0),
    analytics_through: throughs.length && throughs.every(Boolean) ? (throughs as string[]).sort()[0] : null,
    counters_at: takenAt.length ? takenAt[takenAt.length - 1] : null,
    sync: {
      active: syncJobs.length > 0,
      since: syncJobs[0]?.started_at ?? syncJobs[0]?.created_at ?? null,
      last_done_at: lastFinished[0]?.status === "done" ? (lastFinished[0].finished_at ?? null) : null,
      last_error: lastFinished[0]?.status === "failed" ? String(lastFinished[0].error ?? "échec") : null,
    },
    analysis: {
      channel_id: analysisChannel?.id ?? null,
      running: analyzeJobs.length > 0,
      report: reports[0] ?? null,
      proposed: lessonRows.filter((l) => l.status === "proposed"),
      active: lessonRows.filter((l) => l.status === "active"),
    },
  };
}
