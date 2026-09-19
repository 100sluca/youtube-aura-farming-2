import type { LucideIcon } from "lucide-react";
import { Minus, TrendingDown, TrendingUp } from "lucide-react";

import { Card, CardAction, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface KpiDelta {
  text: string;
  trend: "up" | "down" | "flat";
}

export function KpiCard({
  title,
  value,
  hint,
  delta,
  icon: Icon,
  className,
}: {
  title: string;
  value: string;
  hint?: string;
  delta?: KpiDelta;
  icon?: LucideIcon;
  className?: string;
}) {
  const TrendIcon = delta?.trend === "up" ? TrendingUp : delta?.trend === "down" ? TrendingDown : Minus;
  return (
    <Card className={cn("@container/card gap-4 py-5", className)}>
      <CardHeader className="px-5">
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-2xl font-semibold tabular-nums @[220px]/card:text-3xl">{value}</CardTitle>
        {Icon ? (
          <CardAction>
            <span className="bg-muted text-muted-foreground flex size-8 items-center justify-center rounded-md">
              <Icon className="size-4" />
            </span>
          </CardAction>
        ) : null}
      </CardHeader>
      {delta || hint ? (
        <CardFooter className="flex-col items-start gap-1 px-5 text-sm">
          {delta ? (
            <div
              className={cn(
                "flex items-center gap-1 font-medium",
                delta.trend === "up" && "text-emerald-600 dark:text-emerald-400",
                delta.trend === "down" && "text-red-600 dark:text-red-400",
                delta.trend === "flat" && "text-muted-foreground"
              )}
            >
              <TrendIcon className="size-4" />
              {delta.text}
            </div>
          ) : null}
          {hint ? <div className="text-muted-foreground">{hint}</div> : null}
        </CardFooter>
      ) : null}
    </Card>
  );
}
