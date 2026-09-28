"use client";

import * as React from "react";
import { BookOpen, Check, ChevronDown, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatRelative } from "@/lib/format";
import type { Concept } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Couleur du score de potentiel (0-100, estimé par l'agent idée : rétention attendue × faisabilité visuelle). */
function scoreTone(score: number | null): string {
  if (score == null) return "bg-muted text-muted-foreground";
  if (score >= 80) return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400";
  if (score >= 60) return "bg-amber-500/15 text-amber-700 dark:text-amber-400";
  return "bg-muted text-muted-foreground";
}

/** Une idée à trier : accroche, déroulé, score ; ✓ la lance en fabrication, ✗ l'écarte. */
export function IdeaCard({
  concept,
  showSeries,
  disabled,
  onAccept,
  onReject,
}: {
  concept: Concept;
  showSeries: boolean;
  disabled: boolean;
  onAccept: () => void;
  onReject: () => void;
}) {
  const [open, setOpen] = React.useState(false);
  const beats = concept.visual_beats ?? [];
  return (
    <li className="bg-card flex min-w-0 flex-col gap-3 rounded-xl border p-4 shadow-xs">
      <div className="flex items-start gap-3">
        <span
          className={cn("flex size-11 shrink-0 flex-col items-center justify-center rounded-lg text-base leading-none font-semibold tabular-nums", scoreTone(concept.score))}
          title="Potentiel estimé par l’agent (0-100)"
        >
          {concept.score != null ? Math.round(concept.score) : "—"}
          <span className="text-[9px] font-normal opacity-80">score</span>
        </span>
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="leading-snug font-semibold">{concept.title}</h3>
          {concept.hook ? <p className="text-muted-foreground text-sm italic">« {concept.hook} »</p> : null}
        </div>
      </div>

      {concept.premise ? <p className="line-clamp-4 text-sm">{concept.premise}</p> : null}

      {beats.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="text-muted-foreground hover:text-foreground flex w-fit items-center gap-1 text-xs font-medium"
            aria-expanded={open}
          >
            <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
            Déroulé en {beats.length} temps
          </button>
          {open ? (
            <ol className="text-muted-foreground flex list-decimal flex-col gap-0.5 pl-5 text-xs">
              {beats.map((beat, i) => (
                <li key={i}>{beat}</li>
              ))}
            </ol>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-1.5">
        {showSeries && concept.series_name ? <Badge variant="secondary">{concept.series_name}</Badge> : null}
        {concept.facts_count ? (
          <Badge variant="outline" className="gap-1">
            <BookOpen className="size-3" />
            {concept.facts_count} faits sourcés
          </Badge>
        ) : null}
        {concept.angle ? <Badge variant="outline">{concept.angle}</Badge> : null}
        <span className="text-muted-foreground ml-auto text-[11px]">{formatRelative(concept.created_at)}</span>
      </div>

      <div className="mt-auto grid grid-cols-2 gap-2 pt-1">
        <Button variant="outline" disabled={disabled} onClick={onReject} aria-label={`Écarter « ${concept.title} »`}>
          <X />
          Écarter
        </Button>
        <Button
          disabled={disabled}
          onClick={onAccept}
          className="bg-emerald-600 text-white hover:bg-emerald-700 dark:bg-emerald-600 dark:hover:bg-emerald-500"
          aria-label={`Produire « ${concept.title} »`}
        >
          <Check />
          Produire
        </Button>
      </div>
    </li>
  );
}
