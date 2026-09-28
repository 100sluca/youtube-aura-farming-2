/**
 * Rapports de l'agent analyste (docs/25-dashboard-statistiques.md) : lecture des derniers rapports d'une chaîne et
 * avis sur une vidéo, pour le Dashboard et la fiche d'une vidéo (Bibliothèque). Serveur uniquement.
 */
import { IS_MOCK } from "@/lib/data";
import type { AnalysisReport, VideoInsight } from "@/lib/stats-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;

export function mapReport(r: Row): AnalysisReport {
  const report = (r.report as Row | null) ?? null;
  const stats = (r.stats as Row | null) ?? {};
  return {
    id: r.id,
    created_at: r.created_at,
    videos: Number(r.videos ?? 0),
    judged: Number(stats.judged ?? 0),
    median_views: stats.median_views === null || stats.median_views === undefined ? null : Number(stats.median_views),
    summary: report?.summary ?? null,
    patterns: (report?.patterns as AnalysisReport["patterns"] | undefined) ?? [],
    experiments: (report?.experiments as AnalysisReport["experiments"] | undefined) ?? [],
    diagnoses: (report?.videos as AnalysisReport["diagnoses"] | undefined) ?? [],
  };
}

/** Les derniers rapports d'une chaîne, le plus récent d'abord. */
export async function recentReports(channelId: string | null, limit = 6): Promise<AnalysisReport[]> {
  if (!channelId || IS_MOCK) return [];
  const { data, error } = await supabaseAdmin()
    .from("performance_reports")
    .select("*")
    .eq("channel_id", channelId)
    .order("created_at", { ascending: false })
    .limit(limit);
  if (error) throw new Error(error.message);
  return ((data as Row[] | null) ?? []).map(mapReport);
}

/** Avis de l'agent sur une vidéo : le plus récent des rapports qui en parlent. */
export function insightFrom(reports: AnalysisReport[], videoId: string): VideoInsight | null {
  for (const r of reports) {
    const d = r.diagnoses.find((x) => x.video_id === videoId);
    if (d) return { verdict: d.verdict, score: d.score, why: d.why, worked: d.worked ?? [], missed: d.missed ?? [], report_at: r.created_at };
  }
  return null;
}

/** Avis de l'agent analyste sur une vidéo, pour sa fiche. */
export async function getVideoInsight(videoId: string, channelId: string): Promise<VideoInsight | null> {
  try {
    return insightFrom(await recentReports(channelId), videoId);
  } catch {
    return null; // migration 0016 absente
  }
}
