"use server";

/**
 * Retouche d'une vidéo montée (Bibliothèque → Retoucher, docs/34-retouche.md) : enregistrer la retouche et refaire la
 * vidéo (SQL retouch_video, migration 0020 : voix si elle change, montage, contrôle), suivre la vidéo pendant qu'elle est
 * refaite, et proposer les nombres en chiffres avec la règle du worker (worker/numbers.py : to_digits).
 */
import { spawn } from "node:child_process";
import path from "node:path";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import type { ActionResult } from "@/app/production/actions";
import { getGenerationCatalog } from "@/lib/generation-data";
import { normalizeVoiceId } from "@/lib/generation-types";
import { CLIP_VOICES, LEVEL_BOUNDS, type RetouchData, type RetouchInput } from "@/lib/retouch-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

const UUID = /^[0-9a-f-]{36}$/i;
const level = (key: keyof typeof LEVEL_BOUNDS) => z.number().min(LEVEL_BOUNDS[key][0]).max(LEVEL_BOUNDS[key][1]).optional();

const inputSchema = z.object({
  hookTitle: z.string().max(320).nullable(), // titre d'accroche (140 dans l'éditeur) ou citation (docs/58)
  hookDisplay: z.object({ durationS: z.number().min(1).max(3600).nullable() }).nullable(),
  subtitles: z.record(z.string().regex(/^\d{1,3}$/), z.string().max(800)),
  music: z.object({ track: z.string().min(1).max(120).nullable(), startS: z.number().min(0).max(3600).nullable() }).nullable(),
  audio: z.object({ voice_db: level("voice_db"), music_db: level("music_db"), duck_db: level("duck_db"), solo_db: level("solo_db"), sfx_db: level("sfx_db") }),
  voice: z.string().max(120).nullable(),
  acting: z.string().max(40).nullable(),
  sfx: z.boolean().nullable(),
});

/** Espaces normales regroupées ; l'espace insécable d'un nombre (« 1 350 ») reste. */
const tidy = (text: string) => text.replace(/[ \t\r\n]+/g, " ").trim();
// Citation (docs/58) : ses retours à la ligne comptent (dernière ligne « — Auteur »)
const tidyLines = (text: string) =>
  text
    .split(/\r?\n/)
    .map((line) => line.replace(/[ \t]+/g, " ").trim())
    .filter(Boolean)
    .join("\n");

