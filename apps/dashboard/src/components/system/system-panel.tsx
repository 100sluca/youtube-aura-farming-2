"use client";

/**
 * « Machine », en bas de la barre latérale (docs/28-sante-machine.md) : mémoire du PC, ComfyUI et worker d'un coup
 * d'œil, et la fenêtre qui redémarre un programme (ou tout) quand quelque chose coince. Né du 28/09/2026 : le serveur du
 * dashboard avait grossi jusqu'à 11 Go, ComfyUI était tombé pendant un clip MiniMax H3 sans que personne le voie.
 */
import * as React from "react";
import { LoaderCircle, MemoryStick, RefreshCw, RotateCcw, TriangleAlert } from "lucide-react";

import type { ActionResult } from "@/app/production/actions";
import { fetchMemoryHogs, fetchSystemStatus, restartEverything, restartService } from "@/app/system/actions";
import { ConfirmButton } from "@/components/confirm-button";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import type { MemoryHog, RestartTarget, ServiceState, SystemStatus } from "@/lib/system-types";
import { cn } from "@/lib/utils";

const fmt = (n: number) => n.toLocaleString("fr-FR", { maximumFractionDigits: 1 });

function ago(s: number | null): string {
  if (s === null) return "jamais";
  if (s < 90) return `il y a ${s} s`;
  if (s < 5400) return `il y a ${Math.round(s / 60)} min`;
  return `il y a ${Math.round(s / 3600)} h`;
}

function Dot({ state }: { state: ServiceState }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-block size-2 shrink-0 rounded-full",
        state === "ok" ? "bg-emerald-500" : state === "down" ? "bg-red-500" : "bg-muted-foreground/40"
      )}
    />
  );
}

/** État de la machine : toutes les 15 s (5 s fenêtre ouverte), onglet visible seulement, comme le panneau Tâches. */
function useSystemStatus(fast: boolean) {
  const [status, setStatus] = React.useState<SystemStatus | null>(null);
  React.useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const next = await fetchSystemStatus();
        if (alive) setStatus(next);
      } catch {
        // serveur en train de redémarrer : on garde le dernier état connu
      }
    };
    const tick = () => {
      if (document.visibilityState === "visible") void load();
    };
    void load(); // au chargement, même onglet en arrière-plan : la barre latérale ne reste pas vide
    const timer = setInterval(tick, fast ? 5000 : 15000);
    document.addEventListener("visibilitychange", tick); // retour sur l'onglet : état à jour tout de suite
    return () => {
      alive = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [fast]);
  const refresh = React.useCallback(async () => {
    try {
      setStatus(await fetchSystemStatus());
    } catch {
      // idem : le prochain passage rattrapera
    }
  }, []);
  return { status, refresh };
}

async function serverPid(): Promise<number | null> {
  try {
    const res = await fetch("/api/system/ping", { cache: "no-store" });
    return res.ok ? ((await res.json()) as { pid: number }).pid : null;
  } catch {
    return null;
  }
}

/** Après « Redémarrer le dashboard » : attendre qu'un nouveau serveur réponde (autre numéro de processus), puis recharger. */
function waitForNewServer(oldPid: number | null, onGiveUp: () => void) {
  const started = Date.now();
  const timer = setInterval(async () => {
    const pid = await serverPid();
    if (pid !== null && pid !== oldPid) {
      clearInterval(timer);
      window.location.reload();
    } else if (Date.now() - started > 180_000) {
      clearInterval(timer);
      onGiveUp();
    }
  }, 2000);
}

function Meter({ label, used, total, detail, danger }: { label: string; used: number; total: number; detail: string; danger?: boolean }) {
  const pct = total > 0 ? Math.min(100, Math.max(0, Math.round((used / total) * 100))) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span>{label}</span>
        <span className={cn("text-muted-foreground tabular-nums", danger && "font-medium text-red-600 dark:text-red-400")}>{detail}</span>
      </div>
      <Progress value={pct} className={cn("h-1.5", danger && "[&_[data-slot=progress-indicator]]:bg-red-500")} />
    </div>
  );
}

function ServiceRow({ name, state, detail, children }: { name: string; state: ServiceState; detail: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 py-2">
      <Dot state={state} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{name}</p>
        <p className="text-muted-foreground text-xs">{detail}</p>
      </div>
      <div className="flex shrink-0 flex-wrap justify-end gap-1.5">{children}</div>
    </div>
  );
}

