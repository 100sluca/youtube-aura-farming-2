/**
 * Gestionnaire de tâches : ce que le PC fabrique, dans l'ordre où il le fera, avec l'étape en cours, l'avancement
 * et une heure de fin estimée. Serveur uniquement (clé service role) ; le panneau l'interroge toutes les quelques
 * secondes par la route GET /api/tasks/board (pas une action serveur : elles passent une par une, docs/56).
 *
 * Ordre (claim_jobs, migration 0027, docs/40) : priorité du job, puis place de sa vidéo dans la file (queueKey : celle
 * choisie par Luca, sinon l'heure de ses premiers clips, sinon sa création), puis ancienneté ; les vidéos en pause sont
 * sautées. La carte graphique ne fait qu'une chose à la fois (voie « gpu » du worker : storyboard, clips, voix) : on
 * déroule sa file dans cet ordre pour dater la fin de chaque vidéo ; le reste (script, montage…) tourne en parallèle et
 * s'ajoute au bout.
 *
 * Estimation : durée médiane des 300 derniers jobs terminés de chaque type (valeurs par défaut sinon).
 *
 * Retouches (Bibliothèque → Retoucher) : leurs jobs portent la production d'une vidéo déjà finie, que les requêtes
 * ci-dessus ne lisent pas. On les retrouve par leur payload (retouch, remount, source « retouche ») ; les jobs créés
 * ensemble par un même geste (retouch_video, redo_plan, retake_voices, apply_takes, remount_video, réécriture) ont la
 * même date de création et forment une carte. Priorité 20 : sur la carte graphique, elles passent avant les clips.
 */
import { IS_MOCK } from "@/lib/data";
import { formatDateTime, formatTime, parisDayKey } from "@/lib/format";
import { JOB_TYPE_LABELS } from "@/lib/labels";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { EMPTY_TASK_BOARD, type TaskBoard, type TaskJob, type TaskProduction, type TaskRetouch } from "@/lib/task-types";
import type { JobStatus, JobType, ProductionStatus } from "@/lib/types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;

const ACTIVE: ProductionStatus[] = ["draft", "scripting", "storyboard_review", "generating", "assembling"];
// La voix passe aussi par la voie GPU du worker depuis les moteurs PyTorch (docs/18-voix.md)
const GPU_TYPES = new Set<string>(["storyboard", "generate_clip", "tts", "long_make"]);
/** Poids de chaque étape dans la barre d'avancement d'une vidéo (somme 100). */
const WEIGHTS: Partial<Record<JobType, number>> = { script: 10, storyboard: 15, generate_clip: 55, tts: 4, assemble: 10, qa: 3, seo: 3 };
/** Durées par défaut (s) tant qu'aucun job de ce type n'a été mesuré (mesures du 25/09, docs/14). */
const DEFAULT_S: Partial<Record<JobType, number>> = {
  script: 240, storyboard: 360, render: 5, generate_clip: 300, tts: 20, seo: 60, assemble: 60, qa: 15,
  ideate: 90, import_channel: 60, sync_metrics: 60, sync_retention: 20, sync_comments: 20, strategy: 90, improve: 120, upload: 120,
  tiktok_publish: 90, sync_tiktok: 10, sync_instagram: 10, instagram_publish: 90, paf_publish: 90, rewrite: 120, research: 150,
  long_write: 900, long_make: 1200, long_take: 20,
};
/** Jobs interrompus par une pause ou un arrêt (SQL pause_productions, cancel_production) : ils repartent à la reprise. */
const PAUSE_MARK = "Mise en pause";
const STOP_MARK = "Arrêtée par l'utilisateur";

/** Étapes d'une retouche, dans l'ordre où elles s'enchaînent, et leur poids dans la barre d'avancement. */
const RETOUCH_ORDER: Record<string, number> = { rewrite: 0, generate_clip: 1, tts: 2, assemble: 3, qa: 4 };
const RETOUCH_WEIGHTS: Record<string, number> = { rewrite: 100, generate_clip: 55, tts: 25, assemble: 15, qa: 5 };
/** Une retouche finie reste 12 h dans le panneau (le temps d'aller la voir), une retouche en échec 7 jours. */
const RETOUCH_DONE_MS = 12 * 3_600_000;

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const plural = (n: number, word: string) => `${n} ${word}${n > 1 ? "s" : ""}`;
const planList = (keys: string[]) => keys.map((k) => Number(k) + 1).sort((a, b) => a - b).join(", ");

