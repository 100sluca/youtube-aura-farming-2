"use client";

import { Bar, BarChart, CartesianGrid, Cell, XAxis, YAxis } from "recharts";

import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { formatCompact, formatDate, formatNumber } from "@/lib/format";
import type { DayViews } from "@/lib/views-series";

const config = {
  views: { label: "Vues", theme: { light: "#2a78d6", dark: "#3987e5" } },
} satisfies ChartConfig;

const SOURCE_LABELS: Record<DayViews["source"], string> = {
  analytics: "YouTube Analytics",
  estimate: "estimé d’après les compteurs",
  unknown: "pas encore connu",
};

/** `day` est une clé « YYYY-MM-DD » ; midi UTC tombe le même jour à Paris. */
const dayToDate = (day: unknown) => `${String(day)}T12:00:00Z`;

/** Vues par jour : YouTube Analytics (plein), estimations d'après les relevés horaires (clair), jours inconnus (vides).
 * Onglet TikTok (docs/39) : pas d'équivalent d'Analytics, toutes les barres viennent des relevés horaires. */
export function DailyViewsChart({ data, platform = "youtube" }: { data: DayViews[]; platform?: "youtube" | "tiktok" }) {
  const points = data.map((d) => ({ ...d, value: d.views ?? 0 }));
  const tiktok = platform === "tiktok";
  if (!points.some((p) => p.value > 0)) {
    return (
      <div className="text-muted-foreground flex h-[240px] flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 text-center text-sm">
        {points.some((p) => p.source === "unknown") ? (
          <>
            <p className="text-foreground font-medium">Pas encore de vues datées jour par jour</p>
            <p>
              {tiktok
                ? "Les vues de chaque jour se déduisent des relevés faits chaque heure : les premières barres arrivent le lendemain de la première vidéo sortie."
                : "YouTube Analytics les publie avec 2 à 3 jours de retard, et les relevés horaires des compteurs viennent de commencer : les premières barres (estimées) arrivent demain, puis Analytics les confirme."}
            </p>
          </>
        ) : (
          <p>Aucune vue sur la période.</p>
        )}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <ChartContainer config={config} className="aspect-auto h-[240px] w-full">
        <BarChart data={points} margin={{ top: 8, right: 4, left: 0, bottom: 0 }} barCategoryGap={2}>
          <CartesianGrid vertical={false} />
          <XAxis
            dataKey="day"
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            minTickGap={28}
            tickFormatter={(value) => formatDate(dayToDate(value), "d MMM")}
          />
          <YAxis tickLine={false} axisLine={false} width={44} allowDecimals={false} tickFormatter={(value) => formatCompact(Number(value))} />
          <ChartTooltip
            cursor={{ fill: "var(--muted)", opacity: 0.4 }}
            content={
              <ChartTooltipContent
                labelFormatter={(label) => formatDate(dayToDate(label), "EEEE d MMMM")}
                formatter={(_value, _name, item) => {
                  const p = item.payload as DayViews;
                  return (
                    <div className="flex w-full flex-col gap-0.5">
                      <div className="flex items-center gap-4">
                        <span className="text-muted-foreground">Vues</span>
                        <span className="text-foreground ml-auto font-mono font-medium tabular-nums">{p.views === null ? "—" : formatNumber(p.views)}</span>
                      </div>
                      <span className="text-muted-foreground text-[11px]">{tiktok && p.source === "estimate" ? "d’après les relevés horaires" : SOURCE_LABELS[p.source]}</span>
                    </div>
                  );
                }}
              />
            }
          />
          <Bar dataKey="value" fill="var(--color-views)" radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {points.map((p) => (
              <Cell key={p.day} fillOpacity={p.source === "estimate" && !tiktok ? 0.45 : 1} />
            ))}
          </Bar>
        </BarChart>
      </ChartContainer>
      {tiktok ? null : (
        <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-[2px] bg-[#2a78d6] dark:bg-[#3987e5]" />
            YouTube Analytics
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-[2px] bg-[#2a78d6]/45 dark:bg-[#3987e5]/45" />
            Estimé d’après les compteurs (relevés chaque heure)
          </span>
        </div>
      )}
    </div>
  );
}
