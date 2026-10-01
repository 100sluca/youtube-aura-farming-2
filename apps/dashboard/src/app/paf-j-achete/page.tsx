import type { Metadata } from "next";

import { AutoRefresh } from "@/components/auto-refresh";
import { PageHeader } from "@/components/page-header";
import { PafPanel } from "@/components/paf/paf-panel";
import { getPafOverview } from "@/lib/paf";

export const metadata: Metadata = { title: "Paf, j’achète" };
export const dynamic = "force-dynamic";

/** La même vidéo chaque vendredi à 7 h (heure de Paris) sur un compte Instagram à part, par un second compte Zernio (docs/50). */
export default async function PafPage() {
  const overview = await getPafOverview();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader description="La même vidéo, chaque vendredi à 7 h (heure de Paris), sur un compte Instagram à part, par un autre compte Zernio. Rien à valider : l’interrupteur suffit." />
      {overview.job ? <AutoRefresh seconds={10} /> : null}
      <PafPanel overview={overview} />
    </div>
  );
}