/** Nom d'une étape de retouche : « Prises de voix », « Clip du plan 4 », « Montage »… */
function retouchStep(j: Row): string {
  const p = isObj(j.payload) ? j.payload : {};
  switch (j.type) {
    case "rewrite":
      return p.action === "make" ? "Copie des plans" : "Conteur";
    case "generate_clip":
      return typeof p.scene_index === "number" ? `Clip du plan ${p.scene_index + 1}` : "Clip";
    case "tts":
      if (Array.isArray(p.clip_takes)) return "Voix du clip";
      if (isObj(p.takes)) return "Prises de voix";
      if (Array.isArray(p.apply_takes)) return "Prises posées";
      if (typeof p.scene === "number") return `Voix du plan ${p.scene + 1}`;
      return typeof p.voice === "string" && p.voice.startsWith("acting:") ? "Voix des personnages" : "Voix";
    case "assemble":
      return "Montage";
    case "qa":
      return "Contrôle";
    default:
      return JOB_TYPE_LABELS[j.type as JobType] ?? String(j.type);
  }
}

/** Ce qui a été demandé, ce qu'il y a à voir une fois fini, et la page à ouvrir (Retoucher, un onglet, une autre vidéo). */
function retouchWhat(group: Row[]): { what: string; done: string; tab: string | null; href?: string } {
  const of = (type: string) => group.find((j) => j.type === type);
  const payload = (j: Row | undefined) => (j && isObj(j.payload) ? j.payload : {});
  const rewrite = of("rewrite");
  if (rewrite) {
    // docs/53 : « propose » = le conteur écrit (rien n'est créé) ; « make » = la nouvelle vidéo (result.video_id)
    const p = payload(rewrite);
    const made = isObj(rewrite.result) && typeof rewrite.result.video_id === "string" ? rewrite.result.video_id : null;
    return p.action === "make"
      ? {
          what: "Nouvelle vidéo réécrite",
          done: "Nouvelle vidéo lancée : elle se fabrique, puis arrive à valider dans la Bibliothèque",
          tab: "recit",
          href: made ? `/library?video=${made}` : undefined,
        }
      : { what: p.mode === "hook" ? "Nouvelle accroche (conteur)" : "Réécriture du récit (conteur)", done: "Texte proposé : à relire (Retoucher → Récit)", tab: "recit" };
  }
  const tts = payload(of("tts"));
  const clip = of("generate_clip");
  if (Array.isArray(tts.clip_takes)) {
    const asked = tts.clip_takes.map(String);
    return { what: `Voix du clip reprise · plan ${planList(asked)}`, done: "Prise prête : à écouter, puis valider ou non (Retoucher → Plans)", tab: null };
  }
  if (isObj(tts.takes)) {
    const asked = Object.keys(tts.takes);
    const result = isObj(of("tts")?.result) ? (of("tts")?.result as Record<string, unknown>) : {};
    const made = Array.isArray(result.takes) ? result.takes.map(String) : asked;
    const skipped = asked.filter((k) => !made.includes(k));
    const left = skipped.length
      ? ` · ${skipped.length > 1 ? "plans" : "plan"} ${planList(skipped)} sans réplique : pas de voix à redire, ${skipped.length > 1 ? "consignes gardées" : "consigne gardée"}`
      : "";
    return { what: `Nouvelles prises de voix · ${plural(asked.length, "plan")}`, done: `Prises prêtes : à écouter, puis valider ou non (Retoucher → Plans)${left}`, tab: null };
  }
  if (Array.isArray(tts.apply_takes)) {
    const n = tts.apply_takes.length;
    return { what: `Vidéo refaite avec ${plural(n, "prise")} ${n > 1 ? "validées" : "validée"}`, done: "Vidéo refaite : à regarder", tab: null };
  }
  const scene = clip ? payload(clip).scene_index : tts.scene;
  if (clip || typeof tts.scene === "number") {
    const k = typeof scene === "number" ? scene + 1 : "?";
    const what = clip && typeof tts.scene === "number" ? `Plan ${k} : clip et voix refaits` : clip ? `Plan ${k} : clip refait` : `Plan ${k} : nouvelle prise de voix`;
    return { what, done: "Vidéo refaite : à regarder", tab: null };
  }
  if (typeof tts.voice === "string") {
    const acting = tts.voice.startsWith("acting:");
    return { what: acting ? "Voix des personnages rejouées, puis montage" : "Nouvelle voix, puis montage", done: "Vidéo refaite : à regarder", tab: null };
  }
  const retouch = payload(of("assemble")).retouch === true;
  return {
    what: retouch ? "Retouche : vidéo remontée (titre, sous-titres, musique, son)" : "Montage refait avec le modèle actuel",
    done: "Vidéo refaite : à regarder",
    tab: null,
  };
}

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

  const [active, ended, history, loose, looseFailed, review, seriesRows, channelRows, retouchSeeds] = await Promise.all([
    rows(db.from("v_production_overview").select(cols).in("status", ACTIVE)),
    rows(db.from("v_production_overview").select(cols).in("status", ["failed", "cancelled"]).gte("updated_at", since14).order("updated_at", { ascending: false }).limit(30)),
    rows(db.from("jobs").select("type, started_at, finished_at").eq("status", "done").not("started_at", "is", null).not("finished_at", "is", null).order("finished_at", { ascending: false }).limit(300)),
    rows(db.from("jobs").select("id, type, status, progress, progress_label, payload, channel_id, video_id, run_after, started_at, created_at, error").is("production_id", null).in("status", ["queued", "running"]).order("created_at").limit(50)),
    rows(db.from("jobs").select("id, type, status, progress, progress_label, payload, channel_id, video_id, run_after, started_at, created_at, error").is("production_id", null).eq("status", "failed").gte("finished_at", since7).order("finished_at", { ascending: false }).limit(20)),
    db.from("videos").select("id", { count: "exact", head: true }).eq("status", "review"),
    rows(db.from("series").select("slug, name")),
    rows(db.from("channels").select("id, name")),
    // Jobs lancés depuis Retoucher (voir l'en-tête) ; leurs voisins de lot (le contrôle n'a pas de payload) suivent
    rows(
      db
        .from("jobs")
        .select("type, video_id, created_at")
        .not("video_id", "is", null)
        .or("payload->>retouch.eq.true,payload->>remount.eq.true,payload->>source.eq.retouche")
        .gte("created_at", since7)
        .order("created_at", { ascending: false })
        .limit(120),
    ),
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
  const groupKey = (j: Row) => `${j.video_id}|${j.created_at}`;
  const seeds = retouchSeeds.filter((j) => j.type in RETOUCH_ORDER);
  const retouchVideos = [...new Set(seeds.map((j) => j.video_id as string))];
  const retouchSince = seeds.reduce((min: string, j) => (j.created_at < min ? (j.created_at as string) : min), new Date(nowMs).toISOString());
  const [[jobs, covers, prodRows], [retouchRows, retouchVideoRows]] = await Promise.all([
    prodIds.length
      ? Promise.all([
          rows(db.from("jobs").select("id, type, status, priority, progress, progress_label, payload, run_after, started_at, created_at, error, production_id").in("production_id", prodIds).neq("type", "upload")),
          rows(db.from("assets").select("id, production_id, scene_index").in("production_id", prodIds).eq("kind", "storyboard").eq("selected", true).order("scene_index")),
          rows(db.from("productions").select("id, paused_at, queue_at, created_at").in("id", prodIds)),
        ])
      : Promise.resolve([[], [], []] as Row[][]),
    retouchVideos.length
      ? Promise.all([
          rows(
            db
              .from("jobs")
              .select("id, type, status, priority, progress, progress_label, payload, result, run_after, started_at, finished_at, created_at, error, video_id, production_id")
              .in("video_id", retouchVideos)
              .gte("created_at", retouchSince),
          ),
          rows(db.from("videos").select("id, title, status, error, poster_asset_id, channel_id").in("id", retouchVideos)),
        ])
      : Promise.resolve([[], []] as Row[][]),
  ]);
  // Lots de retouche : jobs d'une même vidéo créés ensemble, hors vidéo encore en fabrication (sa carte les montre déjà)
  const seedKeys = new Set(seeds.map(groupKey));
  const retouchGroups = new Map<string, Row[]>();
  for (const j of retouchRows) {
    if (!(j.type in RETOUCH_ORDER) || !seedKeys.has(groupKey(j)) || prodIds.includes(j.production_id)) continue;
    retouchGroups.set(groupKey(j), [...(retouchGroups.get(groupKey(j)) ?? []), j]);
  }
  const retouchGpu = [...retouchGroups.values()].flat().filter((j) => GPU_TYPES.has(j.type) && (j.status === "running" || j.status === "queued"));
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

  // File de la carte graphique, dans l'ordre de claim_jobs (vidéos en pause sautées) : fin estimée de chaque job. Les
  // voix et clips des retouches (priorité 20) y prennent leur place
  const gpu = jobs
    .filter((j) => GPU_TYPES.has(j.type) && (j.status === "running" || (j.status === "queued" && !paused.has(j.production_id))))
    .concat(retouchGpu)
    .sort(
      (a, b) =>
        Number(b.status === "running") - Number(a.status === "running") ||
        a.priority - b.priority ||
        key(a.production_id) - key(b.production_id) ||
        micros(a.created_at) - micros(b.created_at),
    );
  const gpuEnd = new Map<string, number>(); // production → fin de son dernier job GPU (ms)
  const gpuJobEnd = new Map<string, number>(); // job → sa fin estimée (ms)
  let clock = nowMs;
  for (const j of gpu) {
    const d = j.status === "running" ? Math.max(30, dur(j.type) - seconds(j.started_at, nowMs)) : dur(j.type);
    clock += d * 1000;
    gpuEnd.set(j.production_id, clock);
    gpuJobEnd.set(j.id, clock);
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

  // ---- Retouches --------------------------------------------------------------------------------------------------
  const videoOf = new Map(retouchVideoRows.map((v) => [v.id as string, v]));
  const gpuBusy = gpu.some((j) => j.status === "running");
  const toRetouch = (group: Row[], latest: boolean): TaskRetouch => {
    const steps = [...group].sort((a, b) => RETOUCH_ORDER[a.type] - RETOUCH_ORDER[b.type]);
    const first = steps[0];
    const v: Row = videoOf.get(first.video_id) ?? {};
    const { what, done, tab, href } = retouchWhat(steps);
    const running = steps.find((j) => j.status === "running") ?? null;
    const live = steps.filter((j) => j.status === "queued" || j.status === "running");
    const next = live.find((j) => j.status === "queued") ?? null;
    // Un échec définitif bloque la suite (le montage attend la voix) : « Relancer » reprend le lot là où il s'est arrêté
    const failedJob = steps.find((j) => j.status === "failed") ?? null;
    const finished = steps.every((j) => j.status === "done");
    // Contrôle qualité raté : tout a tourné, mais le contrôle a mis la vidéo en échec (« QA : … », worker/steps/qa.py) ;
    // une vidéo refusée ensuite par Luca n'est pas un échec de la retouche
    const qaFailed = finished && latest && v.status === "failed" && /^QA\b/.test(v.error ?? "") && steps.some((j) => j.type === "qa");
    const status: TaskRetouch["status"] = failedJob || qaFailed ? "failed" : running ? "running" : live.length ? "queued" : finished ? "done" : "cancelled";
    const lastEnd = steps.reduce((m: string | null, j) => (j.finished_at && (!m || j.finished_at > m) ? (j.finished_at as string) : m), null);

    let got = 0;
    let total = 0;
    for (const j of steps) {
      const w = RETOUCH_WEIGHTS[j.type] ?? 10;
      total += w;
      if (j.status === "done") got += w;
      else if (j.status === "running") got += w * Math.min(0.95, Math.max((j.progress ?? 0) / 100, seconds(j.started_at, nowMs) / dur(j.type)));
    }

    let stage: string;
    if (status === "failed") stage = failedJob ? `En échec · ${retouchStep(failedJob).toLowerCase()}` : "En échec au contrôle qualité";
    else if (running) stage = running.progress_label ? `${retouchStep(running)} · ${running.progress_label}` : retouchStep(running);
    else if (next) {
      const step = retouchStep(next).toLowerCase();
      const at = new Date(next.run_after).getTime();
      if (next.error && at > nowMs) stage = `Nouvel essai ${whenLabel(next.run_after, nowMs)} · ${step}`;
      else if (at > nowMs + 60_000) stage = `Prévue ${whenLabel(next.run_after, nowMs)} · ${step}`;
      else if (GPU_TYPES.has(next.type) && gpuBusy) stage = `En file · ${step}, après le calcul en cours sur la carte graphique`;
      else stage = `En file · ${step}`;
    } else if (status === "done") stage = lastEnd ? `Terminée ${whenLabel(lastEnd, nowMs)}` : "Terminée";
    else stage = "Arrêtée";

    // Fin estimée : ses voix et clips à leur place dans la file de la carte graphique, puis montage et contrôle
    let eta: number | null = null;
    if (live.length && !failedJob) {
      const gpuEnds = live.map((j) => gpuJobEnd.get(j.id)).filter((t): t is number => typeof t === "number");
      const ioLeft = live
        .filter((j) => !GPU_TYPES.has(j.type))
        .reduce((s, j) => s + (j.status === "running" ? Math.max(15, dur(j.type) - seconds(j.started_at, nowMs)) : dur(j.type)), 0);
      eta = Math.max(nowMs, ...gpuEnds) + ioLeft * 1000;
    }

    return {
      id: first.id,
      video_id: first.video_id,
      title: v.title ?? "Vidéo sans titre",
      channel_name: channelName.get(v.channel_id ?? "") ?? null,
      what,
      status,
      stage,
      progress_pct: status === "done" ? 100 : Math.min(99, Math.round((got / (total || 1)) * 100)),
      steps: steps.map((j) => ({ label: retouchStep(j), status: j.status as JobStatus })),
      step_started_at: running?.started_at ?? null,
      eta_at: eta ? new Date(eta).toISOString() : null,
      created_at: first.created_at,
      finished_at: live.length ? null : lastEnd,
      // échec définitif ; sinon l'erreur d'un essai raté qui va être refait
      error: status === "failed" ? (failedJob?.error ?? v.error ?? "Échec") : status === "queued" && next?.error ? next.error : null,
      result_hint: status === "done" ? done : null,
      job_ids: steps.map((j) => j.id as string),
      failed_job_id: failedJob?.id ?? null,
      cover_asset_id: v.poster_asset_id ?? null,
      href: (status === "done" && href) || `/library/${first.video_id}/retouche${tab ? `?onglet=${tab}` : ""}`,
    };
  };
  // Par vidéo : les retouches en cours ; sinon la dernière finie, en échec ou depuis moins de 12 h (les plus anciennes
  // sont dépassées par celle-ci)
  const groupsByVideo = new Map<string, Row[][]>();
  for (const g of retouchGroups.values()) groupsByVideo.set(g[0].video_id, [...(groupsByVideo.get(g[0].video_id) ?? []), g]);
  const retouches: TaskRetouch[] = [];
  for (const groups of groupsByVideo.values()) {
    const cards = groups.sort((a, b) => micros(b[0].created_at) - micros(a[0].created_at)).map((g, i) => toRetouch(g, i === 0));
    const live = cards.filter((c) => c.status === "running" || c.status === "queued");
    if (live.length) {
      retouches.push(...live);
      continue;
    }
    const last = cards[0];
    const ago = last?.finished_at ? nowMs - new Date(last.finished_at).getTime() : Infinity;
    if (last && (last.status === "failed" || (last.status === "done" && ago < RETOUCH_DONE_MS))) retouches.push(last);
  }
  const rank = { running: 0, queued: 1, failed: 2, done: 3, cancelled: 4 } as const;
  retouches.sort((a, b) => rank[a.status] - rank[b.status] || b.created_at.localeCompare(a.created_at));
  const retouchesLive = retouches.filter((r) => r.status === "running" || r.status === "queued").length;

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
    retouches,
    queue_end_at: queueEnd > nowMs ? new Date(queueEnd).toISOString() : null,
    counts: {
      active: runningTasks.length + queued.length + preparing.length + otherJobs.filter((j) => j.status === "running").length + retouchesLive,
      attention: waiting.length + reviewVideos,
      failures: failed.length + failedJobs.length + retouches.filter((r) => r.status === "failed").length,
    },
  };
}
