"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ArrowUpToLine,
  ChevronDown,
  CircleCheck,
  CircleX,
  Clapperboard,
  Ellipsis,
  EyeOff,
  GripVertical,
  ListChecks,
  LoaderCircle,
  Pause,
  Play,
  RefreshCw,
  Square,
  Trash2,
  X,
} from "lucide-react";

import { retryProduction } from "@/app/production/actions";
import {
  cancelJob,
  dismissJob,
  fetchProductionCard,
  fetchTaskBoard,
  focusProduction,
  pauseProductions,
  removeProduction,
  reorderQueue,
  resumeProduction,
  retryJob,
  stopProduction,
  unpauseProductions,
} from "@/app/tasks/actions";
import { ConfirmButton } from "@/components/confirm-button";
import { ProductionSheet } from "@/components/production/production-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { formatDate, formatRelative, formatTime, parisDayKey } from "@/lib/format";
import { EMPTY_TASK_BOARD, type TaskBoard, type TaskJob, type TaskProduction } from "@/lib/task-types";
import type { ProductionCard } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Événement qui ouvre le panneau depuis n'importe quelle page (OpenTasksButton). */
export const OPEN_TASKS_EVENT = "yt2:open-tasks";

type Notice = { ok: boolean; message: string };
type Result = { ok: boolean; message: string };

/** « vers 18:40 » aujourd'hui, sinon « ven. 26 sept., 04:10 ». */
function etaLabel(eta: string, now: string): string {
  return parisDayKey(eta) === parisDayKey(now) ? `vers ${formatTime(eta)}` : formatDate(eta, "EEE d MMM, HH:mm");
}

/** Ce que « Tout de suite » refera à la reprise : le clip, les images ou la voix en cours (avec son titre si `named`). */
function redoHint(task: TaskProduction, named = false): string {
  const of = named ? ` de « ${task.title} »` : "";
  const pct = task.step_progress ? ` (${task.step_progress} %)` : "";
  switch (task.step_type) {
    case "generate_clip":
      return `Le clip en cours${of}${pct} sera refait à la reprise`;
    case "storyboard":
      return `Les images en cours${of}${pct} seront refaites à la reprise`;
    case "tts":
      return `La voix en cours${of}${pct} sera refaite à la reprise`;
    default:
      return `L’étape en cours${of} sera refaite à la reprise`;
  }
}

function afterStepLabel(task: TaskProduction): string {
  switch (task.step_type) {
    case "generate_clip":
      return "À la fin du clip en cours";
    case "storyboard":
      return "À la fin des images en cours";
    case "tts":
      return "À la fin de la voix en cours";
    default:
      return "À la fin de l’étape en cours";
  }
}

function afterStepHint(task: TaskProduction, now: string): string {
  return `${task.step_end_at ? `Fin prévue ${etaLabel(task.step_end_at, now)}` : "Bientôt"} · rien n’est perdu`;
}

function Cover({ assetId }: { assetId: string | null }) {
  if (!assetId) {
    return (
      <span className="bg-muted text-muted-foreground flex h-16 w-9 shrink-0 items-center justify-center rounded-md" aria-hidden>
        <Clapperboard className="size-4" />
      </span>
    );
  }
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={`/api/media/${assetId}`} alt="" className="h-16 w-9 shrink-0 rounded-md object-cover" loading="lazy" />;
}

/** Glisser-déposer dans la file d'attente : poignée de la carte et trait qui montre où elle va tomber. */
type DragProps = {
  dragging: boolean;
  drop: "before" | "after" | null;
  onDragStart: (event: React.DragEvent) => void;
  onDragEnd: () => void;
  onDragOver: (event: React.DragEvent) => void;
  onDrop: (event: React.DragEvent) => void;
};

