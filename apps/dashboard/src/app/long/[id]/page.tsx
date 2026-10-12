import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { LongDetailView } from "@/components/long/long-detail";
import { getLongDetail } from "@/lib/long";
import { titleOf } from "@/lib/long-types";

export const metadata: Metadata = { title: "Vidéo longue" };
export const dynamic = "force-dynamic";

/** Fiche d'une vidéo longue (docs/63) : script, voix, images, miniature et titre, vidéo et publication. */
export default async function LongVideoPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await getLongDetail(id);
  if (!data) notFound();
  return (
    <>
      <AutoRefresh seconds={data.jobs.length ? 6 : 45} />
      <LongDetailView key={`${data.video.id}-${data.video.stage}`} data={data} />
      <span className="sr-only">{titleOf(data.video)}</span>
    </>
  );
}
