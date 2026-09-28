"use client";

import * as React from "react";
import { LoaderCircle, RefreshCw, UserRound } from "lucide-react";

import { redoCharacter } from "@/app/production/actions";
import { Button } from "@/components/ui/button";
import type { CharacterSheet, ProductionStatus } from "@/lib/types";

/** Personnages d'un drame (docs/35) : la fiche de chacun, faite avant les plans et donnée en référence à chaque plan où il
 * apparaît. « Refaire » refait sa fiche puis tous ces plans : à regarder avant de choisir les images des scènes. */
export function CharacterStrip({
  productionId,
  status,
  characters,
}: {
  productionId: string;
  status: ProductionStatus;
  characters: CharacterSheet[];
}) {
  const [pending, startTransition] = React.useTransition();
  const [notice, setNotice] = React.useState<{ ok: boolean; message: string } | null>(null);
  const reviewable = status === "storyboard_review";
  if (characters.length === 0) return null;

  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">Personnages</h3>
      <p className="text-muted-foreground text-xs">
        Chaque fiche sert de modèle à tous les plans où le personnage apparaît : s’il ne va pas, « Refaire » refait sa fiche puis ces plans.
      </p>
      <ul className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6">
        {characters.map((c) => (
          <li key={c.key} className="flex flex-col gap-1">
            <div className="bg-muted relative aspect-[9/16] overflow-hidden rounded-md border">
              {c.asset_id ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={`/api/media/${c.asset_id}`} alt={c.name} title={c.look} className="size-full object-cover" loading="lazy" />
              ) : (
                <div className="text-muted-foreground flex size-full items-center justify-center">
                  <UserRound className="size-6" />
                </div>
              )}
              {c.busy ? (
                <div className="bg-background/70 absolute inset-0 flex items-center justify-center">
                  <LoaderCircle className="size-5 animate-spin" />
                </div>
              ) : null}
            </div>
            <div className="text-xs leading-tight">
              <span className="font-medium">{c.name}</span>
              {c.role ? <span className="text-muted-foreground"> · {c.role}</span> : null}
            </div>
            {reviewable ? (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 justify-start px-1 text-xs"
                disabled={pending || c.busy}
                onClick={() => startTransition(async () => setNotice(await redoCharacter(productionId, c.key)))}
              >
                <RefreshCw className="size-3.5" />
                Refaire
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      {notice ? <p className={notice.ok ? "text-muted-foreground text-xs" : "text-destructive text-xs"}>{notice.message}</p> : null}
    </section>
  );
}
