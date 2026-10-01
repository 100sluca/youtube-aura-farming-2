/**
 * Temps de fabrication d'une vidéo (docs/45) : chaque passage d'une tâche est écrit dans job_runs par la base
 * (migration 0032), chaque image du storyboard garde son temps dans assets.meta.gen_s. Serveur uniquement.
 */
import { supabaseAdmin } from "@/lib/supabase-admin";
import type { ProductionTiming, TimingItem, TimingStep } from "@/lib/timing-types";
import type { JobType } from "@/lib/types";

/** Les étapes d'une vidéo, dans l'ordre de la chaîne ; l'envoi (YouTube, TikTok) n'est pas de la fabrication. */
export const TIMING_ORDER: JobType[] = ["script", "storyboard", "render", "generate_clip", "tts", "assemble", "qa", "seo"];

type Run = { job_id: string; type: JobType; scene_index: number | null; started_at: string; finished_at: string; outcome: string };

const ms = (iso: string) => new Date(iso).getTime();
const secs = (r: Run) => Math.max(0, (ms(r.finished_at) - ms(r.started_at)) / 1000);

/** Passages lus sur les tâches elles-mêmes, pour les vidéos faites avant le journal : un seul passage par tâche. */
async function runsFromJobs(productionId: string, videoId: string): Promise<Run[]> {
  const { data } = await supabaseAdmin()
    .from("jobs")
    .select("id, type, payload, started_at, finished_at, status, video_id")
    .eq("production_id", productionId)
    .in("type", TIMING_ORDER)
    .not("started_at", "is", null)
    .not("finished_at", "is", null);
  return (data ?? [])
    .filter((j) => !j.video_id || j.video_id === videoId)
    .map((j) => {
      const scene = Number((j.payload as { scene_index?: unknown } | null)?.scene_index);
      return {
        job_id: j.id as string,
        type: j.type as JobType,
        scene_index: Number.isInteger(scene) ? scene : null,
        started_at: j.started_at as string,
        finished_at: j.finished_at as string,
        outcome: j.status as string,
      };
    });
}

export async function getProductionTiming(productionId: string, videoId: string): Promise<ProductionTiming | null> {
  const db = supabaseAdmin();
  const [{ data: logged }, { data: images }] = await Promise.all([
    db
      .from("job_runs")
      .select("job_id, type, scene_index, started_at, finished_at, outcome, video_id")
      .eq("production_id", productionId)
      .in("type", TIMING_ORDER)
      .order("started_at"),
    db.from("assets").select("scene_index, meta").eq("production_id", productionId).eq("kind", "storyboard"),
  ]);
  let runs: Run[] = (logged ?? []).filter((r) => !r.video_id || r.video_id === videoId) as Run[];
  const approx = runs.length === 0;
  if (approx) runs = await runsFromJobs(productionId, videoId);
  if (runs.length === 0) return null;

  const steps: TimingStep[] = TIMING_ORDER.map((type) => {
    const mine = runs.filter((r) => r.type === type);
    return {
      type,
      seconds: mine.reduce((s, r) => s + secs(r), 0),
      retries: mine.length - new Set(mine.map((r) => r.job_id)).size,
      lost: mine.filter((r) => ["failed", "cancelled", "interrupted"].includes(r.outcome)).length,
    };
  }).filter((s) => runs.some((r) => r.type === s.type));

  const byScene = new Map<number, TimingItem>();
  for (const r of runs) {
    if (r.type !== "generate_clip" || r.scene_index === null) continue;
    const item = byScene.get(r.scene_index) ?? { scene: r.scene_index, seconds: 0, runs: 0 };
    item.seconds += secs(r);
    item.runs += 1;
    byScene.set(r.scene_index, item);
  }

  const timed: TimingItem[] = [];
  for (const a of images ?? []) {
    const s = Number((a.meta as { gen_s?: unknown } | null)?.gen_s);
    if (Number.isFinite(s) && a.scene_index !== null) timed.push({ scene: a.scene_index as number, seconds: s, runs: 1 });
  }
  timed.sort((a, b) => a.scene - b.scene);

  const start = Math.min(...runs.map((r) => ms(r.started_at)));
  const end = Math.max(...runs.map((r) => ms(r.finished_at)));
  // validation : des dernières images faites avant le rendu jusqu'au lancement du rendu
  const render = Math.min(...runs.filter((r) => r.type === "render").map((r) => ms(r.started_at)));
  const board = Math.max(...runs.filter((r) => r.type === "storyboard" && ms(r.finished_at) <= render).map((r) => ms(r.finished_at)));
  const validation = Number.isFinite(render) && Number.isFinite(board) ? (render - board) / 1000 : null;

  return {
    approx,
    total_s: steps.reduce((s, x) => s + x.seconds, 0),
    span_s: (end - start) / 1000,
    validation_s: validation,
    steps,
    clips: [...byScene.values()].sort((a, b) => a.scene - b.scene),
    images: { count: (images ?? []).length, timed },
  };
}
