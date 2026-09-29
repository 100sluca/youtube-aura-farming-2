/**
 * Gestionnaire de tâches : ce que le PC fabrique, dans l'ordre où il le fera, avec l'étape en cours, l'avancement
 * et une heure de fin estimée. Serveur uniquement (clé service role) ; le panneau l'interroge toutes les quelques
 * secondes par l'action fetchTaskBoard (app/tasks/actions.ts).
 *
 * Ordre (claim_jobs, migration 0027, docs/40) : priorité du job, puis place de sa vidéo dans la file (queueKey : celle
 * choisie par Luca, sinon l'heure de ses premiers clips, sinon sa création), puis ancienneté ; les vidéos en pause sont
 * sautées. La carte graphique ne fait qu'une chose à la fois (voie « gpu » du worker : storyboard, clips, voix) : on
 * déroule sa file dans cet ordre pour dater la fin de chaque vidéo ; le reste (script, montage…) tourne en parallèle et
 * s'ajoute au bout.
 *
 * Estimation : durée médiane des 300 derniers jobs terminés de chaque type (valeurs par défaut sinon).
 */
import { IS_MOCK } from "@/lib/data";
import { formatDateTime, formatTime, parisDayKey } from "@/lib/format";
import { JOB_TYPE_LABELS } from "@/lib/labels";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { EMPTY_TASK_BOARD, type TaskBoard, type TaskJob, type TaskProduction } from "@/lib/task-types";
import type { JobStatus, JobType, ProductionStatus } from "@/lib/types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;

const ACTIVE: ProductionStatus[] = ["draft", "scripting", "storyboard_review", "generating", "assembling"];
// La voix passe aussi par la voie GPU du worker depuis les moteurs PyTorch (docs/18-voix.md)
const GPU_TYPES = new Set<string>(["storyboard", "generate_clip", "tts"]);
/** Poids de chaque étape dans la barre d'avancement d'une vidéo (somme 100). */
const WEIGHTS: Partial<Record<JobType, number>> = { script: 10, storyboard: 15, generate_clip: 55, tts: 4, assemble: 10, qa: 3, seo: 3 };
/** Durées par défaut (s) tant qu'aucun job de ce type n'a été mesuré (mesures du 25/09, docs/14). */
const DEFAULT_S: Partial<Record<JobType, number>> = {
  script: 240, storyboard: 360, render: 5, generate_clip: 300, tts: 20, seo: 60, assemble: 60, qa: 15,
  ideate: 90, import_channel: 60, sync_metrics: 60, sync_retention: 20, sync_comments: 20, strategy: 90, improve: 120, upload: 120,
  tiktok_publish: 90, sync_tiktok: 10,
};
/** Jobs interrompus par une pause ou un arrêt (SQL pause_productions, cancel_production) : ils repartent à la reprise. */
const PAUSE_MARK = "Mise en pause";
const STOP_MARK = "Arrêtée par l'utilisateur";

async function rows(q: PromiseLike<{ data: unknown; error: { message?: string } | null }>): Promise<Row[]> {
  const { data, error } = await q;
  if (error) throw new Error(error.message ?? String(error));
  return (data as Row[] | null) ?? [];
}

function median(values: number[]): number {
  const s = [...values].sort((a, b) => a - b);
  return s.length ? s[Math.floor(s.length / 2)] : 0;
}

const seconds = (from: string | null, to: number) => (from ? Math.max(0, (to - new Date(from).getTime()) / 1000) : 0);

/** Horodatage Postgres (jusqu'à la microseconde) en microsecondes : deux places de la file diffèrent parfois d'1 µs. */
function micros(ts: string): number {
  const frac = /\.(\d+)/.exec(ts)?.[1] ?? "";
  return Math.floor(Date.parse(ts) / 1000) * 1_000_000 + Number(frac.padEnd(6, "0").slice(0, 6));
}

/** « à 09:30 » aujourd'hui (heure de Paris), sinon « le mer. 30 sept., 09:30 ». */
function whenLabel(ts: string, nowMs: number): string {
  return parisDayKey(ts) === parisDayKey(new Date(nowMs).toISOString()) ? `à ${formatTime(ts)}` : `le ${formatDateTime(ts)}`;
}