export async function retouchVideo(videoId: string, input: RetouchInput): Promise<ActionResult> {
  if (!UUID.test(videoId)) return { ok: false, message: "Vidéo inconnue" };
  const parsed = inputSchema.safeParse(input);
  if (!parsed.success) return { ok: false, message: `Retouche refusée : ${parsed.error.issues[0]?.message ?? "valeurs invalides"}` };
  const r = parsed.data;
  const db = supabaseAdmin();
  const { data: v, error } = await db.from("videos").select("lang, format, tts_provider, tts_voice, retouch").eq("id", videoId).maybeSingle();
  if (error || !v) return { ok: false, message: error?.message ?? "Vidéo introuvable" };

  const retouch: RetouchData = {};
  const hook = tidyLines(r.hookTitle ?? "");
  if (hook) retouch.hook_title = hook;
  // titre éphémère (secondes, fondu compris) ou toute la vidéo ; absent : la durée du modèle de montage
  if (r.hookDisplay) retouch.hook_display = { duration_s: r.hookDisplay.durationS === null ? null : Math.round(r.hookDisplay.durationS * 10) / 10 };
  const subtitles = Object.fromEntries(Object.entries(r.subtitles).map(([k, t]) => [k, tidy(t)]));
  if (Object.keys(subtitles).length) retouch.subtitles = subtitles;
  if (r.music) retouch.music = { track: r.music.track, start_s: r.music.track ? r.music.startS : null };
  const audio = Object.fromEntries(Object.entries(r.audio).filter((e): e is [string, number] => typeof e[1] === "number"));
  if (Object.keys(audio).length) retouch.audio = audio;

  // Voix : refaite seulement si elle change ; la dernière voix choisie à la main reste notée
  const current = v.tts_provider && v.tts_voice ? `${v.tts_provider as string}:${v.tts_voice as string}` : null;
  let redo: string | null = null;
  if (r.voice && normalizeVoiceId(r.voice) !== current) {
    const lang = v.lang === "en" ? "en" : "fr";
    const entry = (await getGenerationCatalog()).voices[lang].find((e) => e.id === normalizeVoiceId(r.voice ?? ""));
    if (!entry) return { ok: false, message: "Voix inconnue du catalogue" };
    if (entry.missing.length) return { ok: false, message: `${entry.engineLabel} n’est pas installé (${entry.missing.join(", ")})` };
    redo = entry.id;
  }
  const previousVoice = (v.retouch as { voice?: unknown } | null)?.voice;
  const voice = redo ?? (typeof previousVoice === "string" ? previousVoice : null);
  if (voice) retouch.voice = voice;
  // Voix des personnages rejouées (docs/41 §8) : chaque personnage garde sa voix, un autre moteur la joue (Gemini) ;
  // le jeu reste noté pour la vidéo, une nouvelle prise d'une réplique le reprend
  let actingRedo: string | null = null;
  const clipsWanted = r.acting === CLIP_VOICES; // drame : revenir aux voix des clips (docs/49 §11)
  if (r.acting && !clipsWanted) {
    const entry = (await getGenerationCatalog()).acting.find((a) => a.id === r.acting);
    if (!entry) return { ok: false, message: "Jeu des voix inconnu du catalogue" };
    if (entry.missing.length) return { ok: false, message: `${entry.label} n’est pas installé (${entry.missing.join(", ")})` };
    actingRedo = entry.id;
  }
  const previousActing = (v.retouch as { acting?: unknown } | null)?.acting;
  const acting = actingRedo ?? (typeof previousActing === "string" ? previousActing : null);
  if (acting) retouch.acting = acting;
  // consignes données plan par plan (onglet Plans, SQL redo_plan) : l'historique reste
  const plans = (v.retouch as { plans?: unknown } | null)?.plans;
  if (plans && typeof plans === "object" && !Array.isArray(plans)) retouch.plans = plans as RetouchData["plans"];
  // consignes en cours d'écriture et prises de voix à juger (onglet Plans, docs/49 §7) : elles restent
  for (const key of ["drafts", "takes", "lines"] as const) {
    const kept = (v.retouch as Record<string, unknown> | null)?.[key];
    if (kept && typeof kept === "object" && !Array.isArray(kept)) (retouch as Record<string, unknown>)[key] = kept;
  }
  // bruitages (case « Bruitages ») : null = ceux du format ; plans au son coupé (onglet Plans) : ils restent
  if (r.sfx !== null) retouch.sfx = r.sfx;
  const muted = (v.retouch as { muted?: unknown } | null)?.muted;
  if (Array.isArray(muted) && muted.length) retouch.muted = muted.filter((i): i is number => Number.isInteger(i));

  // « acting:gemini » : l'étape voix refait les voix des personnages avec ce jeu (même voix par personnage)
  const voiceJob = actingRedo ? `acting:${actingRedo}` : redo;
  // Drame : passer des voix des clips aux voix de synthèse, ou l'inverse, change le format de la vidéo (SQL set_drama_voices)
  const toClips = clipsWanted && v.format !== "B_visual";
  const toSynth = Boolean(actingRedo) && v.format === "B_visual";
  const { error: rpcError } =
    toClips || toSynth
      ? await db.rpc("set_drama_voices", { p_video: videoId, p_clips: toClips, p_voice: toSynth ? voiceJob : null, p_retouch: retouch })
      : await db.rpc("retouch_video", { p_video: videoId, p_retouch: retouch, p_voice: clipsWanted ? null : voiceJob });
  if (rpcError) {
    const missing = /set_drama_voices/.test(rpcError.message) && /(does not exist|could not find)/i.test(rpcError.message);
    return { ok: false, message: missing ? "Migration 0045 à appliquer (supabase/migrations/0045_drames_voix_des_clips.sql)" : rpcError.message };
  }
  revalidatePath("/library");
  revalidatePath(`/library/${videoId}/retouche`);
  return {
    ok: true,
    message: toClips
      ? "Retour aux voix des clips (MiniMax H3), puis montage et contrôle : une minute environ"
      : actingRedo
      ? "Voix refaites (chaque personnage garde la sienne), puis montage calé sur les lèvres et contrôle : quelques minutes"
      : redo
        ? "Nouvelle voix, puis montage et contrôle : quelques minutes (la voix passe sur la carte graphique après la tâche en cours)"
        : "Montage relancé : la vidéo refaite arrive dans une minute environ",
  };
}

