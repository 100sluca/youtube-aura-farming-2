/**
 * Données de la page Création : thèmes, idées à trier, idées en cours d'écriture, storyboards à valider et vidéos
 * en préparation pour la chaîne choisie. Serveur uniquement.
 */
import { IS_MOCK, listConcepts, listSeries } from "@/lib/data";
import { mapConcept, productionCards } from "@/lib/data/supabase";
import { favoriteProductions } from "@/lib/favorites";
import { getGeminiStatus } from "@/lib/gemini";
import { supabaseAdmin } from "@/lib/supabase-admin";
import type { Channel, Concept, ProductionCard, Series } from "@/lib/types";

export interface IdeaJob {
  series: string | null;
  count: number | null;
  status: "queued" | "running";
  created_at: string;
}

export interface PreparingItem {
  id: string;
  title: string;
  stage: string;
}

export interface CreationData {
  series: Series[];
  /** Thème présélectionné : le dernier utilisé sur la chaîne, sinon le premier thème actif. */
  defaultSeries: string | null;
  ideas: Concept[];
  rejected: Concept[];
  ideaJobs: IdeaJob[];
  storyboards: ProductionCard[];
  /** Storyboards gardés dans Favoris (étoile allumée, docs/19) : identifiants de production. */
  favorites: string[];
  preparing: PreparingItem[];
  /** Limite Gemini atteinte : heure de reprise des clips Gemini (docs/17), sinon null. */
  geminiQuotaUntil: string | null;
}

const STAGES: Record<string, string> = {
  draft: "Script en file",
  scripting: "Écriture du script",
  generating: "Images du storyboard",
};

/** Idées à trier (toutes, quel que soit leur âge) et dernières idées écartées. */
async function ideasToSort(): Promise<{ ideas: Concept[]; rejected: Concept[] }> {
  if (IS_MOCK) {
    const concepts = await listConcepts();
    return { ideas: concepts.filter((c) => c.status === "proposed"), rejected: concepts.filter((c) => c.status === "rejected").slice(0, 12) };
  }
  const db = supabaseAdmin();
  const [open, rejected] = await Promise.all([
    db.from("v_concept_overview").select("*").in("status", ["proposed", "approved"]).limit(500),
    db.from("v_concept_overview").select("*").eq("status", "rejected").order("created_at", { ascending: false }).limit(12),
  ]);
  if (open.error) throw new Error(open.error.message);
  return { ideas: (open.data ?? []).map(mapConcept), rejected: (rejected.data ?? []).map(mapConcept) };
}

export async function getCreationData(channel: Channel | undefined): Promise<CreationData> {
  const [allSeries, sorted] = await Promise.all([listSeries(), ideasToSort()]);
  const series = allSeries.filter((s) => s.is_active);
  const lastUsed = allSeries.find((s) => s.id === channel?.last_series_id && s.is_active);
  const defaultSeries = lastUsed?.slug ?? series[0]?.slug ?? null;
  const byScore = (a: Concept, b: Concept) => (b.score ?? 0) - (a.score ?? 0) || b.created_at.localeCompare(a.created_at);
  const ideas = sorted.ideas.sort(byScore);
  const rejected = sorted.rejected;
  if (IS_MOCK || !channel) return { series, defaultSeries, ideas, rejected, ideaJobs: [], storyboards: [], favorites: [], preparing: [], geminiQuotaUntil: null };

  const db = supabaseAdmin();
  const [jobs, prods, gemini] = await Promise.all([
    db.from("jobs").select("payload, status, created_at").eq("type", "ideate").in("status", ["queued", "running"]).order("created_at"),
    db
      .from("productions")
      .select("id, status, concept_id, concepts(title)")
      .eq("channel_id", channel.id)
      .in("status", ["draft", "scripting", "generating", "storyboard_review"])
      .order("created_at"),
    getGeminiStatus(),
  ]);
  const ideaJobs: IdeaJob[] = (jobs.data ?? []).map((j) => {
    const payload = (j.payload ?? {}) as { series?: string; count?: number };
    return { series: payload.series ?? null, count: payload.count ?? null, status: j.status as IdeaJob["status"], created_at: j.created_at };
  });

  const rows = (prods.data ?? []) as { id: string; status: string; concepts: { title: string } | { title: string }[] | null }[];
  const reviewIds = rows.filter((p) => p.status === "storyboard_review").map((p) => p.id);
  // « generating » sans clip en file = storyboard en cours (après validation, les clips prennent le relais)
  const generatingIds = rows.filter((p) => p.status === "generating").map((p) => p.id);
  const { data: clipRows } = generatingIds.length
    ? await db.from("jobs").select("production_id").in("production_id", generatingIds).eq("type", "generate_clip")
    : { data: [] as { production_id: string }[] };
  const rendering = new Set((clipRows ?? []).map((r) => r.production_id));
  const titleOf = (p: (typeof rows)[number]) => (Array.isArray(p.concepts) ? p.concepts[0]?.title : p.concepts?.title) ?? "Vidéo sans titre";
  const preparing = rows
    .filter((p) => p.status !== "storyboard_review" && !rendering.has(p.id))
    .map((p) => ({ id: p.id, title: titleOf(p), stage: STAGES[p.status] ?? p.status }));

  const [storyboards, favorites] = reviewIds.length ? await Promise.all([productionCards(reviewIds), favoriteProductions(reviewIds)]) : [[], []];
  return {
    series,
    defaultSeries,
    ideas,
    rejected,
    ideaJobs,
    storyboards,
    favorites,
    preparing,
    geminiQuotaUntil: gemini.quota_until,
  };
}
