/** État de la machine (barre latérale « Machine », docs/28-sante-machine.md) : types partagés client / serveur. */

export type ServiceState = "ok" | "down" | "unknown";

export interface SystemStatus {
  at: string;
  /** RAM de la machine (Go) ; « réservable » = RAM + fichier d'échange encore disponibles (signe de vie du worker). */
  ram: { totalGb: number; freeGb: number; commitFreeGb: number | null; commitTotalGb: number | null };
  vram: { usedMb: number; totalMb: number } | null;
  comfy: { state: ServiceState; queue: number | null };
  worker: {
    state: ServiceState;
    /** secondes depuis son dernier signe de vie (toutes les 30 s) */
    lastBeatS: number | null;
    /** relance en cours : il finit ses tâches, puis se relance tout seul */
    draining: boolean;
    restartPending: boolean;
    workerId: string | null;
  };
  /** tâche en cours sur la carte graphique (un clip, un storyboard, une voix) */
  gpuJob: { type: string; label: string | null; startedAt: string | null } | null;
  dashboard: { rssGb: number; uptimeS: number; pid: number };
  /** phrases prêtes à afficher, de la plus grave à la moins grave */
  warnings: string[];
}

/** Programme qui occupe de la mémoire (fenêtre « Machine », calculé à l'ouverture). */
export interface MemoryHog {
  label: string;
  gb: number;
  count: number;
  /** geste possible depuis le panneau */
  restart?: RestartTarget;
}

export type RestartTarget = "comfyui" | "worker" | "dashboard";

export const EMPTY_SYSTEM_STATUS: SystemStatus = {
  at: "",
  ram: { totalGb: 0, freeGb: 0, commitFreeGb: null, commitTotalGb: null },
  vram: null,
  comfy: { state: "unknown", queue: null },
  worker: { state: "unknown", lastBeatS: null, draining: false, restartPending: false, workerId: null },
  gpuJob: null,
  dashboard: { rssGb: 0, uptimeS: 0, pid: 0 },
  warnings: [],
};