const planSchema = z.object({
  scene: z.number().int().min(0).max(999),
  clip: z.boolean(),
  voice: z.boolean(),
  note: z.string().max(600),
});

/** Corrige un plan (Retoucher → Plans, docs/38 §6) : refait son clip avec la consigne (note de réalisation pour le modèle
 * vidéo) et/ou redit sa réplique (nouvelle prise), puis remonte la vidéo avec les voix recalées et la contrôle (SQL
 * redo_plan, migration 0028). */
export async function redoPlan(videoId: string, input: { scene: number; clip: boolean; voice: boolean; note: string }): Promise<ActionResult> {
  if (!UUID.test(videoId)) return { ok: false, message: "Vidéo inconnue" };
  const parsed = planSchema.safeParse(input);
  if (!parsed.success) return { ok: false, message: `Correction refusée : ${parsed.error.issues[0]?.message ?? "valeurs invalides"}` };
  const r = parsed.data;
  if (!r.clip && !r.voice) return { ok: false, message: "Choisis le clip, la voix ou les deux" };
  const { error } = await supabaseAdmin().rpc("redo_plan", { p_video: videoId, p_scene: r.scene, p_note: tidy(r.note), p_clip: r.clip, p_voice: r.voice });
  if (error) {
    const missing = /redo_plan/.test(error.message) && /(does not exist|could not find)/i.test(error.message);
    return { ok: false, message: missing ? "Migration 0028 à appliquer (supabase/migrations/0028_corriger_un_plan.sql)" : error.message };
  }
  revalidatePath("/library");
  revalidatePath(`/library/${videoId}/retouche`);
  return {
    ok: true,
    message: r.clip
      ? "Clip du plan en file : il passe sur la carte graphique après la tâche en cours (≈ 7 min), puis montage et contrôle"
      : "Nouvelle prise de voix en file, puis montage et contrôle : quelques minutes",
  };
}

const missing0038 = (message: string) =>
  /(save_plan_note|keep_take|retake_voices|apply_takes)/.test(message) && /(does not exist|could not find)/i.test(message)
    ? "Migration 0038 à appliquer (supabase/migrations/0038_prises_de_voix_par_lot.sql)"
    : message;

/** Consigne d'un plan, enregistrée pendant qu'elle s'écrit (Retoucher → Plans, docs/49 §7). */
export async function savePlanNote(videoId: string, scene: number, note: string): Promise<ActionResult> {
  if (!UUID.test(videoId) || !Number.isInteger(scene) || scene < 0 || scene > 999) return { ok: false, message: "Plan inconnu" };
  const { error } = await supabaseAdmin().rpc("save_plan_note", { p_video: videoId, p_scene: scene, p_note: tidy(note).slice(0, 600) });
  return error ? { ok: false, message: missing0038(error.message) } : { ok: true, message: "Consigne enregistrée" };
}

