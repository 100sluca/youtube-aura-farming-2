"use server";

/**
 * Réglages → Instagram (docs/48-publication-instagram.md) : comptes Instagram connectés à Zernio, lien chaîne YouTube →
 * compte Instagram et options des Reels (app_settings « instagram », lues par le worker). La clé Zernio se règle dans
 * la carte TikTok.
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { getInstagramSettings, listZernioInstagramAccounts } from "@/lib/instagram";
import type { InstagramAccount, InstagramSettings } from "@/lib/instagram-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

export async function refreshInstagramAccounts(): Promise<ActionResult & { accounts: InstagramAccount[] }> {
  const res = await listZernioInstagramAccounts();
  return { ok: res.ok, message: res.message, accounts: res.accounts };
}

export interface InstagramSettingsInput {
  /** id de la chaîne YouTube → compte Instagram choisi ("" = aucun) et publication automatique. */
  links: { channel_id: string; account_id: string; username: string; enabled: boolean }[];
  share_to_feed: boolean;
  ai_label: boolean;
}

export async function saveInstagramSettings(input: InstagramSettingsInput): Promise<ActionResult> {
  const before = await getInstagramSettings();
  const now = new Date().toISOString();
  const channels: InstagramSettings["channels"] = {};
  for (const l of input.links) {
    if (!l.account_id) continue;
    const prev = before.channels[l.channel_id];
    // l'activation (ou un changement de compte) date le premier créneau concerné : rien d'ancien ne part en rafale
    const keep = prev && prev.enabled && prev.account_id === l.account_id;
    channels[l.channel_id] = {
      account_id: l.account_id,
      username: l.username,
      enabled: Boolean(l.enabled),
      enabled_at: l.enabled ? (keep ? prev.enabled_at : now) : null,
    };
  }
  const value: InstagramSettings = { channels, share_to_feed: Boolean(input.share_to_feed), ai_label: Boolean(input.ai_label) };
  const { error } = await supabaseAdmin().from("app_settings").upsert({ key: "instagram", value, updated_at: now });
  if (error) return { ok: false, message: error.message };
  revalidatePath("/settings");
  const auto = Object.values(channels).filter((c) => c.enabled);
  return {
    ok: true,
    message: auto.length
      ? `Enregistré : chaque Short programmé part aussi en Reel sur Instagram (${auto.map((c) => `@${c.username}`).join(", ")}), à la même heure que sur YouTube`
      : "Enregistré : aucune publication automatique sur Instagram",
  };
}
