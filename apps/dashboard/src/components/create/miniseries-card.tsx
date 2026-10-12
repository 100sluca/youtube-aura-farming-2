"use client";

import * as React from "react";
import { Clapperboard, Play, Square } from "lucide-react";

import { launchArcPart, saveMiniseriesSettings, stopArc } from "@/app/create/miniseries-actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import type { Arc, ArcDecision, ArcPartRow, MiniseriesStatus } from "@/lib/miniseries";
import { cn } from "@/lib/utils";

const THRESHOLDS = [0.75, 1, 1.5, 2];

const STAGE: Record<string, string> = {
  draft: "en file",
  scripting: "script",
  generating: "images et clips",
  storyboard_review: "storyboard à valider",
  assembling: "montage",
  ready: "prête",
};

const fmt = new Intl.NumberFormat("fr-FR");

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("fr-FR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
}

function partState(p: ArcPartRow): string {
  if (p.publishedAt) return `publiée ${when(p.publishedAt)}`;
  if (p.scheduledAt) return `programmée ${when(p.scheduledAt)}`;
  return STAGE[p.status] ?? p.status;
}

function verdictText(d: ArcDecision, hours: number): string {
  const base = `${fmt.format(d.views)} vues en ${hours} h`;
  if (d.median == null) return `${base} · ${d.why ?? "pas assez de vidéos pour comparer"}`;
  return `${base} · médiane ${fmt.format(d.median)}${d.ratio != null ? ` (×${d.ratio})` : ""}`;
}

/**
 * Mini-séries (docs/52) : chaque drame s'écrit en 3 parties ; 48 h après la sortie d'une partie, ses vues sont comparées
 * à la médiane de la chaîne. Au-dessus du seuil, la suite est proposée ici (ou lancée seule, pilote allumé).
 */
export function MiniseriesCard({ status }: { status: MiniseriesStatus }) {
  const [pending, startTransition] = React.useTransition();
  const [notice, setNotice] = React.useState<{ ok: boolean; message: string } | null>(null);
  const [showAll, setShowAll] = React.useState(false);
  const { settings } = status;
  const active = status.arcs.filter((a) => a.status === "active");
  const shown = showAll ? status.arcs : active;

  const run = (fn: () => Promise<{ ok: boolean; message: string }>) =>
    startTransition(async () => {
      setNotice(await fn()); // pas de router.refresh() : l'action appelle revalidatePath, sa réponse apporte déjà la page recalculée (docs/56)
    });

  return (
    <Card className="py-5">
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <Clapperboard className="text-muted-foreground size-5" />
          <div className="min-w-0 flex-1">
            <p className="font-medium">Mini-séries</p>
            <p className="text-muted-foreground text-sm">
              Chaque drame s’écrit en {settings.parts} parties qui coupent en pleine action. {settings.eval_hours} h après la sortie d’une partie, ses vues
              YouTube + TikTok sont comparées à la médiane de la chaîne : au-dessus du seuil, la suite {settings.autopilot ? "se fabrique et se programme seule" : "t’est proposée ici"}.
            </p>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={settings.autopilot} disabled={pending} onCheckedChange={(v) => run(() => saveMiniseriesSettings({ autopilot: v }))} />
            Pilote des suites
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">Seuil :</span>
          <div className="bg-muted inline-flex rounded-lg p-0.5" role="radiogroup" aria-label="Seuil des mini-séries">
            {THRESHOLDS.map((t) => (
              <button
                key={t}
                type="button"
                role="radio"
                aria-checked={settings.threshold === t}
                disabled={pending}
                onClick={() => run(() => saveMiniseriesSettings({ threshold: t }))}
                className={cn(
                  "h-8 rounded-md px-3 text-sm font-medium tabular-nums transition-colors",
                  settings.threshold === t ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {t === 1 ? "la médiane" : `×${String(t).replace(".", ",")}`}
              </button>
            ))}
          </div>
        </div>

        {shown.length > 0 ? (
          <ul className="flex flex-col gap-3">
            {shown.map((arc) => (
              <ArcRow key={arc.id} arc={arc} hours={settings.eval_hours} pending={pending} run={run} />
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">Aucune mini-série en cours : la prochaine idée de drame que tu gardes en lance une.</p>
        )}
        {status.arcs.length > active.length ? (
          <button type="button" className="text-muted-foreground hover:text-foreground self-start text-xs underline-offset-4 hover:underline" onClick={() => setShowAll((v) => !v)}>
            {showAll ? "Masquer les mini-séries terminées" : `Voir aussi les ${status.arcs.length - active.length} terminée(s) ou arrêtée(s)`}
          </button>
        ) : null}
        {notice ? <p className={cn("text-sm", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")}>{notice.message}</p> : null}
      </CardContent>
    </Card>
  );
}

function ArcRow({
  arc,
  hours,
  pending,
  run,
}: {
  arc: Arc;
  hours: number;
  pending: boolean;
  run: (fn: () => Promise<{ ok: boolean; message: string }>) => void;
}) {
  const made = arc.parts.length ? Math.max(...arc.parts.map((p) => p.part)) : 0;
  const next = made + 1;
  const canLaunch = arc.status === "active" && made > 0 && next <= arc.partsTotal;
  const last = arc.decisions.find((d) => d.part === made);
  return (
    <li className="rounded-lg border p-3">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{arc.title}</p>
          {arc.premise ? <p className="text-muted-foreground line-clamp-2 text-xs">{arc.premise}</p> : null}
        </div>
        {arc.status !== "active" ? <span className="text-muted-foreground text-xs">{arc.status === "finished" ? "terminée" : "arrêtée"}</span> : null}
      </div>
      <ol className="mt-2 flex flex-col gap-1 text-sm">
        {Array.from({ length: arc.partsTotal }, (_, k) => k + 1).map((n) => {
          const p = arc.parts.find((x) => x.part === n);
          const d = arc.decisions.find((x) => x.part === n);
          const plan = arc.outline.find((x) => x.n === n);
          return (
            <li key={n} className="flex flex-wrap items-baseline gap-x-2">
              <span className={cn("shrink-0 font-medium tabular-nums", !p && "text-muted-foreground")}>Partie {n}</span>
              <span className="text-muted-foreground min-w-0 flex-1 truncate text-xs" title={plan ? `${plan.synopsis} — coupe sur : ${plan.ends_on}` : undefined}>
                {p ? partState(p) : plan ? `à venir · ${plan.synopsis}` : "à venir"}
              </span>
              {d ? (
                <span className={cn("text-xs", d.verdict === "suggested" ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground")}>
                  {verdictText(d, hours)}
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
      {arc.status === "active" ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {canLaunch ? (
            arc.launchRequest === next ? (
              <span className="text-muted-foreground text-xs">Partie {next} demandée : départ dans 2 min.</span>
            ) : (
              <Button size="sm" variant={last?.verdict === "suggested" ? "default" : "outline"} disabled={pending} onClick={() => run(() => launchArcPart(arc.id, next))}>
                <Play />
                {last?.verdict === "suggested" ? `Lancer la partie ${next}` : last ? `Lancer la partie ${next} quand même` : `Lancer la partie ${next} maintenant`}
              </Button>
            )
          ) : null}
          <Button size="sm" variant="ghost" disabled={pending} onClick={() => run(() => stopArc(arc.id))}>
            <Square />
            Arrêter la mini-série
          </Button>
        </div>
      ) : null}
    </li>
  );
}
