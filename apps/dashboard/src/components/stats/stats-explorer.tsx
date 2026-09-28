"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { LibrarySheet } from "@/components/library/library-sheet";
import { DailyViewsChart } from "@/components/stats/daily-views";
import { StatsTable } from "@/components/stats/stats-table";
import { VideosChart } from "@/components/stats/videos-chart";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate, formatNumber } from "@/lib/format";
import type { StatsPage } from "@/lib/stats-types";

/** Graphiques et tableau des vidéos : un clic sur une barre, un point ou une ligne ouvre la même fiche (lecture, stats,
 * fabrication, avis de l'agent analyste). */
export function StatsExplorer({ data, showChannel }: { data: StatsPage; showChannel: boolean }) {
  const router = useRouter();
  const [openId, setOpenId] = React.useState<string | null>(null);
  const openItem = data.videos.find((v) => v.id === openId) ?? null;
  const estimatedDays = data.daily.filter((d) => d.source !== "analytics").length;
  const days = data.daily.length;

  return (
    <>
      <section className="grid gap-4 *:min-w-0 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>Vues par jour</CardTitle>
            <CardDescription>
              {showChannel ? "Toutes les chaînes" : "La chaîne"}, {days} derniers jours
              {data.analytics_through ? ` · YouTube Analytics jusqu’au ${formatDate(`${data.analytics_through}T12:00:00Z`, "d MMMM")}` : ""}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <DailyViewsChart data={data.daily} />
            {estimatedDays > 0 || data.unattributed > 0 ? (
              <p className="text-muted-foreground text-xs">
                YouTube Analytics publie les vues avec 2 à 3 jours de retard : les jours suivants sont estimés d’après les compteurs relevés chaque heure.
                {data.unattributed > 0
                  ? ` ${formatNumber(data.unattributed)} vue${data.unattributed > 1 ? "s" : ""} ne ${data.unattributed > 1 ? "sont" : "est"} pas encore rangée${data.unattributed > 1 ? "s" : ""} dans un jour (comptée${data.unattributed > 1 ? "s" : ""} dans les totaux) : Analytics les datera.`
                  : ""}
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
            <VideosChart videos={data.videos} onOpen={setOpenId} />
          </CardContent>
        </Card>
      </section>

      <section className="flex flex-col gap-3" aria-labelledby="toutes-les-videos">
        <div>
          <h2 id="toutes-les-videos" className="text-lg font-semibold tracking-tight">
            Toutes les vidéos publiées
          </h2>
          <p className="text-muted-foreground text-sm">
            Clique un titre de colonne pour trier, le ⓘ pour savoir d’où vient le chiffre, une ligne pour ouvrir la fiche de la vidéo.
            {data.scheduled > 0 ? ` ${data.scheduled} autre${data.scheduled > 1 ? "s" : ""} programmée${data.scheduled > 1 ? "s" : ""}, pas encore en ligne.` : ""}
          </p>
        </div>
        <StatsTable videos={data.videos} median={data.median_views} showChannel={showChannel} onOpen={setOpenId} />
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
