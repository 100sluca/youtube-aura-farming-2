/**
 * Page Recherche (docs/60-recherche-niches.md) : types partagés par le serveur et les composants client, et les deux
 * calculs refaits côté page. Ils doivent rester identiques à services/worker/worker/research.py (outlier, remake_score).
 */

export type NichePhase = "émergente" | "en hausse" | "installée" | "en baisse" | "à vide" | "inconnue";
export type NicheStatus = "active" | "proposed" | "paused" | "archived";
export type ResearchVideoStatus = "new" | "shortlisted" | "dismissed" | "reproduced";
export type ResearchAction = "scan" | "explore" | "watch" | "adapt" | "reproduce" | "brief" | "ask" | "discover_shorts";
/** « fidele » : même sujet, même déroulé, nos mots en français (docs/64 §3) ; « mecanique » : histoire nouvelle. */
export type ReproduceMode = "fidele" | "mecanique";

export interface ResearchSettings {
  daily_searches: number;
  auto_watch: number;
  brief_weekday: number;
  min_views: number;
}

export const DEFAULT_RESEARCH: ResearchSettings = { daily_searches: 90, auto_watch: 4, brief_weekday: 1, min_views: 50_000 };

export interface NicheQuery {
  q: string;
  lang?: string | null;
  region?: string | null;
}

export interface CurvePoint {
  month: string;
  median_views: number | null;
  hits: number;
  open_share: number | null;
  channels: number;
}

export interface NicheSummary {
  phase: NichePhase;
  phase_reason: string;
  score_parts: { score: number; demand: number; momentum: number; open: number; feasibility: number };
  effort: number | null;
  formats: string[];
  age_months: number | null;
  peak_month: string | null;
  last_month: string | null;
  median_views_month: number | null;
  /** Shorts du mois mesuré (50 au plus : une recherche YouTube) ; sous 10, le mois n'est pas jugé. */
  sample_month?: number | null;
  /** Élan de toutes les niches (× sur deux mois) : la phase se juge par rapport à lui. */
  market?: number | null;
  hits_month: number | null;
  open_share_month: number | null;
  concentration_month: number | null;
  median_vpd_7: number | null;
  median_views_7: number | null;
  hits_7: number | null;
  open_share_7: number | null;
  curve: CurvePoint[];
  weekly: { median_vpd: number | null; hits: number }[];
  classified: number;
  updated_at: string;
}

export interface ResearchNiche {
  id: string;
  slug: string;
  label: string;
  description: string | null;
  queries: NicheQuery[];
  status: NicheStatus;
  origin: "seed" | "manual" | "explore" | "agent" | "discover";
  recipe: string | null;
  summary: NicheSummary | null;
  last_scan_at: string | null;
  created_at: string;
  /** Les Shorts de la niche les plus vus ces 30 derniers jours (id de research_videos). */
  top: string[];
}

export interface VideoClassification {
  format: string;
  niche: string;
  recipe: string;
  series: string;
  effort: number;
  ai_made: boolean | null;
  faceless: boolean | null;
  angle: string;
}

export interface VideoAnalysis {
  summary: string;
  hook_visual: string;
  hook_text: string;
  structure: { t: string; what: string }[];
  pacing: string;
  audio: string;
  on_screen_text: string;
  emotion: string;
  ending: string;
  why_it_works: string[];
  weak_points: string[];
  format: string;
  recipe: string;
  series: string;
  effort: number;
  model?: string | null;
  remake: {
    title: string;
    premise: string;
    hook: string;
    scenario: string;
    style: string;
    speech: string;
    duration_s: number;
    keep: string[];
    change: string[];
  };
}

export interface Adaptation {
  title: string;
  source_language: string;
  subject: string;
  hook: string;
  beats: { t: string; image: string; words: string }[];
  narration: string;
  scenario: string;
  ending: string;
  recipe: string;
  series: string;
  duration_s: number;
  facts_to_check: string[];
  changed: string[];
  model?: string | null;
}

export interface ResearchVideo {
  id: string;
  external_id: string;
  url: string;
  title: string;
  lang: string | null;
  channel_title: string | null;
  channel_subs: number | null;
  channel_created_at: string | null;
  channel_median: number | null;
  published_at: string | null;
  duration_s: number | null;
  views: number;
  likes: number;
  comments: number;
  niche_id: string | null;
  classification: VideoClassification | null;
  analysis: VideoAnalysis | null;
  analysis_at: string | null;
  /** Version fidèle en français (agent research_adapt). */
  adaptation: Adaptation | null;
  status: ResearchVideoStatus;
  concept_id: string | null;
  /** Calculés à la lecture (mêmes règles que le worker). */
  outlier: number | null;
  outlier_base: "chaîne" | "abonnés" | null;
  views_per_day: number;
  age_days: number;
  remake_score: number;
}

export interface NicheBrief {
  niche: string;
  verdict: string;
  why: string;
  how: string;
  first_videos: string[];
}

export interface ResearchReport {
  id: string;
  created_at: string;
  model: string | null;
  report: {
    headline: string;
    /** LA vidéo à faire maintenant (rapports depuis le 04/10). */
    next_video?: { ref: string; why: string; how: string; video_id?: string } | null;
    niches: NicheBrief[];
    remakes: { ref: string; why: string; angle: string; video_id?: string }[];
    fast_formats: { format: string; why: string; recipe: string }[];
    new_niches: { label: string; description: string; queries: string[]; why: string }[];
    warnings: string[];
  };
}

export interface ResearchJob {
  id: string;
  action: ResearchAction;
  status: "queued" | "running";
  video_id: string | null;
  q: string | null;
  question: string | null;
  progress: number | null;
  label: string | null;
}

