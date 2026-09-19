/** Interface commune des sources de données (mock aujourd'hui, Supabase demain). */
import type {
  Alert,
  Channel,
  Concept,
  DailyViewsPoint,
  OverviewKpis,
  ProductionCard,
  RetentionPoint,
  ScheduleSlot,
  ScriptV1,
  VideoFormat,
  VideoMetricsDaily,
  VideoOverview,
} from "@/lib/types";

export type ChannelFilter = "fr" | "en";

export interface VideoComment {
  id: string;
  author: string;
  text: string;
  like_count: number;
  published_at: string;
}

export interface VideoDetail {
  video: VideoOverview;
  daily: VideoMetricsDaily[];
  retention: RetentionPoint[];
  comments: VideoComment[];
  script: ScriptV1 | null;
}

export interface FormatSummary {
  format: VideoFormat;
  videos: number;
  avg_view_pct: number;
  views_per_video: number;
  subs_per_1k_views: number;
}

export interface CategorySummary {
  category: string;
  videos: number;
  avg_view_pct: number;
  views_per_video: number;
}

export interface ExperimentSummary {
  byFormat: FormatSummary[];
  byCategory: CategorySummary[];
}

export interface DataSource {
  getChannels(): Promise<Channel[]>;
  getOverviewKpis(channel?: ChannelFilter): Promise<OverviewKpis>;
  getDailyViews(days: number): Promise<DailyViewsPoint[]>;
  listPublishedVideos(): Promise<VideoOverview[]>;
  getVideoDetail(id: string): Promise<VideoDetail | null>;
  listProductions(): Promise<ProductionCard[]>;
  getSchedule(fromISO: string, days: number): Promise<ScheduleSlot[]>;
  listConcepts(): Promise<Concept[]>;
  listAlerts(): Promise<Alert[]>;
  getExperimentSummary(): Promise<ExperimentSummary>;
}
