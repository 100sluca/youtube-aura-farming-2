/**
 * Page Recherche côté serveur (docs/60-recherche-niches.md) : niches suivies et leur résumé (calculé par le worker,
 * services/worker/worker/steps/research.py), vidéos à reproduire, dernières recommandations, tâches en cours.
 */
import { IS_MOCK } from "@/lib/data";
import { now } from "@/lib/format";
import {
  DEFAULT_RESEARCH,
  ageDays,
  outlierOf,
  parseResearchSettings,
  remakeScore,
  type ResearchAction,
  type ResearchAsk,
  type ResearchJob,
  type ResearchNiche,
  type ResearchOverview,
  type ResearchReport,
  type ResearchVideo,
} from "@/lib/research-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

const VIDEO_COLUMNS =
  "id, external_id, url, title, lang, channel_title, channel_subs, channel_created_at, channel_median, published_at, duration_s, " +
  "views, likes, comments, niche_id, classification, analysis, analysis_at, adaptation, status, concept_id";
const REMAKE_DAYS = 60; // vidéos à reproduire : publiées depuis moins de 60 jours
const REMAKE_SHOWN = 60;
const TOP_PER_NICHE = 8;
const DISCOVER_TOP_DAYS = 75; // niches découvertes : mesurées sur le dernier mois jugé, déjà vieux de 5 à 9 semaines
const ASKS_SHOWN = 6;

const EMPTY: ResearchOverview = {
  settings: DEFAULT_RESEARCH,
  searchesToday: 0,
  niches: [],
  videos: [],
  nicheVideos: [],
  reproduced: [],
  report: null,
  asks: [],
  jobs: [],
  lastJob: null,
};

type Row = Record<string, unknown>;

function toVideo(r: Row, at: Date): ResearchVideo {
  const views = Number(r.views ?? 0);
  const median = r.channel_median != null ? Number(r.channel_median) : null;
  const subs = r.channel_subs != null ? Number(r.channel_subs) : null;
  const [outlier, base] = outlierOf(views, median, subs);
  const age = ageDays((r.published_at as string) ?? null, at);
  const cls = (r.classification ?? null) as ResearchVideo["classification"];
  return {
    id: r.id as string,
    external_id: r.external_id as string,
    url: r.url as string,
    title: (r.title as string) ?? "",
    lang: (r.lang as string) ?? null,
    channel_title: (r.channel_title as string) ?? null,
    channel_subs: subs,
    channel_created_at: (r.channel_created_at as string) ?? null,
    channel_median: median,
    published_at: (r.published_at as string) ?? null,
    duration_s: r.duration_s != null ? Number(r.duration_s) : null,
    views,
    likes: Number(r.likes ?? 0),
    comments: Number(r.comments ?? 0),
    niche_id: (r.niche_id as string) ?? null,
    classification: cls,
    analysis: (r.analysis ?? null) as ResearchVideo["analysis"],
    analysis_at: (r.analysis_at as string) ?? null,
    adaptation: (r.adaptation ?? null) as ResearchVideo["adaptation"],
    status: r.status as ResearchVideo["status"],
    concept_id: (r.concept_id as string) ?? null,
    outlier,
    outlier_base: base,
    views_per_day: views / age,
    age_days: age,
    remake_score: remakeScore(views, outlier, age, cls?.effort),
  };
}

