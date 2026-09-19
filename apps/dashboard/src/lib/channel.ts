import type { ChannelLang } from "@/lib/types";

/** Normalise le paramètre d'URL `?channel=` (Toutes / FR / EN). */
export function parseChannel(value: string | string[] | null | undefined): ChannelLang | undefined {
  const v = Array.isArray(value) ? value[0] : value;
  return v === "fr" || v === "en" ? v : undefined;
}

/** Ajoute `?channel=` à un chemin si un filtre est actif. */
export function withChannel(href: string, channel: ChannelLang | undefined): string {
  if (!channel) return href;
  return `${href}${href.includes("?") ? "&" : "?"}channel=${channel}`;
}
