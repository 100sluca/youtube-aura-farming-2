import { IS_MOCK } from "@/lib/data";
import type { ScenarioItem, ScenarioPlan } from "@/lib/scenario-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

/**
 * Mes scénarios (docs/59) : les scénarios libres que Luca confie à l'équipe d'agents depuis Création (concepts.scenario,
 * migration 0048). Chacun devient une production du thème caché « Mes scénarios » : le metteur en scène le met en forme
 * (concepts.scenario.plan, montré ici), le scénariste écrit les plans, le relecteur vérifie la fidélité, puis le
 * storyboard arrive à valider dans Création comme celui d'un drame.
 */
type Row = {
  id: string;
  title: string;
  created_at: string;
  scenario: { text?: string; style?: string; speech?: string; duration_s?: number | null; plan?: ScenarioPlan } | null;
  productions: { id: string; status: string; error: string | null; created_at: string; videos: { id: string; status: string; archived_at: string | null }[] | null }[] | null;
};

/** Les derniers scénarios de la chaîne, du plus récent au plus ancien, avec leur production la plus récente. */
export async function getScenarios(channelId: string, limit = 8): Promise<ScenarioItem[]> {
  if (IS_MOCK) return [];
  const { data, error } = await supabaseAdmin()
    .from("concepts")
    .select("id, title, created_at, scenario, productions(id, status, error, created_at, videos(id, status, archived_at))")
    .eq("channel_id", channelId)
    .not("scenario", "is", null)
    .order("created_at", { ascending: false })
    .limit(limit);
  if (error) return []; // migration 0048 absente : pas de carte remplie, rien ne casse
  return ((data ?? []) as unknown as Row[]).map((r) => {
    const prod = [...(r.productions ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ?? null;
    const video = prod?.videos?.find((v) => !v.archived_at) ?? null;
    const s = r.scenario ?? {};
    return {
      conceptId: r.id,
      title: r.title,
      text: s.text ?? "",
      createdAt: r.created_at,
      style: s.style ?? "auto",
      speech: s.speech ?? "auto",
      durationS: s.duration_s ?? null,
      plan: s.plan ?? null,
      productionId: prod?.id ?? null,
      status: prod?.status ?? null,
      error: prod?.error ?? null,
      videoId: video?.id ?? null,
      videoStatus: video?.status ?? null,
    };
  });
}