function TaskCard({
  task,
  now,
  onDetails,
  drag,
  children,
}: {
  task: TaskProduction;
  now: string;
  onDetails: () => void;
  drag?: DragProps;
  children?: React.ReactNode;
}) {
  const ended = task.status === "failed" || task.status === "cancelled";
  const meta = [task.channel_name, task.series_name].filter(Boolean).join(" · ");
  return (
    <li
      className={cn(
        "relative flex gap-3 rounded-lg border p-3",
        task.status === "failed" && "border-destructive/40",
        task.paused && !task.running && "bg-muted/40",
        drag?.dragging && "opacity-40",
      )}
      onDragOver={drag?.onDragOver}
      onDrop={drag?.onDrop}
    >
      {drag?.drop ? (
        <span className={cn("bg-primary pointer-events-none absolute inset-x-1 h-0.5 rounded-full", drag.drop === "before" ? "-top-[5px]" : "-bottom-[5px]")} aria-hidden />
      ) : null}
      {drag ? (
        <button
          type="button"
          draggable
          onDragStart={drag.onDragStart}
          onDragEnd={drag.onDragEnd}
          className="text-muted-foreground hover:text-foreground -my-1 -ml-1.5 flex w-4 shrink-0 cursor-grab items-center justify-center active:cursor-grabbing"
          aria-label="Glisser pour changer sa place dans la file"
          title="Glisser pour changer sa place dans la file"
        >
          <GripVertical className="size-4" />
        </button>
      ) : null}
      <Cover assetId={task.cover_asset_id} />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex items-start gap-2">
          <button type="button" onClick={onDetails} className="line-clamp-2 text-left text-sm leading-snug font-medium hover:underline">
            {task.title}
          </button>
          {task.queue_position ? (
            <Badge variant="secondary" className="ml-auto shrink-0 tabular-nums" title="Place dans la file">
              n° {task.queue_position}
            </Badge>
          ) : task.paused && !task.running ? (
            <Badge variant="outline" className="ml-auto shrink-0 gap-1">
              <Pause className="size-3" />
              En pause
            </Badge>
          ) : null}
        </div>
        {meta ? <p className="text-muted-foreground truncate text-xs">{meta}</p> : null}
        <p className="flex items-center gap-1.5 text-xs font-medium">
          {task.running ? <LoaderCircle className="size-3.5 shrink-0 animate-spin text-violet-500" /> : null}
          {task.stage}
        </p>
        {task.pause_pending ? (
          <p className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
            <Pause className="size-3.5 shrink-0" />
            Pause demandée : elle s’arrête à la fin de cette étape{task.step_end_at ? ` (${etaLabel(task.step_end_at, now)})` : ""}.
          </p>
        ) : null}
        {!ended ? <Progress value={task.progress_pct} className={cn("h-1.5", task.paused && !task.running && "opacity-50")} aria-label={`Avancement ${task.progress_pct} %`} /> : null}
        {!ended && (task.step_started_at || task.eta_at) ? (
          <p className="text-muted-foreground text-[11px] tabular-nums">
            {task.step_started_at ? `Étape commencée ${formatRelative(task.step_started_at, new Date(now))}` : null}
            {task.step_started_at && task.eta_at ? " · " : null}
            {task.eta_at ? `${task.phase === "preparation" ? "storyboard" : "prête"} ${etaLabel(task.eta_at, now)} (estimation)` : null}
          </p>
        ) : null}
        {task.error && task.status === "failed" ? <p className="text-destructive line-clamp-3 text-xs">{task.error}</p> : null}
        {children ? <div className="flex flex-wrap gap-1.5 pt-0.5">{children}</div> : null}
      </div>
    </li>
  );
}

function JobRow({ job, now, children }: { job: TaskJob; now: string; children?: React.ReactNode }) {
  return (
    <li className={cn("flex flex-col gap-1.5 rounded-lg border p-3", job.status === "failed" && "border-destructive/40")}>
      <div className="flex items-center gap-2 text-sm">
        {job.status === "running" ? <LoaderCircle className="size-3.5 shrink-0 animate-spin text-violet-500" /> : null}
        <span className="font-medium">{job.label}</span>
        <span className="text-muted-foreground ml-auto shrink-0 text-xs">
          {job.status === "running" ? "en cours" : job.status === "queued" ? "en file" : formatRelative(job.created_at, new Date(now))}
        </span>
      </div>
      {job.detail || job.progress_label ? (
        <p className="text-muted-foreground text-xs">{[job.detail, job.progress_label].filter(Boolean).join(" · ")}</p>
      ) : null}
      {job.error && job.status === "failed" ? <p className="text-destructive line-clamp-3 text-xs">{job.error}</p> : null}
      {children ? <div className="flex flex-wrap gap-1.5">{children}</div> : null}
    </li>
  );
}

