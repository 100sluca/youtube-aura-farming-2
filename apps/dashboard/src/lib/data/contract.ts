/** Interface commune des sources de données (Supabase, ou démo factice avec NEXT_PUBLIC_MOCK=1). */
import type {
  Channel,
  Concept,
  DailyViewsPoint,
  OverviewKpis,
  ProductionCard,
  RetentionPoint,
  ScheduleSlot,
  ScriptV1,
  Series,
  VideoFormat,
  VideoMetricsDaily,
  VideoOverview,
} from "@/lib/types";

/** Slug d'une chaîne (en-tête du dashboard) ; absent = toutes les chaînes. */
export type ChannelFilter = string;

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
  /** Vues par jour, une clé par slug de chaîne. */
  getDailyViews(days: number): Promise<DailyViewsPoint[]>;
  getVideoDetail(id: string): Promise<VideoDetail | null>;
  listProductions(): Promise<ProductionCard[]>;
  /** Une production (panneau de détail du gestionnaire de tâches). */
  getProductionCard(id: string): Promise<ProductionCard | null>;
  getSchedule(fromISO: string, days: number): Promise<ScheduleSlot[]>;
  listConcepts(): Promise<Concept[]>;
  getExperimentSummary(): Promise<ExperimentSummary>;
  /** Séries de contenu (absentes du mock : facultatif). */
  listSeries?(): Promise<Series[]>;
}