/** Prise validée (true), refusée (false : sa consigne se rouvre) ou de nouveau à écouter (null). */
export async function keepTake(videoId: string, scene: number, keep: boolean | null): Promise<ActionResult> {
  if (!UUID.test(videoId) || !Number.isInteger(scene) || scene < 0 || scene > 999) return { ok: false, message: "Plan inconnu" };
  const { error } = await supabaseAdmin().rpc("keep_take", { p_video: videoId, p_scene: scene, p_keep: keep });
  if (error) return { ok: false, message: missing0038(error.message) };
  revalidatePath(`/library/${videoId}/retouche`);
  return { ok: true, message: keep === true ? "Prise validée" : keep === false ? "Prise refusée : donne une nouvelle consigne" : "Prise à réécouter" };
}

/** Nouvelles prises de voix de tous les plans qui ont une consigne (et des prises refusées), en un seul lot ; la vidéo
 * ne change pas tant que les prises ne sont pas validées. */
export async function retakeVoices(videoId: string): Promise<ActionResult> {
  if (!UUID.test(videoId)) return { ok: false, message: "Vidéo inconnue" };
  const { error } = await supabaseAdmin().rpc("retake_voices", { p_video: videoId });
  if (error) return { ok: false, message: missing0038(error.message) };
  revalidatePath(`/library/${videoId}/retouche`);
  return { ok: true, message: "Prises de voix en file : chaque réplique est redite puis réécoutée, ≈ 1 min par plan" };
}

/** La voix que le modèle vidéo a donnée au plan dans son clip brut, reprise comme une prise à écouter puis valider
 * (worker/takes.py : clip_takes) ; la vidéo ne change pas tant que la prise n'est pas posée. */
export async function takeClipVoice(videoId: string, scene: number): Promise<ActionResult> {
  if (!UUID.test(videoId) || !Number.isInteger(scene) || scene < 0 || scene > 999) return { ok: false, message: "Plan inconnu" };
  const db = supabaseAdmin();
  const { data: v, error } = await db.from("videos").select("production_id, final_asset_id, archived_at").eq("id", videoId).maybeSingle();
  if (error || !v) return { ok: false, message: error?.message ?? "Vidéo introuvable" };
  if (v.archived_at) return { ok: false, message: "Ancienne version déjà remplacée : reprends la voix sur la vidéo refaite" };
  if (!v.production_id || !v.final_asset_id) return { ok: false, message: "Vidéo pas encore montée" };
  const busy = await db
    .from("jobs")
    .select("id", { count: "exact", head: true })
    .eq("video_id", videoId)
    .in("status", ["queued", "running"])
    .in("type", ["generate_clip", "tts", "assemble", "qa", "upload"]);
  if (busy.count) return { ok: false, message: "Une voix, un clip, un montage ou un envoi est déjà en cours pour cette vidéo" };
  const { error: insertError } = await db.from("jobs").insert({
    type: "tts",
    video_id: videoId,
    production_id: v.production_id,
    priority: 20,
    max_attempts: 2,
    payload: { clip_takes: [scene], retouch: true },
  });
  if (insertError) return { ok: false, message: insertError.message };
  revalidatePath(`/library/${videoId}/retouche`);
  return { ok: true, message: "Voix du clip en préparation : elle arrive comme une prise à écouter (≈ 1 min, suivi dans Tâches)" };
}

/** Rendu complet avec toutes les prises validées : piste des répliques, un montage calé sur les lèvres, le contrôle. */
export async function applyTakes(videoId: string): Promise<ActionResult> {
  if (!UUID.test(videoId)) return { ok: false, message: "Vidéo inconnue" };
  const { error } = await supabaseAdmin().rpc("apply_takes", { p_video: videoId });
  if (error) return { ok: false, message: missing0038(error.message) };
  revalidatePath("/library");
  revalidatePath(`/library/${videoId}/retouche`);
  return { ok: true, message: "Prises validées posées, puis montage et contrôle : quelques minutes" };
}

/** Coupe le son du clip des plans choisis (Retoucher → Plans, docs/49 §13) — ni ambiance ni bruitage, la réplique d'un
 * plan parlé restant, isolée par Demucs —, rend le son aux autres, puis refait la vidéo (SQL retouch_video, sans voix).
 * `scenes` : index des plans à couper, la liste complète voulue. */
