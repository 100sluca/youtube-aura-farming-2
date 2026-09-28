/**
 * Santé de la machine (docs/28-sante-machine.md) : mémoire, ComfyUI, worker, tâche en cours sur la carte graphique, et
 * redémarrages lancés depuis la barre latérale. Le dashboard tourne sur le PC lui-même : il lit la mémoire avec Node,
 * interroge ComfyUI, lit le signe de vie que le worker écrit toutes les 30 s (app_settings.worker_status) et lance
 * launcher/restart.ps1 pour arrêter puis relancer un programme.
 */
import { execFile, spawn } from "node:child_process";
import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { supabaseAdmin } from "@/lib/supabase-admin";
import type { MemoryHog, RestartTarget, ServiceState, SystemStatus } from "@/lib/system-types";

const YT2_HOME = process.env.YT2_HOME ?? "C:/YouTube2";
const COMFY_URL = (process.env.COMFY_BASE_URL ?? "http://127.0.0.1:8188").replace(/\/+$/, "");
const RESTART_SCRIPT = path.join(process.cwd(), "..", "..", "launcher", "restart.ps1");
const GB = 1024 ** 3;
const BEAT_STALE_S = 120; // le worker écrit toutes les 30 s : 2 min sans nouvelles = arrêté ou bloqué

const round1 = (n: number) => Math.round(n * 10) / 10;
const gb = (n: number) => `${round1(n).toLocaleString("fr-FR")} Go`;

async function comfyStatus(): Promise<{ state: ServiceState; queue: number | null }> {
  try {
    const signal = AbortSignal.timeout(4000); // pendant un rendu lourd, ComfyUI répond parfois lentement
    const [stats, queue] = await Promise.all([
      fetch(`${COMFY_URL}/system_stats`, { cache: "no-store", signal }),
      fetch(`${COMFY_URL}/queue`, { cache: "no-store", signal }),
    ]);
    if (!stats.ok) return { state: "down", queue: null };
    const q = queue.ok ? ((await queue.json()) as { queue_running?: unknown[]; queue_pending?: unknown[] }) : null;
    return { state: "ok", queue: q ? (q.queue_running?.length ?? 0) + (q.queue_pending?.length ?? 0) : null };
  } catch {
    return { state: "down", queue: null };
  }
}

type WorkerBeat = {
  worker_id?: string; started_at?: string; draining?: boolean; comfy_up?: boolean;
  ram_free_gb?: number; commit_free_gb?: number; commit_total_gb?: number; vram_used_mb?: number; vram_total_mb?: number;
};

export async function getSystemStatus(): Promise<SystemStatus> {
  const db = supabaseAdmin();
  const [comfy, settings, gpu] = await Promise.all([
    comfyStatus(),
    db.from("app_settings").select("key, value, updated_at").in("key", ["worker_status", "worker_restart"]),
    db.from("jobs").select("type, progress_label, started_at").eq("status", "running").like("locked_by", "%/gpu")
      .order("started_at", { ascending: false }).limit(1).maybeSingle(),
  ]);
  const rows = settings.data ?? [];
  const beatRow = rows.find((r) => r.key === "worker_status");
  const beat = (beatRow?.value ?? null) as WorkerBeat | null;
  const requestedAt = (rows.find((r) => r.key === "worker_restart")?.value as { requested_at?: string } | undefined)?.requested_at;
  const lastBeatS = beatRow ? Math.max(0, Math.round((Date.now() - Date.parse(beatRow.updated_at as string)) / 1000)) : null;
  const fresh = lastBeatS !== null && lastBeatS < BEAT_STALE_S;
  const restartPending = Boolean(requestedAt && beat?.started_at && Date.parse(requestedAt) > Date.parse(beat.started_at));
  // ComfyUI peut tarder à répondre au dashboard pendant un rendu : le signe de vie du worker (même test) fait foi aussi
  const comfyState: ServiceState = comfy.state === "ok" || (fresh && beat?.comfy_up) ? "ok" : "down";

  const status: SystemStatus = {
    at: new Date().toISOString(),
    ram: {
      totalGb: round1(os.totalmem() / GB),
      freeGb: round1(os.freemem() / GB),
      commitFreeGb: fresh && beat?.commit_free_gb != null ? beat.commit_free_gb : null,
      commitTotalGb: fresh && beat?.commit_total_gb != null ? beat.commit_total_gb : null,
    },
    vram: fresh && beat?.vram_total_mb ? { usedMb: beat.vram_used_mb ?? 0, totalMb: beat.vram_total_mb } : null,
    comfy: { state: comfyState, queue: comfy.queue },
    worker: {
      state: beatRow ? (fresh ? "ok" : "down") : "unknown",
      lastBeatS,
      draining: Boolean(fresh && beat?.draining),
      restartPending,
      workerId: beat?.worker_id ?? null,
    },
    gpuJob: gpu.data ? { type: gpu.data.type as string, label: (gpu.data.progress_label as string | null) ?? null, startedAt: (gpu.data.started_at as string | null) ?? null } : null,
    dashboard: { rssGb: round1(process.memoryUsage().rss / GB), uptimeS: Math.round(process.uptime()), pid: process.pid },
    warnings: [],
  };
  status.warnings = warningsFor(status);
  return status;
}

