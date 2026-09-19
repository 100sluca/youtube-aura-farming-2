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
import { formatCompact, formatDate, formatNumber } from "@/lib/format";
import type { ChannelLang, DailyViewsPoint } from "@/lib/types";

const config = {
  fr: { label: "Chaîne FR", color: "var(--chart-1)" },
  en: { label: "Channel EN", color: "var(--chart-2)" },
} satisfies ChartConfig;

/** `day` est une clé « YYYY-MM-DD » ; midi UTC tombe le même jour à Paris. */
const dayToDate = (day: unknown) => `${String(day)}T12:00:00Z`;

export function DailyViewsChart({ data, channel }: { data: DailyViewsPoint[]; channel?: ChannelLang }) {
  const showFr = !channel || channel === "fr";
  const showEn = !channel || channel === "en";
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
                  <span className="text-muted-foreground">{config[name as keyof typeof config]?.label ?? String(name)}</span>
                  <span className="text-foreground ml-auto font-mono font-medium tabular-nums">
                    {formatNumber(Number(value))}
                  </span>
                </div>
              )}
            />
          }
        />
        <ChartLegend content={<ChartLegendContent />} />
        {showFr ? <Bar dataKey="fr" stackId="views" fill="var(--color-fr)" radius={showEn ? [0, 0, 0, 0] : [4, 4, 0, 0]} /> : null}
        {showEn ? <Bar dataKey="en" stackId="views" fill="var(--color-en)" radius={[4, 4, 0, 0]} /> : null}
      </BarChart>
    </ChartContainer>
  );
}
