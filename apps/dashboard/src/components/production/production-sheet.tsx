"use client";

import * as React from "react";
import { Copy, RefreshCw, TriangleAlert } from "lucide-react";

import { remakeProduction, retryProduction } from "@/app/production/actions";
import { FormatBadge } from "@/components/format-badge";
import { StoryboardPanel } from "@/components/production/storyboard-panel";
import { VideoPanel } from "@/components/production/video-panel";
import { JobStatusBadge, ProductionStatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { formatPercent, formatRelative, formatTime } from "@/lib/format";
import { JOB_TYPE_LABELS, categoryMeta, videoProviderLabel } from "@/lib/labels";
import type { ProductionCard } from "@/lib/types";

export function ProductionSheet({ card, onClose }: { card: ProductionCard | null; onClose: () => void }) {
  const [pending, startTransition] = React.useTransition();
  const [retry, setRetry] = React.useState<string | null>(null);
  const [remake, setRemake] = React.useState<{ ok: boolean; message: string } | null>(null);
  const lang = card?.videos[0]?.lang ?? "fr";
  return (
    <Sheet
      open={card !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-2xl">
        {card ? (
          <>
            <SheetHeader className="border-b pr-12">
              <SheetTitle className="leading-snug">{card.concept?.title ?? "Production"}</SheetTitle>
              <SheetDescription>
                {card.production.channel_name ? `${card.production.channel_name} · ` : ""}
                {card.production.series_name ? `${card.production.series_name} · ` : ""}
                créée {formatRelative(card.production.created_at)} · mise à jour {formatRelative(card.production.updated_at)}
              </SheetDescription>
              <div className="flex flex-wrap gap-1.5">
                <ProductionStatusBadge status={card.production.status} />
                <FormatBadge format={card.production.format} />
                {card.concept?.category ? (
                  <Badge variant="outline">
                    <span aria-hidden>{categoryMeta(card.concept.category).emoji}</span>
                    {categoryMeta(card.concept.category).label}
                  </Badge>
                ) : null}
                {card.production.image_workflow ? <Badge variant="secondary">images : {card.production.image_workflow}</Badge> : null}
                {card.production.video_provider ? (
                  <Badge variant="secondary">vidéo : {videoProviderLabel(card.production.video_provider)}</Badge>
                ) : null}
              </div>
              {card.production.script ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={pending}
                    onClick={() => startTransition(async () => setRemake(await remakeProduction(card.production.id)))}
                  >
                    <Copy />
                    Refaire avec les réglages actuels
                  </Button>
                  {remake ? (
                    <p className={`text-xs ${remake.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`}>{remake.message}</p>
                  ) : null}
                </div>
              ) : null}
              {card.production.status !== "failed" ? (
                <div className="flex flex-col gap-1.5 pt-1">
                  <Progress value={card.progress_pct} aria-label="Progression" />
                  <p className="text-muted-foreground text-xs">
                    {card.current_step ?? "—"} · {formatPercent(card.progress_pct)}
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  <p className="text-destructive text-sm">{card.production.error}</p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-fit"
                    disabled={pending}
                    onClick={() => startTransition(async () => setRetry((await retryProduction(card.production.id)).message))}
                  >
                    <RefreshCw />
                    Relancer les jobs en échec
                  </Button>
                  {retry ? <p className="text-xs text-emerald-600 dark:text-emerald-400">{retry}</p> : null}
                </div>
              )}
            </SheetHeader>

            <ScrollArea className="min-h-0 flex-1">
              <div className="flex flex-col gap-6 p-4">
                <VideoPanel videos={card.videos} />

                {card.storyboard && card.storyboard.length > 0 ? (
                  <>
                    <Separator />
                    <StoryboardPanel productionId={card.production.id} status={card.production.status} scenes={card.storyboard} />
                  </>
                ) : null}

                {card.production.script ? (
                  <>
                    <Separator />
                    <section className="flex flex-col gap-2">
                      <h3 className="text-sm font-semibold">Script ({card.production.script.scenes.length} scènes)</h3>
                      {card.production.lint && card.production.lint.length > 0 ? (
                        <div className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs">
                          <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
                          <ul className="flex flex-col gap-0.5">
                            {card.production.lint.map((issue) => (
                              <li key={issue}>{issue}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      <ol className="flex flex-col gap-1.5 text-sm">
                        {card.production.script.scenes.map((scene, pos) => (
                          <li key={scene.index} className="flex gap-2">
                            <span className="text-muted-foreground w-5 shrink-0 tabular-nums">{pos + 1}.</span>
                            <span>
                              {scene.role ? <span className="text-muted-foreground mr-1 text-xs">[{scene.role}]</span> : null}
                              {scene.narration?.[lang] || scene.on_screen_text?.[lang] || scene.visual_prompt}
                            </span>
                          </li>
                        ))}
                      </ol>
                      {card.production.script.loop_note ? (
                        <p className="text-muted-foreground text-xs">Boucle : {card.production.script.loop_note}</p>
                      ) : null}
                    </section>
                  </>
                ) : null}

                <Separator />

                <section className="flex flex-col gap-2">
                  <h3 className="text-sm font-semibold">Jobs ({card.jobs.length})</h3>
                  {card.jobs.length === 0 ? (
                    <p className="text-muted-foreground text-sm">Aucun job pour l’instant.</p>
                  ) : (
                    <ul className="flex flex-col gap-2">
                      {card.jobs.map((job) => (
                        <li key={job.id} className="flex flex-col gap-2 rounded-lg border p-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-medium">{JOB_TYPE_LABELS[job.type] ?? job.type}</span>
                            {job.progress_label ? <span className="text-muted-foreground text-xs">{job.progress_label}</span> : null}
                            <JobStatusBadge status={job.status} className="ml-auto" />
                          </div>
                          {job.status === "running" ? <Progress value={job.progress} className="h-1.5" aria-label="Progression du job" /> : null}
                          <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs tabular-nums">
                            <span>
                              Tentatives {job.attempts}/{job.max_attempts}
                            </span>
                            <span>Début : {job.started_at ? formatTime(job.started_at) : "—"}</span>
                            <span>Fin : {job.finished_at ? formatTime(job.finished_at) : "—"}</span>
                            {job.locked_by ? <span>Worker : {job.locked_by}</span> : null}
                          </div>
                          {job.error ? <p className="text-destructive text-xs">{job.error}</p> : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </div>
            </ScrollArea>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
