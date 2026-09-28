"use client";

import { Bar, BarChart, CartesianGrid, Cell, XAxis, YAxis } from "recharts";

import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { channelColor } from "@/lib/channel";
import { formatCompact, formatDate, formatNumber } from "@/lib/format";
import type { DailyViewsPoint } from "@/lib/types";

/** `day` est une clé « YYYY-MM-DD » ; midi UTC tombe le même jour à Paris. */
const dayToDate = (day: unknown) => `${String(day)}T12:00:00Z`;

/** Vues par jour, une barre empilée par chaîne affichée (couleur de la chaîne). Un jour estimé d'après les relevés
 * horaires (`estimated` = 1, YouTube Analytics pas encore publié : docs/25) est plus clair. */
export function DailyViewsChart({ data, channels }: { data: DailyViewsPoint[]; channels: { slug: string; name: string }[] }) {
  const config = Object.fromEntries(channels.map((c) => [c.slug, { label: c.name, color: channelColor(c.slug) }])) satisfies ChartConfig;
  if (!data.some((point) => channels.some((c) => Number(point[c.slug] ?? 0) > 0)) && data.some((point) => point.missing)) {
    return (
      <div className="text-muted-foreground flex h-[260px] flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 text-center text-sm">
        <p className="text-foreground font-medium">Pas encore de vues datées jour par jour</p>
        <p>YouTube Analytics les publie avec 2 à 3 jours de retard ; en attendant, les derniers jours sont estimés d’après les compteurs relevés chaque heure.</p>
      </div>
    );
  }
  return (
    <ChartContainer config={config} className="aspect-auto h-[260px] w-full">
      <BarChart data={data} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis
          dataKey="day"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          minTickGap={28}
          tickFormatter={(value) => formatDate(dayToDate(value), "d MMM")}
        />
        <YAxis tickLine={false} axisLine={false} width={44} tickFormatter={(value) => formatCompact(Number(value))} />
        <ChartTooltip
          cursor={{ fill: "var(--muted)", opacity: 0.4 }}
          content={
            <ChartTooltipContent
              labelFormatter={(label) => formatDate(dayToDate(label), "EEEE d MMMM")}
              formatter={(value, name, item) => (
                <div className="flex w-full items-center gap-2">
                  <span className="size-2.5 shrink-0 rounded-[2px]" style={{ background: item.color }} />
                  <span className="text-muted-foreground">{config[String(name)]?.label ?? String(name)}</span>
                  <span className="text-foreground ml-auto font-mono font-medium tabular-nums">{formatNumber(Number(value))}</span>
                </div>
              )}
            />
          }
        />
        {channels.length > 1 ? <ChartLegend content={<ChartLegendContent />} /> : null}
        {channels.map((c, i) => (
          <Bar key={c.slug} dataKey={c.slug} stackId="views" fill={`var(--color-${c.slug})`} radius={i === channels.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}>
            {data.map((point) => (
              <Cell key={point.day} fillOpacity={point.estimated ? 0.45 : 1} />
            ))}
          </Bar>
        ))}
      </BarChart>
    </ChartContainer>
  );
}
