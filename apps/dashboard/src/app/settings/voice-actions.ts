"use server";

/**
 * Clés Gemini réservées à la voix (Réglages → Modèles de génération → Jeu des voix, docs/41 §8) : Gemini 3.8 Flash TTS
 * les prend avant celles du LLM (Réglages → IA), pour que les voix ne mangent pas le quota des scripts. Même stockage que
 * les clés du LLM : app_secrets chiffrées (AES-GCM, CREDENTIALS_KEY), gemini_voice_api_key puis _2, _3… ; le navigateur
 * n'en voit que les 4 derniers caractères.
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { decryptSecret, encryptSecret } from "@/lib/crypto";
import { supabaseAdmin } from "@/lib/supabase-admin";

const VOICE_KEY = /^gemini_voice_api_key(?:_(\d+))?$/;
const TTS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions";
const TTS_MODEL = "gemini-3.8-flash-tts";

const nameOf = (slot: number) => (slot <= 1 ? "gemini_voice_api_key" : `gemini_voice_api_key_${slot}`);

async function usedSlots(): Promise<number[]> {
  const { data } = await supabaseAdmin().from("app_secrets").select("name").like("name", "gemini_voice_api_key%");
  return (data ?? []).map((r) => VOICE_KEY.exec(r.name as string)).filter((m): m is RegExpExecArray => m !== null).map((m) => Number(m[1] ?? 1));
}

function fail(error: unknown): ActionResult {
  return { ok: false, message: error instanceof Error ? error.message : String((error as { message?: string })?.message ?? error) };
}

/** Ajoute une clé de la voix à la suite des autres (premier numéro libre). */
export async function saveVoiceKey(value: string): Promise<ActionResult & { slot?: number; hint?: string }> {
  const secret = value.trim();
  if (secret.length < 8) return { ok: false, message: "Clé trop courte" };
  try {
    const used = await usedSlots();
    let slot = 1;
    while (used.includes(slot)) slot += 1;
    const { error } = await supabaseAdmin()
      .from("app_secrets")
      .upsert({ name: nameOf(slot), value_encrypted: await encryptSecret(secret), hint: secret.slice(-4), updated_at: new Date().toISOString() });
    if (error) return fail(error);
    revalidatePath("/settings");
    return { ok: true, message: `Clé de la voix n° ${slot} enregistrée (…${secret.slice(-4)})`, slot, hint: secret.slice(-4) };
  } catch (error) {
    return fail(error);
  }
}

export async function deleteVoiceKey(slot: number): Promise<ActionResult> {
  const { error } = await supabaseAdmin().from("app_secrets").delete().eq("name", nameOf(slot));
  if (error) return fail(error);
  revalidatePath("/settings");
  return { ok: true, message: `Clé de la voix n° ${slot} retirée` };
}

/** Fait dire un mot à Gemini TTS avec la clé n° `slot` : la clé marche-t-elle pour la voix, et avec quel quota ? */
export async function testVoiceKey(slot: number): Promise<ActionResult> {
  try {
    const { data } = await supabaseAdmin().from("app_secrets").select("value_encrypted").eq("name", nameOf(slot)).maybeSingle();
    if (!data?.value_encrypted) return { ok: false, message: `Pas de clé de la voix n° ${slot}` };
    const key = await decryptSecret(data.value_encrypted as string);
    const started = Date.now();
    const res = await fetch(TTS_URL, {
      method: "POST",
      headers: { "x-goog-api-key": key, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: TTS_MODEL,
        input: [{ type: "user_input", content: [{ type: "text", text: "Bonjour." }] }],
        response_format: { type: "audio" },
        generation_config: { speech_config: [{ voice: "Kore" }] },
      }),
      cache: "no-store",
    });
    if (!res.ok) {
      const body = (await res.text()).slice(0, 200);
      return { ok: false, message: res.status === 429 ? `Clé n° ${slot} : quota de la voix épuisé pour aujourd’hui (${body})` : `Clé n° ${slot} : ${res.status} ${body}` };
    }
    return { ok: true, message: `Clé n° ${slot} : Gemini ${TTS_MODEL} répond en ${((Date.now() - started) / 1000).toFixed(1)} s` };
  } catch (error) {
    return fail(error);
  }
}
