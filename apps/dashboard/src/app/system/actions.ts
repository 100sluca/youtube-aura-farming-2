"use server";

/**
 * Gestes de la fenêtre « Machine » (barre latérale, docs/28-sante-machine.md) : lire l'état du PC, voir ce qui prend la
 * mémoire, redémarrer ComfyUI, le worker ou le dashboard. Ces gestes arrêtent des programmes du PC : refusés si la page
 * n'est pas ouverte sur le PC lui-même (localhost).
 */
import { headers } from "next/headers";

import type { ActionResult } from "@/app/production/actions";
import { forceWorkerRestart, getSystemStatus, launchRestart, memoryHogs, requestWorkerRestart } from "@/lib/system";
import type { MemoryHog, RestartTarget, SystemStatus } from "@/lib/system-types";

function fail(error: unknown): ActionResult {
  return { ok: false, message: error instanceof Error ? error.message : String(error) };
}

async function fromThisPc(): Promise<boolean> {
  const host = (await headers()).get("host") ?? "";
  return /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i.test(host);
}

const NOT_LOCAL: ActionResult = { ok: false, message: "Redémarrage possible seulement depuis le PC lui-même (http://localhost:3000)" };

export async function fetchSystemStatus(): Promise<SystemStatus> {
  return getSystemStatus();
}

export async function fetchMemoryHogs(): Promise<MemoryHog[]> {
  return memoryHogs();
}

export async function restartService(target: RestartTarget, force = false): Promise<ActionResult> {
  if (!(await fromThisPc())) return NOT_LOCAL;
  try {
    if (target === "comfyui") {
      launchRestart("comfyui");
      return { ok: true, message: "ComfyUI redémarre (≈ 30 s). Un rendu en cours sera repris automatiquement." };
    }
    if (target === "dashboard") {
      launchRestart("dashboard");
      return { ok: true, message: "Le dashboard redémarre : la page se recharge toute seule d'ici 20 à 40 s." };
    }
    const status = await getSystemStatus();
    if (force || status.worker.state === "down") {
      const requeued = await forceWorkerRestart(status.worker.workerId);
      return { ok: true, message: `Worker arrêté puis relancé${requeued ? ` ; ${requeued} tâche(s) en cours remise(s) en file` : ""}.` };
    }
    await requestWorkerRestart();
    const job = status.gpuJob?.label ?? status.gpuJob?.type;
    return {
      ok: true,
      message: job
        ? `Le worker se relancera après « ${job} » : il finit d'abord ses tâches en cours.`
        : "Le worker se relance dans les 30 secondes.",
    };
  } catch (error) {
    return fail(error);
  }
}

/** Tout redémarrer : ComfyUI tout de suite, le worker après sa tâche en cours, le dashboard en dernier. */
export async function restartEverything(): Promise<ActionResult> {
  if (!(await fromThisPc())) return NOT_LOCAL;
  try {
    const status = await getSystemStatus();
    if (status.worker.state === "down") await forceWorkerRestart(status.worker.workerId);
    else await requestWorkerRestart();
    launchRestart("comfyui");
    launchRestart("dashboard");
    return { ok: true, message: "Tout redémarre : ComfyUI et le dashboard tout de suite, le worker après sa tâche en cours. La page se recharge toute seule." };
  } catch (error) {
    return fail(error);
  }
}