function warningsFor(s: SystemStatus): string[] {
  const w: string[] = [];
  if (s.comfy.state === "down")
    w.push("ComfyUI ne répond pas : ni image ni clip possible. Le worker le relance tout seul au prochain rendu ; sinon, « Redémarrer ComfyUI ».");
  if (s.worker.state === "down" && s.worker.lastBeatS !== null)
    w.push(`Le worker ne donne plus de nouvelles depuis ${Math.round(s.worker.lastBeatS / 60)} min : plus rien n'avance. « Redémarrer le worker », au besoin en forçant.`);
  if (s.ram.freeGb < 3)
    w.push(`Mémoire presque pleine : ${gb(s.ram.freeGb)} libres sur ${gb(s.ram.totalGb)}. Un clip MiniMax H3 peut faire tomber ComfyUI.`);
  else if (s.ram.commitFreeGb !== null && s.ram.commitFreeGb < 6)
    w.push(`Mémoire réservable presque épuisée (${gb(s.ram.commitFreeGb)}) : ComfyUI risque de tomber au prochain gros modèle.`);
  if (s.dashboard.rssGb >= 3)
    w.push(`Le dashboard occupe ${gb(s.dashboard.rssGb)} (il grossit au fil des jours) : le redémarrer libère cette mémoire.`);
  return w;
}

// ---- programmes qui prennent le plus de mémoire (à l'ouverture de la fenêtre « Machine ») ------------------------------

const NAMES: [RegExp, string][] = [
  [/^brave/, "Brave"], [/^chrome/, "Chrome"], [/^msedge/, "Edge"], [/^firefox/, "Firefox"], [/^capcut/, "CapCut"],
  [/^adobe premiere/, "Premiere Pro"], [/^afterfx/, "After Effects"], [/^photoshop/, "Photoshop"], [/^discord/, "Discord"],
  [/^claude/, "Claude"], [/^code/, "VS Code"], [/^antigravity/, "Antigravity"], [/^spotify/, "Spotify"],
  [/^whatsapp/, "WhatsApp"], [/^notion/, "Notion"], [/^epicgames|^epicwebhelper/, "Epic Games"], [/^steam/, "Steam"],
  [/^lm studio|^lms/, "LM Studio"], [/^ollama/, "Ollama"], [/^vmmem/, "Docker (base de données)"],
  [/^docker/, "Docker (base de données)"], [/^msmpeng/, "Antivirus Windows"], [/^dwm/, "Affichage Windows"],
  [/^explorer/, "Explorateur Windows"], [/^obs/, "OBS"], [/^memory compression/, "Mémoire compressée (Windows)"],
];

