/** Dashboard des statistiques (docs/25-dashboard-statistiques.md) : types et règles partagés serveur / navigateur.
 * Données : lib/stats.ts. */
import type { DayViews } from "@/lib/views-series";
import type { LibraryItem } from "@/lib/library-types";

export type StatsPeriod = "7" | "28" | "90" | "all";

export const STATS_PERIODS: { id: StatsPeriod; label: string; days: number | null }[] = [
  { id: "7", label: "7 jours", days: 7 },
  { id: "28", label: "28 jours", days: 28 },
  { id: "90", label: "90 jours", days: 90 },
  { id: "all", label: "Tout", days: null },
];

export function isStatsPeriod(value: unknown): value is StatsPeriod {
  return typeof value === "string" && STATS_PERIODS.some((p) => p.id === value);
}

/** Mêmes règles que l'agent analyste (worker/performance.py) : note = vues comparables (à 7 jours si la vidéo en a
 * plus de 7) ÷ médiane des vidéos jugeables (24 h au moins) des 90 derniers jours ; top = premier tiers et ×1,25 au
 * moins, flop = dernier tiers et ×0,8 au plus. */
export const MIN_AGE_H = 24;
export const TOP_SCORE = 1.25;
export const FLOP_SCORE = 0.8;

export type Verdict = "top" | "moyen" | "flop" | "trop récente";

export const VERDICT_LABELS: Record<Verdict, string> = {
  top: "Top",
  moyen: "Moyen",
  flop: "Flop",
  "trop récente": "Trop récente",
};

export const RECIPE_LABELS: Record<string, string> = {
  timelapse: "Chantier",
  tour: "Visite",
  story: "Récit",
};

export interface VideoInsight {
  verdict: Verdict;
  score: number | null;
  why: string;
  worked: string[];
  missed: string[];
  report_at: string;
}

export interface StatsVideo extends LibraryItem {
  age_h: number;
  /** Vues à 7 jours pour une vidéo de plus de 7 jours (si connues), sinon vues du moment. */
  comparable_views: number;
  score: number | null;
  verdict: Verdict;
  like_rate_pct: number | null;
  engagement_pct: number | null; // (j'aime + commentaires + partages) ÷ vues
  engaged_pct: number | null; // vues engagées ÷ vues
  insight: VideoInsight | null; // diagnostic du dernier rapport de l'agent analyste
}

export interface StatsTotals {
  videos: number;
  views: number;
  likes: number;
  comments: number;
  shares: number | null;
  subscribers_gained: number | null;
  /** Rétention moyenne pondérée par les vues (vidéos où YouTube Analytics l'a publiée). */
  average_view_pct: number | null;
  hook_retention_pct: number | null;
  average_view_duration_s: number | null;
  watch_hours: number | null;
  like_rate_pct: number | null;
}

export type LessonTarget = "idea" | "script" | "seo" | "production";
export type LessonStatus = "proposed" | "active" | "rejected" | "superseded" | "retired";

export const LESSON_TARGET_LABELS: Record<LessonTarget, string> = {
  idea: "Agent idées",
  script: "Scénaristes",
  seo: "Agent SEO",
  production: "À régler toi-même",
};

export interface Lesson {
  id: string;
  target: LessonTarget;
  recipe: string | null;
  rule: string;
  why: string | null;
  confidence: "faible" | "moyenne" | "bonne";
  status: LessonStatus;
  created_at: string;
  decided_at: string | null;
}

export interface AnalysisReport {
  id: string;
  created_at: string;
  videos: number;
  judged: number;
  median_views: number | null;
  summary: string | null; // null : trop peu de vidéos, pas d'appel à l'agent
  patterns: { finding: string; evidence: string; confidence: string }[];
  experiments: { hypothesis: string; test: string }[];
  diagnoses: { video_id: string; ref: string; title: string; verdict: Verdict; score: number | null; why: string; worked: string[]; missed: string[] }[];
}

export interface StatsPage {
  period: StatsPeriod;
  videos: StatsVideo[]; // publiées sur la période, plus récentes d'abord
  totals: StatsTotals;
  scheduled: number; // programmées, pas encore en ligne
  median_views: number | null;
  subscribers: number | null;
  subscribers_delta_7d: number | null;
  daily: DayViews[];
  unattributed: number;
  analytics_through: string | null;
  counters_at: string | null;
  sync: { active: boolean; since: string | null; last_done_at: string | null; last_error: string | null };
  connected: boolean;
  analysis: {
    channel_id: string | null;
    running: boolean;
    report: AnalysisReport | null;
    proposed: Lesson[];
    active: Lesson[];
  };
}
