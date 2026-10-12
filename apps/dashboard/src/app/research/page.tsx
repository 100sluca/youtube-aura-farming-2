import type { Metadata } from "next";

import { AutoRefresh } from "@/components/auto-refresh";
import { PageHeader } from "@/components/page-header";
import { ResearchView } from "@/components/research/research-view";
import { getResearchOverview } from "@/lib/research";
import { getDiscovery } from "@/lib/research-discovery";

export const metadata: Metadata = { title: "Recherche" };
export const dynamic = "force-dynamic";

/** Veille des niches (docs/60) : ce qui marche en Shorts, pourquoi, depuis quand, et quoi reproduire. Tout est gratuit :
 * API YouTube, Gemini qui regarde les vidéos, calculs faits par le worker. */
export default async function ResearchPage() {
  const [data, discovery] = await Promise.all([getResearchOverview(), getDiscovery()]);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader description="Les Shorts qui marchent dans chaque niche, pourquoi ils marchent, où en est chaque niche (émergente, en hausse, en baisse) et les vidéos à reproduire. Données publiques de YouTube, relevées chaque jour ; Gemini regarde les meilleures." />
      {data.jobs.length || discovery.running ? <AutoRefresh seconds={8} /> : null}
      <ResearchView data={data} discovery={discovery} />
    </div>
  );
}
