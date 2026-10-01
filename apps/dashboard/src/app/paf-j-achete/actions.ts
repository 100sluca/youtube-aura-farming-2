"use server";

/**
 * Onglet « Paf, j'achète » (docs/50-paf-j-achete.md) : clé du second compte Zernio (chiffrée dans app_secrets, le
 * navigateur n'en voit que les 4 derniers caractères), compte Instagram, légende et interrupteur (app_settings
 * « paf_j_achete », lus par le worker).
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { encryptSecret } from "@/lib/crypto";
import { getPafSettings, listPafAccounts, nextPafSlot, pafFolder, pafVideo } from "@/lib/paf";
import { PAF_SECRET, PAF_SETTINGS_KEY, type PafAccount, type PafSettings } from "@/lib/paf-types";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { zernioKey } from "@/lib/tiktok";

const PATH = "/paf-j-achete";
const LIVE = ["queued", "sending", "scheduled", "pending", "publishing", "processing", "uploading"];

function fail(error: unknown): ActionResult {
  return { ok: false, message: error instanceof Error ? error.message : String((error as { message?: string })?.message ?? error) };
}

async function write(value: PafSettings): Promise<string | null> {
  const { error } = await supabaseAdmin().from("app_settings").upsert({ key: PAF_SETTINGS_KEY, value, updated_at: new Date().toISOString() });
  return error ? error.message : null;
}

/** Vérifie la clé auprès de Zernio, puis l'enregistre chiffrée. Jamais la clé du compte TikTok / @arzakparker. */
export async function savePafKey(value: string): Promise<ActionResult & { hint?: string; accounts?: PafAccount[] }> {
  const secret = value.trim();
  if (secret.length < 16) return { ok: false, message: "Clé trop courte" };
  if (secret === (await zernioKey().catch(() => null))) {
    return { ok: false, message: "C’est la clé Zernio de TikTok / @arzakparker : il faut celle de l’autre compte Zernio" };
  }
  const check = await listPafAccounts(secret);
  if (!check.ok) return { ok: false, message: `Clé refusée : ${check.message}` };
  try {
    const { error } = await supabaseAdmin()
      .from("app_secrets")
      .upsert({ name: PAF_SECRET, value_encrypted: await encryptSecret(secret), hint: secret.slice(-4), updated_at: new Date().toISOString() });
    if (error) return fail(error);
  } catch (error) {
    return fail(error);
  }
  revalidatePath(PATH);
  return { ok: true, message: `Clé enregistrée (…${secret.slice(-4)}) · ${check.message}`, hint: secret.slice(-4), accounts: check.accounts };
}

export async function deletePafKey(): Promise<ActionResult> {
  const { error } = await supabaseAdmin().from("app_secrets").delete().eq("name", PAF_SECRET);
  if (error) return fail(error);
  revalidatePath(PATH);
  return { ok: true, message: "Clé retirée : plus rien ne part le vendredi" };
}

export async function refreshPafAccounts(): Promise<ActionResult & { accounts: PafAccount[] }> {
  const res = await listPafAccounts();
  return { ok: res.ok, message: res.message, accounts: res.accounts };
}

export interface PafSettingsInput {
  account_id: string;
  username: string;
  captions: string[];
  share_to_feed: boolean;
}

export async function savePafSettings(input: PafSettingsInput): Promise<ActionResult> {
  const before = await getPafSettings();
  const captions = input.captions.map((c) => c.trim().slice(0, 2200)).filter(Boolean);
  const error = await write({
    ...before,
    account_id: input.account_id,
    username: input.username,
    captions,
    share_to_feed: Boolean(input.share_to_feed),
  });
  if (error) return { ok: false, message: error };
  revalidatePath(PATH);
  return {
    ok: true,
    message: `Enregistré${captions.length > 1 ? ` : ${captions.length} légendes, une tirée au sort à chaque vendredi` : captions.length ? " : toujours la même légende" : " : sans légende"} (vaut pour les vendredis pas encore envoyés à Zernio)`,
  };
}

/** Interrupteur. Coupé : rien ne part plus, et le Reel déjà programmé chez Zernio est supprimé. */
export async function setPafEnabled(enabled: boolean): Promise<ActionResult> {
  const db = supabaseAdmin();
  const before = await getPafSettings();
  if (enabled) {
    if (!(await db.from("app_secrets").select("name").eq("name", PAF_SECRET).maybeSingle()).data) return { ok: false, message: "Coller d’abord la clé Zernio de ce compte" };
    if (!before.account_id) return { ok: false, message: "Choisir d’abord le compte Instagram" };
    if (!(await pafVideo(await pafFolder()))) return { ok: false, message: "Mettre d’abord la vidéo (.mp4) dans le dossier" };
    const error = await write({ ...before, enabled: true, enabled_at: before.enabled ? before.enabled_at : new Date().toISOString() });
    if (error) return { ok: false, message: error };
    revalidatePath(PATH);
    const slot = nextPafSlot();
    const first = slot.getTime() < Date.now() ? "le vendredi suivant" : `vendredi ${slot.toLocaleDateString("fr-FR", { day: "numeric", month: "long", timeZone: "Europe/Paris" })}`;
    return { ok: true, message: `Activé : premier envoi ${first} à 7 h (programmé chez Zernio 2 jours avant)` };
  }

  const error = await write({ ...before, enabled: false, enabled_at: null });
  if (error) return { ok: false, message: error };
  await db.from("jobs").update({ status: "cancelled", finished_at: new Date().toISOString() }).eq("type", "paf_publish").eq("status", "queued");
  const { data: live } = await db.from("paf_posts").select("friday, post_id").in("status", LIVE);
  let removed = 0;
  for (const row of live ?? []) {
    if (row.post_id) {
      await db.from("jobs").insert({ type: "paf_publish", priority: 25, max_attempts: 3, payload: { friday: row.friday, delete_post: row.post_id, source: "onglet" } });
      removed += 1;
    } else {
      await db.from("paf_posts").update({ status: "cancelled", updated_at: new Date().toISOString() }).eq("friday", row.friday);
    }
  }
  revalidatePath(PATH);
  return { ok: true, message: removed ? "Coupé : le Reel déjà programmé est retiré de Zernio" : "Coupé : plus rien ne part le vendredi" };
}

/** Relance un vendredi en échec (publié tout de suite si 7 h est passé). */
export async function retryPaf(friday: string): Promise<ActionResult> {
  const db = supabaseAdmin();
  const { data: row } = await db.from("paf_posts").select("status").eq("friday", friday).maybeSingle();
  if (row?.status !== "failed") return { ok: false, message: "Seul un vendredi en échec se relance" };
  const { data: busy } = await db.from("jobs").select("id").eq("type", "paf_publish").in("status", ["queued", "running"]).limit(1);
  if (busy?.length) return { ok: false, message: "Un envoi est déjà en cours" };
  await db.from("paf_posts").update({ status: "queued", error: null, updated_at: new Date().toISOString() }).eq("friday", friday);
  const { error } = await db.from("jobs").insert({ type: "paf_publish", priority: 30, max_attempts: 3, payload: { friday, source: "onglet" } });
  if (error) return fail(error);
  revalidatePath(PATH);
  return { ok: true, message: "Relancé : le worker le renvoie dans la minute" };
}
