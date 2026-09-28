/** Chaîne sélectionnée dans l'en-tête, lue dans le cookie (Server Components et actions serveur uniquement). */
import { cookies } from "next/headers";

import { CHANNEL_COOKIE } from "@/lib/channel";
import { getChannels } from "@/lib/data";
import type { Channel } from "@/lib/types";

export interface ChannelContext {
  channels: Channel[];
  /** Chaîne choisie dans l'en-tête ; undefined = toutes les chaînes. */
  selected: Channel | undefined;
}

export async function getChannelContext(): Promise<ChannelContext> {
  const [channels, store] = await Promise.all([getChannels(), cookies()]);
  const slug = store.get(CHANNEL_COOKIE)?.value;
  return { channels, selected: channels.find((c) => c.slug === slug) };
}

/** Chaîne pour créer une vidéo : celle de l'en-tête, sinon la première chaîne active. */
export function creationChannel({ channels, selected }: ChannelContext): Channel | undefined {
  return selected ?? channels.find((c) => c.is_active) ?? channels[0];
}
