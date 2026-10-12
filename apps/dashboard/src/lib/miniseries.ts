import { IS_MOCK } from "@/lib/data";
import { supabaseAdmin } from "@/lib/supabase-admin";

/**
 * Mini-séries des drames (docs/52) : story_arcs (l'histoire en 3 parties) et app_settings.miniseries, lus par le worker
 * toutes les 2 min (worker/arcs.py). 48 h après la sortie d'une partie, ses vues YouTube + TikTok sont comparées à la
 * médiane de la chaîne ; au-dessus du seuil la suite est proposée ici, ou lancée seule si le pilote est allumé.
 */
export type MiniseriesSettings = { autopilot: boolean; threshold: number; eval_hours: number; parts: number };

export type ArcDecision = {
  part: number;
  views: number;
  median: number | null;
  refs: number;
  ratio: number | null;
  verdict: "suggested" | "below";
  why?: string;
  at: string;
  launched_at?: string;
  autopilot?: boolean;
};

export type ArcPartRow = {
  part: number;
  productionId: string;
  status: string;
  title: string | null;
  videoStatus: string | null;
  publishedAt: string | null;
  scheduledAt: string | null;
};

export type ArcOutlinePart = { n: number; synopsis: string; opens_with?: string; ends_on: string };

export type Arc = {
  id: string;
  title: string;
  status: "active" | "stopped" | "finished";
  partsTotal: number;
  premise: string;
  outline: ArcOutlinePart[];
  decisions: ArcDecision[];
  launchRequest: number | null;
  parts: ArcPartRow[];
  createdAt: string;
};

export type MiniseriesStatus = { settings: MiniseriesSettings; arcs: Arc[] };

const DEFAULTS: MiniseriesSettings = { autopilot: false, threshold: 1, eval_hours: 48, parts: 3 };

type ArcRow = {
  id: string;
  title: string;
  status: Arc["status"];
  parts_total: number;
  outline: { premise?: string; parts?: ArcOutlinePart[] } | null;
  decisions: ArcDecision[] | null;
  launch_request: number | null;
  created_at: string;
  productions:
    | {
        id: string;
        arc_part: number;
        status: string;
        videos: { title: string | null; status: string; published_at: string | null; scheduled_at: string | null; archived_at: string | null }[] | null;
      }[]
    | null;
};

export async function getMiniseries(channelId: string | null): Promise<MiniseriesStatus> {
  if (IS_MOCK) return { settings: DEFAULTS, arcs: [] };
  const db = supabaseAdmin();
  let query = db
    .from("story_arcs")
    .select(
      "id, title, status, parts_total, outline, decisions, launch_request, created_at, productions(id, arc_part, status, videos(title, status, published_at, scheduled_at, archived_at))",
    )
    .order("created_at", { ascending: false })
    .limit(12);
  if (channelId) query = query.eq("channel_id", channelId);
  const [{ data: setting }, { data: rows }] = await Promise.all([
    db.from("app_settings").select("value").eq("key", "miniseries").maybeSingle(),
    query,
  ]);
  const arcs = ((rows ?? []) as ArcRow[]).map((a) => ({
    id: a.id,
    title: a.title,
    status: a.status,
    partsTotal: a.parts_total,
    premise: a.outline?.premise ?? "",
    outline: a.outline?.parts ?? [],
    decisions: a.decisions ?? [],
    launchRequest: a.launch_request,
    createdAt: a.created_at,
    parts: (a.productions ?? [])
      .filter((p) => !["failed", "cancelled", "archived"].includes(p.status))
      .map((p) => {
        const v = (p.videos ?? []).find((x) => !x.archived_at) ?? null;
        return {
          part: p.arc_part,
          productionId: p.id,
          status: p.status,
          title: v?.title ?? null,
          videoStatus: v?.status ?? null,
          publishedAt: v?.published_at ?? null,
          scheduledAt: v?.scheduled_at ?? null,
        };
      })
      .sort((x, y) => x.part - y.part),
  }));
  return { settings: { ...DEFAULTS, ...((setting?.value ?? {}) as Partial<MiniseriesSettings>) }, arcs };
}
