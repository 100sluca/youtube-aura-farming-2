"use server";

/** Chaîne choisie dans l'en-tête : cookie lu par toutes les pages (lib/channel-server.ts). */
import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";

import { ALL_CHANNELS, CHANNEL_COOKIE } from "@/lib/channel";

export async function selectChannel(slug: string): Promise<void> {
  const store = await cookies();
  if (slug === ALL_CHANNELS) store.delete(CHANNEL_COOKIE);
  else if (/^[a-z0-9_-]{1,32}$/.test(slug)) store.set(CHANNEL_COOKIE, slug, { path: "/", sameSite: "lax", maxAge: 60 * 60 * 24 * 365 });
  revalidatePath("/", "layout");
}