export function SystemPanel() {
  const [open, setOpen] = React.useState(false);
  const { status, refresh } = useSystemStatus(open);
  const s = status;
  const alerts = s?.warnings.length ?? 0;
  return (
    <div className="border-sidebar-border mt-auto border-t p-3">
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="hover:bg-sidebar-accent focus-visible:ring-sidebar-ring w-full rounded-md p-2 text-left outline-none focus-visible:ring-2"
        aria-label="Machine : mémoire, ComfyUI, worker"
      >
        <div className="flex items-center justify-between gap-2 text-xs font-medium">
          <span className="flex items-center gap-1.5">
            <MemoryStick className="size-3.5" /> Machine
          </span>
          <span className="text-muted-foreground flex items-center gap-2 font-normal">
            <span className="flex items-center gap-1"><Dot state={s?.comfy.state ?? "unknown"} />ComfyUI</span>
            <span className="flex items-center gap-1"><Dot state={s?.worker.state ?? "unknown"} />Worker</span>
          </span>
        </div>
        <Progress
          value={s && s.ram.totalGb ? Math.round(((s.ram.totalGb - s.ram.freeGb) / s.ram.totalGb) * 100) : 0}
          className={cn("mt-2 h-1.5", s && s.ram.freeGb < 3 && "[&_[data-slot=progress-indicator]]:bg-red-500")}
        />
        <p className="text-muted-foreground mt-1 text-[11px] tabular-nums">
          {s ? `RAM : ${fmt(s.ram.freeGb)} Go libres sur ${fmt(s.ram.totalGb)}` : "Lecture de l'état…"}
        </p>
        {alerts ? (
          <p className="mt-1 flex items-center gap-1 text-[11px] font-medium text-amber-600 dark:text-amber-400">
            <TriangleAlert className="size-3 shrink-0" /> {alerts === 1 ? "1 alerte" : `${alerts} alertes`} : voir le détail
          </p>
        ) : null}
      </button>
      <Button variant="outline" size="sm" className="mt-2 w-full" onClick={() => setOpen(true)}>
        <RotateCcw /> Redémarrer…
      </Button>
      <SystemDialog open={open} onOpenChange={setOpen} status={s} refresh={refresh} />
    </div>
  );
}

