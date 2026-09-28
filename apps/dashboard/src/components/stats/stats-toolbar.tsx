"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CircleCheck, CircleX, RefreshCw } from "lucide-react";

import { refreshStats } from "@/app/dashboard/actions";
import type { ActionResult } from "@/app/production/actions";
import { Button } from "@/components/ui/button";
import { formatRelative } from "@/lib/format";
import { STATS_PERIODS, type StatsPeriod } from "@/lib/stats-types";
import { cn } from "@/lib/utils";

/** Période (date de mise en ligne des vidéos affichées), bouton « Actualiser » et fraîcheur des chiffres. */
export function StatsToolbar({
  period,
  syncActive,
  syncSince,
  countersAt,
  lastError,
  connected,
}: {
  period: StatsPeriod;
  syncActive: boolean;
  syncSince: string | null;
  countersAt: string | null;
  lastError: string | null;
  connected: boolean;
}) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [notice, setNotice] = React.useState<ActionResult | null>(null);
  const busy = pending || syncActive;
  // Une synchro prend moins d'une minute : au-delà de 3 min en file, le worker est sans doute arrêté
  const [clock, setClock] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (!syncActive) return;
    const timer = setInterval(() => setClock(Date.now()), 15_000);
    return () => clearInterval(timer);
  }, [syncActive]);
  const stuck = syncActive && Boolean(syncSince) && clock - new Date(syncSince ?? 0).getTime() > 3 * 60_000;

  return (
    <div className="flex flex-col items-start gap-2 md:items-end">
      <div className="flex flex-wrap items-center gap-2">
        <nav className="bg-muted inline-flex rounded-lg p-0.5 text-sm" aria-label="Période">
          {STATS_PERIODS.map((p) => (
            <Link
              key={p.id}
              href={p.id === "28" ? "/dashboard" : `/dashboard?periode=${p.id}`}
              scroll={false}
              aria-current={period === p.id ? "page" : undefined}
              className={cn(
                "flex h-8 items-center rounded-md px-3 font-medium whitespace-nowrap transition-colors",
                period === p.id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {p.label}
            </Link>
          ))}
        </nav>
        <Button
          variant="outline"
          size="sm"
          disabled={busy || !connected}
          onClick={() =>
            startTransition(async () => {
              const res = await refreshStats();
              setNotice(res);
              router.refresh();
            })
          }
        >
          <RefreshCw className={cn(busy && "animate-spin")} />
          {busy ? "Actualisation…" : "Actualiser"}
        </Button>
      </div>
      <p className="text-muted-foreground text-xs" suppressHydrationWarning>
        {!connected
          ? "Aucune chaîne connectée à YouTube"
          : countersAt
            ? `Compteurs relevés ${formatRelative(countersAt)} · automatiquement chaque heure`
            : "Compteurs jamais relevés : clique « Actualiser »"}
      </p>
      {notice && !syncActive ? (
        <p className={cn("flex items-center gap-1.5 text-xs", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")} role="status">
          {notice.ok ? <CircleCheck className="size-3.5" /> : <CircleX className="size-3.5" />}
          {notice.ok ? "Chiffres à jour." : notice.message}
        </p>
      ) : null}
      {syncActive && stuck ? (
        <p className="max-w-md text-xs text-amber-700 dark:text-amber-400" role="status">
          La synchro attend depuis plus de 3 minutes : le worker est-il lancé ?
        </p>
      ) : null}
      {lastError && !syncActive ? (
        <p className="text-destructive max-w-md text-xs" role="alert">
          Dernière synchro en échec : {lastError.slice(0, 180)}
        </p>
      ) : null}
    </div>
  );
}