export async function muteClips(videoId: string, scenes: number[]): Promise<ActionResult> {
  if (!UUID.test(videoId)) return { ok: false, message: "Vidéo inconnue" };
  const parsed = z.array(z.number().int().min(0).max(999)).max(200).safeParse(scenes);
  if (!parsed.success) return { ok: false, message: "Plans invalides" };
  const db = supabaseAdmin();
  const { data: v, error } = await db.from("videos").select("retouch").eq("id", videoId).maybeSingle();
  if (error || !v) return { ok: false, message: error?.message ?? "Vidéo introuvable" };
  const muted = [...new Set(parsed.data)].sort((a, b) => a - b);
  const retouch: RetouchData = { ...((v.retouch ?? {}) as RetouchData) };
  if (muted.length) retouch.muted = muted;
  else delete retouch.muted;
  const { error: rpcError } = await db.rpc("retouch_video", { p_video: videoId, p_retouch: retouch, p_voice: null });
  if (rpcError) return { ok: false, message: rpcError.message };
  revalidatePath("/library");
  revalidatePath(`/library/${videoId}/retouche`);
  return {
    ok: true,
    message: muted.length
      ? `Son coupé sur ${muted.length} plan${muted.length > 1 ? "s" : ""}, puis montage et contrôle : une à deux minutes (voix isolée sur les plans parlés)`
      : "Son des clips rendu à tous les plans, puis montage et contrôle : une minute environ",
  };
}

// ---- Nombres en chiffres : la fonction du worker (worker/numbers.py), dans son environnement Python --------------------

const WORKER_DIR = path.join(process.cwd(), "..", "..", "services", "worker");
const PYTHON = process.env.WORKER_PYTHON ?? path.join(process.env.YT2_HOME ?? "C:/YouTube2", "worker-venv", "Scripts", "python.exe");
const DIGITS = [
  "import json, sys",
  "from worker.numbers import to_digits",
  "d = json.loads(sys.stdin.buffer.read().decode('utf-8'))",
  "sys.stdout.write(json.dumps([to_digits(t, d['lang']) for t in d['texts']]))",
].join("\n");

/** Textes affichés avec les nombres en chiffres (« treize cent cinquante tonnes » → « 1 350 tonnes »), même règle que le
 * montage automatique. Rien n'est enregistré : l'écran montre la proposition, Luca relit puis refait la vidéo. */
export async function suggestDigits(texts: string[], lang: string): Promise<{ ok: true; texts: string[] } | { ok: false; message: string }> {
  const input = JSON.stringify({ texts: texts.slice(0, 80).map((t) => String(t).slice(0, 800)), lang: lang === "en" ? "en" : "fr" });
  return new Promise((resolve) => {
    let out = "";
    let err = "";
    const child = spawn(PYTHON, ["-c", DIGITS], { cwd: WORKER_DIR, windowsHide: true, env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
    const timer = setTimeout(() => {
      child.kill();
      resolve({ ok: false, message: "Conversion trop longue (20 s)" });
    }, 20_000);
    child.stdout.on("data", (d: Buffer) => (out += d.toString("utf8")));
    child.stderr.on("data", (d: Buffer) => (err += d.toString("utf8")));
    child.on("error", () => {
      clearTimeout(timer);
      resolve({ ok: false, message: `Python du worker introuvable (${PYTHON})` });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        const missing = /No module named 'worker\.numbers'|cannot import name 'to_digits'/.test(err);
        resolve({ ok: false, message: missing ? "La règle des chiffres n’est pas encore dans le worker" : `Conversion impossible : ${err.trim().split("\n").pop() ?? code}` });
        return;
      }
      try {
        const res: unknown = JSON.parse(out);
        resolve(Array.isArray(res) && res.length === JSON.parse(input).texts.length ? { ok: true, texts: res.map(String) } : { ok: false, message: "Réponse illisible" });
      } catch {
        resolve({ ok: false, message: "Réponse illisible" });
      }
    });
    child.stdin.end(input, "utf8");
  });
}
