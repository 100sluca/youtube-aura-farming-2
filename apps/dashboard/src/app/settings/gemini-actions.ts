"use server";

/**
 * Réglages → Gemini en ligne (docs/17-gemini-en-ligne.md) : enregistrer le compte, la durée et le modèle
 * (app_settings « gemini », lus par le worker), ouvrir Gemini dans le Chrome dédié pour s'y connecter, vérifier la
 * session Google. Séparé des modèles locaux (actions.ts) : on ne mélange pas les deux réglages.
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { getGeminiBrowserInfo, getGeminiSettings, openGeminiWindow } from "@/lib/gemini";
import { GEMINI_DURATIONS, type GeminiBrowserInfo, type GeminiSettings } from "@/lib/gemini-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

export async function saveGeminiSettings(input: GeminiSettings): Promise<ActionResult> {
  const authuser = Math.round(Number(input.authuser));
  if (!Number.isInteger(authuser) || authuser < 0 || authuser > 9) return { ok: false, message: "Numéro de compte entre 0 et 9" };
  if (!(GEMINI_DURATIONS as readonly string[]).includes(input.duration)) return { ok: false, message: "Durée inconnue" };
  const value: GeminiSettings = { authuser, model: String(input.model ?? "").trim().slice(0, 60), duration: input.duration };
  const { error } = await supabaseAdmin().from("app_settings").upsert({ key: "gemini", value, updated_at: new Date().toISOString() });
  if (error) return { ok: false, message: error.message };
  revalidatePath("/settings");
  return {
    ok: true,
    message: `Enregistré : compte n° ${authuser}, ${value.duration === "auto" ? "durée ajustée à chaque scène" : `clips de ${value.duration} s`}, ${value.model ? `modèle « ${value.model} »` : "modèle proposé par Gemini"}`,
  };
}

export async function openGemini(): Promise<ActionResult> {
  const settings = await getGeminiSettings();
  const res = await openGeminiWindow(settings.authuser);
  revalidatePath("/settings");
  return res.ok ? { ok: true, message: res.message } : { ok: false, message: res.message };
}

export async function checkGeminiBrowser(): Promise<ActionResult & { info?: GeminiBrowserInfo }> {
  const info = await getGeminiBrowserInfo();
  if (!info.running) return { ok: false, message: "Le Chrome dédié est fermé : « Ouvrir Gemini dans Chrome » pour le lancer", info };
  if (info.signedIn === true) return { ok: true, message: "Connecté à Google dans le Chrome dédié", info };
  if (info.signedIn === false) return { ok: false, message: "Pas encore connecté à Google dans le Chrome dédié", info };
  return { ok: false, message: "Session Google impossible à lire : regarde la fenêtre Chrome", info };
}
