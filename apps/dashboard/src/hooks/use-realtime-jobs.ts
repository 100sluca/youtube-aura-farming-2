"use client";

/**
 * Abonnement temps réel aux jobs — STUB.
 *
 * Cible : Supabase Realtime sur la table `jobs` (postgres_changes, event `*`),
 * filtré sur les `production_id` affichés. À chaque événement, la carte de la
 * production concernée est mise à jour (job remplacé / inséré, `progress_pct`
 * et `current_step` recalculés comme dans la vue `v_production_progress`).
 *
 * Exemple d'implémentation future :
 *
 *   const supabase = createBrowserClient(url, anonKey)
 *   const channel = supabase
 *     .channel("jobs")
 *     .on("postgres_changes", { event: "*", schema: "public", table: "jobs" }, (payload) => …)
 *     .subscribe()
 *   return () => supabase.removeChannel(channel)
 *
 * Pour l'instant, renvoie les données initiales telles quelles.
 */
import type { ProductionCard } from "@/lib/types";

export function useRealtimeJobs(initial: ProductionCard[]): ProductionCard[] {
  return initial;
}
