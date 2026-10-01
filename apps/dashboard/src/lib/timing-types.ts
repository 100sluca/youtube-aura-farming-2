/** Temps de fabrication d'une vidéo (docs/45) : partagé entre le serveur (lib/timing.ts) et la fiche de la vidéo. */
import type { JobType } from "@/lib/types";

export type TimingStep = {
  type: JobType;
  /** temps de calcul cumulé de tous les passages (retentés, refaits, attente d'un service compris) */
  seconds: number;
  /** passages en plus du premier de chaque tâche : échecs retentés, attentes, reprises, Refaire */
  retries: number;
  /** passages ratés, arrêtés ou coupés par un arrêt du worker */
  lost: number;
};

export type TimingItem = { scene: number; seconds: number; runs: number };

export type ProductionTiming = {
  /** true : vidéo faite avant le journal des passages (30/09), temps lus sur les tâches, donc approximatifs */
  approx: boolean;
  /** somme des temps de calcul (script → contrôle qualité) */
  total_s: number;
  /** du premier départ au dernier arrêt, attentes comprises */
  span_s: number | null;
  /** fin des images → lancement du rendu : le temps passé à attendre la validation du storyboard */
  validation_s: number | null;
  steps: TimingStep[];
  /** une ligne par clip, dans l'ordre des scènes */
  clips: TimingItem[];
  /** une ligne par image générée (essais refusés compris) ; secondes connues pour les vidéos faites après le 30/09 */
  images: { count: number; timed: TimingItem[] };
};
