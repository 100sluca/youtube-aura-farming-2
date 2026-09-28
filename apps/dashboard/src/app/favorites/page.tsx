import type { Metadata } from "next";

import { FavoritesView } from "@/components/favorites/favorites-view";
import { PageHeader } from "@/components/page-header";
import { getChannelContext } from "@/lib/channel-server";
import { listFavorites } from "@/lib/favorites";

export const metadata: Metadata = { title: "Favoris" };

export default async function FavoritesPage() {
  const { selected } = await getChannelContext();
  const favorites = await listFavorites(selected?.id);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader description="Les storyboards gardés avec l’étoile : l’idée, le script et les images retenues, même si la vidéo a été abandonnée ou supprimée. « Refaire avec ces images » le remet dans Création, prêt à valider ; « Nouvelles images » garde l’idée et le script mais refait les images avec les réglages actuels." />
      <FavoritesView key={selected?.id ?? "all"} favorites={favorites} showChannel={!selected} />
    </div>
  );
}
