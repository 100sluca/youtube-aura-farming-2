"use client";

import * as React from "react";
import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";

import { SeverityBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { formatDateTime, formatRelative } from "@/lib/format";
import type { Alert, AlertSeverity } from "@/lib/types";
import { cn } from "@/lib/utils";

const ICONS: Record<AlertSeverity, typeof Info> = {
  info: Info,
  warning: TriangleAlert,
  error: CircleAlert,
};

function AlertRow({ alert, acknowledged, onAcknowledge }: { alert: Alert; acknowledged: boolean; onAcknowledge?: () => void }) {
  const Icon = ICONS[alert.severity];
  return (
    <li
      className={cn(
        "flex flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-start",
        acknowledged ? "bg-muted/30 opacity-75" : "bg-card",
        !acknowledged && alert.severity === "error" && "border-red-500/40",
        !acknowledged && alert.severity === "warning" && "border-amber-500/40"
      )}
    >
      <span
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-lg",
          alert.severity === "error" && "bg-red-500/10 text-red-600 dark:text-red-400",
          alert.severity === "warning" && "bg-amber-500/10 text-amber-600 dark:text-amber-400",
          alert.severity === "info" && "bg-sky-500/10 text-sky-600 dark:text-sky-400"
        )}
      >
        <Icon className="size-4" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={alert.severity} />
          <span className="text-muted-foreground text-xs" title={formatDateTime(alert.created_at)}>
            {formatRelative(alert.created_at)} · {formatDateTime(alert.created_at)}
          </span>
        </div>
        <p className="font-medium leading-snug">{alert.title}</p>
        {alert.body ? <p className="text-muted-foreground text-sm">{alert.body}</p> : null}
        {acknowledged ? (
          <p className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
            <CircleCheck className="size-3.5" />
            Acquittée{alert.acknowledged_at ? ` ${formatRelative(alert.acknowledged_at)}` : " à l’instant"}
          </p>
        ) : null}
      </div>
      {!acknowledged && onAcknowledge ? (
        <Button variant="outline" size="sm" className="shrink-0 self-start" onClick={onAcknowledge}>
          <CircleCheck />
          Acquitter
        </Button>
      ) : null}
    </li>
  );
}

export function AlertsList({ alerts }: { alerts: Alert[] }) {
  const [acked, setAcked] = React.useState<Record<string, boolean>>({});
  const isAcknowledged = (alert: Alert) => Boolean(alert.acknowledged_at) || Boolean(acked[alert.id]);
  const open = alerts.filter((a) => !isAcknowledged(a));
  const done = alerts.filter(isAcknowledged);

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold">
          À traiter <span className="text-muted-foreground font-normal tabular-nums">({open.length})</span>
        </h2>
        {open.length === 0 ? (
          <p className="text-muted-foreground rounded-xl border border-dashed p-6 text-center text-sm">Aucune alerte ouverte. Tout roule.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {open.map((alert) => (
              <AlertRow
                key={alert.id}
                alert={alert}
                acknowledged={false}
                onAcknowledge={() => setAcked((prev) => ({ ...prev, [alert.id]: true }))}
              />
            ))}
          </ul>
        )}
      </section>

      {done.length > 0 ? (
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold">
            Acquittées <span className="text-muted-foreground font-normal tabular-nums">({done.length})</span>
          </h2>
          <ul className="flex flex-col gap-3">
            {done.map((alert) => (
              <AlertRow key={alert.id} alert={alert} acknowledged />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
