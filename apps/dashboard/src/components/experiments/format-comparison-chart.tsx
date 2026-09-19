"use client";

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import type { FormatSummary } from "@/lib/data/contract";
import { formatCompact, formatNumber, formatPercent } from "@/lib/format";

const config = {
  A_voiceover: { label: "Format A · voix off", color: "var(--chart-1)" },
  B_visual: { label: "Format B · visuel", color: "var(--chart-2)" },
} satisfies ChartConfig;

type MetricKey = "avg_view_pct" | "views_per_video" | "subs_per_1k_views";

const METRICS: { key: MetricKey; label: string; format: (value: number) => string }[] = [
  { key: "avg_view_pct", label: "Rétention moyenne", format: (v) => formatPercent(v, 1) },
  { key: "views_per_video", label: "Vues / vidéo", format: (v) => formatCompact(v) },
  { key: "subs_per_1k_views", label: "Abonnés / 1 000 vues", format: (v) => formatNumber(v, 2) },
];

/** Les trois métriques ont des échelles différentes : chaque barre est indexée sur le meilleur format (= 100). */
export function FormatComparisonChart({ byFormat }: { byFormat: FormatSummary[] }) {
  const a = byFormat.find((f) => f.format === "A_voiceover");
  const b = byFormat.find((f) => f.format === "B_visual");
  const data = METRICS.map((metric) => {
    const va = a?.[metric.key] ?? 0;
    const vb = b?.[metric.key] ?? 0;
    const max = Math.max(va, vb, Number.EPSILON);
    return {
      metric: metric.label,
      A_voiceover: Math.round((va / max) * 100),
      B_visual: Math.round((vb / max) * 100),
      rawA: metric.format(va),
      rawB: metric.format(vb),
    };
  });

  return (
    <ChartContainer config={config} className="aspect-auto h-[260px] w-full">
      <BarChart data={data} margin={{ top: 8, right: 4, left: 0, bottom: 0 }} barGap={6}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="metric" tickLine={false} axisLine={false} tickMargin={8} />
        <YAxis domain={[0, 100]} width={36} tickLine={false} axisLine={false} tickFormatter={(value) => String(value)} />
        <ChartTooltip
          cursor={{ fill: "var(--muted)", opacity: 0.4 }}
          content={
            <ChartTooltipContent
              formatter={(value, name, item) => {
                const raw = name === "A_voiceover" ? item.payload?.rawA : item.payload?.rawB;
                return (
                  <div className="flex w-full items-center gap-2">
                    <span className="size-2.5 shrink-0 rounded-[2px]" style={{ background: item.color }} />
                    <span className="text-muted-foreground">{config[name as keyof typeof config]?.label ?? String(name)}</span>
                    <span className="ml-auto font-mono font-medium tabular-nums">
                      {String(raw)} <span className="text-muted-foreground">(indice {String(value)})</span>
                    </span>
                  </div>
                );
              }}
            />
          }
        />
        <ChartLegend content={<ChartLegendContent />} />
        <Bar dataKey="A_voiceover" fill="var(--color-A_voiceover)" radius={[4, 4, 0, 0]} />
        <Bar dataKey="B_visual" fill="var(--color-B_visual)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ChartContainer>
  );
}
