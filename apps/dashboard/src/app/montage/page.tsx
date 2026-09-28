import type { Metadata } from "next";

import { MontageEditor } from "@/components/montage/montage-editor";
import { PageHeader } from "@/components/page-header";
import { getMontageData } from "@/lib/montage";

export const metadata: Metadata = { title: "Montage" };

export default async function MontagePage() {
  const data = await getMontageData();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader description="Ta patte sur toutes les vidéos : où et comment s’affichent le titre d’accroche, les sous-titres et les textes à l’écran, et le son (volume de la voix, des musiques et des bruitages). Place les éléments sur l’aperçu, règle police, couleurs, fonds et volumes, puis enregistre : le modèle utilisé sert à tous les montages suivants." />
      <MontageEditor data={data} />
    </div>
  );
}
