import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { VoiceStudio } from "@/components/long/voice-studio";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { getVoiceStudio } from "@/lib/long";

export const metadata: Metadata = { title: "Studio du modificateur" };
export const dynamic = "force-dynamic";

/** Studio du modificateur de voix (docs/67) : Luca règle lui-même une modification légère de sa voix et l'écoute sur
 * un extrait, avant / après, en quelques secondes ; le réglage enregistré se choisit ensuite pour une vidéo. */
export default async function VoiceStudioPage({ searchParams }: { searchParams: Promise<{ video?: string }> }) {
  const { video } = await searchParams;
  const data = await getVoiceStudio();
  const videoId = video && /^[0-9a-f-]{36}$/i.test(video) ? video : null;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Studio du modificateur"
        description="Change légèrement ta voix, curseur par curseur, et écoute tout de suite l’avant / après sur une de tes prises. Pas de conversion vers une autre voix : c’est la tienne, juste un peu déplacée."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href={videoId ? `/long/${videoId}` : "/long"}>
              <ArrowLeft /> {videoId ? "Retour à la vidéo" : "Vidéos longues"}
            </Link>
          </Button>
        }
      />
      <VoiceStudio data={data} videoId={videoId} />
    </div>
  );
}
