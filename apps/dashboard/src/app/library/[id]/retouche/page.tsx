import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { RetouchEditor } from "@/components/library/retouch-editor";
import { getRetouchPage } from "@/lib/retouch";

export const metadata: Metadata = { title: "Retouche" };

/** Retouche d'une vidéo montée (docs/34-retouche.md), ouverte depuis sa fiche dans la Bibliothèque. */
export default async function RetouchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await getRetouchPage(id);
  if (!data) notFound();

  return (
    <div className="flex flex-col gap-4">
      <Link href={`/library?video=${id}`} className="text-muted-foreground hover:text-foreground flex w-fit items-center gap-1.5 text-sm">
        <ArrowLeft className="size-4" />
        Bibliothèque
      </Link>
      {/* Remonté quand la vidéo est relancée ou refaite : les champs repartent de la retouche enregistrée */}
      <RetouchEditor key={`${data.state.finalAssetId}-${data.state.busy}`} data={data} />
    </div>
  );
}
