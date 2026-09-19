"use client";

import * as React from "react";
import { Check, Sparkles, X } from "lucide-react";

import { ConceptStatusBadge, ToneBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatRelative } from "@/lib/format";
import { CONCEPT_SOURCE_LABELS, categoryMeta } from "@/lib/labels";
import type { Concept, ConceptStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export function IdeasTable({ concepts }: { concepts: Concept[] }) {
  const [overrides, setOverrides] = React.useState<Record<string, ConceptStatus>>({});
  const statusOf = (concept: Concept): ConceptStatus => overrides[concept.id] ?? concept.status;
  const setStatus = (id: string, status: ConceptStatus) => setOverrides((prev) => ({ ...prev, [id]: status }));

  const counts = concepts.reduce<Record<ConceptStatus, number>>(
    (acc, concept) => {
      acc[statusOf(concept)] += 1;
      return acc;
    },
    { proposed: 0, approved: 0, rejected: 0, used: 0 }
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <ToneBadge tone="info">Proposées {counts.proposed}</ToneBadge>
        <ToneBadge tone="success">Approuvées {counts.approved}</ToneBadge>
        <ToneBadge tone="danger">Rejetées {counts.rejected}</ToneBadge>
        <ToneBadge tone="neutral">Utilisées {counts.used}</ToneBadge>
        <div className="md:ml-auto">
          <Tooltip>
            <TooltipTrigger asChild>
              <span tabIndex={0} className="inline-flex rounded-md">
                <Button disabled>
                  <Sparkles />
                  Générer 10 idées
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>Nécessite le worker connecté</TooltipContent>
          </Tooltip>
        </div>
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Titre</TableHead>
              <TableHead>Catégorie</TableHead>
              <TableHead className="w-40">Score</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Statut</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {concepts.map((concept) => {
              const status = statusOf(concept);
              const meta = categoryMeta(concept.category);
              const locked = status === "used";
              return (
                <TableRow key={concept.id} className={cn(status === "rejected" && "opacity-60")}>
                  <TableCell className="whitespace-normal">
                    <div className="flex max-w-[28rem] min-w-[14rem] flex-col gap-0.5">
                      <span className="font-medium">{concept.title}</span>
                      {concept.hook ? <span className="text-muted-foreground text-xs">{concept.hook}</span> : null}
                      <span className="text-muted-foreground/70 text-[11px]">{formatRelative(concept.created_at)}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">
                      <span aria-hidden>{meta.emoji}</span>
                      {meta.label}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Progress value={concept.score ?? 0} className="h-1.5 w-20" aria-label={`Score ${concept.score ?? 0}`} />
                      <span className="text-xs tabular-nums">{concept.score ?? "—"}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{CONCEPT_SOURCE_LABELS[concept.source]}</TableCell>
                  <TableCell>
                    <ConceptStatusBadge status={status} />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="inline-flex gap-1.5">
                      <Button
                        variant={status === "approved" ? "default" : "outline"}
                        size="sm"
                        disabled={locked || status === "approved"}
                        onClick={() => setStatus(concept.id, "approved")}
                        aria-label={`Approuver « ${concept.title} »`}
                      >
                        <Check />
                        Approuver
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={locked || status === "rejected"}
                        onClick={() => setStatus(concept.id, "rejected")}
                        aria-label={`Rejeter « ${concept.title} »`}
                      >
                        <X />
                        Rejeter
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
