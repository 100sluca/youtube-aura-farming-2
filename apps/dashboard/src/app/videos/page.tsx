import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";
import { VideosTable } from "@/components/videos/videos-table";
import { parseChannel } from "@/lib/channel";
import { listPublishedVideos } from "@/lib/data";

export const metadata: Metadata = { title: "Vidéos publiées" };

export default async function VideosPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const channel = parseChannel((await searchParams).channel);
  const videos = await listPublishedVideos();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader description="Toutes les Shorts en ligne, avec leurs métriques YouTube synchronisées. Cliquez sur une ligne pour le détail (rétention, vues par jour, commentaires, script)." />
      <VideosTable key={channel ?? "all"} videos={videos} initialChannel={channel} />
    </div>
  );
}