function classify(name: string, cmd: string): { label: string; restart?: RestartTarget } {
  if (/ComfyUI[\\/]main\.py/i.test(cmd)) return { label: "ComfyUI", restart: "comfyui" };
  if (/worker\.main|worker-venv\\Scripts\\worker/i.test(cmd)) return { label: "Worker", restart: "worker" };
  if (/tts_runners|[\\/]tts[\\/]\w+[\\/]venv/i.test(cmd)) return { label: "Moteur de voix" };
  if (/next[\\/]dist[\\/]|start-server\.js|turbopack/i.test(cmd)) return { label: "Dashboard (serveur)", restart: "dashboard" };
  const n = name.toLowerCase();
  const known = NAMES.find(([re]) => re.test(n));
  return { label: known ? known[1] : name.replace(/\.exe$/i, "") };
}

export async function memoryHogs(limit = 8): Promise<MemoryHog[]> {
  const script = "Get-CimInstance Win32_Process | Select-Object Name, WorkingSetSize, CommandLine | ConvertTo-Json -Compress";
  const out = await new Promise<string>((resolve) =>
    execFile("powershell.exe", ["-NoProfile", "-Command", script], { maxBuffer: 64 * 1024 * 1024, timeout: 30_000, windowsHide: true },
      (error, stdout) => resolve(error ? "[]" : stdout)),
  );
  let procs: { Name?: string; WorkingSetSize?: number; CommandLine?: string | null }[] = [];
  try {
    procs = JSON.parse(out || "[]");
  } catch {
    return [];
  }
  const groups = new Map<string, MemoryHog>();
  for (const p of Array.isArray(procs) ? procs : [procs]) {
    const { label, restart } = classify(p.Name ?? "?", p.CommandLine ?? "");
    const g = groups.get(label) ?? { label, gb: 0, count: 0, restart };
    g.gb += (p.WorkingSetSize ?? 0) / GB;
    g.count += 1;
    groups.set(label, g);
  }
  return [...groups.values()].map((g) => ({ ...g, gb: round1(g.gb) })).sort((a, b) => b.gb - a.gb).slice(0, limit);
}

// ---- redémarrages ----------------------------------------------------------------------------------------------------

/** Lance launcher/restart.ps1 hors de l'arbre de processus du dashboard : « start » rend PowerShell orphelin (le cmd
 * intermédiaire se termine aussitôt), si bien que l'arrêt du dashboard (taskkill /T) ne l'emporte pas avec lui. */
export function launchRestart(target: RestartTarget): void {
  if (!existsSync(RESTART_SCRIPT)) throw new Error(`Script de redémarrage introuvable : ${RESTART_SCRIPT}`);
  const command = `start "" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "${RESTART_SCRIPT}" -Target ${target} -Root "${YT2_HOME}"`;
  spawn(process.env.ComSpec ?? "cmd.exe", ["/d", "/s", "/c", `"${command}"`], {
    detached: true, stdio: "ignore", windowsHide: true, windowsVerbatimArguments: true,
  }).unref();
}

/** Relance propre : le worker finit ses tâches en cours, n'en prend plus, puis son superviseur le relance (≤ 30 s après
 * la fin de la tâche GPU en cours). */
export async function requestWorkerRestart(): Promise<void> {
  const { error } = await supabaseAdmin().from("app_settings")
    .upsert({ key: "worker_restart", value: { requested_at: new Date().toISOString(), by: "dashboard" }, updated_at: new Date().toISOString() });
  if (error) throw new Error(error.message);
}

/** Relance forcée (worker bloqué ou arrêté) : ses tâches en cours sont remises en file tout de suite, sans attendre les
 * 15 min de requeue_stale_jobs, puis le script arrête le worker et relance C:\YouTube2\worker.bat. */
export async function forceWorkerRestart(workerId: string | null): Promise<number> {
  let requeued = 0;
  if (workerId) {
    const { data } = await supabaseAdmin().from("jobs")
      .update({ status: "queued", locked_by: null, locked_at: null, error: "Worker redémarré de force depuis le dashboard" })
      .eq("status", "running").like("locked_by", `${workerId}/%`).select("id");
    requeued = data?.length ?? 0;
  }
  launchRestart("worker");
  return requeued;
}
