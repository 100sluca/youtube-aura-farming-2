"use server";

/**
 * Réglages IA depuis le dashboard : les deux chaînes de modèles (1er choix, 2e choix… : écriture, autres agents) et
 * plusieurs clés API par fournisseur (docs/24 §3). Les réglages vont dans app_settings (clé « llm »), les clés dans
 * app_secrets chiffrées (AES-GCM, CREDENTIALS_KEY, même format que les jetons YouTube ; gemini_api_key, puis
 * gemini_api_key_2, _3…) : le worker les lit à chaque appel et elles priment sur son .env. Le navigateur ne reçoit
 * jamais une clé, seulement ses 4 derniers caractères.
 */
import { revalidatePath } from "next/cache";

import { slugify } from "@/lib/channel";
import { decryptSecret, encryptSecret } from "@/lib/crypto";
import { getGenerationCatalog } from "@/lib/generation-data";
import { normalizeVoiceId, type GenerationSettings, type VoiceLang, type VoicePreviewState } from "@/lib/generation-types";
import { KEY_NAME, PROVIDER_ORDER, cleanChain, secretName, type ChainEntry, type ChainKind, type Provider } from "@/lib/llm-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

import type { ActionResult } from "@/app/production/actions";

type Keyed = Exclude<Provider, "ollama">;

function fail(error: unknown): ActionResult {
  return { ok: false, message: error instanceof Error ? error.message : String((error as { message?: string })?.message ?? error) };
}

const isKeyed = (v: unknown): v is Keyed => v === "gemini" || v === "anthropic" || v === "mistral";

/** Enregistre les deux chaînes ; les anciens champs (provider, models, fallbacks, writer_models) en sont déduits pour ce
 * qui les lit encore. */
export async function saveLlmSettings(input: {
  chains: Record<ChainKind, ChainEntry[]>;
  custom_models: Record<Provider, string[]>;
}): Promise<ActionResult> {
  const general = cleanChain(input.chains.default);
  const writer = cleanChain(input.chains.writer);
  if (!general.length) return { ok: false, message: "La chaîne des autres agents doit avoir au moins un modèle" };
  if (!writer.length) return { ok: false, message: "La chaîne d’écriture doit avoir au moins un modèle" };
  const firstModel = (chain: ChainEntry[], p: Provider) => chain.find((e) => e.provider === p)?.model ?? "";
  const models = Object.fromEntries(PROVIDER_ORDER.map((p) => [p, firstModel(general, p)]).filter(([, m]) => m));
  const value = {
    chains: { writer, default: general },
    provider: general[0].provider,
    fallbacks: [...new Set(general.map((e) => e.provider))].slice(1),
    models,
    writer_models: Object.fromEntries(
      PROVIDER_ORDER.map((p) => [p, firstModel(writer, p)]).filter(([p, m]) => m && m !== models[p as Provider]),
    ),
    custom_models: Object.fromEntries(PROVIDER_ORDER.map((p) => [p, [...new Set((input.custom_models[p] ?? []).map((m) => m.trim()).filter(Boolean))]])),
  };
  const { error } = await supabaseAdmin().from("app_settings").upsert({ key: "llm", value, updated_at: new Date().toISOString() });
  if (error) return fail(error);
  revalidatePath("/settings");
  return { ok: true, message: `Réglages enregistrés : écriture ${writer.map((e) => e.model).join(" → ")} ; autres agents ${general.map((e) => e.model).join(" → ")}` };
}

async function usedSlots(provider: Keyed): Promise<number[]> {
  const { data } = await supabaseAdmin().from("app_secrets").select("name").like("name", `${provider}_api_key%`);
  return (data ?? []).map((r) => KEY_NAME.exec(r.name as string)).filter((m) => m && m[1] === provider).map((m) => Number(m![2] ?? 1));
}

/** Ajoute une clé à la suite des clés du fournisseur (le premier numéro libre) ; renvoie son numéro et ses 4 derniers
 * caractères pour l'affichage. */