export async function getResearchOverview(): Promise<ResearchOverview> {
  if (IS_MOCK) return EMPTY;
  const db = supabaseAdmin();
  const at = now();
  const today = at.toISOString().slice(0, 10);
  const since = new Date(at.getTime() - REMAKE_DAYS * 86_400_000).toISOString();
  const month = new Date(at.getTime() - 30 * 86_400_000).toISOString();
  const discoverSince = new Date(at.getTime() - DISCOVER_TOP_DAYS * 86_400_000).toISOString();

  const [settingsRes, quotaRes, nichesRes, videosRes, reproducedRes, reportRes, jobsRes, lastRes, asksRes] = await Promise.all([
    db.from("app_settings").select("value").eq("key", "research").maybeSingle(),
    db.from("api_quota_usage").select("units").eq("endpoint", "search.list").eq("day", today),
    db.from("research_niches").select("*").neq("status", "archived").order("created_at"),
    db
      .from("research_videos")
      .select(VIDEO_COLUMNS)
      .in("status", ["new", "shortlisted"])
      .gte("published_at", since)
      .not("classification", "is", null)
      .neq("classification->>effort", "5") // hors de portée (tournage, jeu vidéo…) : jamais à reproduire
      .order("views", { ascending: false })
      .limit(1000),
    db.from("research_videos").select(VIDEO_COLUMNS).eq("status", "reproduced").order("analysis_at", { ascending: false }).limit(12),
    db.from("research_reports").select("*").order("created_at", { ascending: false }).limit(1).maybeSingle(),
    db.from("jobs").select("id, status, payload, progress, progress_label").eq("type", "research").in("status", ["queued", "running"]),
    db
      .from("jobs")
      .select("status, payload, finished_at, error, result")
      .eq("type", "research")
      .in("status", ["done", "failed"])
      .neq("payload->>action", "ask")
      .order("finished_at", { ascending: false })
      .limit(1)
      .maybeSingle(),
    db
      .from("jobs")
      .select("id, status, payload, result, error, created_at")
      .eq("type", "research")
      .eq("payload->>action", "ask")
      .order("created_at", { ascending: false })
      .limit(ASKS_SHOWN),
  ]);
  if (nichesRes.error) throw new Error(`research_niches : ${nichesRes.error.message} (migration 0050 appliquée ?)`);

  const settings = parseResearchSettings(settingsRes.data?.value);
  const searchesToday = (quotaRes.data ?? []).reduce((s, r) => s + Number(r.units ?? 0), 0);
  const minViews = settings.min_views;

  const videos = ((videosRes.data ?? []) as unknown as Row[])
    .map((r) => toVideo(r, at))
    .filter((v) => v.views >= minViews && (v.classification?.effort ?? 3) <= 4)
    .sort((a, b) => Number(b.status === "shortlisted") - Number(a.status === "shortlisted") || b.remake_score - a.remake_score)
    .slice(0, REMAKE_SHOWN);

  // Les Shorts les plus vus de chaque niche ces 30 derniers jours (75 pour une niche découverte, mesurée sur le dernier
  // mois jugé)
  const nicheRows = (nichesRes.data ?? []) as Row[];
  const discovered = new Set(nicheRows.filter((n) => n.origin === "discover").map((n) => n.id as string));
  const nicheIds = nicheRows.map((n) => n.id as string);
  // l'API rend 1 000 lignes au plus par requête : par pages (≈ 7 000 lignes avec les niches découvertes)
  const links: Row[] = [];
  for (let page = 0; nicheIds.length && page < 12; page++) {
    const res = await db
      .from("research_video_niches")
      .select("niche_id, video_id, research_videos!inner(id, views, published_at)")
      .in("niche_id", nicheIds)
      .gte("research_videos.published_at", discoverSince)
      .order("video_id")
      .order("niche_id")
      .range(page * 1000, page * 1000 + 999);
    links.push(...((res.data ?? []) as Row[]));
    if ((res.data?.length ?? 0) < 1000) break;
  }
  const top = new Map<string, { id: string; views: number }[]>();
  for (const r of links as unknown as {
    niche_id: string;
    video_id: string;
    research_videos: { views: number; published_at: string | null };
  }[]) {
    if (!discovered.has(r.niche_id) && (r.research_videos?.published_at ?? "") < month) continue;
    const list = top.get(r.niche_id) ?? [];
    list.push({ id: r.video_id, views: Number(r.research_videos?.views ?? 0) });
    top.set(r.niche_id, list);
  }
  const topIds = new Set<string>();
  const niches: ResearchNiche[] = nicheRows.map((n) => {
    const ids = (top.get(n.id as string) ?? []).sort((a, b) => b.views - a.views).slice(0, TOP_PER_NICHE).map((x) => x.id);
    ids.forEach((id) => topIds.add(id));
    return { ...(n as unknown as ResearchNiche), queries: (n.queries as ResearchNiche["queries"]) ?? [], top: ids };
  });
  niches.sort((a, b) => (b.summary?.score_parts.score ?? -1) - (a.summary?.score_parts.score ?? -1));

  // Questions au stratège, et les vidéos qu'il cite
  const asks: ResearchAsk[] = ((asksRes.data ?? []) as Row[]).map((j) => {
    const p = (j.payload ?? {}) as Record<string, unknown>;
    const res = (j.result ?? {}) as Record<string, unknown>;
    return {
      id: j.id as string,
      question: String(p.question ?? ""),
      status: j.status as ResearchAsk["status"],
      answer: (res.answer as string) ?? null,
      video_ids: ((res.video_ids as string[]) ?? []).filter(Boolean),
      niches: ((res.niches as string[]) ?? []).filter(Boolean),
      error: (j.error as string) ?? null,
      at: j.created_at as string,
    };
  });
  const report = (reportRes.data as ResearchReport | null) ?? null;
  for (const a of asks) a.video_ids.forEach((id) => topIds.add(id));
  if (report?.report.next_video?.video_id) topIds.add(report.report.next_video.video_id);

  // Fiches des vidéos d'aperçu des niches (et de celles citées) qui ne sont pas déjà dans la liste à reproduire
  const known = new Set(videos.map((v) => v.id));
  const missing = [...topIds].filter((id) => !known.has(id));
  const extra: ResearchVideo[] = [];
  for (let i = 0; i < missing.length; i += 200) {
    const res = await db.from("research_videos").select(VIDEO_COLUMNS).in("id", missing.slice(i, i + 200));
    extra.push(...((res.data ?? []) as unknown as Row[]).map((r) => toVideo(r, at)));
  }

  const jobs: ResearchJob[] = (jobsRes.data ?? []).map((j) => {
    const p = (j.payload ?? {}) as Record<string, unknown>;
    return {
      id: j.id as string,
      action: ((p.action as string) ?? "scan") as ResearchAction,
      status: j.status as ResearchJob["status"],
      video_id: (p.video_id as string) ?? null,
      q: (p.q as string) ?? null,
      question: (p.question as string) ?? null,
      progress: (j.progress as number) ?? null,
      label: (j.progress_label as string) ?? null,
    };
  });
  const last = lastRes.data;
  return {
    settings,
    searchesToday,
    niches,
    videos,
    nicheVideos: extra,
    reproduced: ((reproducedRes.data ?? []) as unknown as Row[]).map((r) => toVideo(r, at)),
    report,
    asks,
    jobs,
    lastJob: last
      ? {
          action: (((last.payload ?? {}) as Record<string, unknown>).action as ResearchAction) ?? "scan",
          status: last.status as string,
          finished_at: (last.finished_at as string) ?? null,
          error: (last.error as string) ?? null,
          result: (last.result as Record<string, unknown>) ?? null,
        }
      : null,
  };
}