function stageLabel(job: Row, clipJobs: Row[]): string {
  const type = job.type as JobType;
  if (type === "generate_clip") {
    const done = clipJobs.filter((j) => j.status === "done").length;
    const base = `Clip ${Math.min(clipJobs.length, done + 1)} sur ${clipJobs.length}`;
    // Gemini en ligne (docs/17) : le job attend la vidéo ou la fin de la limite, remis en file entre deux passages
    const gemini = clipJobs.find((j) => j.status === "queued" && typeof j.progress_label === "string" && j.progress_label.startsWith("Gemini"));
    return gemini ? `${base} · ${gemini.progress_label}` : base;
  }
  const base = JOB_TYPE_LABELS[type] ?? type;
  return job.progress_label && type !== "script" ? `${base} · ${job.progress_label}` : base;
}

export async function getTaskBoard(): Promise<TaskBoard> {
  if (IS_MOCK) return { ...EMPTY_TASK_BOARD, generated_at: new Date().toISOString() };
  const db = supabaseAdmin();
  const nowMs = Date.now();
  const since14 = new Date(nowMs - 14 * 86_400_000).toISOString();
  const since7 = new Date(nowMs - 7 * 86_400_000).toISOString();
  const cols = "id, status, format, title, series_name, channel_name, error, created_at, updated_at";

  const [active, ended, history, loose, looseFailed, review, seriesRows, channelRows] = await Promise.all([
    rows(db.from("v_production_overview").select(cols).in("status", ACTIVE)),
    rows(db.from("v_production_overview").select(cols).in("status", ["failed", "cancelled"]).gte("updated_at", since14).order("updated_at", { ascending: false }).limit(30)),
    rows(db.from("jobs").select("type, started_at, finished_at").eq("status", "done").not("started_at", "is", null).not("finished_at", "is", null).order("finished_at", { ascending: false }).limit(300)),
    rows(db.from("jobs").select("id, type, status, progress, progress_label, payload, channel_id, video_id, run_after, started_at, created_at, error").is("production_id", null).in("status", ["queued", "running"]).order("created_at").limit(50)),
    rows(db.from("jobs").select("id, type, status, progress, progress_label, payload, channel_id, video_id, run_after, started_at, created_at, error").is("production_id", null).eq("status", "failed").gte("finished_at", since7).order("finished_at", { ascending: false }).limit(20)),
    db.from("videos").select("id", { count: "exact", head: true }).eq("status", "review"),
    rows(db.from("series").select("slug, name")),
    rows(db.from("channels").select("id, name")),
  ]);
  const seriesName = new Map(seriesRows.map((s) => [s.slug as string, s.name as string]));
  const channelName = new Map(channelRows.map((c) => [c.id as string, c.name as string]));

  // Durées médianes mesurées, par type de job
  const byType = new Map<string, number[]>();
  for (const j of history) {
    const d = (new Date(j.finished_at).getTime() - new Date(j.started_at).getTime()) / 1000;
    if (d > 0) byType.set(j.type, [...(byType.get(j.type) ?? []), d]);
  }
  const dur = (type: JobType) => median(byType.get(type) ?? []) || DEFAULT_S[type] || 60;

  const prodIds = active.map((p) => p.id as string);
  const [jobs, covers, prodRows] = prodIds.length
    ? await Promise.all([
        rows(db.from("jobs").select("id, type, status, priority, progress, progress_label, payload, run_after, started_at, created_at, error, production_id").in("production_id", prodIds).neq("type", "upload")),
        rows(db.from("assets").select("id, production_id, scene_index").in("production_id", prodIds).eq("kind", "storyboard").eq("selected", true).order("scene_index")),
        rows(db.from("productions").select("id, paused_at, queue_at, created_at").in("id", prodIds)),
      ])
    : [[], [], []];
  const jobsOf = new Map<string, Row[]>();
  for (const j of jobs) jobsOf.set(j.production_id, [...(jobsOf.get(j.production_id) ?? []), j]);
  const coverOf = new Map<string, string>();
  for (const a of covers) if (!coverOf.has(a.production_id)) coverOf.set(a.production_id, a.id);
  const paused = new Set(prodRows.filter((p) => p.paused_at).map((p) => p.id as string));

  // Place de chaque vidéo dans la file, comme production_queue_key (migration 0027) : choisie par Luca, sinon l'heure de
  // ses premiers clips, sinon sa création
  const firstClip = new Map<string, number>();
  for (const j of jobs) {
    if (j.type !== "generate_clip") continue;
    const t = micros(j.created_at);
    if (t < (firstClip.get(j.production_id) ?? Infinity)) firstClip.set(j.production_id, t);
  }
  const keyOf = new Map<string, number>(
    prodRows.map((p) => [p.id as string, p.queue_at ? micros(p.queue_at) : (firstClip.get(p.id) ?? micros(p.created_at))]),
  );
  const key = (id: string | null) => (id ? keyOf.get(id) : undefined) ?? Number.MAX_SAFE_INTEGER;

  // File de la carte graphique, dans l'ordre de claim_jobs (vidéos en pause sautées) : fin estimée de chaque job
  const gpu = jobs
    .filter((j) => GPU_TYPES.has(j.type) && (j.status === "running" || (j.status === "queued" && !paused.has(j.production_id))))
    .sort(
      (a, b) =>
        Number(b.status === "running") - Number(a.status === "running") ||
        a.priority - b.priority ||
        key(a.production_id) - key(b.production_id) ||
        micros(a.created_at) - micros(b.created_at),
    );
  const gpuEnd = new Map<string, number>(); // production → fin de son dernier job GPU (ms)
  let clock = nowMs;
  for (const j of gpu) {
    const d = j.status === "running" ? Math.max(30, dur(j.type) - seconds(j.started_at, nowMs)) : dur(j.type);
    clock += d * 1000;
    gpuEnd.set(j.production_id, clock);
  }

  const toTask = (p: Row): TaskProduction => {
    const pj = jobsOf.get(p.id) ?? [];
    const isPaused = paused.has(p.id);
    const running = pj.find((j) => j.status === "running") ?? null;
    // Jobs faits ou à faire : un job interrompu par une pause ou un arrêt repartira à la reprise
    const counted = pj.filter((j) => j.status !== "cancelled" || j.error === PAUSE_MARK || j.error === STOP_MARK);
    const clips = counted.filter((j) => j.type === "generate_clip");
    const clipsDone = clips.filter((j) => j.status === "done").length;
    // Production encore « en cours » mais bloquée : un job a définitivement échoué (3 essais) et plus rien ne tourne.
    // Elle n'avancera plus seule (le montage attend ce clip) : on la montre en échec, avec « Relancer ».
    // Refaire / Réinventer une scène (payload.scenes, docs/27) : un échec laisse le storyboard tel quel, rien ne l'attend
    const failedJob = pj.find((j) => j.status === "failed" && !(j.type === "storyboard" && Array.isArray(j.payload?.scenes))) ?? null;
    const blocked = Boolean(failedJob) && !running && ACTIVE.includes(p.status as ProductionStatus) && p.status !== "storyboard_review";
    const status = (blocked ? "failed" : p.status) as ProductionStatus;

    // Avancement pondéré par étape (une étape pas encore créée compte zéro)
    const expected = Object.keys(WEIGHTS).filter(
      (t) => (t !== "tts" || p.format === "A_voiceover") && (t !== "storyboard" || pj.some((j) => j.type === "storyboard") || ["draft", "scripting"].includes(status)),
    ) as JobType[];
    const total = expected.reduce((s, t) => s + (WEIGHTS[t] ?? 0), 0) || 1;
    let got = 0;
    for (const t of expected) {
      const list = counted.filter((j) => j.type === t);
      if (!list.length) continue;
      const frac =
        list.reduce((s, j) => {
          if (j.status === "done") return s + 1;
          if (j.status === "running") return s + Math.min(0.95, Math.max((j.progress ?? 0) / 100, seconds(j.started_at, nowMs) / dur(t)));
          return s;
        }, 0) / list.length;
      got += (WEIGHTS[t] ?? 0) * frac;
    }
    const progress = status === "storyboard_review" ? Math.max(Math.round((got / total) * 100), 25) : Math.round((got / total) * 100);

    const pending = counted
      .filter((j) => j.status === "queued" || j.status === "cancelled")
      .sort((a, b) => a.priority - b.priority || micros(a.created_at) - micros(b.created_at));
    let stage: string;
    if (status === "storyboard_review") stage = "Storyboard à valider";
    else if (status === "cancelled") stage = "Arrêtée";
    else if (status === "failed") stage = "En échec";
    else if (running) stage = stageLabel(running, clips);
    else if (isPaused) {
      stage = clips.length
        ? `En pause · ${clipsDone} clip${clipsDone > 1 ? "s" : ""} sur ${clips.length} fait${clipsDone > 1 ? "s" : ""}`
        : pending[0]
          ? `En pause · avant : ${(JOB_TYPE_LABELS[pending[0].type as JobType] ?? pending[0].type).toLowerCase()}`
          : "En pause";
    } else {
      const next = pending.find((j) => j.status === "queued");
      const label = next ? stageLabel(next, clips) : "";
      // Tâche programmée plus tard (script réécrit à une heure donnée…) : on dit quand elle partira
      const later = next && new Date(next.run_after).getTime() > nowMs + 60_000 && !label.includes("· Gemini") ? ` · prévue ${whenLabel(next.run_after, nowMs)}` : "";
      stage = !next ? "En file" : label.includes("· Gemini") ? label : `En file · ${label.toLowerCase()}${later}`;
    }

    // Fin estimée : file de la carte graphique + ce qui reste à faire ailleurs (script, voix, montage…) ; aucune en pause.
    // Rien ne part avant la plus proche heure de départ de ses tâches en file (run_after)
    let eta: number | null = null;
    if (ACTIVE.includes(status) && status !== "storyboard_review" && !isPaused) {
      const ioLeft = pj
        .filter((j) => !GPU_TYPES.has(j.type) && (j.status === "queued" || j.status === "running"))
        .reduce((s, j) => s + (j.status === "running" ? Math.max(15, dur(j.type) - seconds(j.started_at, nowMs)) : dur(j.type)), 0);
      const noStoryboardYet = ["draft", "scripting"].includes(status) && !pj.some((j) => j.type === "storyboard");
      const queuedStarts = pj.filter((j) => j.status === "queued").map((j) => new Date(j.run_after).getTime());
      const startAt = running || !queuedStarts.length ? nowMs : Math.max(nowMs, Math.min(...queuedStarts));
      const base = Math.max(gpuEnd.get(p.id) ?? nowMs, startAt);
      eta = base + (ioLeft + (noStoryboardYet ? dur("storyboard") : 0)) * 1000;
    }
    const stepEnd = running ? nowMs + Math.max(30, dur(running.type) - seconds(running.started_at, nowMs)) * 1000 : null;

    return {
      id: p.id,
      title: p.title ?? "Vidéo sans titre",
      channel_name: p.channel_name ?? null,
      series_name: p.series_name ?? null,
      status,
      stage,
      progress_pct: status === "failed" || status === "cancelled" ? progress : Math.min(99, progress),
      running: Boolean(running),
      step_started_at: running?.started_at ?? null,
      eta_at: eta ? new Date(eta).toISOString() : null,
      queue_position: null,
      cover_asset_id: coverOf.get(p.id) ?? null,
      error: p.error ?? (blocked ? (failedJob?.error ?? "Un job a échoué") : null),
      updated_at: p.updated_at,
      phase: pj.some((j) => j.type === "generate_clip") ? "fabrication" : "preparation",
      paused: isPaused,
      pause_pending: isPaused && Boolean(running),
      step_type: (running?.type as JobType | undefined) ?? null,
      gpu_step: Boolean(running && GPU_TYPES.has(running.type)),
      step_progress: running ? (running.progress ?? 0) : null,
      step_end_at: stepEnd ? new Date(stepEnd).toISOString() : null,
      clips_done: clipsDone,
      clips_total: clips.length,
    };
  };

  const all = active.map(toTask);
  const blockedTasks = all.filter((t) => t.status === "failed"); // bloquées (voir toTask) : rangées avec les échecs
  const tasks = all.filter((t) => t.status !== "failed");
  const byKey = (a: TaskProduction, b: TaskProduction) => key(a.id) - key(b.id);
  const runningTasks = tasks
    .filter((t) => t.running && t.status !== "storyboard_review")
    .sort((a, b) => Number(b.gpu_step) - Number(a.gpu_step) || byKey(a, b));
  const waiting = tasks.filter((t) => t.status === "storyboard_review");
  const idle = tasks.filter((t) => !t.running && t.status !== "storyboard_review");
  // File d'attente : l'ordre de claim_jobs pour les clips, que Luca peut changer (reorder_queue) ; la préparation (script,
  // images du storyboard) passe avant les clips par sa priorité et se range par fin estimée
  const queued = idle
    .filter((t) => !t.paused && t.phase === "fabrication")
    .sort(byKey)
    .map((t, i) => ({ ...t, queue_position: i + 1 }));
  const preparing = idle
    .filter((t) => !t.paused && t.phase === "preparation")
    .sort((a, b) => (a.eta_at ?? "").localeCompare(b.eta_at ?? "") || byKey(a, b));
  const pausedTasks = idle.filter((t) => t.paused).sort(byKey);

  const toJob = (j: Row): TaskJob => {
    const payload = (j.payload ?? {}) as Record<string, unknown>;
    const parts = [
      typeof payload.series === "string" ? (seriesName.get(payload.series) ?? payload.series) : null,
      typeof payload.count === "number" ? `${payload.count} idées` : null,
      j.type === "voice_preview" && typeof payload.voice === "string" ? payload.voice : null,
      j.type === "tiktok_publish" && payload.source === "rattrapage" ? "rattrapage d’une ancienne vidéo" : null,
      channelName.get(j.channel_id ?? (typeof payload.channel_id === "string" ? payload.channel_id : "")) ?? null,
    ].filter(Boolean);
    const detail = parts.length ? parts.join(" · ") : null;
    return {
      id: j.id,
      type: j.type,
      label: JOB_TYPE_LABELS[j.type as JobType] ?? j.type,
      status: j.status as JobStatus,
      progress: j.progress ?? 0,
      progress_label: j.progress_label ?? null,
      detail,
      started_at: j.started_at ?? null,
      created_at: j.created_at,
      error: j.error ?? null,
    };
  };
  // Hors vidéo : on masque les envois YouTube programmés plus tard (ils attendent leur créneau, rien ne tourne)
  const otherJobs = loose.filter((j) => j.status === "running" || new Date(j.run_after).getTime() <= nowMs + 60_000).map(toJob);
  const failedJobs = looseFailed.map(toJob);
  const ends = tasks.map((t) => (t.eta_at ? new Date(t.eta_at).getTime() : 0));
  const queueEnd = ends.length ? Math.max(...ends) : 0;
  const failed = [...blockedTasks, ...ended.filter((p) => p.status === "failed").map(toTask)];
  const stopped = ended.filter((p) => p.status === "cancelled").map(toTask);
  const reviewVideos = review.count ?? 0;

  return {
    generated_at: new Date(nowMs).toISOString(),
    running: runningTasks,
    queued,
    preparing,
    paused: pausedTasks,
    waiting,
    review_videos: reviewVideos,
    failed,
    stopped,
    other_jobs: otherJobs,
    failed_jobs: failedJobs,
    queue_end_at: queueEnd > nowMs ? new Date(queueEnd).toISOString() : null,
    counts: {
      active: runningTasks.length + queued.length + preparing.length + otherJobs.filter((j) => j.status === "running").length,
      attention: waiting.length + reviewVideos,
      failures: failed.length + failedJobs.length,
    },
  };
}
