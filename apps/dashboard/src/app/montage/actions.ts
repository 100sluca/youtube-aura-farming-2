"use server";

/**
 * Actions de l'onglet Montage (docs/23-montage.md) : enregistrer, dupliquer, renommer, supprimer un modèle de montage,
 * choisir celui de toutes les vidéos (SQL set_default_montage_template), rendu exact (job montage_preview du worker),
 * réglages d'une musique (docs/26-musique.md), suppression d'une police ajoutée. Le worker lit le modèle par défaut et
 * les musiques à chaque montage.
 */
import { promises as fs } from "node:fs";

import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { IS_MOCK } from "@/lib/data";
import { fontPath } from "@/lib/font-files";
import { musicTrackSchema, schemaError, templateSchema } from "@/lib/montage-schema";
import { audioConstants } from "@/lib/music-library";
import type { MontageFormat, MontagePreviewState, MontageTemplate } from "@/lib/montage-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

const UUID = /^[0-9a-f-]{36}$/i;

function fail(error: unknown): ActionResult {
  const message = error instanceof Error ? error.message : String((error as { message?: string })?.message ?? error);
  if (/montage_templates_name_key|duplicate key/.test(message)) return { ok: false, message: "Un modèle porte déjà ce nom" };
  if (/montage_templates.*does not exist|relation .*montage_templates/.test(message)) {
    return { ok: false, message: "Migration 0013 absente : relance le lanceur (il applique les migrations)" };
  }
  return { ok: false, message };
}

function cleanName(name: string): string | null {
  const n = name.replace(/\s+/g, " ").trim();
  return n.length >= 1 && n.length <= 60 ? n : null;
}

function check(template: MontageTemplate): { ok: true; value: unknown } | { ok: false; message: string } {
  const parsed = templateSchema.safeParse(template);
  return parsed.success ? { ok: true, value: parsed.data } : { ok: false, message: `Réglage refusé : ${schemaError(parsed.error)}` };
}

/** Enregistre un modèle : met à jour `id`, ou en crée un (nom obligatoire). `makeDefault` : il sert aussitôt à toutes
 * les vidéos. Renvoie l'identifiant du modèle. */
export async function saveMontageTemplate(input: {
  id: string | null;
  name: string;
  template: MontageTemplate;
  makeDefault?: boolean;
}): Promise<ActionResult & { id?: string }> {
  if (IS_MOCK) return { ok: false, message: "Indisponible en mode démo" };
  const name = cleanName(input.name);
  if (!name) return { ok: false, message: "Nom de 1 à 60 caractères" };
  const valid = check(input.template);
  if (!valid.ok) return valid;
  const db = supabaseAdmin();
  let id = input.id;
  if (id) {
    if (!UUID.test(id)) return { ok: false, message: "Modèle inconnu" };
    const { error } = await db.from("montage_templates").update({ name, template: valid.value }).eq("id", id);
    if (error) return fail(error);
  } else {
    const { data, error } = await db.from("montage_templates").insert({ name, template: valid.value }).select("id").single();
    if (error) return fail(error);
    id = data.id as string;
  }
  if (input.makeDefault) {
    const { error } = await db.rpc("set_default_montage_template", { p_id: id });
    if (error) return fail(error);
  }
  revalidatePath("/montage");
  const { data: row } = await db.from("montage_templates").select("is_default").eq("id", id).maybeSingle();
  return {
    ok: true,
    id,
    message: row?.is_default
      ? `« ${name} » enregistré : il sert à tous les prochains montages`
      : `« ${name} » enregistré (il ne sert pas encore : « Utiliser pour toutes les vidéos »)`,
  };
}

export async function setDefaultMontageTemplate(id: string): Promise<ActionResult> {
  if (IS_MOCK) return { ok: false, message: "Indisponible en mode démo" };
  if (!UUID.test(id)) return { ok: false, message: "Modèle inconnu" };
  const { error } = await supabaseAdmin().rpc("set_default_montage_template", { p_id: id });
  if (error) return fail(error);
  revalidatePath("/montage");
  return { ok: true, message: "Ce modèle sert désormais à tous les prochains montages" };
}

