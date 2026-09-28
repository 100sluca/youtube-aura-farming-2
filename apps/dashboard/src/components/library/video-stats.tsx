"use client";

import { Brain, ThumbsDown, ThumbsUp } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";

import { ToneBadge } from "@/components/status-badge";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Skeleton } from "@/components/ui/skeleton";
import type { VideoDetail } from "@/lib/data/contract";
import { formatDate, formatDateTime, formatNumber, formatPercent, formatRelative, formatSigned } from "@/lib/format";
import { VERDICT_LABELS, type VideoInsight } from "@/lib/stats-types";
import type { VideoOverview } from "@/lib/types";

const retentionConfig = {
  w: { label: "Audience", color: "var(--chart-1)" },
} satisfies ChartConfig;

const dailyConfig = {
  views: { label: "Vues", color: "var(--chart-2)" },
} satisfies ChartConfig;

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-muted/40 flex flex-col gap-1 rounded-lg border p-3">
      <span className="text-muted-foreground text-xs">{label}</span>
      <span className="text-lg font-semibold tabular-nums">{value}</span>
    </div>
  );
}

const INSIGHT_TONES = { top: "success", moyen: "neutral", flop: "danger", "trop récente": "info" } as const;

/** Avis de l'agent analyste sur la vidéo (dernier rapport qui en parle, docs/25). */
function InsightBlock({ insight }: { insight: VideoInsight }) {
  return (
    <section className="flex flex-col gap-2 rounded-lg border border-violet-500/30 bg-violet-500/5 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Brain className="size-4 text-violet-600 dark:text-violet-300" />
        <h3 className="text-sm font-semibold">L’avis de l’agent analyste</h3>
        <ToneBadge tone={INSIGHT_TONES[insight.verdict]}>
          {VERDICT_LABELS[insight.verdict]}
          {insight.score !== null && insight.verdict !== "trop récente" ? ` ×${formatNumber(insight.score, insight.score >= 10 ? 0 : 2)}` : ""}
        </ToneBadge>
        <span className="text-muted-foreground ml-auto text-xs">{formatDateTime(insight.report_at)}</span>
      </div>
      <p className="text-sm">{insight.why}</p>
      {insight.worked.map((w) => (
        <p key={w} className="flex gap-1.5 text-xs">
          <ThumbsUp className="mt-0.5 size-3 shrink-0 text-emerald-600 dark:text-emerald-400" />
          {w}
        </p>
      ))}
      {insight.missed.map((m) => (
        <p key={m} className="flex gap-1.5 text-xs">
          <ThumbsDown className="mt-0.5 size-3 shrink-0 text-red-600 dark:text-red-400" />
          {m}
        </p>
      ))}
    </section>
  );
}