function Section({
  title,
  count,
  hint,
  children,
  tone,
}: {
  title: string;
  count: number;
  hint?: string;
  children: React.ReactNode;
  tone?: "danger" | "warning";
}) {
  return (
    <section className="flex flex-col gap-2">
      <h3
        className={cn(
          "flex items-center gap-2 text-xs font-semibold tracking-wide uppercase",
          tone === "danger" ? "text-destructive" : tone === "warning" ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground",
        )}
      >
        {title}
        <span className="font-normal tabular-nums">{count}</span>
      </h3>
      {hint ? <p className="text-muted-foreground -mt-1 text-xs">{hint}</p> : null}
      <ul className="flex flex-col gap-2">{children}</ul>
    </section>
  );
}

/** Ligne de menu : un titre et, dessous, ce que le geste fait vraiment. */
function MenuEntry({ icon, title, hint }: { icon: React.ReactNode; title: string; hint?: string }) {
  return (
    <>
      {icon}
      <span className="flex min-w-0 flex-col">
        <span>{title}</span>
        {hint ? <span className="text-muted-foreground text-xs leading-snug">{hint}</span> : null}
      </span>
    </>
  );
}

/** Geste à confirmer dans un menu (arrêter) : le premier choix demande confirmation, le second agit (pas de double-clic). */
function ConfirmMenuItem({ onConfirm, title, hint, confirmLabel }: { onConfirm: () => void; title: string; hint?: string; confirmLabel: string }) {
  const [armedAt, setArmedAt] = React.useState<number | null>(null);
  return (
    <DropdownMenuItem
      variant="destructive"
      onSelect={(event) => {
        if (armedAt === null) {
          event.preventDefault();
          setArmedAt(event.timeStamp);
          return;
        }
        if (event.timeStamp - armedAt < 600) {
          event.preventDefault();
          return;
        }
        onConfirm();
      }}
    >
      <MenuEntry icon={<Square />} title={armedAt === null ? title : confirmLabel} hint={armedAt === null ? hint : "Choisis encore pour confirmer"} />
    </DropdownMenuItem>
  );
}

/** Les deux façons de s'arrêter quand un calcul tourne sur la carte graphique : tout de suite, ou à la fin de ce calcul. */
function WhenItems({ gpuTask, named, now, onPick }: { gpuTask: TaskProduction; named: boolean; now: string; onPick: (immediate: boolean) => void }) {
  return (
    <>
      <DropdownMenuItem onSelect={() => onPick(true)}>
        <MenuEntry icon={<Pause />} title="Tout de suite" hint={redoHint(gpuTask, named)} />
      </DropdownMenuItem>
      <DropdownMenuItem onSelect={() => onPick(false)}>
        <MenuEntry icon={<CircleCheck />} title={afterStepLabel(gpuTask)} hint={afterStepHint(gpuTask, now)} />
      </DropdownMenuItem>
    </>
  );
}

