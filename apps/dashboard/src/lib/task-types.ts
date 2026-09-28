/** Gestionnaire de tâches (panneau de droite) : types partagés serveur / navigateur. Calcul : lib/tasks.ts. */
import type { JobStatus, JobType, ProductionStatus } from "@/lib/types";

/** Une vidéo en fabrication, vue comme une tâche. */
export interface TaskProduction {
  id: string;
  title: string;
  channel_name: string | null;
  series_name: string | null;
  status: ProductionStatus;
  /** Étape lisible : « Écriture du script », « Clip 3 sur 6 », « Storyboard à valider »… */
  stage: string;
  progress_pct: number;
  running: boolean;
  /** Début de l'étape en cours (ISO). */
  step_started_at: string | null;
  /** Fin estimée de la vidéo (ISO), d'après les durées mesurées des tâches précédentes. */
  eta_at: string | null;
  /** Place dans la file (1 = la prochaine), null si elle tourne ou attend Luca. */
  queue_position: number | null;
  /** Image retenue de la première scène du storyboard (asset servi par /api/media). */
  cover_asset_id: string | null;
  error: string | null;
  updated_at: string;
}

/** Une tâche hors vidéo : idées, synchronisation des stats, import d'une chaîne, stratégie… */
export interface TaskJob {
  id: string;
  type: JobType;
  label: string;
  status: JobStatus;
  progress: number;
  progress_label: string | null;
  detail: string | null; // thème, chaîne…
  started_at: string | null;
  created_at: string;
  error: string | null;
}

export interface TaskBoard {
  generated_at: string;
  running: TaskProduction[];
  queued: TaskProduction[];
  /** Storyboards prêts : la fabrication attend le ✓ de Luca (page Création). */
  waiting: TaskProduction[];
  /** Vidéos finies qui attendent l'autorisation de publier (Bibliothèque, filtre « À valider »). */
  review_videos: number;
  failed: TaskProduction[];
  stopped: TaskProduction[];
  other_jobs: TaskJob[];
  failed_jobs: TaskJob[];
  /** Fin estimée de toute la file (ISO). */
  queue_end_at: string | null;
  counts: { active: number; attention: number; failures: number };
}

export const EMPTY_TASK_BOARD: TaskBoard = {
  generated_at: new Date(0).toISOString(),
  running: [],
  queued: [],
  waiting: [],
  review_videos: 0,
  failed: [],
  stopped: [],
  other_jobs: [],
  failed_jobs: [],
  queue_end_at: null,
  counts: { active: 0, attention: 0, failures: 0 },
};
