"use client";

import * as React from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Scatter, ScatterChart, XAxis, YAxis, ZAxis } from "recharts";

import { FORMAT_CHART_CONFIG, FORMAT_DOT, FORMAT_LABELS, FORMAT_ORDER, formatKey, type FormatKey } from "@/components/stats/formats";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatCompact, formatDuration, formatNumber, formatPercent, parisParts } from "@/lib/format";
import type { StatsVideo } from "@/lib/stats-types";
import { cn } from "@/lib/utils";

type View = "ranking" | "scatter";
type Axis = "duration" | "retention" | "hook" | "hour";

const AXES: { id: Axis; label: string; value: (v: StatsVideo) => number | null; format: (n: number) => string }[] = [
  { id: "duration", label: "Durée de la vidéo", value: (v) => v.duration_s, format: (n) => formatDuration(n) },
  { id: "retention", label: "Rétention moyenne", value: (v) => v.average_view_pct ?? null, format: (n) => formatPercent(n) },
  { id: "hook", label: "Encore là à 3 s", value: (v) => v.hook_retention_pct ?? null, format: (n) => formatPercent(n) },
  {
    id: "hour",
    label: "Heure de publication",
    value: (v) => {
      if (!v.published_at) return null;
      const p = parisParts(v.published_at);
      return p.hour + p.minute / 60;
    },
    format: (n) => `${Math.floor(n)} h${String(Math.round((n % 1) * 60)).padStart(2, "0")}`,
  },
];

const RANKING_MAX = 10;

/** Identifiant de la vidéo sous un clic Recharts (la donnée arrive seule ou sous `payload` selon la forme). */
function clickedId(d: unknown): string | null {
  const item = d as { id?: string; payload?: { id?: string } } | null;
  return item?.payload?.id ?? item?.id ?? null;
}

function short(title: string | null, max = 26): string {
  const t = title ?? "Sans titre";
  return t.length > max ? `${t.slice(0, max - 1)}…` : t;
}

function Legend({ formats }: { formats: FormatKey[] }) {
  return (
    <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
      {formats.map((f) => (
        <span key={f} className="flex items-center gap-1.5">
          <span className={cn("size-2.5 rounded-full", FORMAT_DOT[f])} />
          {FORMAT_LABELS[f]}
        </span>
      ))}
    </div>
  );
}

function VideoTip({ video, extra }: { video: StatsVideo; extra?: string }) {
  return (
    <div className="border-border/50 bg-background grid max-w-64 gap-1 rounded-lg border px-2.5 py-1.5 text-xs shadow-xl">
      <p className="font-medium">{video.title ?? "Sans titre"}</p>
      <p className="text-muted-foreground flex items-center gap-1.5">
        <span className={cn("size-2 rounded-full", FORMAT_DOT[formatKey(video)])} />
        {FORMAT_LABELS[formatKey(video)]}
      </p>
      <p className="tabular-nums">
        {formatNumber(video.views)} vues{extra ? ` · ${extra}` : ""}
      </p>
      <p className="text-muted-foreground">Clique pour ouvrir la fiche</p>
    </div>
  );
}