/** Bouton « Tâches » de l'en-tête et panneau de droite : ce qui se fabrique, dans l'ordre, et les gestes de pause et d'arrêt. */
export function TaskManager() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [board, setBoard] = React.useState<TaskBoard>(EMPTY_TASK_BOARD);
  const [notice, setNotice] = React.useState<Notice | null>(null);
  const [detail, setDetail] = React.useState<ProductionCard | null>(null);
  const [pending, startTransition] = React.useTransition();
  const [dragId, setDragId] = React.useState<string | null>(null);
  const [dropAt, setDropAt] = React.useState<{ id: string; after: boolean } | null>(null);
  const dragging = React.useRef(false); // pas de rafraîchissement pendant un glisser : la liste ne bouge pas sous la souris

  // Rafraîchissement : toutes les 3 s panneau ouvert, toutes les 15 s sinon (pastille du bouton), onglet visible seulement
  React.useEffect(() => {
    let alive = true;
    const tick = async () => {
      if (document.visibilityState !== "visible" || dragging.current) return;
      try {
        const next = await fetchTaskBoard();
        if (alive && !dragging.current) setBoard(next);
      } catch {
        // serveur momentanément indisponible : on garde le dernier état
      }
    };
    void tick();
    const timer = setInterval(tick, open ? 3000 : 15000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [open]);

  React.useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener(OPEN_TASKS_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_TASKS_EVENT, onOpen);
  }, []);

  /** Lance un geste ; `okMessage` remplace le message du serveur quand le panneau sait mieux dire ce qui va se passer. */
  const run = (fn: () => Promise<Result>, okMessage?: string) =>
    startTransition(async () => {
      const res = await fn();
      setNotice(res.ok && okMessage ? { ok: true, message: okMessage } : res);
      try {
        setBoard(await fetchTaskBoard());
      } catch {
        // ignoré : le prochain rafraîchissement rattrapera
      }
      router.refresh();
    });

  const showDetails = (id: string) => startTransition(async () => setDetail(await fetchProductionCard(id)));

  const { counts } = board;
  const now = board.generated_at;
  const inFlight = board.running.length + board.queued.length + board.preparing.length;
  const nothing =
    inFlight +
      board.paused.length +
      board.waiting.length +
      board.review_videos +
      board.failed.length +
      board.stopped.length +
      board.other_jobs.length +
      board.failed_jobs.length ===
    0;
  // La vidéo dont un clip, des images ou la voix tournent sur la carte graphique (celle qu'une pause « tout de suite » coupe)
  const gpuTask = board.running.find((t) => t.gpu_step && !t.paused) ?? null;
  const pausable = [...board.running.filter((t) => !t.paused), ...board.queued, ...board.preparing];
  const resumable = [...board.running.filter((t) => t.paused), ...board.paused];
  const queueIds = board.queued.map((t) => t.id);

  // ---- ordre de la file -------------------------------------------------------------------------------------------
  const applyOrder = (order: string[], okMessage: string) => {
    if (order.join() === queueIds.join()) return;
    setBoard((b) => {
      const byId = new Map(b.queued.map((t) => [t.id, t]));
      const queued = order.flatMap((id, i) => {
        const t = byId.get(id);
        return t ? [{ ...t, queue_position: i + 1 }] : [];
      });
      return { ...b, queued };
    });
    run(() => reorderQueue(order), okMessage);
  };
  const moveTo = (task: TaskProduction, index: number) => {
    const order = queueIds.filter((id) => id !== task.id);
    const at = Math.max(0, Math.min(index, order.length));
    order.splice(at, 0, task.id);
    const first = gpuTask ? `« ${task.title} » passe en premier, juste après la vidéo en cours` : `« ${task.title} » passe en premier`;
    applyOrder(order, at === 0 ? first : `« ${task.title} » passe n° ${at + 1}`);
  };
  const endDrag = () => {
    dragging.current = false;
    setDragId(null);
    setDropAt(null);
  };
  const dragProps = (task: TaskProduction): DragProps => ({
    dragging: dragId === task.id,
    drop: dropAt && dragId && dropAt.id === task.id && dragId !== task.id ? (dropAt.after ? "after" : "before") : null,
    onDragStart: (event) => {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", task.id);
      const card = (event.currentTarget as HTMLElement).closest("li");
      if (card) event.dataTransfer.setDragImage(card, 24, 24);
      dragging.current = true;
      setDragId(task.id);
    },
    onDragEnd: endDrag,
    onDragOver: (event) => {
      if (!dragId) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      const box = event.currentTarget.getBoundingClientRect();
      const after = event.clientY > box.top + box.height / 2;
      setDropAt((d) => (d && d.id === task.id && d.after === after ? d : { id: task.id, after }));
    },
    onDrop: (event) => {
      event.preventDefault();
      const moved = board.queued.find((t) => t.id === dragId);
      const after = dropAt?.id === task.id ? dropAt.after : false;
      endDrag();
      if (!moved || moved.id === task.id) return;
      const order = queueIds.filter((id) => id !== moved.id);
      order.splice(order.indexOf(task.id) + (after ? 1 : 0), 0, moved.id);
      applyOrder(order, `« ${moved.title} » passe n° ${order.indexOf(moved.id) + 1}`);
    },
  });

  // ---- pause ----------------------------------------------------------------------------------------------------------
  const pauseOne = (task: TaskProduction, immediate: boolean) => {
    const message = !task.running
      ? `« ${task.title} » en pause : elle garde sa place et tout ce qui est fait`
      : task.gpu_step && immediate
        ? `« ${task.title} » en pause dans quelques secondes. ${redoHint(task)} ; le reste est gardé.`
        : `« ${task.title} » se met en pause à la fin de l’étape en cours : rien n’est perdu`;
    run(() => pauseProductions([task.id], immediate), message);
  };
  const focus = (task: TaskProduction, immediate: boolean) =>
    run(() => focusProduction(task.id, immediate), `Tout est en pause sauf « ${task.title} », qui passe en premier. Reprends les autres quand tu veux.`);

  // Morceaux de menus rendus par de simples fonctions (pas des composants définis ici : un menu ouvert serait remonté,
  // donc refermé, à chaque rafraîchissement du panneau)

  /** « Tout mettre en pause sauf celle-ci » : au choix tout de suite ou à la fin du calcul en cours d'une autre vidéo. */
  const focusItem = (task: TaskProduction, title: string, hint: string) =>
    gpuTask && gpuTask.id !== task.id ? (
      <DropdownMenuSub>
        <DropdownMenuSubTrigger>
          <MenuEntry icon={<ListChecks />} title={title} hint={hint} />
        </DropdownMenuSubTrigger>
        <DropdownMenuSubContent className="w-72">
          <WhenItems gpuTask={gpuTask} named now={now} onPick={(immediate) => focus(task, immediate)} />
        </DropdownMenuSubContent>
      </DropdownMenuSub>
    ) : (
      <DropdownMenuItem onSelect={() => focus(task, true)}>
        <MenuEntry icon={<ListChecks />} title={title} hint={hint} />
      </DropdownMenuItem>
    );

  const stopItem = (task: TaskProduction) => (
    <ConfirmMenuItem
      title="Arrêter la fabrication"
      hint="Rien n’est supprimé : elle passe dans « Arrêtées »"
      confirmLabel="Confirmer l’arrêt"
      onConfirm={() => run(() => stopProduction(task.id))}
    />
  );

  const moreMenu = (items: React.ReactNode) => (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="ghost" disabled={pending} aria-label="Plus d’actions" title="Plus d’actions">
          <Ellipsis />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        {items}
      </DropdownMenuContent>
    </DropdownMenu>
  );

  return (
    <>
      <Button variant="outline" size="sm" className="relative gap-2" onClick={() => setOpen(true)} aria-label="Gestionnaire de tâches">
        {board.running.length > 0 ? <LoaderCircle className="size-4 animate-spin" /> : <ListChecks className="size-4" />}
        <span className="hidden sm:inline">Tâches</span>
        {counts.active > 0 ? (
          <span className="bg-primary text-primary-foreground rounded-full px-1.5 text-[11px] leading-5 font-semibold tabular-nums">{counts.active}</span>
        ) : null}
        {counts.failures > 0 || counts.attention > 0 ? (
          <span
            className={cn("absolute -top-1 -right-1 size-2.5 rounded-full ring-2 ring-background", counts.failures > 0 ? "bg-red-500" : "bg-amber-500")}
            aria-label={counts.failures > 0 ? "Des tâches ont échoué" : "Des vidéos attendent ton avis"}
          />
        ) : null}
      </Button>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-md">
          <SheetHeader className="border-b pr-12">
            <SheetTitle>Tâches</SheetTitle>
            <SheetDescription>
              {inFlight > 0
                ? `${inFlight} vidéo${inFlight > 1 ? "s" : ""} en fabrication${board.queue_end_at ? ` · file terminée ${etaLabel(board.queue_end_at, now)} (estimation)` : ""}`
                : "Rien ne se fabrique en ce moment."}
              {board.paused.length > 0 ? ` · ${board.paused.length} en pause` : ""}
            </SheetDescription>
            {pausable.length + resumable.length > 0 ? (
              <div className="flex flex-wrap gap-2 pt-1">
                {pausable.length > 0 ? (
                  gpuTask ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button size="sm" variant="outline" disabled={pending}>
                          <Pause />
                          Tout mettre en pause
                          <ChevronDown />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="start" className="w-72">
                        <WhenItems
                          gpuTask={gpuTask}
                          named
                          now={now}
                          onPick={(immediate) =>
                            run(
                              () => pauseProductions(pausable.map((t) => t.id), immediate),
                              immediate
                                ? "Tout est en pause ; le calcul en cours s’arrête dans quelques secondes. Ce qui est fait est gardé."
                                : "Tout se met en pause ; le calcul en cours se termine d’abord. Rien n’est perdu.",
                            )
                          }
                        />
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={pending}
                      onClick={() => run(() => pauseProductions(pausable.map((t) => t.id), true), "Tout est en pause. Ce qui est fait est gardé.")}
                    >
                      <Pause />
                      Tout mettre en pause
                    </Button>
                  )
                ) : null}
                {resumable.length > 0 ? (
                  <Button size="sm" variant="outline" disabled={pending} onClick={() => run(() => unpauseProductions(resumable.map((t) => t.id)))}>
                    <Play />
                    Tout reprendre{resumable.length > 1 ? ` (${resumable.length})` : ""}
                  </Button>
                ) : null}
              </div>
            ) : null}
            {notice ? (
              <p className={cn("flex items-center gap-1.5 text-xs", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")} role="status">
                {notice.ok ? <CircleCheck className="size-3.5 shrink-0" /> : <CircleX className="size-3.5 shrink-0" />}
                {notice.message}
              </p>
            ) : null}
          </SheetHeader>

          <ScrollArea className="min-h-0 flex-1">
            <div className="flex flex-col gap-6 p-4">
              {counts.attention > 0 ? (
                <Section title="À toi de jouer" count={counts.attention} tone="warning">
                  {board.waiting.length > 0 ? (
                    <li className="flex items-center gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                      <span className="flex-1">
                        {board.waiting.length} storyboard{board.waiting.length > 1 ? "s" : ""} à regarder : ton ✓ lance la fabrication.
                      </span>
                      <Button size="sm" asChild onClick={() => setOpen(false)}>
                        <Link href="/create#storyboards">
                          Voir <ArrowRight />
                        </Link>
                      </Button>
                    </li>
                  ) : null}
                  {board.review_videos > 0 ? (
                    <li className="flex items-center gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                      <span className="flex-1">
                        {board.review_videos} vidéo{board.review_videos > 1 ? "s" : ""} finie{board.review_videos > 1 ? "s" : ""} : à publier ou refuser.
                      </span>
                      <Button size="sm" asChild onClick={() => setOpen(false)}>
                        <Link href="/library?statut=a_valider">
                          Voir <ArrowRight />
                        </Link>
                      </Button>
                    </li>
                  ) : null}
                </Section>
              ) : null}

              {board.running.length > 0 ? (
                <Section title="En cours" count={board.running.length}>
                  {board.running.map((task) => (
                    <TaskCard key={task.id} task={task} now={now} onDetails={() => showDetails(task.id)}>
                      {task.paused ? (
                        <>
                          <Button size="sm" variant="outline" disabled={pending} onClick={() => run(() => unpauseProductions([task.id]), `« ${task.title} » continue`)}>
                            <Play />
                            Annuler la pause
                          </Button>
                          {task.gpu_step ? (
                            <Button size="sm" variant="ghost" disabled={pending} onClick={() => pauseOne(task, true)} title={redoHint(task)}>
                              <Pause />
                              Pause tout de suite
                            </Button>
                          ) : null}
                        </>
                      ) : task.gpu_step ? (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button size="sm" variant="outline" disabled={pending}>
                              <Pause />
                              Pause
                              <ChevronDown />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="start" className="w-72">
                            <WhenItems gpuTask={task} named={false} now={now} onPick={(immediate) => pauseOne(task, immediate)} />
                          </DropdownMenuContent>
                        </DropdownMenu>
                      ) : (
                        <Button size="sm" variant="outline" disabled={pending} onClick={() => pauseOne(task, true)} title="L’étape en cours se termine, puis elle attend">
                          <Pause />
                          Pause
                        </Button>
                      )}
                      {moreMenu(
                        <>
                          {!task.paused ? (
                            <>
                              {focusItem(task, "Tout mettre en pause sauf celle-ci", "Elle passe en premier ; tu reprendras les autres quand tu veux")}
                              <DropdownMenuSeparator />
                            </>
                          ) : null}
                          {stopItem(task)}
                        </>,
                      )}
                    </TaskCard>
                  ))}
                </Section>
              ) : null}

              {board.queued.length > 0 ? (
                <Section
                  title="En file d’attente"
                  count={board.queued.length}
                  hint={board.queued.length > 1 ? "La vidéo en cours finit d’abord. Pour changer l’ordre : glisse la poignée ⠿, ou ⋯." : undefined}
                >
                  {board.queued.map((task, index) => (
                    <TaskCard key={task.id} task={task} now={now} onDetails={() => showDetails(task.id)} drag={board.queued.length > 1 ? dragProps(task) : undefined}>
                      <Button size="sm" variant="outline" disabled={pending} onClick={() => pauseOne(task, true)}>
                        <Pause />
                        Pause
                      </Button>
                      {index > 0 ? (
                        <Button size="sm" variant="ghost" disabled={pending} onClick={() => moveTo(task, 0)} title={gpuTask ? "Juste après la vidéo en cours" : "Passer en premier"}>
                          <ArrowUpToLine />
                          En premier
                        </Button>
                      ) : null}
                      {moreMenu(
                        <>
                          {index > 0 ? (
                            <>
                              <DropdownMenuItem onSelect={() => moveTo(task, 0)}>
                                <MenuEntry icon={<ArrowUpToLine />} title="Passer en premier" hint={gpuTask ? "Juste après la vidéo en cours" : undefined} />
                              </DropdownMenuItem>
                              <DropdownMenuItem onSelect={() => moveTo(task, index - 1)}>
                                <MenuEntry icon={<ArrowUp />} title="Monter d’une place" />
                              </DropdownMenuItem>
                            </>
                          ) : null}
                          {index < board.queued.length - 1 ? (
                            <DropdownMenuItem onSelect={() => moveTo(task, index + 1)}>
                              <MenuEntry icon={<ArrowDown />} title="Descendre d’une place" />
                            </DropdownMenuItem>
                          ) : null}
                          {board.queued.length > 1 ? <DropdownMenuSeparator /> : null}
                          {focusItem(task, "Tout mettre en pause sauf celle-ci", "Elle passe en premier ; tu reprendras les autres quand tu veux")}
                          <DropdownMenuSeparator />
                          {stopItem(task)}
                        </>,
                      )}
                    </TaskCard>
                  ))}
                </Section>
              ) : null}

              {board.preparing.length > 0 ? (
                <Section
                  title="En préparation"
                  count={board.preparing.length}
                  hint="Script et images du storyboard : ils passent avant les clips, pour que tu puisses valider vite."
                >
                  {board.preparing.map((task) => (
                    <TaskCard key={task.id} task={task} now={now} onDetails={() => showDetails(task.id)}>
                      <Button size="sm" variant="outline" disabled={pending} onClick={() => pauseOne(task, true)}>
                        <Pause />
                        Pause
                      </Button>
                      {moreMenu(
                        <>
                          {focusItem(task, "Tout mettre en pause sauf celle-ci", "Elle passe en premier ; tu reprendras les autres quand tu veux")}
                          <DropdownMenuSeparator />
                          {stopItem(task)}
                        </>,
                      )}
                    </TaskCard>
                  ))}
                </Section>
              ) : null}

              {board.paused.length > 0 ? (
                <Section
                  title="En pause"
                  count={board.paused.length}
                  hint="Tout ce qui est fait est gardé. À la reprise, elle retrouve sa place dans la file (jamais devant la vidéo en cours)."
                >
                  {board.paused.map((task) => (
                    <TaskCard key={task.id} task={task} now={now} onDetails={() => showDetails(task.id)}>
                      <Button size="sm" variant="outline" disabled={pending} onClick={() => run(() => unpauseProductions([task.id]), `« ${task.title} » reprend sa place dans la file`)}>
                        <Play />
                        Reprendre
                      </Button>
                      {moreMenu(
                        <>
                          {task.phase === "fabrication" ? (
                            <DropdownMenuItem
                              onSelect={() =>
                                run(
                                  () => unpauseProductions([task.id], [task.id, ...queueIds]),
                                  gpuTask ? `« ${task.title} » reprend en premier, juste après la vidéo en cours` : `« ${task.title} » reprend en premier`,
                                )
                              }
                            >
                              <MenuEntry icon={<ArrowUpToLine />} title="Reprendre en premier" hint={gpuTask ? "Juste après la vidéo en cours" : undefined} />
                            </DropdownMenuItem>
                          ) : null}
                          {focusItem(task, "Reprendre seulement celle-ci", "Les autres se mettent en pause ; elle passe en premier")}
                          <DropdownMenuSeparator />
                          {stopItem(task)}
                        </>,
                      )}
                    </TaskCard>
                  ))}
                </Section>
              ) : null}

              {board.waiting.length > 0 ? (
                <Section title="Storyboards à valider" count={board.waiting.length}>
                  {board.waiting.map((task) => (
                    <TaskCard key={task.id} task={task} now={now} onDetails={() => showDetails(task.id)}>
                      <Button size="sm" variant="outline" asChild onClick={() => setOpen(false)}>
                        <Link href="/create#storyboards">
                          <Clapperboard />
                          Regarder
                        </Link>
                      </Button>
                    </TaskCard>
                  ))}
                </Section>
              ) : null}

              {board.other_jobs.length > 0 ? (
                <Section title="Autres tâches" count={board.other_jobs.length}>
                  {board.other_jobs.map((job) => (
                    <JobRow key={job.id} job={job} now={now}>
                      <Button size="sm" variant="ghost" disabled={pending} onClick={() => run(() => cancelJob(job.id))}>
                        <X />
                        {job.status === "running" ? "Arrêter" : "Annuler"}
                      </Button>
                    </JobRow>
                  ))}
                </Section>
              ) : null}

              {board.failed.length + board.failed_jobs.length > 0 ? (
                <Section title="Échecs" count={board.failed.length + board.failed_jobs.length} tone="danger">
                  {board.failed.map((task) => (
                    <TaskCard key={task.id} task={task} now={now} onDetails={() => showDetails(task.id)}>
                      <Button size="sm" variant="outline" disabled={pending} onClick={() => run(() => retryProduction(task.id))}>
                        <RefreshCw />
                        Relancer
                      </Button>
                      <ConfirmButton size="sm" variant="ghost" disabled={pending} onConfirm={() => run(() => removeProduction(task.id))} confirmLabel="Confirmer la suppression">
                        <Trash2 />
                        Supprimer
                      </ConfirmButton>
                    </TaskCard>
                  ))}
                  {board.failed_jobs.map((job) => (
                    <JobRow key={job.id} job={job} now={now}>
                      <Button size="sm" variant="outline" disabled={pending} onClick={() => run(() => retryJob(job.id))}>
                        <RefreshCw />
                        Relancer
                      </Button>
                      <Button size="sm" variant="ghost" disabled={pending} onClick={() => run(() => dismissJob(job.id))}>
                        <EyeOff />
                        Masquer
                      </Button>
                    </JobRow>
                  ))}
                </Section>
              ) : null}

              {board.stopped.length > 0 ? (
                <Section title="Arrêtées (14 derniers jours)" count={board.stopped.length}>
                  {board.stopped.map((task) => (
                    <TaskCard key={task.id} task={task} now={now} onDetails={() => showDetails(task.id)}>
                      <Button size="sm" variant="outline" disabled={pending} onClick={() => run(() => resumeProduction(task.id))}>
                        <Play />
                        Reprendre
                      </Button>
                      <ConfirmButton size="sm" variant="ghost" disabled={pending} onConfirm={() => run(() => removeProduction(task.id))} confirmLabel="Confirmer la suppression">
                        <Trash2 />
                        Supprimer
                      </ConfirmButton>
                    </TaskCard>
                  ))}
                </Section>
              ) : null}

              {nothing ? (
                <div className="text-muted-foreground flex flex-col items-center gap-3 rounded-xl border border-dashed p-8 text-center text-sm">
                  <ListChecks className="size-6" />
                  <p>Aucune tâche. Les vidéos que tu lances depuis Création apparaîtront ici, étape par étape.</p>
                  <Button size="sm" variant="outline" asChild onClick={() => setOpen(false)}>
                    <Link href="/create">Aller à Création</Link>
                  </Button>
                </div>
              ) : null}
            </div>
          </ScrollArea>
        </SheetContent>
      </Sheet>

      <ProductionSheet card={detail} onClose={() => setDetail(null)} />
    </>
  );
}

/** Ouvre le panneau des tâches depuis une page (Vue d'ensemble…). */
export function OpenTasksButton({ children, ...props }: React.ComponentProps<typeof Button>) {
  return (
    <Button {...props} onClick={() => window.dispatchEvent(new Event(OPEN_TASKS_EVENT))}>
      {children}
    </Button>
  );
}
