"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { LibrarySheet } from "@/components/library/library-sheet";
import { DailyViewsChart } from "@/components/stats/daily-views";
import { InstagramTable } from "@/components/stats/instagram-table";
import { DURATION_AXIS, HOUR_AXIS, VideosChart, type ChartAxis } from "@/components/stats/videos-chart";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate, formatPercent } from "@/lib/format";
import { instagramLabel, type InstagramStatsPage, type InstagramStatsVideo } from "@/lib/instagram-stats-types";

const LATER = "Instagram la donne après les premières vues.";

const AXES: ChartAxis<InstagramStatsVideo>[] = [
  DURATION_AXIS,
  { id: "hook", label: "Encore là à 3 s", value: (v) => v.hook_pct, format: (n) => formatPercent(n), later: LATER },
  { id: "watched", label: "Part regardée", value: (v) => v.watched_pct, format: (n) => formatPercent(n), later: LATER },
  HOUR_AXIS,
];

/** Graphiques et tableau des Reels (docs/62) : un clic ouvre la fiche de la vidéo de l'appli, ou le Reel sur Instagram
 * (« Paf, j'achète », publié à la main). */
export function InstagramExplorer({ data }: { data: InstagramStatsPage }) {
  const router = useRouter();
  const [openId, setOpenId] = React.useState<string | null>(null);
  const openItem = data.videos.find((v) => v.item?.id === openId)?.item ?? null;
  const open = (v: InstagramStatsVideo) => {
    if (v.item) setOpenId(v.item.id);
    else if (v.url) window.open(v.url, "_blank", "noopener,noreferrer");
  };
  const openById = (id: string) => {
    const v = data.videos.find((x) => x.id === id);
    if (v) open(v);
  };
  const connected = data.accounts.filter((a) => a.connected);
  const showAccount = !data.account_id && connected.length > 1;
  const current = data.accounts.find((a) => a.id === data.account_id) ?? (connected.length === 1 ? connected[0] : null);
  const unknownDays = data.daily.filter((d) => d.source === "unknown").length;

  return (
    <>
      <section className="grid gap-4 *:min-w-0 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>Vues par jour</CardTitle>
            <CardDescription>
              {current ? instagramLabel(current) : "Tous les comptes"}, {data.daily.length} derniers jours · d’après les relevés faits chaque heure
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <DailyViewsChart data={data.daily} platform="instagram" />
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
            <CardTitle>Chaque Reel</CardTitle>
            <CardDescription>Couleur = format · clique pour ouvrir la fiche</CardDescription>
          </CardHeader>
          <CardContent>
            <VideosChart videos={data.videos.filter((v) => !v.views_pending)} onOpen={openById} axes={AXES} />
          </CardContent>
        </Card>
      </section>

      <section className="flex flex-col gap-3" aria-labelledby="tous-les-reels">
        <div>
          <h2 id="tous-les-reels" className="text-lg font-semibold tracking-tight">
            Tous les Reels sortis sur Instagram
          </h2>
          <p className="text-muted-foreground text-sm">
            Clique un titre de colonne pour trier, le ⓘ pour savoir d’où vient le chiffre, une ligne pour ouvrir la fiche. Les colonnes YouTube et TikTok donnent
            les vues de la même vidéo sur les autres réseaux.
          </p>
        </div>
        <InstagramTable videos={data.videos} median={data.median_views} showAccount={showAccount} onOpen={open} />
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
