"use client";

import { Terminal } from "lucide-react";

import { ChannelBadge } from "@/components/channel-badge";
import { FormatBadge } from "@/components/format-badge";
import { JobStatusBadge, ProductionStatusBadge, VideoStatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { formatDateTime, formatPercent, formatRelative, formatTime } from "@/lib/format";
import { JOB_TYPE_LABELS, categoryMeta } from "@/lib/labels";
import type { ProductionCard } from "@/lib/types";

export function ProductionSheet({ card, onClose }: { card: ProductionCard | null; onClose: () => void }) {
  return (
    <Sheet
      open={card !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-xl">
        {card ? (
          <>
            <SheetHeader className="border-b pr-12">
              <SheetTitle className="leading-snug">{card.concept?.title ?? "Production"}</SheetTitle>
              <SheetDescription>
                Créée {formatRelative(card.production.created_at)} · mise à jour {formatRelative(card.production.updated_at)}
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
                {card.production.video_provider ? <Badge variant="secondary">{card.production.video_provider}</Badge> : null}
              </div>
              {card.production.status !== "failed" ? (
                <div className="flex flex-col gap-1.5 pt-1">
                  <Progress value={card.progress_pct} aria-label="Progression" />
                  <p className="text-muted-foreground text-xs">
                    {card.current_step ?? "—"} · {formatPercent(card.progress_pct)}
                  </p>
                </div>
              ) : (
                <p className="text-destructive text-sm">{card.production.error}</p>
              )}
            </SheetHeader>

            <ScrollArea className="min-h-0 flex-1">
              <div className="flex flex-col gap-6 p-4">
                <section className="flex flex-col gap-2">
                  <h3 className="text-sm font-semibold">Vidéos</h3>
                  <ul className="flex flex-col gap-2">
                    {card.videos.map((video) => (
                      <li key={video.id} className="flex flex-col gap-1 rounded-lg border p-3 text-sm">
                        <div className="flex items-center gap-2">
                          <ChannelBadge lang={video.lang} />
                          <span className="min-w-0 flex-1 truncate">{video.title ?? "Sans titre"}</span>
                          <VideoStatusBadge status={video.status} />
                        </div>
                        <p className="text-muted-foreground text-xs">
                          {video.scheduled_at ? `Créneau : ${formatDateTime(video.scheduled_at)}` : "Aucun créneau assigné"}
                          {video.youtube_video_id ? ` · YouTube ${video.youtube_video_id}` : ""}
                        </p>
                        {video.error ? <p className="text-destructive text-xs">{video.error}</p> : null}
                      </li>
                    ))}
                  </ul>
                </section>

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
                            <span className="text-sm font-medium">{JOB_TYPE_LABELS[job.type]}</span>
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

                <Separator />

                <section className="flex flex-col gap-2">
                  <h3 className="text-sm font-semibold">Journal</h3>
                  <div className="bg-muted/40 text-muted-foreground flex items-center gap-3 rounded-lg border border-dashed p-4 text-sm">
                    <Terminal className="size-4 shrink-0" />
                    <p>Le journal du worker s’affichera ici en temps réel (Supabase Realtime, table « jobs »).</p>
                  </div>
                </section>
              </div>
            </ScrollArea>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
