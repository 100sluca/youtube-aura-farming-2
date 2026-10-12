import type { Metadata } from "next";

import { AutoRefresh } from "@/components/auto-refresh";
import { LongView } from "@/components/long/long-view";
import { PageHeader } from "@/components/page-header";
import { getLongOverview } from "@/lib/long";

export const metadata: Metadata = { title: "Vidéos longues" };
export const dynamic = "force-dynamic";

/** Vidéos longues « histoire et mystères » narrées par Luca (docs/63) : sujets, script à relire, Studio voix, images,
 * miniatures, montage et publication, tout depuis cette page. */
export default async function LongPage() {
  const data = await getLongOverview();
  const busy = data.jobs.length > 0;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader description="Vidéos de 20 à 25 min en 16:9, images et clips faits par l’IA, racontées avec ta voix. Choisis un sujet, relis le script, enregistre-le dans le Studio voix : le reste se fait seul jusqu’à la publication." />
      <AutoRefresh seconds={busy ? 6 : 30} />
      <LongView data={data} />
    </div>
  );
}