/** Statistiques YouTube d'une vidéo : totaux, avis de l'agent analyste, courbe de rétention, vues par jour, commentaires. */
export function VideoStats({
  video,
  detail,
  insight,
  loading,
}: {
  video: VideoOverview;
  detail: VideoDetail | null;
  insight?: VideoInsight | null;
  loading: boolean;
}) {
  const retentionPoints = detail?.retention.map((p) => ({ t: Math.round(p.t * 100), w: Math.round(p.w * 1000) / 10 })) ?? [];
  const subs = video.subscribers_gained === null ? null : (video.subscribers_gained ?? 0) - (video.subscribers_lost ?? 0);
  const analyticsPending = video.average_view_pct === null && video.shares === null;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Vues" value={formatNumber(video.views)} />
          <StatTile label="J’aime" value={formatNumber(video.likes)} />
          <StatTile label="Commentaires" value={formatNumber(video.comments)} />
          <StatTile label="Partages" value={formatNumber(video.shares)} />
          <StatTile label="Rétention" value={formatPercent(video.average_view_pct, 1)} />
          <StatTile label="Encore là à 3 s" value={formatPercent(video.hook_retention_pct)} />
          <StatTile label="Durée regardée" value={video.average_view_duration_s == null ? "—" : `${formatNumber(video.average_view_duration_s, 1)} s`} />
          <StatTile label="Abonnés gagnés" value={subs === null ? "—" : formatSigned(subs)} />
        </div>
        {analyticsPending ? (
          <p className="text-muted-foreground text-xs">Rétention, accroche, durée regardée, partages et abonnés : YouTube Analytics les publie 2 à 3 jours après la mise en ligne.</p>
        ) : null}
      </div>

      {insight ? <InsightBlock insight={insight} /> : null}

      {loading || !detail ? (
        <div className="flex flex-col gap-4" aria-busy>
          <Skeleton className="h-[200px] w-full" />
          <Skeleton className="h-[180px] w-full" />
        </div>
      ) : (
        <>
          {retentionPoints.length > 0 ? (
            <section className="flex flex-col gap-3">
              <div>
                <h3 className="text-sm font-semibold">Courbe de rétention</h3>
                <p className="text-muted-foreground text-xs">Part de l’audience encore présente selon l’avancement de la vidéo.</p>
              </div>
              <ChartContainer config={retentionConfig} className="aspect-auto h-[200px] w-full">
                <LineChart data={retentionPoints} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} />
                  <XAxis
                    dataKey="t"
                    type="number"
                    domain={[0, 100]}
                    ticks={[0, 25, 50, 75, 100]}
                    tickFormatter={(value) => `${value} %`}
                    tickLine={false}
                    axisLine={false}
                    tickMargin={8}
                  />
                  {/* au-delà de 100 % : revisionnages (un Short tourne en boucle) */}
                  <YAxis domain={[0, (max: number) => Math.max(100, Math.ceil(max / 20) * 20)]} width={44} tickFormatter={(value) => `${value} %`} tickLine={false} axisLine={false} />
                  <ChartTooltip
                    content={
                      <ChartTooltipContent
                        labelFormatter={(label) => `À ${String(label)} % de la vidéo`}
                        formatter={(value) => (
                          <span className="flex w-full items-center justify-between gap-4">
                            <span className="text-muted-foreground">Audience</span>
                            <span className="font-mono font-medium tabular-nums">{formatPercent(Number(value), 1)}</span>
                          </span>
                        )}
                      />
                    }
                  />
                  <Line dataKey="w" type="monotone" stroke="var(--color-w)" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ChartContainer>
            </section>
          ) : null}

          {detail.daily.length > 0 ? (
            <section className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Vues par jour (14 j)</h3>
              <ChartContainer config={dailyConfig} className="aspect-auto h-[180px] w-full">
                <BarChart data={detail.daily} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} />
                  <XAxis
                    dataKey="day"
                    tickLine={false}
                    axisLine={false}
                    tickMargin={8}
                    minTickGap={16}
                    tickFormatter={(value) => formatDate(`${String(value)}T12:00:00Z`, "d/M")}
                  />
                  <YAxis width={44} tickLine={false} axisLine={false} tickFormatter={(value) => formatNumber(Number(value))} />
                  <ChartTooltip
                    content={
                      <ChartTooltipContent
                        labelFormatter={(label) => formatDate(`${String(label)}T12:00:00Z`, "EEEE d MMMM")}
                        formatter={(value) => (
                          <span className="flex w-full items-center justify-between gap-4">
                            <span className="text-muted-foreground">Vues</span>
                            <span className="font-mono font-medium tabular-nums">{formatNumber(Number(value))}</span>
                          </span>
                        )}
                      />
                    }
                  />
                  <Bar dataKey="views" fill="var(--color-views)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ChartContainer>
            </section>
          ) : (
            <p className="text-muted-foreground text-xs">Les vues jour par jour arrivent avec YouTube Analytics, 2 à 3 jours après la mise en ligne.</p>
          )}

          {detail.comments.length > 0 ? (
            <section className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Commentaires récents</h3>
              <ul className="flex flex-col gap-3">
                {detail.comments.map((comment) => (
                  <li key={comment.id} className="flex flex-col gap-1 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{comment.author}</span>
                      <span className="text-muted-foreground text-xs">{formatRelative(comment.published_at)}</span>
                      <span className="text-muted-foreground ml-auto inline-flex items-center gap-1 text-xs tabular-nums">
                        <ThumbsUp className="size-3" />
                        {formatNumber(comment.like_count)}
                      </span>
                    </div>
                    <p className="text-muted-foreground">{comment.text}</p>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}
