import type { Metadata } from "next";
import { Info } from "lucide-react";

import { AutoRefresh } from "@/components/auto-refresh";
import { PageHeader } from "@/components/page-header";
import { AnalysisPanel } from "@/components/stats/analysis-panel";
import { StatsExplorer } from "@/components/stats/stats-explorer";
import { StatsKpis } from "@/components/stats/stats-kpis";
import { StatsToolbar } from "@/components/stats/stats-toolbar";
import { getChannelContext } from "@/lib/channel-server";
import { getStatsPage } from "@/lib/stats";
import { isStatsPeriod } from "@/lib/stats-types";

export const metadata: Metadata = { title: "Dashboard" };

/** Dashboard des statistiques (docs/25-dashboard-statistiques.md) : toutes les vidéos publiées avec leurs chiffres,
 * triables, en graphiques, et l'agent analyste qui dit ce qui marche et pourquoi. */
export default async function DashboardPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const [{ periode }, { channels, selected }] = await Promise.all([searchParams, getChannelContext()]);
  const period = isStatsPeriod(periode) ? periode : "28";
  const data = await getStatsPage(channels, selected, period);
  const busy = data.sync.active || data.analysis.running;

  return (
    <div className="flex flex-col gap-6">
      <AutoRefresh seconds={busy ? 4 : 60} />
      <PageHeader
        description={`Les chiffres de chaque vidéo publiée ${selected ? `sur « ${selected.name} »` : "sur tes chaînes"}, pour voir ce qui marche : vues, rétention, accroche à 3 s, j’aime, commentaires, partages, abonnés. La période filtre les vidéos par date de mise en ligne.`}
        actions={
          <StatsToolbar
            period={period}
            syncActive={data.sync.active}
            syncSince={data.sync.since}
            countersAt={data.counters_at}
            lastError={data.sync.last_error}
            connected={data.connected}
          />
        }
      />

      {data.connected && !data.analytics_through ? (
        <div className="flex gap-3 rounded-xl border border-sky-500/40 bg-sky-500/5 p-4 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-sky-600 dark:text-sky-400" />
          <p>
            <span className="font-medium">YouTube Analytics n’a encore rien publié pour cette chaîne.</span>{" "}
            <span className="text-muted-foreground">
              Il donne rétention, accroche à 3 s, durée regardée, partages et abonnés par vidéo avec 2 à 3 jours de retard : ces colonnes se rempliront toutes
              seules. Vues, j’aime, commentaires et abonnés de la chaîne sont déjà à jour (relevés chaque heure).
            </span>
          </p>
        </div>
      ) : null}

      <StatsKpis data={data} />
      <StatsExplorer data={data} showChannel={!selected && channels.length > 1} />
      <AnalysisPanel analysis={data.analysis} />
    </div>
  );
}
