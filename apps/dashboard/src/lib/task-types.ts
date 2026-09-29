/** Gestionnaire de tâches (panneau de droite) : types partagés serveur / navigateur. Calcul : lib/tasks.ts. */
import type { JobStatus, JobType, ProductionStatus } from "@/lib/types";

/** Une vidéo en fabrication, vue comme une tâche. */
export interface TaskProduction {
  id: string;
  title: string;
  channel_name: string | null;
  series_name: string | null;
  status: ProductionStatus;
  /** Étape lisible : « Écriture du script », « Clip 3 sur 6 », « Storyboard à valider », « En pause · 9 clips sur 13 faits »… */
  stage: string;
  progress_pct: number;
  running: boolean;
  /** Début de l'étape en cours (ISO). */
  step_started_at: string | null;
  /** Fin estimée de la vidéo (ISO), d'après les durées mesurées des tâches précédentes ; null en pause. */
  eta_at: string | null;
  /** Place dans la file (1 = la prochaine), null si elle tourne, se prépare, est en pause ou attend Luca. */
  queue_position: number | null;
  /** Image retenue de la première scène du storyboard (asset servi par /api/media). */
  cover_asset_id: string | null;
  error: string | null;
  updated_at: string;
  /** « preparation » : script ou images du storyboard pas encore faits ; « fabrication » : clips, voix, montage. */
  phase: "preparation" | "fabrication";
  /** En pause (docs/40) : elle garde sa place et tout ce qui est fait ; ses tâches attendent la reprise. */
  paused: boolean;
  /** Pause demandée pendant une étape qui se termine (clip, script…) : elle s'arrête à la fin de cette étape. */
  pause_pending: boolean;
  /** Type du job en cours (null si rien ne tourne). */
  step_type: JobType | null;
  /** L'étape en cours tourne sur la carte graphique (images, clip, voix) : « Pause tout de suite » l'interrompt. */
  gpu_step: boolean;
  /** Avancement de l'étape en cours (0-100) et sa fin estimée (ISO). */
  step_progress: number | null;
  step_end_at: string | null;
  /** Clips faits et prévus (0 et 0 avant le rendu). */
  clips_done: number;
  clips_total: number;
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
  /** Vidéos validées qui attendent la carte graphique, dans l'ordre où elle les fera (réordonnable, docs/40). */
  queued: TaskProduction[];
  /** Script ou images du storyboard en attente : passent avant les clips (priorité) pour que Luca valide vite. */
  preparing: TaskProduction[];
  /** En pause, dans l'ordre de la file (la place qu'elles retrouveront à la reprise). */
  paused: TaskProduction[];
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
  preparing: [],
  paused: [],
  waiting: [],
  review_videos: 0,
  failed: [],
  stopped: [],
  other_jobs: [],
  failed_jobs: [],
  queue_end_at: null,
  counts: { active: 0, attention: 0, failures: 0 },
};

/** Toutes les vidéos du panneau, quelle que soit leur rubrique (Bibliothèque : étape de chaque vidéo en fabrication). */
export function allTasks(board: TaskBoard): TaskProduction[] {
  return [...board.running, ...board.queued, ...board.preparing, ...board.paused, ...board.waiting, ...board.failed, ...board.stopped];
}