function SystemDialog({
  open,
  onOpenChange,
  status: s,
  refresh,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  status: SystemStatus | null;
  refresh: () => Promise<void>;
}) {
  const [notice, setNotice] = React.useState<ActionResult | null>(null);
  const [pending, startTransition] = React.useTransition();
  const [reloading, setReloading] = React.useState(false);
  const [hogs, setHogs] = React.useState<MemoryHog[] | null>(null);
  const [hogsLoading, setHogsLoading] = React.useState(false);

  const loadHogs = React.useCallback(async () => {
    setHogsLoading(true);
    try {
      setHogs(await fetchMemoryHogs());
    } finally {
      setHogsLoading(false);
    }
  }, []);
  // à l'ouverture : la liste des programmes (≈ 2 s de PowerShell côté serveur)
  React.useEffect(() => {
    if (!open) return;
    let alive = true;
    void fetchMemoryHogs().then((next) => {
      if (alive) setHogs(next);
    });
    return () => {
      alive = false;
    };
  }, [open]);

  function run(action: () => Promise<ActionResult>, reloadsDashboard = false) {
    startTransition(async () => {
      const oldPid = reloadsDashboard ? await serverPid() : null;
      const res = await action();
      setNotice(res);
      if (res.ok && reloadsDashboard) {
        setReloading(true);
        waitForNewServer(oldPid, () => {
          setReloading(false);
          setNotice({ ok: false, message: "Le dashboard ne revient pas : double-cliquer C:\\YouTube2\\dashboard.bat" });
        });
      } else {
        void refresh();
        void loadHogs();
      }
    });
  }
  const restart = (target: RestartTarget, force = false) => run(() => restartService(target, force), target === "dashboard");

  const busy = pending || reloading;
  const gpu = s?.gpuJob ? s.gpuJob.label ?? s.gpuJob.type : null;
  const worker = s?.worker;
  const workerDetail = !worker
    ? "…"
    : worker.state === "unknown"
      ? "Pas encore de signe de vie : le relancer une fois pour qu'il en envoie"
      : worker.state === "down"
        ? `Silencieux depuis ${ago(worker.lastBeatS).replace("il y a ", "")} : plus rien n'avance`
        : `Actif · signe de vie ${ago(worker.lastBeatS)}${worker.draining || worker.restartPending ? " · se relance après la tâche en cours" : ""}`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Machine</DialogTitle>
          <DialogDescription>
            Mémoire du PC et programmes de YouTube 2.0. Redémarrer un programme libère sa mémoire ; les tâches interrompues
            reprennent toutes seules.
          </DialogDescription>
        </DialogHeader>

        {s?.warnings.length ? (
          <ul className="space-y-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs">
            {s.warnings.map((w) => (
              <li key={w} className="flex gap-1.5">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-amber-600 dark:text-amber-400" /> {w}
              </li>
            ))}
          </ul>
        ) : null}

        <section className="space-y-3">
          <h3 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">Mémoire</h3>
          {s ? (
            <>
              <Meter label="RAM" used={s.ram.totalGb - s.ram.freeGb} total={s.ram.totalGb}
                detail={`${fmt(s.ram.freeGb)} Go libres sur ${fmt(s.ram.totalGb)}`} danger={s.ram.freeGb < 3} />
              {s.ram.commitFreeGb !== null && s.ram.commitTotalGb ? (
                <Meter label="Réservable (RAM + fichier d'échange)" used={s.ram.commitTotalGb - s.ram.commitFreeGb}
                  total={s.ram.commitTotalGb} detail={`${fmt(s.ram.commitFreeGb)} Go libres sur ${fmt(s.ram.commitTotalGb)}`}
                  danger={s.ram.commitFreeGb < 6} />
              ) : null}
              {s.vram ? (
                <Meter label="Carte graphique" used={s.vram.usedMb} total={s.vram.totalMb}
                  detail={`${fmt(s.vram.usedMb / 1024)} Go utilisés sur ${fmt(s.vram.totalMb / 1024)}`} />
              ) : null}
            </>
          ) : (
            <p className="text-muted-foreground text-xs">Lecture de l&apos;état…</p>
          )}
        </section>

        <section>
          <h3 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">Programmes</h3>
          <div className="divide-y">
            <ServiceRow
              name="ComfyUI"
              state={s?.comfy.state ?? "unknown"}
              detail={!s ? "…" : s.comfy.state === "ok"
                ? `En marche${s.comfy.queue ? ` · ${s.comfy.queue} rendu(s) en cours ou en file` : ""}`
                : "Ne répond pas"}
            >
              <ConfirmButton size="sm" variant="outline" disabled={busy} onConfirm={() => restart("comfyui")}
                confirmLabel={gpu ? "Couper le rendu ?" : "Confirmer ?"}>
                Redémarrer
              </ConfirmButton>
            </ServiceRow>
            <ServiceRow name="Worker" state={worker?.state ?? "unknown"}
              detail={<>{workerDetail}{gpu ? <><br />Sur la carte graphique : {gpu}</> : null}</>}>
              <Button size="sm" variant="outline" disabled={busy || worker?.draining || worker?.restartPending}
                onClick={() => restart("worker")}>
                Redémarrer
              </Button>
              {worker && worker.state !== "ok" ? (
                <ConfirmButton size="sm" variant="outline" disabled={busy} onConfirm={() => restart("worker", true)}
                  confirmLabel="Arrêter de force ?">
                  Forcer
                </ConfirmButton>
              ) : null}
            </ServiceRow>
            <ServiceRow name="Dashboard" state="ok"
              detail={s ? `Serveur : ${fmt(s.dashboard.rssGb)} Go de mémoire · lancé ${ago(s.dashboard.uptimeS)}` : "…"}>
              <ConfirmButton size="sm" variant="outline" disabled={busy} onConfirm={() => restart("dashboard")}
                confirmLabel="Recharger la page ?">
                Redémarrer
              </ConfirmButton>
            </ServiceRow>
          </div>
        </section>

        <section>
          <div className="flex items-center justify-between">
            <h3 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">Ce qui prend la mémoire</h3>
            <Button size="sm" variant="ghost" className="h-7" disabled={hogsLoading} onClick={() => void loadHogs()}>
              {hogsLoading ? <LoaderCircle className="animate-spin" /> : <RefreshCw />} Actualiser
            </Button>
          </div>
          {hogs === null ? (
            <p className="text-muted-foreground text-xs">Calcul…</p>
          ) : (
            <ul className="mt-1 space-y-1 text-sm">
              {hogs.map((h) => (
                <li key={h.label} className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate">
                    {h.label}
                    {h.count > 1 ? <span className="text-muted-foreground text-xs"> × {h.count}</span> : null}
                  </span>
                  <span className="text-muted-foreground tabular-nums">{fmt(h.gb)} Go</span>
                </li>
              ))}
            </ul>
          )}
          <p className="text-muted-foreground mt-2 text-xs">
            Les autres programmes (navigateurs, montage…) se ferment à la main pendant les clips MiniMax H3, qui prennent
            25 à 30 Go.
          </p>
        </section>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-4">
          <p className={cn("min-w-0 flex-1 text-xs", notice ? (notice.ok ? "text-emerald-700 dark:text-emerald-400" : "text-red-600 dark:text-red-400") : "text-muted-foreground")}>
            {reloading ? "Le dashboard redémarre, la page va se recharger…" : notice?.message ?? "ComfyUI, puis le worker après sa tâche en cours, puis cette page."}
          </p>
          <ConfirmButton disabled={busy} onConfirm={() => run(() => restartEverything(), true)} confirmLabel="Tout redémarrer ?">
            {busy ? <LoaderCircle className="animate-spin" /> : <RotateCcw />} Tout redémarrer
          </ConfirmButton>
        </div>
      </DialogContent>
    </Dialog>
  );
}
