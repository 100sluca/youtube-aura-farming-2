import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";
import { KanbanBoard } from "@/components/production/kanban-board";
import { Badge } from "@/components/ui/badge";
import { parseChannel } from "@/lib/channel";
import { listProductions } from "@/lib/data";

export const metadata: Metadata = { title: "Production" };

export default async function ProductionPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const channel = parseChannel((await searchParams).channel);
  const productions = await listProductions();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        description="Suivi des productions du script à l’envoi YouTube. Chaque production génère une Short FR et une Short EN. Cliquez sur une carte pour voir ses jobs."
        actions={
          <Badge variant="secondary" className="tabular-nums">
            {productions.length} productions actives
          </Badge>
        }
      />
      <KanbanBoard key={channel ?? "all"} initial={productions} channel={channel} />
    </div>
  );
}
