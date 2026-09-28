"use client";

import * as React from "react";

import { diffLines, foldDiff } from "@/lib/line-diff";
import { cn } from "@/lib/utils";

/** Différences ligne à ligne : en vert ce qui arrive, en rouge ce qui part, le reste replié. */
export function DiffView({ before, after, className }: { before: string; after: string; className?: string }) {
  const blocks = React.useMemo(() => foldDiff(diffLines(before, after)), [before, after]);
  const changed = blocks.some((b) => b.type === "lines" && b.lines.some((l) => l.type !== "same"));
  if (!changed) return <p className={cn("text-muted-foreground text-sm", className)}>Aucune différence.</p>;
  return (
    <div className={cn("overflow-hidden rounded-md border font-mono text-xs leading-relaxed", className)}>
      {blocks.map((block, i) =>
        block.type === "skip" ? (
          <div key={i} className="bg-muted/40 text-muted-foreground border-y px-3 py-1 text-center font-sans first:border-t-0 last:border-b-0">
            {block.count} ligne{block.count > 1 ? "s" : ""} identique{block.count > 1 ? "s" : ""}
          </div>
        ) : (
          block.lines.map((line, k) => (
            <div
              key={`${i}-${k}`}
              className={cn(
                "flex gap-2 px-3 whitespace-pre-wrap",
                line.type === "add" && "bg-emerald-500/15 text-emerald-900 dark:text-emerald-200",
                line.type === "del" && "bg-red-500/15 text-red-900 dark:text-red-200",
                line.type === "same" && "text-muted-foreground",
              )}
            >
              <span aria-hidden className="w-3 shrink-0 select-none">
                {line.type === "add" ? "+" : line.type === "del" ? "−" : ""}
              </span>
              <span className="sr-only">{line.type === "add" ? "ajouté : " : line.type === "del" ? "retiré : " : ""}</span>
              <span className="min-w-0 break-words">{line.text || " "}</span>
            </div>
          ))
        ),
      )}
    </div>
  );
}
