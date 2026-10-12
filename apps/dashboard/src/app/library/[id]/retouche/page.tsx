import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { RetouchEditor } from "@/components/library/retouch-editor";
import { getRetouchPage } from "@/lib/retouch";
import { getRewriteData } from "@/lib/rewrite-story";

export const metadata: Metadata = { title: "Retouche" };

/** Retouche d'une vidéo montée (docs/34-retouche.md), ouverte depuis sa fiche dans la Bibliothèque ; `?onglet=recit`
 * ouvre l'onglet Récit (docs/53). */
export default async function RetouchPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ onglet?: string }> }) {
  const [{ id }, { onglet }] = await Promise.all([params, searchParams]);
  const [data, story] = await Promise.all([getRetouchPage(id), getRewriteData(id)]);
  if (!data) notFound();

  return (
    <div className="flex flex-col gap-4">
      <Link href={`/library?video=${id}`} className="text-muted-foreground hover:text-foreground flex w-fit items-center gap-1.5 text-sm">
        <ArrowLeft className="size-4" />
        Bibliothèque
      </Link>
      {/* Remonté quand la vidéo est relancée ou refaite : les champs repartent de la retouche enregistrée */}
      <RetouchEditor key={`${data.state.finalAssetId}-${data.state.busy}`} data={data} story={story} tab={onglet} />
    </div>
  );
}
