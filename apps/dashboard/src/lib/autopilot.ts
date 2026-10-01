import { IS_MOCK } from "@/lib/data";
import { supabaseAdmin } from "@/lib/supabase-admin";

/** Pilote automatique (docs/46) : app_settings.autopilot, lu par le worker toutes les 2 min (worker/autopilot.py). */
export type AutopilotSettings = {
  enabled: boolean;
  series: string | null;
  target: number;
  channel_id: string | null;
  started_at: string | null;
  stopped_at?: string | null;
  stopped_reason?: string | null;
};

export type AutopilotProduction = { id: string; title: string; status: string; created_at: string };

export type AutopilotStatus = AutopilotSettings & { productions: AutopilotProduction[] };

const EMPTY: AutopilotStatus = { enabled: false, series: null, target: 3, channel_id: null, started_at: null, productions: [] };

export async function getAutopilot(): Promise<AutopilotStatus> {
  if (IS_MOCK) return EMPTY;
  const db = supabaseAdmin();
  const { data } = await db.from("app_settings").select("value").eq("key", "autopilot").maybeSingle();
  const value = { ...EMPTY, ...((data?.value ?? {}) as Partial<AutopilotSettings>) };
  if (!value.started_at) return { ...value, productions: [] };
  const { data: rows } = await db
    .from("productions")
    .select("id, status, created_at, concepts(title)")
    .eq("autopilot", true)
    .gte("created_at", value.started_at)
    .order("created_at");
  const productions = ((rows ?? []) as { id: string; status: string; created_at: string; concepts: { title: string } | { title: string }[] | null }[]).map(
    (p) => ({
      id: p.id,
      status: p.status,
      created_at: p.created_at,
      title: (Array.isArray(p.concepts) ? p.concepts[0]?.title : p.concepts?.title) ?? "Idée en cours de choix",
    }),
  );
  return { ...value, productions };
}
