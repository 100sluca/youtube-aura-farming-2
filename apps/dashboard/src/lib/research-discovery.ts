/**
 * Recherche → Découverte (docs/63 §9) : les chaînes qui percent, regroupées par niche et classées par argent estimé.
 * Serveur uniquement ; types partagés avec le composant.
 */
import { IS_MOCK } from "@/lib/data";
import { supabaseAdmin } from "@/lib/supabase-admin";

export interface DiscoveredChannel {
  id: string;
  title: string;
  lang: string | null;
  months: number | null;
  subs: number | null;
  videos: number | null;
  format: "long" | "short" | "mixed" | null;
  monthlyViews: number | null;
  rpm: number | null;
  revenue: number | null;
  niche: string;
  category: string;
  faceless: boolean | null;
  aiMade: boolean | null;
  effort: number | null;
  why: string;
  formatName: string;
  top: { id: string; title: string; views: number; duration_s: number }[];
  status: string;
}

export interface DiscoveredNiche {
  niche: string;
  category: string;
  revenue: number;
  channels: DiscoveredChannel[];
  langs: string[];
  youngest: number | null;
  effort: number | null;
}

export interface DiscoveryData {
  niches: DiscoveredNiche[];
  total: number;
  lastRun: string | null;
  seedsDone: number;
  running: { status: string; label: string | null; progress: number | null } | null;
}

const EMPTY: DiscoveryData = { niches: [], total: 0, lastRun: null, seedsDone: 0, running: null };

export async function getDiscovery(): Promise<DiscoveryData> {
  if (IS_MOCK) return EMPTY;
  const db = supabaseAdmin();
  const [rows, seeds, job] = await Promise.all([
    db.from("research_channels").select("*").neq("status", "dismissed").order("monthly_revenue", { ascending: false, nullsFirst: false }).limit(400),
    db.from("research_seed_runs").select("run_at").order("run_at", { ascending: false }).limit(200),
    db
      .from("jobs")
      .select("status, progress, progress_label")
      .eq("type", "research")
      .eq("payload->>action", "discover")
      .in("status", ["queued", "running"])
      .limit(1),
  ]);
  if (rows.error) return EMPTY; // migration 0055 absente
  const now = Date.now();
  const channels: DiscoveredChannel[] = (rows.data ?? []).map((r) => {
    const c = (r.classification ?? {}) as Record<string, unknown>;
    return {
      id: r.channel_ext_id,
      title: r.title,
      lang: r.lang,
      months: r.created_at_yt ? Math.max(0.5, (now - new Date(r.created_at_yt).getTime()) / (30.44 * 86400000)) : null,
      subs: r.subs,
      videos: r.videos,
      format: r.format,
      monthlyViews: r.monthly_views,
      rpm: r.rpm != null ? Number(r.rpm) : null,
      revenue: r.monthly_revenue != null ? Number(r.monthly_revenue) : null,
      niche: String(c.niche || "non classée"),
      category: String(c.category || ""),
      faceless: typeof c.faceless === "boolean" ? c.faceless : null,
      aiMade: typeof c.ai_made === "boolean" ? c.ai_made : null,
      effort: typeof c.effort === "number" ? c.effort : null,
      why: String(c.why || ""),
      formatName: String(c.format_name || ""),
      top: (r.top_videos ?? []) as DiscoveredChannel["top"],
      status: r.status,
    };
  });
  const by = new Map<string, DiscoveredChannel[]>();
  for (const ch of channels) {
    const key = ch.niche.toLowerCase();
    if (!by.has(key)) by.set(key, []);
    by.get(key)!.push(ch);
  }
  const niches: DiscoveredNiche[] = [...by.values()].map((list) => ({
    niche: list[0].niche,
    category: list[0].category,
    revenue: list.reduce((n, c) => n + (c.revenue ?? 0), 0),
    channels: list.sort((a, b) => (b.revenue ?? 0) - (a.revenue ?? 0)),
    langs: [...new Set(list.map((c) => c.lang ?? "?"))],
    youngest: list.reduce<number | null>((m, c) => (c.months == null ? m : m == null ? c.months : Math.min(m, c.months)), null),
    effort: list.reduce<number | null>((m, c) => (c.effort == null ? m : m == null ? c.effort : Math.min(m, c.effort)), null),
  }));
  niches.sort((a, b) => b.revenue - a.revenue);
  const j = job.data?.[0];
  return {
    niches,
    total: channels.length,
    lastRun: seeds.data?.[0]?.run_at ?? null,
    seedsDone: seeds.data?.length ?? 0,
    running: j ? { status: j.status, label: j.progress_label, progress: j.progress } : null,
  };
}