export async function renameMontageTemplate(id: string, name: string): Promise<ActionResult> {
  if (IS_MOCK) return { ok: false, message: "Indisponible en mode démo" };
  const clean = cleanName(name);
  if (!UUID.test(id) || !clean) return { ok: false, message: "Nom de 1 à 60 caractères" };
  const { error } = await supabaseAdmin().from("montage_templates").update({ name: clean }).eq("id", id);
  if (error) return fail(error);
  revalidatePath("/montage");
  return { ok: true, message: `Renommé en « ${clean} »` };
}

export async function deleteMontageTemplate(id: string): Promise<ActionResult> {
  if (IS_MOCK) return { ok: false, message: "Indisponible en mode démo" };
  if (!UUID.test(id)) return { ok: false, message: "Modèle inconnu" };
  const db = supabaseAdmin();
  const { data, error } = await db.from("montage_templates").delete().eq("id", id).select("is_default").maybeSingle();
  if (error) return fail(error);
  revalidatePath("/montage");
  return {
    ok: true,
    message: data?.is_default ? "Modèle supprimé : les montages reprennent le modèle d’origine" : "Modèle supprimé",
  };
}

const PREVIEW_UNKNOWN: MontagePreviewState = { status: "unknown", label: null, error: null, videoUrl: null, posterUrl: null, elapsedS: null };

/** Rendu exact : quelques secondes montées par le worker avec le vrai code du montage (job montage_preview, voie io,
 * priorité 5 : passe avant les tâches en file ; un seul essai). Le modèle envoyé est celui de l'éditeur, enregistré ou non. */
export async function requestMontagePreview(input: {
  template: MontageTemplate;
  recipe: MontageFormat;
  assetId: string | null;
  texts: { hook: string; subtitle: string; title: string };
}): Promise<ActionResult & { jobId?: string }> {
  if (IS_MOCK) return { ok: false, message: "Indisponible en mode démo" };
  const valid = check(input.template);
  if (!valid.ok) return valid;
  const clip = (s: string) => s.replace(/\s+/g, " ").trim().slice(0, 300);
  const payload = {
    template: valid.value,
    recipe: ["story", "timelapse", "tour"].includes(input.recipe) ? input.recipe : "story",
    asset_id: input.assetId && UUID.test(input.assetId) ? input.assetId : null,
    texts: { hook: clip(input.texts.hook), subtitle: clip(input.texts.subtitle), title: clip(input.texts.title) },
    duration_s: 5,
  };
  const { data, error } = await supabaseAdmin()
    .from("jobs")
    .insert({ type: "montage_preview", priority: 5, max_attempts: 1, payload })
    .select("id")
    .single();
  if (error) {
    if (/invalid input value for enum job_type/.test(error.message)) {
      return { ok: false, message: "Migration 0014 absente : relance le lanceur (il applique les migrations)" };
    }
    return fail(error);
  }
  return { ok: true, message: "Rendu en file", jobId: data.id as string };
}

/** Rendu exact avec le son (onglet Son, docs/26-musique.md) : une vidéo déjà montée, avec la musique choisie (son volume
 * et son début tels qu'à l'écran) et les niveaux du modèle en cours ; le worker copie l'image et refait le son avec le
 * code du montage (job montage_preview, mode « sound », quelques secondes). */
