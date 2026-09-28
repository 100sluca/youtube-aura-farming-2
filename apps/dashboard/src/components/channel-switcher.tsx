"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, ChevronsUpDown, Layers, Plus } from "lucide-react";

import { selectChannel } from "@/app/channel-actions";
import { ChannelAvatar } from "@/components/channel-badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ALL_CHANNELS } from "@/lib/channel";
import { LANG_LABELS } from "@/lib/labels";
import type { Channel } from "@/lib/types";

/** Chaîne affichée partout (Vue d'ensemble, Bibliothèque, Calendrier, Création) ; « Toutes » cumule. */
export function ChannelSwitcher({ channels, selected }: { channels: Channel[]; selected: string | null }) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const current = channels.find((c) => c.slug === selected);

  function choose(slug: string) {
    startTransition(async () => {
      await selectChannel(slug);
      router.refresh();
    });
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="max-w-56 gap-2" disabled={pending} aria-label="Chaîne affichée">
          {current ? <ChannelAvatar channel={current} className="size-5" /> : <Layers className="size-4" />}
          <span className="hidden truncate sm:inline">{current?.name ?? "Toutes les chaînes"}</span>
          <ChevronsUpDown className="text-muted-foreground size-3.5 shrink-0" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="text-muted-foreground text-xs font-normal">Chaîne affichée</DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => choose(ALL_CHANNELS)}>
          <Layers className="size-4" />
          Toutes les chaînes
          {!current ? <Check className="ml-auto size-4" /> : null}
        </DropdownMenuItem>
        {channels.map((channel) => (
          <DropdownMenuItem key={channel.id} onSelect={() => choose(channel.slug)}>
            <ChannelAvatar channel={channel} className="size-5" />
            <span className="flex min-w-0 flex-col">
              <span className="truncate">{channel.name}</span>
              <span className="text-muted-foreground text-[11px]">
                {LANG_LABELS[channel.lang]} · {channel.youtube_channel_id ? "connectée à YouTube" : "pas encore connectée"}
              </span>
            </span>
            {current?.id === channel.id ? <Check className="ml-auto size-4" /> : null}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings?add_channel=1#chaines">
            <Plus className="size-4" />
            Ajouter une chaîne
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