export interface ResearchAsk {
  id: string;
  question: string;
  status: "queued" | "running" | "done" | "failed";
  answer: string | null;
  video_ids: string[];
  niches: string[];
  error: string | null;
  at: string;
}

export interface ResearchOverview {
  settings: ResearchSettings;
  searchesToday: number;
  niches: ResearchNiche[];
  /** Vidéos à reproduire, les meilleures d'abord (retenues par le stratège en tête). */
  videos: ResearchVideo[];
  /** Aperçu des niches : leurs Shorts les plus vus du mois qui ne sont pas dans `videos`. */
  nicheVideos: ResearchVideo[];
  reproduced: ResearchVideo[];
  report: ResearchReport | null;
  /** Questions posées au stratège, les plus récentes d'abord. */
  asks: ResearchAsk[];
  jobs: ResearchJob[];
  lastJob: { action: ResearchAction; status: string; finished_at: string | null; error: string | null; result: Record<string, unknown> | null } | null;
}

export const SEARCH_CAP = 100;

export const PHASE_HELP: Record<NichePhase, string> = {
  émergente: "Les premiers tubes datent de moins de 4 mois : peu de concurrence, à prendre tôt.",
  "en hausse": "Les meilleurs Shorts des deux derniers mois font nettement plus de vues que ceux d’avant, et elle monte plus vite que l’ensemble des niches.",
  installée: "Elle suit le marché : la demande tient, la concurrence aussi.",
  "en baisse": "Les vues des meilleurs Shorts retombent : la niche s’essouffle ou sature.",
  "à vide": "Pas de tube : peu de demande pour ces recherches.",
  inconnue: "Courbe encore trop courte (4 mois jugés ou 4 semaines de relevés il faut).",
};

export const EFFORT_LABELS: Record<number, string> = {
  1: "une recette le fait telle quelle",
  2: "une recette, avec un réglage",
  3: "nouvelle recette à écrire",
  4: "difficile pour l’IA",
  5: "impossible sans tournage",
};

export const RECIPE_LABELS: Record<string, string> = {
  timelapse: "chantier en accéléré",
  tour: "visite",
  story: "récit narré",
  drama: "histoire jouée",
  quote: "citation",
  none: "aucune recette",
};

export const VERDICT_TONES: Record<string, "success" | "info" | "warning" | "danger" | "neutral"> = {
  "à lancer": "success",
  "à tester": "info",
  "à surveiller": "warning",
  "à éviter": "danger",
};

// ---- Calculs (worker/research.py) -----------------------------------------------------------------------------------

const SUBS_FLOOR = 1_000;

/** Titre écrit surtout en alphabet latin (même règle que worker/research.mostly_latin) : une vidéo en hindi ou en
 * bengali se refait mal en français. */
export function mostlyLatin(text: string): boolean {
  const letters = [...text].filter((c) => /\p{L}/u.test(c));
  if (!letters.length) return true;
  return letters.filter((c) => (c.codePointAt(0) ?? 0) < 0x250).length / letters.length >= 0.6;
}

const EFFORT_FEASIBILITY: Record<number, number> = { 1: 1.0, 2: 0.8, 3: 0.55, 4: 0.3, 5: 0.0 };

export function ageDays(publishedAt: string | null, at: Date): number {
  if (!publishedAt) return 1 / 24;
  return Math.max((at.getTime() - new Date(publishedAt).getTime()) / 86_400_000, 1 / 24);
}

export function outlierOf(views: number, channelMedian: number | null, channelSubs: number | null): [number | null, "chaîne" | "abonnés" | null] {
  if (channelMedian && channelMedian > 0) return [Math.round((views / channelMedian) * 100) / 100, "chaîne"];
  if (channelSubs != null) return [Math.round((views / Math.max(channelSubs, SUBS_FLOOR)) * 100) / 100, "abonnés"];
  return [null, null];
}

function demand(views: number): number {
  if (!views || views <= 0) return 0;
  return Math.max(0, Math.min(1, (Math.log10(views) - 4) / 3));
}

/** Même formule que worker/research.remake_score. */
export function remakeScore(views: number, ratio: number | null, age: number, effort: number | null | undefined): number {
  const over = Math.log10(Math.max(ratio ?? 1, 1)) / 2;
  const speed = demand((views / age) * 7);
  const fresh = Math.max(0, 1 - age / 120);
  const feas = effort != null ? (EFFORT_FEASIBILITY[effort] ?? 0.5) : 0.5;
  return Math.round(100 * (0.35 * Math.min(over, 1) + 0.25 * speed + 0.15 * fresh + 0.25 * feas) * 10) / 10;
}

/** Miniature YouTube d'un Short : la vidéo verticale est au centre de l'image 4:3 (object-cover la recadre). */
export function thumbUrl(externalId: string): string {
  return `https://i.ytimg.com/vi/${externalId}/hqdefault.jpg`;
}

export function parseResearchSettings(value: unknown): ResearchSettings {
  const v = (value && typeof value === "object" ? value : {}) as Partial<ResearchSettings>;
  const num = (x: unknown, d: number) => (typeof x === "number" && Number.isFinite(x) ? x : d);
  return {
    daily_searches: num(v.daily_searches, DEFAULT_RESEARCH.daily_searches),
    auto_watch: num(v.auto_watch, DEFAULT_RESEARCH.auto_watch),
    brief_weekday: num(v.brief_weekday, DEFAULT_RESEARCH.brief_weekday),
    min_views: num(v.min_views, DEFAULT_RESEARCH.min_views),
  };
}
