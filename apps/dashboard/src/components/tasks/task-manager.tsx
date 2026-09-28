"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CircleCheck,
  CircleX,
  Clapperboard,
  EyeOff,
  ListChecks,
  LoaderCircle,
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
  removeProduction,
  resumeProduction,
  retryJob,
  stopProduction,
} from "@/app/tasks/actions";
import { ConfirmButton } from "@/components/confirm-button";
import { ProductionSheet } from "@/components/production/production-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

/** « vers 18:40 » aujourd'hui, sinon « ven. 26 sept., 04:10 ». */
function etaLabel(eta: string, now: string): string {
  return parisDayKey(eta) === parisDayKey(now) ? `vers ${formatTime(eta)}` : formatDate(eta, "EEE d MMM, HH:mm");
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

function TaskCard({
  task,
  now,
  onDetails,
  children,
}: {
  task: TaskProduction;
  now: string;
  onDetails: () => void;
  children?: React.ReactNode;
}) {
  const ended = task.status === "failed" || task.status === "cancelled";
  const meta = [task.channel_name, task.series_name].filter(Boolean).join(" · ");
  return (
    <li className={cn("flex gap-3 rounded-lg border p-3", task.status === "failed" && "border-destructive/40")}>
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
          ) : null}
        </div>
        {meta ? <p className="text-muted-foreground truncate text-xs">{meta}</p> : null}
        <p className="flex items-center gap-1.5 text-xs font-medium">
          {task.running ? <LoaderCircle className="size-3.5 shrink-0 animate-spin text-violet-500" /> : null}
          {task.stage}
        </p>
        {!ended ? <Progress value={task.progress_pct} className="h-1.5" aria-label={`Avancement ${task.progress_pct} %`} /> : null}
        {!ended && (task.step_started_at || task.eta_at) ? (
          <p className="text-muted-foreground text-[11px] tabular-nums">
            {task.step_started_at ? `Étape commencée ${formatRelative(task.step_started_at, new Date(now))}` : null}
            {task.step_started_at && task.eta_at ? " · " : null}
            {task.eta_at ? `prête ${etaLabel(task.eta_at, now)} (estimation)` : null}
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

function Section({ title, count, children, tone }: { title: string; count: number; children: React.ReactNode; tone?: "danger" | "warning" }) {
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
      <ul className="flex flex-col gap-2">{children}</ul>
    </section>
  );
}

/** Bouton « Tâches » de l'en-tête et panneau de droite : ce qui se fabrique, dans l'ordre, et les gestes d'arrêt. */
export function TaskManager() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [board, setBoard] = React.useState<TaskBoard>(EMPTY_TASK_BOARD);
  const [notice, setNotice] = React.useState<Notice | null>(null);
  const [detail, setDetail] = React.useState<ProductionCard | null>(null);
  const [pending, startTransition] = React.useTransition();

  // Rafraîchissement : toutes les 3 s panneau ouvert, toutes les 15 s sinon (pastille du bouton), onglet visible seulement
  React.useEffect(() => {
    let alive = true;
    const tick = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const next = await fetchTaskBoard();
        if (alive) setBoard(next);
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

  const run = (fn: () => Promise<Notice>) =>
    startTransition(async () => {
      const res = await fn();
      setNotice(res);
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
  const inFlight = board.running.length + board.queued.length;
  const nothing =
    inFlight + board.waiting.length + board.review_videos + board.failed.length + board.stopped.length + board.other_jobs.length + board.failed_jobs.length ===
    0;

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
            </SheetDescription>
            {notice ? (
              <p className={cn("flex items-center gap-1.5 text-xs", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")} role="status">
                {notice.ok ? <CircleCheck className="size-3.5" /> : <CircleX className="size-3.5" />}
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
                      <ConfirmButton size="sm" variant="outline" disabled={pending} onConfirm={() => run(() => stopProduction(task.id))} confirmLabel="Confirmer l’arrêt">
                        <Square />
                        Arrêter
                      </ConfirmButton>
                    </TaskCard>
                  ))}
                </Section>
              ) : null}

              {board.queued.length > 0 ? (
                <Section title="En file d’attente" count={board.queued.length}>
                  {board.queued.map((task) => (
                    <TaskCard key={task.id} task={task} now={now} onDetails={() => showDetails(task.id)}>
                      <ConfirmButton size="sm" variant="ghost" disabled={pending} onConfirm={() => run(() => stopProduction(task.id))} confirmLabel="Confirmer l’arrêt">
                        <Square />
                        Arrêter
                      </ConfirmButton>
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