export async function requestSoundPreview(input: {
  template: MontageTemplate;
  videoId: string;
  trackId: string | null;
  gainDb: number;
  startS: number;
}): Promise<ActionResult & { jobId?: string }> {
  if (IS_MOCK) return { ok: false, message: "Indisponible en mode démo" };
  const valid = check(input.template);
  if (!valid.ok) return valid;
  if (!UUID.test(input.videoId)) return { ok: false, message: "Vidéo d’essai inconnue" };
  if (input.trackId !== null && (!input.trackId || input.trackId.length > 120 || /[\\/]/.test(input.trackId))) {
    return { ok: false, message: "Musique inconnue" };
  }
  const clamp = (v: number, min: number, max: number) => (Number.isFinite(v) ? Math.min(max, Math.max(min, v)) : 0);
  const payload = {
    mode: "sound",
    template: valid.value,
    video_id: input.videoId,
    music_track: input.trackId,
    track_gain_db: clamp(input.gainDb, -24, 24),
    track_start_s: clamp(input.startS, 0, 3600),
  };
  const { data, error } = await supabaseAdmin()
    .from("jobs")
    .insert({ type: "montage_preview", priority: 5, max_attempts: 1, payload })
    .select("id")
    .single();
  if (error) return fail(error);
  return { ok: true, message: "Rendu en file", jobId: data.id as string };
}

export async function getMontagePreview(jobId: string): Promise<MontagePreviewState> {
  if (!UUID.test(jobId)) return PREVIEW_UNKNOWN;
  const { data } = await supabaseAdmin()
    .from("jobs")
    .select("status, progress_label, error, result")
    .eq("id", jobId)
    .eq("type", "montage_preview")
    .maybeSingle();
  if (!data) return PREVIEW_UNKNOWN;
  const result = (data.result ?? {}) as { elapsed_s?: number };
  const done = data.status === "done";
  return {
    status: data.status as MontagePreviewState["status"],
    label: (data.progress_label as string | null) ?? null,
    error: (data.error as string | null) ?? null,
    videoUrl: done ? `/api/montage-preview/${jobId}` : null,
    posterUrl: done ? `/api/montage-preview/${jobId}?image=1` : null,
    elapsedS: result.elapsed_s ?? null,
  };
}

/** Réglages d'une musique de la bibliothèque (table music_tracks, docs/26-musique.md) : description, ambiances, formats,
 * préférence, active, volume, début. Enregistrés aussitôt, pour tous les modèles ; le prochain montage les prend. */
export async function updateMusicTrack(id: string, patch: Record<string, unknown>): Promise<ActionResult> {
  if (IS_MOCK) return { ok: false, message: "Indisponible en mode démo" };
  if (!id || id.length > 120 || /[\\/]/.test(id)) return { ok: false, message: "Musique inconnue" };
  const parsed = musicTrackSchema.safeParse(patch);
  if (!parsed.success) return { ok: false, message: `Réglage refusé : ${schemaError(parsed.error)}` };
  const value = { ...parsed.data };
  if (value.moods) {
    const known = Object.keys((await audioConstants()).moods ?? {});
    value.moods = value.moods.filter((m) => known.includes(m));
  }
  if (!Object.keys(value).length) return { ok: true, message: "Rien à enregistrer" };
  const { data, error } = await supabaseAdmin().from("music_tracks").update(value).eq("id", id).select("id").maybeSingle();
  if (error) {
    if (/music_tracks/.test(error.message)) return { ok: false, message: "Migration 0018 absente : relance le lanceur (il applique les migrations)" };
    return fail(error);
  }
  if (!data) return { ok: false, message: "Musique inconnue (fichier retiré ?)" };
  return { ok: true, message: "Enregistré" };
}

/** Supprime une police ajoutée depuis l'onglet (DATA_DIR/fonts) ; les polices livrées et celles de Windows restent. */
export async function deleteUserFont(id: string): Promise<ActionResult> {
  const target = await fontPath(id);
  if (!target || target.source !== "user") return { ok: false, message: "Seules les polices ajoutées ici peuvent être retirées" };
  try {
    await fs.unlink(target.path);
  } catch (error) {
    return fail(error);
  }
  revalidatePath("/montage");
  return { ok: true, message: `${target.file} retirée` };
}
