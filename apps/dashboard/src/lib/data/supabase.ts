/**
 * Source de données Supabase — À BRANCHER.
 *
 * Chaque fonction indique la table / vue / RPC à interroger. Le client à
 * utiliser côté serveur est `supabaseServer()` (RLS) ou `supabaseAdmin()`
 * (service role) de `@/lib/supabase-admin`.
 */
import type { DataSource } from "./contract";

function notWired(): never {
  throw new Error("TODO: brancher Supabase");
}

export const supabaseSource: DataSource = {
  // Table `channels` (order by slug).
  async getChannels() {
    return notWired();
  },

  // Vue `channel_metrics_daily` (90 derniers jours, agrégée par chaîne) +
  // `productions` / `videos` pour le pipeline. `channel` filtre sur channels.slug.
  async getOverviewKpis() {
    return notWired();
  },

  // Table `channel_metrics_daily` : views par jour, pivotée FR / EN.
  async getDailyViews() {
    return notWired();
  },

  // Vue `v_video_overview` where status = 'published' order by published_at desc.
  async listPublishedVideos() {
    return notWired();
  },

  // Vue `v_video_overview` (1 ligne) + `video_metrics_daily` (14 jours) +
  // `video_retention` + `video_comments` + `productions.script`.
  async getVideoDetail() {
    return notWired();
  },

  // Tables `productions` + `videos` + `jobs` + vue `v_production_progress`
  // (status not in ('archived')).
  async listProductions() {
    return notWired();
  },

  // Table `videos` (scheduled_at / youtube_publish_at / published_at dans la
  // fenêtre) croisée avec `channels.publish_slots` ; RPC `next_free_slot`
  // pour le prochain créneau libre.
  async getSchedule() {
    return notWired();
  },

  // Table `concepts` order by score desc, created_at desc.
  async listConcepts() {
    return notWired();
  },

  // Table `alerts` order by created_at desc.
  async listAlerts() {
    return notWired();
  },

  // Vue `v_video_overview` agrégée par format puis par category.
  async getExperimentSummary() {
    return notWired();
  },
};
