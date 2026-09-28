/**
 * Point d'entrée de la couche données.
 *
 * Délègue au mock quand `NEXT_PUBLIC_MOCK=1` ou quand Supabase n'est pas
 * configuré (`NEXT_PUBLIC_SUPABASE_URL` absent), sinon à `./supabase`.
 */
import type { Series } from "@/lib/types";

import type { DataSource } from "./contract";
import { mockSource } from "./mock";
import { supabaseSource } from "./supabase";

export type {
  CategorySummary,
  ChannelFilter,
  DataSource,
  ExperimentSummary,
  FormatSummary,
  VideoComment,
  VideoDetail,
} from "./contract";

export const IS_MOCK =
  process.env.NEXT_PUBLIC_MOCK === "1" || !process.env.NEXT_PUBLIC_SUPABASE_URL;

const source: DataSource = IS_MOCK ? mockSource : supabaseSource;

export const getChannels: DataSource["getChannels"] = () => source.getChannels();
export const getOverviewKpis: DataSource["getOverviewKpis"] = (channel) =>
  source.getOverviewKpis(channel);
export const getDailyViews: DataSource["getDailyViews"] = (days) => source.getDailyViews(days);
export const getVideoDetail: DataSource["getVideoDetail"] = (id) => source.getVideoDetail(id);
export const listProductions: DataSource["listProductions"] = () => source.listProductions();
export const getProductionCard: DataSource["getProductionCard"] = (id) => source.getProductionCard(id);
export const getSchedule: DataSource["getSchedule"] = (fromISO, days) =>
  source.getSchedule(fromISO, days);
export const listConcepts: DataSource["listConcepts"] = () => source.listConcepts();
export const getExperimentSummary: DataSource["getExperimentSummary"] = () =>
  source.getExperimentSummary();
export const listSeries = (): Promise<Series[]> => source.listSeries?.() ?? Promise.resolve([]);
