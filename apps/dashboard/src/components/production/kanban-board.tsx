"use client";

import * as React from "react";
import { CircleCheck, RefreshCw, TriangleAlert } from "lucide-react";

import { ChannelBadge } from "@/components/channel-badge";
import { FormatBadge } from "@/components/format-badge";
import { ProductionSheet } from "@/components/production/production-sheet";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useRealtimeJobs } from "@/hooks/use-realtime-jobs";
import { formatMinutes, formatPercent, formatRelative } from "@/lib/format";
import type { ChannelLang, ProductionCard } from "@/lib/types";
import { cn } from "@/lib/utils";

type ColumnId = "script" | "clips" | "assembly" | "review" | "ready" | "failed";

const COLUMNS: { id: ColumnId; title: string; accent: string }[] = [
  { id: "script", title: "Script", accent: "bg-zinc-400" },
  { id: "clips", title: "Génération des clips", accent: "bg-violet-500" },
  { id: "assembly", title: "Assemblage", accent: "bg-sky-500" },
  { id: "review", title: "Contrôle / revue", accent: "bg-amber-500" },
  { id: "ready", title: "Prête", accent: "bg-emerald-500" },
  { id: "failed", title: "En échec", accent: "bg-red-500" },
];

export function columnOf(card: ProductionCard): ColumnId {
  const status = card.production.status;
  if (status === "failed") return "failed";
  if (status === "draft" || status === "scripting") return "script";
  if (status === "generating") return "clips";
  if (status === "assembling") {
    const inReview = card.videos.length > 0 && card.videos.every((v) => v.status === "qa" || v.status === "review");
    return inReview ? "review" : "assembly";
  }
  return "ready";
}

function KanbanCard({
  card,
  retried,
  onOpen,
  onRetry,
}: {
  card: ProductionCard;
  retried: boolean;
  onOpen: (card: ProductionCard) => void;
  onRetry: (id: string) => void;
}) {
  const failed = card.production.status === "failed";
  const failedVideos = card.videos.filter((v) => v.status === "failed");
  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => onOpen(card)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(card);
        }
      }}
      className={cn(
        "hover:bg-accent/40 focus-visible:ring-ring/50 cursor-pointer gap-3 py-4 transition-colors outline-none focus-visible:ring-[3px]",
        failed && "border-destructive/40"
      )}
    >
      <CardHeader className="px-4">
        <CardTitle className="line-clamp-2 text-sm leading-snug">{card.concept?.title ?? "Production sans concept"}</CardTitle>
        {card.concept?.hook ? <CardDescription className="line-clamp-1">{card.concept.hook}</CardDescription> : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3 px-4">
        <div className="flex flex-wrap items-center gap-1.5">
          {card.videos.map((video) => (
            <ChannelBadge
              key={video.id}
              lang={video.lang as ChannelLang}
              className={cn(video.status === "failed" && "border-red-500/60 text-red-600 dark:text-red-400")}
            />
          ))}
          <FormatBadge format={card.production.format} />
        </div>

        {failed ? (
          <div className="border-destructive/40 bg-destructive/10 text-destructive flex gap-2 rounded-md border p-2 text-xs">
            <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
            <span className="line-clamp-3">{card.production.error ?? "Erreur inconnue"}</span>
          </div>
        ) : (
          <>
            <Progress value={card.progress_pct} aria-label={`Progression ${card.progress_pct} %`} />
            <div className="text-muted-foreground flex items-center justify-between gap-2 text-xs">
              <span className="truncate">{card.current_step ?? "—"}</span>
              <span className="shrink-0 tabular-nums">
                {formatPercent(card.progress_pct)}
                {card.eta_minutes != null ? ` · ETA ${formatMinutes(card.eta_minutes)}` : ""}
              </span>
            </div>
          </>
        )}

        {failedVideos.length > 0 && !failed ? (
          <p className="text-destructive text-xs">
            {failedVideos.map((v) => `${v.lang.toUpperCase()} : ${v.error ?? "échec"}`).join(" · ")}
          </p>
        ) : null}

        {failed || failedVideos.length > 0 ? (
          retried ? (
            <p className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400" role="status">
              <CircleCheck className="size-3.5" />
              Relance envoyée (mock)
            </p>
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="w-fit"
              onClick={(event) => {
                event.stopPropagation();
                onRetry(card.production.id);
              }}
            >
              <RefreshCw />
              Relancer
            </Button>
          )
        ) : null}

        <p className="text-muted-foreground text-[11px]">Mis à jour {formatRelative(card.production.updated_at)}</p>
      </CardContent>
    </Card>
  );
}

export function KanbanBoard({ initial, channel }: { initial: ProductionCard[]; channel?: ChannelLang }) {
  const cards = useRealtimeJobs(initial);
  const [selected, setSelected] = React.useState<ProductionCard | null>(null);
  const [retried, setRetried] = React.useState<Record<string, boolean>>({});

  const visible = channel ? cards.filter((card) => card.videos.some((v) => v.lang === channel)) : cards;
  const grouped = new Map<ColumnId, ProductionCard[]>(COLUMNS.map((c) => [c.id, []]));
  for (const card of visible) grouped.get(columnOf(card))!.push(card);

  return (
    <>
      <div className="-mx-4 overflow-x-auto px-4 pb-2 md:mx-0 md:px-0">
        <div className="flex min-w-max gap-4">
          {COLUMNS.map((column) => {
            const items = grouped.get(column.id) ?? [];
            return (
              <section key={column.id} aria-label={column.title} className="bg-muted/40 flex w-[300px] shrink-0 flex-col gap-3 rounded-xl border p-3">
                <header className="flex items-center gap-2 px-1">
                  <span className={cn("size-2 rounded-full", column.accent)} aria-hidden />
                  <h3 className="text-sm font-semibold">{column.title}</h3>
                  <span className="text-muted-foreground ml-auto text-xs tabular-nums">{items.length}</span>
                </header>
                <div className="flex flex-col gap-3">
                  {items.map((card) => (
                    <KanbanCard
                      key={card.production.id}
                      card={card}
                      retried={Boolean(retried[card.production.id])}
                      onOpen={setSelected}
                      onRetry={(id) => setRetried((prev) => ({ ...prev, [id]: true }))}
                    />
                  ))}
                  {items.length === 0 ? (
                    <p className="text-muted-foreground rounded-lg border border-dashed p-4 text-center text-xs">Aucune production</p>
                  ) : null}
                </div>
              </section>
            );
          })}
        </div>
      </div>
      <ProductionSheet card={selected} onClose={() => setSelected(null)} />
    </>
  );
}