export async function saveSecret(provider: Provider, value: string): Promise<ActionResult & { slot?: number; hint?: string }> {
  if (!isKeyed(provider)) return { ok: false, message: "Ollama n'a pas de clé" };
  const secret = value.trim();
  if (secret.length < 8) return { ok: false, message: "Clé trop courte" };
  try {
    const used = await usedSlots(provider);
    let slot = 1;
    while (used.includes(slot)) slot += 1;
    const { error } = await supabaseAdmin()
      .from("app_secrets")
      .upsert({ name: secretName(provider, slot), value_encrypted: await encryptSecret(secret), hint: secret.slice(-4), updated_at: new Date().toISOString() });
    if (error) return fail(error);
    revalidatePath("/settings");
    return { ok: true, message: `Clé ${provider} n° ${slot} enregistrée (…${secret.slice(-4)})`, slot, hint: secret.slice(-4) };
  } catch (error) {
    return fail(error);
  }
}

export async function deleteSecret(provider: Provider, slot = 1): Promise<ActionResult> {
  if (!isKeyed(provider)) return { ok: false, message: "Ollama n'a pas de clé" };
  const { error } = await supabaseAdmin().from("app_secrets").delete().eq("name", secretName(provider, slot));
  if (error) return fail(error);
  revalidatePath("/settings");
  return { ok: true, message: `Clé ${provider} n° ${slot} retirée` };
}

/** La clé n° `slot`, sinon la première enregistrée. */
async function secretFor(provider: Provider, slot?: number): Promise<string | null> {
  if (!isKeyed(provider)) return null;
  const pick = slot ?? (await usedSlots(provider)).sort((a, b) => a - b)[0];
  if (!pick) return null;
  const { data } = await supabaseAdmin().from("app_secrets").select("value_encrypted").eq("name", secretName(provider, pick)).maybeSingle();
  return data?.value_encrypted ? decryptSecret(data.value_encrypted) : null;
}

