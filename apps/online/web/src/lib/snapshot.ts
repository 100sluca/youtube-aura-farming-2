/** Instantané envoyé par le dashboard du PC : copie des types de apps/dashboard/src/lib/online-snapshot.ts (à tenir
 * ensemble). Tout champ peut manquer dans un instantané plus ancien : la page reste prudente (?? et ?.). */

export type Platform = "youtube" | "tiktok" | "instagram";
export type Verdict = "top" | "moyen" | "flop" | "trop récente";
export type Day = { day: string; views: number | null };

export interface PlatformStats {
  views: number | null;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  watched_pct: number | null;
  hook_pct: number | null;
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

export interface Video {
  key: string;
  title: string;
  published_at: string;
  channel: string | null;
  recipe: string | null;
  series: string | null;
  duration_s: number | null;
  thumbnail: string | null;
  youtube: PlatformStats | null;
  tiktok: PlatformStats | null;
  instagram: PlatformStats | null;
  insight: string | null;
}

export interface Production {
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

export interface NetworkAccount {
  key: string;
  platform: Platform;
  account: string | null;
  name: string;
  role: string;
  avatar_url: string | null;
  connected: boolean;
  warning: string | null;
  followers: number | null;
  followers_delta_7d: number | null;
  views_7d: number | null;
  views_prev_7d: number | null;
  views_28d: number | null;
  posts_7d: number;
  daily: Day[];
  estimated: boolean;
}

export interface Kpis {
  subscribers: number;
  subscribers_delta_7d: number;
  views_7d: number;
  views_7d_delta_pct: number | null;
  average_view_pct_28d: number | null;
  watch_hours_28d: number;
  published_7d: number;
  pipeline: { generating: number; ready: number; scheduled: number; failed: number };
  ypp: { subs_target: number; views_90d: number; views_90d_target: number };
}

type Totals = Record<string, number | null> | null;

export interface ResearchNiche {
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
}

export interface ResearchVideo {
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
}

export interface Research {
  report: {
    created_at: string;
    headline: string;
    next_video?: { ref: string; why: string; how: string; video_id?: string } | null;
    niches: { niche: string; verdict: string; why: string; how: string; first_videos: string[] }[];
    remakes: { ref: string; why: string; angle: string; video_id?: string }[];
    fast_formats: { format: string; why: string; recipe: string }[];
    new_niches: { label: string; description: string; queries: string[]; why: string }[];
    warnings: string[];
  } | null;
  niches: ResearchNiche[];
  videos: ResearchVideo[];
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

export interface Snapshot {
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
    kpis: Kpis | null;
    subscribers: number | null;
    subscribers_delta_7d: number | null;
    totals: Totals;
    median_views: number | null;
    scheduled: number;
    analytics_through: string | null;
    counters_at: string | null;
    daily: Day[];
    analysis: { created_at: string; summary: string | null; findings: string[]; proposed: number; active: number } | null;
  } | null;
  tiktok: { configured: boolean; totals: Totals; daily: Day[]; followers: number | null; synced_at: string | null } | null;
  instagram: { configured: boolean; totals: Totals; daily: Day[]; followers: number | null; synced_at: string | null } | null;
  networks: NetworkAccount[];
  videos: Video[];
  production: {
    items: Production[];
    review_videos: number;
    queue_end_at: string | null;
    other_jobs: { label: string; status: string; progress: number; detail: string | null; started_at: string | null }[];
    retouches: { title: string; what: string; stage: string; status: string; progress_pct: number; eta_at: string | null }[];
    failed_jobs: number;
  } | null;
  upcoming: { at: string; title: string; channel: string | null; platforms: string[] }[];
  research?: Research | null;
}

export interface SnapshotResponse {
  received_at: string | null;
  snapshot: Snapshot | null;
}

export const PLATFORMS: Platform[] = ["youtube", "tiktok", "instagram"];
export const PLATFORM_LABEL: Record<Platform, string> = { youtube: "YouTube", tiktok: "TikTok", instagram: "Instagram" };
