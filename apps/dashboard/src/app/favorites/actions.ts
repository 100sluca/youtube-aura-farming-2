"use server";

/**
 * Gestes des favoris (docs/19-favoris.md) : l'étoile d'un storyboard (Création, fiche d'une vidéo de la Bibliothèque)
 * le garde ou le retire ; la page Favoris le refait, avec ses images ou de nouvelles, ou le retire.
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { creationChannel, getChannelContext } from "@/lib/channel-server";
import { removeFavorite, restoreFavorite, saveFavorite, type FavoriteResult } from "@/lib/favorites";
import { supabaseAdmin } from "@/lib/supabase-admin";

export type FavoriteToggle = { ok: boolean; message: string; favorite: boolean };

function refresh() {
  revalidatePath("/", "layout");
}

function result(res: FavoriteResult): ActionResult {
  if (res.ok) refresh();
  return res.ok ? { ok: true, message: res.message } : { ok: false, message: res.message };
}

/** Étoile : garde le storyboard de cette production, ou le retire s'il est déjà gardé. */
export async function toggleFavorite(productionId: string): Promise<FavoriteToggle> {
  const { data, error } = await supabaseAdmin().from("favorites").select("id").eq("production_id", productionId).maybeSingle();
  if (error) return { ok: false, message: error.message, favorite: false };
  const res = data ? await removeFavorite(data.id as string) : await saveFavorite(productionId);
  if (res.ok) refresh();
  return { ok: res.ok, message: res.message, favorite: res.ok ? !data : Boolean(data) };
}

export async function deleteFavorite(favoriteId: string): Promise<ActionResult> {
  return result(await removeFavorite(favoriteId));
}

/** Refaire : même chaîne que l'original (sinon celle de l'en-tête), avec ces images ou de nouvelles. */
export async function remakeFavorite(favoriteId: string, keepImages: boolean): Promise<ActionResult> {
  const channel = creationChannel(await getChannelContext());
  return result(await restoreFavorite(favoriteId, keepImages, channel?.id ?? null));
}
