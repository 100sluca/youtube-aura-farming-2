"use client";

/**
 * Encart « Clés API » du gestionnaire des tâches (docs/49 §9). Demande de Luca (01/10) : savoir quelle clé tourne et
 * lesquelles sont tombées (quota du jour, refus), pour la voix Gemini comme pour les modèles de langue. Une clé qui tombe
 * fait aussi une alerte (worker/keyusage.py). Le détail des quotas est dans Réglages → Quotas.
 */
import * as React from "react";
import Link from "next/link";
import { KeyRound } from "lucide-react";

import { fetchKeyBoard } from "@/app/key-actions";
import { EMPTY_KEY_BOARD, POOL_LABEL, STATUS_LABEL, frenchHour as hour, type KeyBoard, type KeySlot } from "@/lib/api-key-types";
import { cn } from "@/lib/utils";


function SlotChip({ s, current }: { s: KeySlot; current: boolean }) {
  const down = s.status === "quota_day" || s.status === "invalid";
  const title = [
    `Clé n°${s.slot}${s.hint ? ` (…${s.hint})` : ""} : ${STATUS_LABEL[s.status]}`,
    s.calls ? `${s.ok} réussi${s.ok > 1 ? "s" : ""}, ${s.failed} refusé${s.failed > 1 ? "s" : ""} aujourd’hui` : "",
    s.status === "quota_day" && s.blockedUntil ? `revient vers ${hour(s.blockedUntil)}` : "",
    s.lastError && down ? s.lastError.slice(0, 160) : "",
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] tabular-nums",
        current && "border-emerald-500/60 bg-emerald-500/10 font-medium text-emerald-700 dark:text-emerald-400",
        down && "border-destructive/40 bg-destructive/10 text-destructive line-through decoration-1",
        s.status === "quota_minute" && "border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400",
        s.status === "unused" && "text-muted-foreground border-dashed",
      )}
    >
      n°{s.slot}
      {s.ok ? <span className="opacity-70">· {s.ok}</span> : null}
    </span>
  );
}

export function ApiKeysPanel({ open }: { open: boolean }) {
  const [board, setBoard] = React.useState<KeyBoard>(EMPTY_KEY_BOARD);

  React.useEffect(() => {
    if (!open) return;
    let alive = true;
    const tick = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const next = await fetchKeyBoard();
        if (alive) setBoard(next);
      } catch {
        // serveur momentanément indisponible : on garde le dernier état
      }
    };
    void tick();
    const timer = setInterval(tick, 10_000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [open]);

  if (!board.groups.length) return null;
  const down = board.groups.reduce((n, g) => n + g.down, 0);
  return (
    <section className="flex flex-col gap-2">
      <h3 className={cn("flex items-center gap-2 text-xs font-semibold tracking-wide uppercase", down ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground")}>
        <KeyRound className="size-3.5" />
        Clés API aujourd’hui
        {down ? <span className="font-normal normal-case">· {down} tombée{down > 1 ? "s" : ""}</span> : null}
      </h3>
      <ul className="flex flex-col gap-1.5">
        {board.groups.map((g) => {
          const alive = g.slots.filter((s) => s.status !== "quota_day" && s.status !== "invalid").length;
          return (
            <li key={`${g.pool}-${g.model}`} className="flex flex-col gap-1 rounded-lg border p-2 text-xs">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-medium">
                  {POOL_LABEL[g.pool]} · {g.model}
                </span>
                <span className="text-muted-foreground">
                  {g.current ? `clé n°${g.current} en service` : "aucune réponse aujourd’hui"} · {alive}/{g.slots.length} disponible{alive > 1 ? "s" : ""}
                  {g.limit ? ` · ${g.limit} par clé et par jour` : ""}
                </span>
              </div>
              <div className="flex flex-wrap gap-1">
                {g.slots.map((s) => (
                  <SlotChip key={s.slot} s={s} current={s.slot === g.current} />
                ))}
              </div>
            </li>
          );
        })}
      </ul>
      <p className="text-muted-foreground text-[11px]">
        Les quotas de Google repartent vers {hour(board.resetAt)} ·{" "}
        <Link href="/settings#quotas" className="underline underline-offset-2">
          détail des quotas
        </Link>
      </p>
    </section>
  );
}
