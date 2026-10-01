"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Bot, CircleCheck, CircleX, LoaderCircle, Square } from "lucide-react";

import { startAutopilot, stopAutopilot } from "@/app/create/actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { AutopilotStatus } from "@/lib/autopilot";
import type { Series } from "@/lib/types";
import { cn } from "@/lib/utils";

const TARGETS = [1, 2, 3, 5, 8];

const STAGE: Record<string, string> = {
  draft: "idée choisie",
  scripting: "script",
  generating: "images et clips",
  assembling: "montage",
  storyboard_review: "storyboard",
  ready: "prête",
  failed: "ratée",
  cancelled: "arrêtée",
  archived: "archivée",
};

/**
 * Pilote automatique (docs/46) : un thème, un nombre de vidéos, et le worker fait tout seul, sans validation : meilleure
 * idée, script, personnages, images (4 essais au plus par image pour la continuité), clips, voix, montage.
 */
export function AutopilotCard({
  channelId,
  series,
  defaultSeries,
  status,
}: {
  channelId: string;
  series: Series[];
  defaultSeries: string | null;
  status: AutopilotStatus;
}) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [seriesSlug, setSeriesSlug] = React.useState(status.series ?? defaultSeries ?? "");
  const [target, setTarget] = React.useState(status.target || 3);
  const [notice, setNotice] = React.useState<{ ok: boolean; message: string } | null>(null);
  const running = status.enabled;
  const theme = series.find((s) => s.slug === (running ? status.series : seriesSlug));
  const ready = status.productions.filter((p) => p.status === "ready").length;

  const run = (fn: () => Promise<{ ok: boolean; message: string }>) =>
    startTransition(async () => {
      setNotice(await fn());
      router.refresh();
    });

  return (
    <Card className={cn("py-5", running && "border-emerald-500/50")}>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <Bot className={cn("size-5", running ? "text-emerald-500" : "text-muted-foreground")} />
          <div className="min-w-0 flex-1">
            <p className="font-medium">Pilote automatique</p>
            <p className="text-muted-foreground text-sm">
              {running
                ? `En marche : ${ready}/${status.target} vidéo(s) « ${theme?.name ?? status.series} » prête(s). Aucune validation demandée.`
                : "Tu pars ? Choisis un thème : l’app trouve la meilleure idée, écrit le script, fait les images, les clips, la voix Gemini et le montage, sans rien te demander."}
            </p>
          </div>
          {running ? (
            <Button variant="outline" disabled={pending} onClick={() => run(stopAutopilot)}>
              <Square />
              Arrêter le pilote
            </Button>
          ) : null}
        </div>

        {!running ? (
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-end">
            <Select value={seriesSlug} onValueChange={setSeriesSlug}>
              <SelectTrigger className="w-full" aria-label="Thème du pilote">
                <SelectValue placeholder="Choisir un thème" />
              </SelectTrigger>
              <SelectContent>
                {series.map((s) => (
                  <SelectItem key={s.slug} value={s.slug}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="bg-muted inline-flex rounded-lg p-0.5" role="radiogroup" aria-label="Nombre de vidéos">
              {TARGETS.map((n) => (
                <button
                  key={n}
                  type="button"
                  role="radio"
                  aria-checked={target === n}
                  onClick={() => setTarget(n)}
                  className={cn(
                    "h-8 min-w-10 rounded-md px-3 text-sm font-medium tabular-nums transition-colors",
                    target === n ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {n}
                </button>
              ))}
            </div>
            <Button disabled={pending || !seriesSlug} onClick={() => run(() => startAutopilot(channelId, seriesSlug, target))}>
              <Bot />
              Lancer {target} vidéo{target > 1 ? "s" : ""} en automatique
            </Button>
          </div>
        ) : null}

        {status.productions.length > 0 ? (
          <ul className="flex flex-col gap-1 text-sm">
            {status.productions.map((p) => (
              <li key={p.id} className="flex items-center gap-2">
                {p.status === "ready" ? (
                  <CircleCheck className="size-4 text-emerald-500" />
                ) : p.status === "failed" || p.status === "cancelled" ? (
                  <CircleX className="text-destructive size-4" />
                ) : (
                  <LoaderCircle className="text-muted-foreground size-4 animate-spin" />
                )}
                <span className="min-w-0 truncate">{p.title}</span>
                <span className="text-muted-foreground shrink-0 text-xs">· {STAGE[p.status] ?? p.status}</span>
              </li>
            ))}
          </ul>
        ) : null}
        {!running && status.stopped_reason ? (
          <p className="text-muted-foreground text-xs">Dernier passage arrêté : {status.stopped_reason}.</p>
        ) : null}
        {notice ? <p className={cn("text-sm", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")}>{notice.message}</p> : null}
      </CardContent>
    </Card>
  );
}
