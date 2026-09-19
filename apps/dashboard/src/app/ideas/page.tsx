import type { Metadata } from "next";

import { IdeasTable } from "@/components/ideas/ideas-table";
import { PageHeader } from "@/components/page-header";
import { listConcepts } from "@/lib/data";

export const metadata: Metadata = { title: "Idées" };

export default async function IdeasPage() {
  const concepts = await listConcepts();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader description="Concepts proposés par l’agent d’idéation (ou saisis à la main). Approuvez ceux qui méritent une production, rejetez les autres." />
      <IdeasTable concepts={concepts} />
    </div>
  );
}
