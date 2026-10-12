/** Petits éléments communs aux onglets : logos des réseaux, carte chiffre, ligne de réseau, mini-courbe. */
import type { ReactNode } from "react";
import { Area, AreaChart } from "recharts";

import { Badge } from "@/components/ui/badge";
import { Card, CardAction, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, type ChartConfig } from "@/components/ui/chart";
import { Progress } from "@/components/ui/progress";
import { isNum } from "@/lib/format";
import { PLATFORM_LABEL, type Platform } from "@/lib/snapshot";
import { cn } from "@/lib/utils";

const PATHS: Record<Platform, ReactNode> = {
  youtube: (
    <path
      fill="currentColor"
      d="M21.6 7.2a2.5 2.5 0 0 0-1.8-1.8C18.2 5 12 5 12 5s-6.2 0-7.8.4A2.5 2.5 0 0 0 2.4 7.2 26 26 0 0 0 2 12a26 26 0 0 0 .4 4.8 2.5 2.5 0 0 0 1.8 1.8c1.6.4 7.8.4 7.8.4s6.2 0 7.8-.4a2.5 2.5 0 0 0 1.8-1.8A26 26 0 0 0 22 12a26 26 0 0 0-.4-4.8zM10 15V9l5.2 3z"
    />
  ),
  tiktok: (
    <path
      fill="currentColor"
      d="M16.6 3h-3.3v12.4a2.7 2.7 0 1 1-2.7-2.7c.3 0 .5 0 .8.1V9.4l-.8-.1a6 6 0 1 0 6 6V9.2a7.7 7.7 0 0 0 4.4 1.4V7.3A4.4 4.4 0 0 1 16.6 3z"
    />
  ),
  instagram: (
    <g fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="18" height="18" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none" />
    </g>
  ),
};

const COLOR: Record<Platform, string> = { youtube: "text-youtube", tiktok: "text-tiktok", instagram: "text-instagram" };

export function PlatformIcon({ platform, className }: { platform: Platform; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-label={PLATFORM_LABEL[platform]} className={cn("size-4 shrink-0", COLOR[platform], className)}>
      {PATHS[platform]}
    </svg>
  );
}

export function PlatformDot({ platform }: { platform: Platform }) {
  return <span className={cn("inline-block size-2 shrink-0 rounded-full", { youtube: "bg-youtube", tiktok: "bg-tiktok", instagram: "bg-instagram" }[platform])} />;
}

/** Carte chiffre, façon « section cards » du tableau de bord shadcn. */
export function StatCard({ label, value, unit, badge, footer, hint }: { label: string; value: string; unit?: string; badge?: ReactNode; footer?: ReactNode; hint?: ReactNode }) {
  return (
    <Card className="gap-3 py-4">
      <CardHeader className="px-4">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl font-semibold tabular-nums">
          {value}
          {unit ? <span className="text-muted-foreground ml-1 text-base font-normal">{unit}</span> : null}
        </CardTitle>
        {badge ? <CardAction>{badge}</CardAction> : null}
      </CardHeader>
      {footer || hint ? (
        <CardFooter className="flex-col items-start gap-0.5 px-4 text-sm">
          {footer ? <div className="font-medium">{footer}</div> : null}
          {hint ? <div className="text-muted-foreground text-xs">{hint}</div> : null}
        </CardFooter>
      ) : null}
    </Card>
  );
}

/** Évolution par rapport à la période d'avant : +12 %, ou ×8 au-delà du triple. */
export function TrendBadge({ now, before }: { now: number | null | undefined; before: number | null | undefined }) {
  if (!isNum(now) || !isNum(before) || before <= 0) return null;
  const ratio = now / before;
  const d = (ratio - 1) * 100;
  const text = ratio >= 3 ? `×${Math.round(ratio)}` : `${d > 0 ? "+" : d < 0 ? "−" : "±"}${Math.abs(Math.round(d))} %`;
  return (
    <Badge variant="outline" className={cn(d > 0.5 ? "text-success" : d < -0.5 ? "text-destructive" : "text-muted-foreground")}>
      {text}
    </Badge>
  );
}

/** Jauge : valeur, objectif, part atteinte. */
export function Meter({ label, value, target, format, note, accent = false }: { label: string; value: number | null | undefined; target: number; format: (n: number) => string; note?: string; accent?: boolean }) {
  const p = isNum(value) && target > 0 ? Math.min(100, (value / target) * 100) : 0;
  return (
    <div className="grid gap-2">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span>{label}</span>
        <span className="tabular-nums">
          <span className="font-medium">{isNum(value) ? format(value) : "—"}</span>
          <span className="text-muted-foreground"> / {format(target)}</span>
        </span>
      </div>
      <Progress value={Math.max(p, p > 0 ? 1 : 0)} className={cn(accent && "[&>[data-slot=progress-indicator]]:bg-signal")} />
      <div className="text-muted-foreground text-xs">{note ?? (p > 0 && p < 0.1 ? "moins de 0,1 %" : `${p.toFixed(p < 10 ? 1 : 0).replace(".", ",")} %`)}</div>
    </div>
  );
}

/** Mini-courbe sans axe (comptes, niches). */
export function Sparkline({ values, color, className }: { values: (number | null)[]; color: string; className?: string }) {
  const data = values.map((v, i) => ({ i, v: isNum(v) ? v : null }));
  if (data.filter((d) => d.v !== null).length < 2) return <div className={cn("h-10", className)} />;
  const config = { v: { label: "Vues", color } } satisfies ChartConfig;
  // overflow-hidden : dans une grille, le graphique ne doit pas imposer sa largeur mesurée (sinon la page déborde)
  return (
    <div className="w-full min-w-0 overflow-hidden">
      <ChartContainer config={config} className={cn("aspect-auto h-10 w-full", className)}>
        <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <Area dataKey="v" type="monotone" stroke="var(--color-v)" fill="var(--color-v)" fillOpacity={0.15} strokeWidth={1.5} connectNulls isAnimationActive={false} />
        </AreaChart>
      </ChartContainer>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-muted-foreground py-2 text-sm">{children}</p>;
}
