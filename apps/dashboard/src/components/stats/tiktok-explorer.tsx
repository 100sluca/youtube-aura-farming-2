"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { LibrarySheet } from "@/components/library/library-sheet";
import { DailyViewsChart } from "@/components/stats/daily-views";
import { TikTokTable } from "@/components/stats/tiktok-table";
import { DURATION_AXIS, HOUR_AXIS, VideosChart, type ChartAxis } from "@/components/stats/videos-chart";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate, formatPercent } from "@/lib/format";
import type { TikTokStatsPage, TikTokStatsVideo } from "@/lib/tiktok-stats-types";

const LATER = "TikTok la donne 24 à 48 h après la sortie.";

const AXES: ChartAxis<TikTokStatsVideo>[] = [
  DURATION_AXIS,
  { id: "watched", label: "Part regardée", value: (v) => v.watched_pct, format: (n) => formatPercent(n), later: LATER },
  { id: "completion", label: "Vue jusqu’au bout", value: (v) => v.completion_pct, format: (n) => formatPercent(n), later: LATER },
  { id: "for_you", label: "Part « Pour toi »", value: (v) => v.for_you_pct, format: (n) => formatPercent(n), later: LATER },
  HOUR_AXIS,
];

/** Graphiques et tableau des vidéos TikTok (docs/39) : un clic ouvre la fiche de la vidéo de l'appli (lecture, stats
 * YouTube et TikTok, fabrication), ou la vidéo sur TikTok si elle y a été publiée à la main. */
export function TikTokExplorer({ data }: { data: TikTokStatsPage }) {
  const router = useRouter();
  const [openId, setOpenId] = React.useState<string | null>(null);
  const openItem = data.videos.find((v) => v.item?.id === openId)?.item ?? null;
  const open = (v: TikTokStatsVideo) => {
    if (v.item) setOpenId(v.item.id);
    else if (v.url) window.open(v.url, "_blank", "noopener,noreferrer");
  };
  const openById = (id: string) => {
    const v = data.videos.find((x) => x.id === id);
    if (v) open(v);
  };
  const showAccount = !data.account_id && data.accounts.length > 1;
  const unknownDays = data.daily.filter((d) => d.source === "unknown").length;

  return (
    <>
      <section className="grid gap-4 *:min-w-0 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>Vues par jour</CardTitle>
            <CardDescription>
              {showAccount ? "Tous les comptes" : `@${data.accounts.find((a) => a.id === data.account_id)?.username ?? data.accounts[0]?.username ?? "?"}`},{" "}
              {data.daily.length} derniers jours · d’après les relevés faits chaque heure
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <DailyViewsChart data={data.daily} platform="tiktok" />
            {unknownDays > 0 && data.snapshots_since ? (
              <p className="text-muted-foreground text-xs">
                Relevés commencés le {formatDate(data.snapshots_since, "d MMMM")} : les jours d’avant (et ceux où le worker ne tournait pas) restent vides, leurs vues
                comptent dans les totaux.
              </p>
            ) : null}
          </CardContent>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Chaque vidéo</CardTitle>
            <CardDescription>Couleur = format · clique pour ouvrir la fiche</CardDescription>
          </CardHeader>
          <CardContent>
            <VideosChart videos={data.videos.filter((v) => !v.views_pending)} onOpen={openById} axes={AXES} />
          </CardContent>
        </Card>
      </section>

      <section className="flex flex-col gap-3" aria-labelledby="toutes-les-videos-tiktok">
        <div>
          <h2 id="toutes-les-videos-tiktok" className="text-lg font-semibold tracking-tight">
            Toutes les vidéos sorties sur TikTok
          </h2>
          <p className="text-muted-foreground text-sm">
            Clique un titre de colonne pour trier, le ⓘ pour savoir d’où vient le chiffre, une ligne pour ouvrir la fiche. La colonne YouTube donne les vues de la
            même vidéo sur YouTube.
          </p>
        </div>
        <TikTokTable videos={data.videos} median={data.median_views} showAccount={showAccount} onOpen={open} />
      </section>

      <LibrarySheet
        item={openItem}
        onClose={() => {
          setOpenId(null);
          router.refresh();
        }}
      />
    </>
  );
}