/** Chaque vidéo : classement par vues, ou nuage vues × une autre mesure. Un clic ouvre la fiche de la vidéo. */
export function VideosChart({ videos, onOpen }: { videos: StatsVideo[]; onOpen: (id: string) => void }) {
  const [view, setView] = React.useState<View>("ranking");
  const [axisId, setAxisId] = React.useState<Axis>("duration");
  const axis = AXES.find((a) => a.id === axisId) ?? AXES[0];
  const present = FORMAT_ORDER.filter((f) => videos.some((v) => formatKey(v) === f));

  const ranking = [...videos]
    .sort((a, b) => b.views - a.views)
    .slice(0, RANKING_MAX)
    .map((v) => ({ id: v.id, label: short(v.title), views: v.views, format: formatKey(v), video: v }));

  const points = videos
    .map((v) => ({ id: v.id, x: axis.value(v), y: Math.max(1, v.views), format: formatKey(v), video: v }))
    .filter((p): p is typeof p & { x: number } => p.x !== null && p.x !== undefined);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="bg-muted inline-flex rounded-lg p-0.5 text-sm" role="tablist" aria-label="Affichage">
          {(
            [
              ["ranking", "Classement"],
              ["scatter", "Nuage"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={view === id}
              onClick={() => setView(id)}
              className={cn(
                "h-7 rounded-md px-3 font-medium transition-colors",
                view === id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        {view === "scatter" ? (
          <Select value={axisId} onValueChange={(v) => setAxisId(v as Axis)}>
            <SelectTrigger size="sm" className="w-48" aria-label="Mesure en abscisse">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {AXES.map((a) => (
                <SelectItem key={a.id} value={a.id}>
                  Vues × {a.label.toLowerCase()}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}
      </div>

      {videos.length === 0 ? (
        <p className="text-muted-foreground flex h-[240px] items-center justify-center text-sm">Aucune vidéo publiée sur la période.</p>
      ) : view === "ranking" ? (
        <ChartContainer config={FORMAT_CHART_CONFIG} className="aspect-auto w-full" style={{ height: Math.max(120, ranking.length * 30 + 16) }}>
          <BarChart data={ranking} layout="vertical" margin={{ top: 0, right: 48, left: 0, bottom: 0 }} barCategoryGap={4}>
            <XAxis type="number" hide domain={[0, "dataMax"]} />
            <YAxis
              type="category"
              dataKey="label"
              width={170}
              tickLine={false}
              axisLine={false}
              interval={0}
              // une ligne par titre (Recharts couperait le texte sur deux lignes)
              tick={({ x, y, payload }) => (
                <text x={x} y={y} dy={4} textAnchor="end" fontSize={11} className="fill-muted-foreground">
                  {String(payload?.value ?? "")}
                </text>
              )}
            />
            <ChartTooltip cursor={{ fill: "var(--muted)", opacity: 0.4 }} content={({ payload }) => (payload?.[0] ? <VideoTip video={(payload[0].payload as { video: StatsVideo }).video} /> : null)} />
            <Bar
              dataKey="views"
              radius={[0, 4, 4, 0]}
              isAnimationActive={false}
              className="cursor-pointer"
              onClick={(d) => {
                const id = clickedId(d);
                if (id) onOpen(id);
              }}
            >
              {ranking.map((r) => (
                <Cell key={r.id} fill={`var(--color-${r.format})`} />
              ))}
              <LabelList dataKey="views" position="right" className="fill-muted-foreground" fontSize={11} formatter={(v: unknown) => formatCompact(Number(v))} />
            </Bar>
          </BarChart>
        </ChartContainer>
      ) : points.length === 0 ? (
        <p className="text-muted-foreground flex h-[240px] items-center justify-center px-6 text-center text-sm">
          Pas encore de {axis.label.toLowerCase()} : YouTube Analytics la publie 2 à 3 jours après la mise en ligne.
        </p>
      ) : (
        <ChartContainer config={FORMAT_CHART_CONFIG} className="aspect-auto h-[260px] w-full">
          <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
            <CartesianGrid />
            <XAxis type="number" dataKey="x" name={axis.label} domain={["auto", "auto"]} tickLine={false} axisLine={false} tickMargin={8} tickFormatter={(n) => axis.format(Number(n))} />
            <YAxis type="number" dataKey="y" name="Vues" scale="log" domain={[1, "auto"]} allowDataOverflow width={44} tickLine={false} axisLine={false} tickFormatter={(n) => formatCompact(Number(n))} />
            <ZAxis range={[90, 90]} />
            <ChartTooltip
              cursor={false}
              content={({ payload }) => {
                const p = payload?.[0]?.payload as { video: StatsVideo; x: number } | undefined;
                return p ? <VideoTip video={p.video} extra={`${axis.label.toLowerCase()} ${axis.format(p.x)}`} /> : null;
              }}
            />
            {present.map((f) => (
              <Scatter
                key={f}
                name={FORMAT_LABELS[f]}
                data={points.filter((p) => p.format === f)}
                fill={`var(--color-${f})`}
                stroke="var(--card)"
                strokeWidth={2}
                isAnimationActive={false}
                className="cursor-pointer"
                onClick={(d) => {
                  const id = clickedId(d);
                  if (id) onOpen(id);
                }}
              />
            ))}
          </ScatterChart>
        </ChartContainer>
      )}
      {videos.length > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Legend formats={present} />
          {view === "ranking" && videos.length > RANKING_MAX ? (
            <span className="text-muted-foreground text-xs">{RANKING_MAX} premières sur {videos.length} : tout est dans le tableau</span>
          ) : null}
          {view === "scatter" ? <span className="text-muted-foreground text-xs">Vues en échelle logarithmique</span> : null}
        </div>
      ) : null}
    </div>
  );
}
