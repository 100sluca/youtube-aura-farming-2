"use server";

/**
 * Bibliothèque → « Publier sur TikTok » (docs/36-publication-tiktok.md) : met en file la publication d'une vidéo montée
 * par Zernio (fonction SQL request_tiktok_publish, migration 0024). Le worker la programme au créneau YouTube s'il est à
 * venir, sinon la publie tout de suite.
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { getLibraryTikTok, getTikTokSettings, zernioKey } from "@/lib/tiktok";
import type { LibraryTikTok } from "@/lib/tiktok-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

export async function publishOnTikTok(videoId: string): Promise<ActionResult & { tiktok?: LibraryTikTok }> {
  const db = supabaseAdmin();
  const { data: video } = await db.from("videos").select("channel_id").eq("id", videoId).maybeSingle();
  if (!video) return { ok: false, message: "Vidéo introuvable" };
  const [settings, key] = await Promise.all([getTikTokSettings(), zernioKey()]);
  if (!key) return { ok: false, message: "Clé Zernio absente : Réglages → TikTok" };
  if (!settings.channels[video.channel_id as string]?.account_id) return { ok: false, message: "Aucun compte TikTok relié à cette chaîne : Réglages → TikTok" };
  const { error } = await db.rpc("request_tiktok_publish", { p_video: videoId });
  if (error) return { ok: false, message: error.message };
  revalidatePath("/library");
  return { ok: true, message: "Publication TikTok en file : le worker s’en charge", tiktok: await getLibraryTikTok(videoId, video.channel_id as string) };
}
