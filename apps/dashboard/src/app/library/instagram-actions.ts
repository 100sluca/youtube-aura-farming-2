"use server";

/**
 * Bibliothèque → « Publier sur Instagram » (docs/48-publication-instagram.md) : met en file le Reel d'une vidéo montée
 * (fonction SQL request_instagram_publish, migration 0036). Le worker le programme au créneau YouTube s'il est à venir,
 * sinon le publie tout de suite.
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { getInstagramSettings, getLibraryInstagram } from "@/lib/instagram";
import type { LibraryInstagram } from "@/lib/instagram-types";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { zernioKey } from "@/lib/tiktok";

export async function publishOnInstagram(videoId: string): Promise<ActionResult & { instagram?: LibraryInstagram }> {
  const db = supabaseAdmin();
  const { data: video } = await db.from("videos").select("channel_id").eq("id", videoId).maybeSingle();
  if (!video) return { ok: false, message: "Vidéo introuvable" };
  const [settings, key] = await Promise.all([getInstagramSettings(), zernioKey()]);
  if (!key) return { ok: false, message: "Clé Zernio absente : Réglages → TikTok" };
  if (!settings.channels[video.channel_id as string]?.account_id) return { ok: false, message: "Aucun compte Instagram relié à cette chaîne : Réglages → Instagram" };
  const { error } = await db.rpc("request_instagram_publish", { p_video: videoId });
  if (error) return { ok: false, message: error.message };
  revalidatePath("/library");
  return { ok: true, message: "Reel en file : le worker s’en charge", instagram: await getLibraryInstagram(videoId, video.channel_id as string) };
}
