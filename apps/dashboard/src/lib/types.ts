/**
 * Types du domaine — miroir de supabase/migrations/0001_init.sql.
 * Source de vérité : la migration SQL. À terme, générer via
 * `supabase gen types typescript` et ne garder ici que les types dérivés.
 */

export type ChannelLang = "fr" | "en";
export type VideoFormat = "A_voiceover" | "B_visual";
export type ConceptStatus = "proposed" | "approved" | "rejected" | "used";
export type ProductionStatus =
  | "draft"
  | "scripting"
  | "generating"
  | "assembling"
  | "ready"
  | "failed"
  | "archived";
export type VideoStatus =
  | "pending"
  | "rendering"
  | "qa"
  | "review"
  | "ready"
  | "uploading"
  | "scheduled"
  | "published"
  | "failed"
  | "unpublished";
export type JobType =
  | "ideate"
  | "script"
  | "generate_clip"
  | "tts"
  | "assemble"
  | "qa"
  | "upload"
  | "sync_metrics"
  | "sync_retention"
  | "sync_comments"
  | "improve";
export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";
export type AlertSeverity = "info" | "warning" | "error";

export interface Channel {
  id: string;
  slug: string;
  name: string;
  lang: ChannelLang;
  youtube_channel_id: string | null;
  timezone: string;
  publish_slots: string[]; // "09:00"
  auto_publish: boolean;
  is_active: boolean;
}

export interface Concept {
  id: string;
  title: string;
  hook: string | null;
  category: string | null;
  premise: string | null;
  visual_beats: string[];
  source: "agent" | "manual" | "clone";
  score: number | null;
  status: ConceptStatus;
  created_at: string;
}

/** Script produit par l'agent script (productions.script, version 1). */
export interface ScriptScene {
  index: number;
  duration_s: number;
  visual_prompt: string;
  narration: Partial<Record<ChannelLang, string>>;
  on_screen_text?: Partial<Record<ChannelLang, string>>;
  sfx?: string;
}
export interface ScriptV1 {
  version: 1;
  scenes: ScriptScene[];
  loop_note?: string;
  metadata: Record<ChannelLang, { title: string; description: string; tags: string[] }>;
}

export interface Production {
  id: string;
  concept_id: string | null;
  format: VideoFormat;
  status: ProductionStatus;
  script: ScriptV1 | null;
  target_duration_s: number;
  style_preset: string | null;
  video_provider: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface Video {
  id: string;
  production_id: string;
  channel_id: string;
  lang: ChannelLang;
  format: VideoFormat;
  status: VideoStatus;
  title: string | null;
  description: string | null;
  tags: string[];
  duration_s: number | null;
  scheduled_at: string | null;
  youtube_video_id: string | null;
  youtube_publish_at: string | null;
  published_at: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface Job {
  id: string;
  type: JobType;
  status: JobStatus;
  priority: number;
  production_id: string | null;
  video_id: string | null;
  channel_id: string | null;
  progress: number; // 0-100
  progress_label: string | null;
  attempts: number;
  max_attempts: number;
  run_after: string;
  locked_by: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  created_at: string;
}

export interface VideoMetricsDaily {
  video_id: string;
  day: string; // YYYY-MM-DD
  views: number;
  likes: number;
  comments: number;
  shares: number;
  subscribers_gained: number;
  average_view_duration_s: number | null;
  average_view_pct: number | null;
}

export interface RetentionPoint {
  t: number; // elapsedVideoTimeRatio 0..1
  w: number; // audienceWatchRatio 0..1+
  rel?: "ABOVE_AVERAGE" | "AVERAGE" | "BELOW_AVERAGE";
}

export interface ChannelMetricsDaily {
  channel_id: string;
  day: string;
  subscribers: number | null;
  subscribers_gained: number;
  views: number;
  estimated_minutes_watched: number | null;
  likes: number;
  comments: number;
}

export interface Alert {
  id: string;
  severity: AlertSeverity;
  title: string;
  body: string | null;
  job_id: string | null;
  video_id: string | null;
  acknowledged_at: string | null;
  created_at: string;
}

/** Ligne de la vue v_video_overview (liste des vidéos publiées). */
export interface VideoOverview {
  id: string;
  production_id: string;
  channel_id: string;
  channel_slug: string;
  lang: ChannelLang;
  format: VideoFormat;
  status: VideoStatus;
  title: string | null;
  category: string | null;
  scheduled_at: string | null;
  youtube_video_id: string | null;
  youtube_publish_at: string | null;
  published_at: string | null;
  duration_s: number | null;
  views: number;
  likes: number;
  comments: number;
  shares: number | null;
  subscribers_gained: number | null;
  average_view_pct: number | null;
  poster_url?: string | null;
}

/** Carte "en production" : une production + ses vidéos + l'agrégat des jobs. */
export interface ProductionCard {
  production: Production;
  concept: Pick<Concept, "id" | "title" | "hook" | "category"> | null;
  videos: Video[];
  jobs: Job[];
  progress_pct: number;
  current_step: string | null; // ex. "Clips 5/8"
  eta_minutes: number | null;
}

/** Créneau du calendrier : rempli (vidéo) ou vide (à combler). */
export interface ScheduleSlot {
  channel_slug: string;
  at: string; // ISO
  video: Pick<Video, "id" | "title" | "status" | "format" | "youtube_video_id"> | null;
}

export interface OverviewKpis {
  subscribers: number;
  subscribers_delta_7d: number;
  views_7d: number;
  views_7d_delta_pct: number | null; // vs 7 jours précédents
  average_view_pct_28d: number | null;
  watch_hours_28d: number;
  published_7d: number;
  pipeline: { generating: number; ready: number; scheduled: number; failed: number };
  ypp: { subs_target: number; views_90d: number; views_90d_target: number };
}

export interface DailyViewsPoint {
  day: string;
  fr: number;
  en: number;
}
