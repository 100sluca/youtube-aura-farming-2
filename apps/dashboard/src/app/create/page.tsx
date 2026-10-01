import type { Metadata } from "next";
import Link from "next/link";

import { AutoRefresh } from "@/components/auto-refresh";
import { AutopilotCard } from "@/components/create/autopilot-card";
import { CreationBoard } from "@/components/create/creation-board";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { getAutopilot } from "@/lib/autopilot";
import { creationChannel, getChannelContext } from "@/lib/channel-server";
import { getCreationData } from "@/lib/creation";

export const metadata: Metadata = { title: "Création" };

export default async function CreatePage() {
  const context = await getChannelContext();
  const channel = creationChannel(context);
  if (!channel) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed p-10 text-center">
        <p className="text-muted-foreground text-sm">Aucune chaîne : commence par en ajouter une.</p>
        <Button asChild>
          <Link href="/settings?add_channel=1#chaines">Ajouter une chaîne</Link>
        </Button>
      </div>
    );
  }
  const [data, autopilot] = await Promise.all([getCreationData(channel), getAutopilot()]);
  // une scène refaite ou réinventée revient d'elle-même (docs/27)
  const busy = data.ideaJobs.length > 0 || data.preparing.length > 0 || data.storyboards.some((c) => c.storyboard?.some((s) => s.busy));

  return (
    <div className="flex flex-col gap-6">
      <AutoRefresh seconds={busy ? 5 : 30} />
      <PageHeader description="Choisis la chaîne et le thème, génère des idées notées sur leur potentiel, puis garde (✓) ou écarte (✗). Chaque ✓ écrit le script et prépare les images ; tu regardes le storyboard ici, et son ✓ fabrique la vidéo d’une traite." />
      <AutopilotCard channelId={channel.id} series={data.series} defaultSeries={data.defaultSeries} status={autopilot} />
      <CreationBoard key={channel.id} channels={context.channels} channel={channel} data={data} />
    </div>
  );
}