/** Modèles visibles avec la clé Gemini enregistrée (ceux qui savent générer du texte). */
export async function listGeminiModels(): Promise<{ ok: boolean; models: string[]; message: string }> {
  const key = await secretFor("gemini");
  if (!key) return { ok: false, models: [], message: "Enregistrer d'abord la clé Gemini" };
  const res = await fetch("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", { headers: { "x-goog-api-key": key }, cache: "no-store" });
  if (!res.ok) return { ok: false, models: [], message: `Google répond ${res.status} : ${(await res.text()).slice(0, 200)}` };
  const body = (await res.json()) as { models?: { name: string; supportedGenerationMethods?: string[] }[] };
  const models = (body.models ?? [])
    .filter((m) => (m.supportedGenerationMethods ?? []).includes("generateContent"))
    .map((m) => m.name.replace(/^models\//, ""))
    .filter((n) => /^gemini/.test(n) && !/(image|tts|live|audio|embedding|robotics|transcribe|omni)/.test(n))
    .sort();
  return { ok: true, models, message: `${models.length} modèles texte disponibles avec cette clé` };
}

/** Appel minimal pour vérifier une clé et un modèle. */
export async function testLlm(provider: Provider, model: string, slot?: number): Promise<ActionResult> {
  const res = await testLlmWith(provider, model, slot);
  return slot && res.ok ? { ...res, message: `Clé n° ${slot} · ${res.message}` } : res;
}

async function testLlmWith(provider: Provider, model: string, slot?: number): Promise<ActionResult> {
  const m = model.trim();
  if (!m) return { ok: false, message: "Choisir un modèle" };
  try {
    if (provider === "gemini") {
      const key = await secretFor("gemini", slot);
      if (!key) return { ok: false, message: "Pas de clé Gemini enregistrée" };
      const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(m)}:generateContent`, {
        method: "POST",
        headers: { "x-goog-api-key": key, "Content-Type": "application/json" },
        body: JSON.stringify({ contents: [{ role: "user", parts: [{ text: "Réponds uniquement : OK" }] }], generationConfig: { maxOutputTokens: 20 } }),
        cache: "no-store",
      });
      if (!res.ok) return { ok: false, message: `Gemini ${m} : ${res.status} ${(await res.text()).slice(0, 300)}` };
      const body = (await res.json()) as { candidates?: { content?: { parts?: { text?: string }[] } }[] };
      const text = body.candidates?.[0]?.content?.parts?.map((p) => p.text ?? "").join("") ?? "";
      return { ok: true, message: `Gemini ${m} répond : « ${text.trim().slice(0, 60) || "(vide)"} »` };
    }
    if (provider === "anthropic") {
      const key = await secretFor("anthropic", slot);
      if (!key) return { ok: false, message: "Pas de clé Anthropic enregistrée" };
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json" },
        body: JSON.stringify({ model: m, max_tokens: 20, messages: [{ role: "user", content: "Réponds uniquement : OK" }] }),
        cache: "no-store",
      });
      if (!res.ok) return { ok: false, message: `Anthropic ${m} : ${res.status} ${(await res.text()).slice(0, 300)}` };
      const body = (await res.json()) as { content?: { text?: string }[] };
      return { ok: true, message: `Claude ${m} répond : « ${(body.content?.[0]?.text ?? "").trim().slice(0, 60)} »` };
    }
    if (provider === "mistral") {
      const key = await secretFor("mistral", slot);
      if (!key) return { ok: false, message: "Pas de clé Mistral enregistrée" };
      const res = await fetch("https://api.mistral.ai/v1/chat/completions", {
        method: "POST",
        headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
        body: JSON.stringify({ model: m, max_tokens: 20, messages: [{ role: "user", content: "Réponds uniquement : OK" }] }),
        cache: "no-store",
      });
      if (!res.ok) return { ok: false, message: `Mistral ${m} : ${res.status} ${(await res.text()).slice(0, 300)}` };
      const body = (await res.json()) as { choices?: { message?: { content?: string } }[] };
      return { ok: true, message: `Mistral ${m} répond : « ${(body.choices?.[0]?.message?.content ?? "").trim().slice(0, 60)} »` };
    }
    const res = await fetch("http://127.0.0.1:11434/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: m, stream: false, keep_alive: 0, messages: [{ role: "user", content: "Réponds uniquement : OK" }] }),
      cache: "no-store",
    });
    if (!res.ok) return { ok: false, message: `Ollama ${m} : ${res.status} ${(await res.text()).slice(0, 300)}` };
    const body = (await res.json()) as { message?: { content?: string } };
    return { ok: true, message: `Ollama ${m} répond : « ${(body.message?.content ?? "").trim().slice(0, 60)} »` };
  } catch (error) {
    return fail(error);
  }
}

/** Modèles de génération (app_settings « generation ») : le worker les lit à chaque job et les fige dans chaque
 * nouvelle production ; une production en cours garde les siens. */
export async function saveGenerationSettings(input: GenerationSettings): Promise<ActionResult> {
  const catalog = await getGenerationCatalog();
  const image = catalog.image.find((e) => e.name === input.image_workflow);
  const video = catalog.video.find((e) => e.name === input.video_workflow);
  if (!image || !video) return { ok: false, message: "Modèle inconnu du catalogue (services/worker/workflows/catalog.json)" };
  const voice = (lang: VoiceLang) => {
    const list = catalog.voices[lang];
    return list.find((v) => v.id === normalizeVoiceId(input.voices[lang] ?? "")) ?? list[0];
  };
  const fr = voice("fr");
  const en = voice("en");
  if (!fr || !en) return { ok: false, message: "Aucune voix dans le catalogue (services/worker/workflows/catalog.json)" };
  const value: GenerationSettings = {
    image_workflow: image.name,
    video_workflow: video.name,
    storyboard_candidates: Math.min(4, Math.max(1, Math.round(Number(input.storyboard_candidates) || 2))),
    // Voix Kokoro sous leur nom seul (« ff_siwis ») : format que comprend aussi un worker pas encore relancé
    voices: { fr: fr.id.replace(/^kokoro:/, ""), en: en.id.replace(/^kokoro:/, "") },
  };
  const { error } = await supabaseAdmin().from("app_settings").upsert({ key: "generation", value, updated_at: new Date().toISOString() });
  if (error) return fail(error);
  revalidatePath("/settings");
  const missing = [image, video].filter((e) => e.missing && e.missing.length > 0).map((e) => e.label);
  const notInstalled = [fr, en].filter((v) => v.missing.length > 0).map((v) => v.engineLabel);
  return {
    ok: true,
    message:
      `Enregistré : images ${image.label}, vidéo ${video.label}, voix ${fr.label} (${fr.engineLabel}). S'applique aux prochaines productions` +
      (missing.length ? ` · attention, fichiers absents de ComfyUI pour ${missing.join(" et ")}` : "") +
      (notInstalled.length ? ` · moteur de voix non installé : ${[...new Set(notInstalled)].join(", ")}` : ""),
  };
}

const PREVIEW_UNKNOWN: VoicePreviewState = { status: "unknown", label: null, error: null, audioUrl: null, durationS: null, elapsedS: null };

/** Essai de voix : met en file un job voice_preview (voie GPU du worker, priorité 5 : juste après la tâche en cours ;
 * un seul essai, pas de nouvelle tentative). La vitesse est celle de la chaîne de cette langue, comme en production. */
export async function previewVoice(input: { voice: string; lang: VoiceLang; text: string }): Promise<ActionResult & { jobId?: string }> {
  const lang: VoiceLang = input.lang === "en" ? "en" : "fr";
  const catalog = await getGenerationCatalog();
  const voice = catalog.voices[lang].find((v) => v.id === normalizeVoiceId(input.voice));
  if (!voice) return { ok: false, message: "Voix inconnue du catalogue" };
  if (voice.missing.length) return { ok: false, message: `${voice.engineLabel} n’est pas installé (${voice.missing.join(", ")})` };
  const db = supabaseAdmin();
  const { data: channel } = await db.from("channels").select("voice_speed").eq("lang", lang).limit(1).maybeSingle();
  const payload = { voice: voice.id, lang, text: input.text.replace(/\s+/g, " ").trim().slice(0, 600), speed: Number(channel?.voice_speed) || null };
  const { data, error } = await db.from("jobs").insert({ type: "voice_preview", priority: 5, max_attempts: 1, payload }).select("id").single();
  if (error) return fail(error);
  return { ok: true, message: "Essai en file", jobId: data.id as string };
}

export async function getVoicePreview(jobId: string): Promise<VoicePreviewState> {
  if (!/^[0-9a-f-]{36}$/i.test(jobId)) return PREVIEW_UNKNOWN;
  const { data } = await supabaseAdmin().from("jobs").select("status, progress_label, error, result").eq("id", jobId).eq("type", "voice_preview").maybeSingle();
  if (!data) return PREVIEW_UNKNOWN;
  const result = (data.result ?? {}) as { duration_s?: number; elapsed_s?: number };
  return {
    status: data.status as VoicePreviewState["status"],
    label: (data.progress_label as string | null) ?? null,
    error: (data.error as string | null) ?? null,
    audioUrl: data.status === "done" ? `/api/voice-preview/${jobId}` : null,
    durationS: result.duration_s ?? null,
    elapsedS: result.elapsed_s ?? null,
  };
}

export async function setAutoPublish(slug: string, enabled: boolean): Promise<ActionResult> {
  const { error } = await supabaseAdmin().from("channels").update({ auto_publish: enabled }).eq("slug", slug);
  if (error) return fail(error);
  revalidatePath("/settings");
  return { ok: true, message: enabled ? "Publication automatique activée" : "Validation humaine avant publication" };
}

// ---------------------------------------------------------------------------------------------------------------
// Chaînes YouTube (migration 0008) : on en ajoute autant qu'on veut ; chacune a un nom, une langue (voix, sous-titres,
// métadonnées) et sa connexion OAuth. La connexion lance l'import de l'historique (job import_channel).
// ---------------------------------------------------------------------------------------------------------------

const LANGS = ["fr", "en"] as const;
type Lang = (typeof LANGS)[number];
const isLang = (v: unknown): v is Lang => typeof v === "string" && (LANGS as readonly string[]).includes(v);

export async function createChannel(name: string, lang: string): Promise<ActionResult & { slug?: string }> {
  const clean = name.trim().slice(0, 80);
  if (clean.length < 2) return { ok: false, message: "Donner un nom à la chaîne" };
  if (!isLang(lang)) return { ok: false, message: "Langue inconnue" };
  const db = supabaseAdmin();
  const { data: existing } = await db.from("channels").select("slug");
  const taken = new Set((existing ?? []).map((c) => c.slug as string));
  const base = slugify(clean);
  let slug = base;
  for (let i = 2; taken.has(slug); i++) slug = `${base.slice(0, 28)}-${i}`;
  const { error } = await db.from("channels").insert({ slug, name: clean, lang, auto_publish: false, is_active: true });
  if (error) return fail(error);
  revalidatePath("/", "layout");
  return { ok: true, message: `Chaîne « ${clean} » ajoutée : connecte-la maintenant à YouTube.`, slug };
}

export async function updateChannel(id: string, name: string, lang: string): Promise<ActionResult> {
  const clean = name.trim().slice(0, 80);
  if (clean.length < 2) return { ok: false, message: "Donner un nom à la chaîne" };
  if (!isLang(lang)) return { ok: false, message: "Langue inconnue" };
  const { error } = await supabaseAdmin().from("channels").update({ name: clean, lang }).eq("id", id);
  if (error) return fail(error);
  revalidatePath("/", "layout");
  return { ok: true, message: "Chaîne mise à jour (la langue s’applique aux prochaines vidéos)" };
}

/** Supprimer une chaîne : seulement si elle n'a aucune vidéo produite (l'historique importé part avec elle). */
export async function deleteChannel(id: string): Promise<ActionResult> {
  const db = supabaseAdmin();
  const { count } = await db.from("videos").select("id", { count: "exact", head: true }).eq("channel_id", id).eq("origin", "app");
  if ((count ?? 0) > 0) return { ok: false, message: "Cette chaîne a des vidéos produites : supprime-les d’abord depuis la Bibliothèque" };
  const imported = await db.from("videos").delete().eq("channel_id", id).eq("origin", "imported");
  if (imported.error) return fail(imported.error);
  const { error } = await db.from("channels").delete().eq("id", id);
  if (error) return fail(error);
  revalidatePath("/", "layout");
  return { ok: true, message: "Chaîne supprimée" };
}

/** Importer (ou mettre à jour) l'historique YouTube d'une chaîne connectée : vidéos déjà en ligne, marquées « Importée ». */
export async function importChannelHistory(id: string): Promise<ActionResult> {
  const db = supabaseAdmin();
  const { data: ch } = await db.from("channels").select("youtube_channel_id").eq("id", id).maybeSingle();
  if (!ch?.youtube_channel_id) return { ok: false, message: "Connecter d’abord la chaîne à YouTube" };
  const { data: pending } = await db.from("jobs").select("id").eq("type", "import_channel").eq("channel_id", id).in("status", ["queued", "running"]).limit(1);
  if ((pending ?? []).length) return { ok: true, message: "Import déjà en cours" };
  const { error } = await db.from("jobs").insert({ type: "import_channel", channel_id: id, priority: 70 });
  if (error) return fail(error);
  revalidatePath("/", "layout");
  return { ok: true, message: "Import en file : les vidéos apparaîtront dans la Bibliothèque (marquées « Importée »)" };
}
