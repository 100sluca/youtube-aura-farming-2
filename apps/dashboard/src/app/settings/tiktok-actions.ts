"use server";

/**
 * Réglages → TikTok (docs/36-publication-tiktok.md) : clé API Zernio (chiffrée dans app_secrets, le navigateur n'en voit
 * que les 4 derniers caractères), comptes TikTok connectés à Zernio, lien chaîne YouTube → compte TikTok et options des
 * publications (app_settings « tiktok », lues par le worker).
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { encryptSecret } from "@/lib/crypto";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { ZERNIO_SECRET, getTikTokSettings, listZernioTikTokAccounts } from "@/lib/tiktok";
import type { TikTokAccount, TikTokSettings } from "@/lib/tiktok-types";

function fail(error: unknown): ActionResult {
  return { ok: false, message: error instanceof Error ? error.message : String((error as { message?: string })?.message ?? error) };
}

/** Vérifie la clé auprès de Zernio, puis l'enregistre chiffrée. */
export async function saveZernioKey(value: string): Promise<ActionResult & { hint?: string; accounts?: TikTokAccount[] }> {
  const secret = value.trim();
  if (secret.length < 16) return { ok: false, message: "Clé trop courte" };
  const check = await listZernioTikTokAccounts(secret);
  if (!check.ok) return { ok: false, message: `Clé refusée : ${check.message}` };
  try {
    const { error } = await supabaseAdmin()
      .from("app_secrets")
      .upsert({ name: ZERNIO_SECRET, value_encrypted: await encryptSecret(secret), hint: secret.slice(-4), updated_at: new Date().toISOString() });
    if (error) return fail(error);
  } catch (error) {
    return fail(error);
  }
  revalidatePath("/settings");
  return { ok: true, message: `Clé Zernio enregistrée (…${secret.slice(-4)}) · ${check.message}`, hint: secret.slice(-4), accounts: check.accounts };
}

export async function deleteZernioKey(): Promise<ActionResult> {
  const { error } = await supabaseAdmin().from("app_secrets").delete().eq("name", ZERNIO_SECRET);
  if (error) return fail(error);
  revalidatePath("/settings");
  return { ok: true, message: "Clé Zernio retirée : plus aucune publication TikTok ne part" };
}

export async function refreshTikTokAccounts(): Promise<ActionResult & { accounts: TikTokAccount[] }> {
  const res = await listZernioTikTokAccounts();
  return { ok: res.ok, message: res.message, accounts: res.accounts };
}

export interface TikTokSettingsInput {
  /** id de la chaîne YouTube → compte TikTok choisi ("" = aucun), publication automatique et rattrapage (docs/39). */
  links: { channel_id: string; account_id: string; username: string; enabled: boolean; backlog: boolean }[];
  allow_comment: boolean;
  allow_duet: boolean;
  allow_stitch: boolean;
  ai_label: boolean;
}

export async function saveTikTokSettings(input: TikTokSettingsInput): Promise<ActionResult> {
  const before = await getTikTokSettings();
  const now = new Date().toISOString();
  const channels: TikTokSettings["channels"] = {};
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
      // rattrapage (docs/39) : les vidéos déjà sorties sur YouTube partent une par une dans les créneaux restés vides
      backlog: Boolean(l.backlog),
    };
  }
  const value: TikTokSettings = {
    channels,
    allow_comment: Boolean(input.allow_comment),
    allow_duet: Boolean(input.allow_duet),
    allow_stitch: Boolean(input.allow_stitch),
    ai_label: Boolean(input.ai_label),
  };
  const { error } = await supabaseAdmin().from("app_settings").upsert({ key: "tiktok", value, updated_at: now });
  if (error) return fail(error);
  revalidatePath("/settings");
  revalidatePath("/calendar");
  const auto = Object.values(channels).filter((c) => c.enabled);
  const backlog = Object.values(channels).some((c) => c.backlog);
  return {
    ok: true,
    message:
      (auto.length
        ? `Enregistré : chaque Short programmé part aussi sur TikTok (${auto.map((c) => `@${c.username}`).join(", ")}), à la même heure que sur YouTube`
        : "Enregistré : aucune publication automatique sur TikTok") +
      (backlog ? ". Rattrapage actif : les anciennes vidéos prennent les créneaux restés vides, une par créneau" : ""),
  };
}
