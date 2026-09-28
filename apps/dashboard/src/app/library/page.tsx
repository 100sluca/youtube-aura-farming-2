import type { Metadata } from "next";

import { AutoRefresh } from "@/components/auto-refresh";
import { DemoView } from "@/components/library/demo-view";
import { LibraryTabs } from "@/components/library/library-tabs";
import { LibraryView } from "@/components/library/library-view";
import { PageHeader } from "@/components/page-header";
import { getChannelContext } from "@/lib/channel-server";
import { listDemos } from "@/lib/demos";
import { getLibrary } from "@/lib/library";
import { isLibraryGroup } from "@/lib/library-types";

export const metadata: Metadata = { title: "Bibliothèque" };

export default async function LibraryPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [params, { selected }] = await Promise.all([searchParams, getChannelContext()]);
  const [{ items, totalBytes }, demos] = await Promise.all([getLibrary(selected?.id), listDemos()]);
  const initialGroup = isLibraryGroup(params.statut) ? params.statut : null;
  // ?video=<id> : ouvre directement sa fiche (lien depuis l'onglet Montage, docs/28)
  const openId = typeof params.video === "string" ? params.video : null;

  return (
    <div className="flex flex-col gap-6">
      <AutoRefresh seconds={60} />
      <PageHeader
        description={`Toutes les vidéos ${selected ? `de « ${selected.name} »` : "de tes chaînes"} : celles produites ici, en fabrication comme finies, et l’historique importé de YouTube (marqué « Importée ») ; dans « Démos et essais », les vidéos faites hors de l’appli. Clique pour regarder, publier ou voir les stats ; supprime pour libérer le disque.`}
      />
      <LibraryTabs
        initial={params.vue === "demos" ? "demos" : "videos"}
        videoCount={items.length}
        demoCount={demos.length}
        videos={
          <LibraryView
            key={`${selected?.id ?? "all"}-${initialGroup ?? ""}`}
            items={items}
            totalBytes={totalBytes}
            initialGroup={initialGroup}
            initialOpenId={openId}
            showChannel={!selected}
          />
        }
        demos={<DemoView demos={demos} />}
      />
    </div>
  );
}
