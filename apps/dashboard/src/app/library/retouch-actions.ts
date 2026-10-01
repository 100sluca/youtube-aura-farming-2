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
import { getRetouchState } from "@/lib/retouch";
import { LEVEL_BOUNDS, type RetouchData, type RetouchInput, type RetouchState } from "@/lib/retouch-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

const UUID = /^[0-9a-f-]{36}$/i;
const level = (key: keyof typeof LEVEL_BOUNDS) => z.number().min(LEVEL_BOUNDS[key][0]).max(LEVEL_BOUNDS[key][1]).optional();

const inputSchema = z.object({
  hookTitle: z.string().max(140).nullable(),
  hookDisplay: z.object({ durationS: z.number().min(1).max(3600).nullable() }).nullable(),
  subtitles: z.record(z.string().regex(/^\d{1,3}$/), z.string().max(800)),
  music: z.object({ track: z.string().min(1).max(120).nullable(), startS: z.number().min(0).max(3600).nullable() }).nullable(),
  audio: z.object({ voice_db: level("voice_db"), music_db: level("music_db"), duck_db: level("duck_db"), solo_db: level("solo_db"), sfx_db: level("sfx_db") }),
  voice: z.string().max(120).nullable(),
  acting: z.string().max(40).nullable(),
});

/** Espaces normales regroupées ; l'espace insécable d'un nombre (« 1 350 ») reste. */
const tidy = (text: string) => text.replace(/[ \t\r\n]+/g, " ").trim();

export async function retouchVideo(videoId: string, input: RetouchInput): Promise<ActionResult> {
  if (!UUID.test(videoId)) return { ok: false, message: "Vidéo inconnue" };
  const parsed = inputSchema.safeParse(input);
  if (!parsed.success) return { ok: false, message: `Retouche refusée : ${parsed.error.issues[0]?.message ?? "valeurs invalides"}` };
  const r = parsed.data;
  const db = supabaseAdmin();
  const { data: v, error } = await db.from("videos").select("lang, tts_provider, tts_voice, retouch").eq("id", videoId).maybeSingle();
  if (error || !v) return { ok: false, message: error?.message ?? "Vidéo introuvable" };

  const retouch: RetouchData = {};
  const hook = tidy(r.hookTitle ?? "");
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
  if (r.acting) {
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

  // « acting:gemini » : l'étape voix refait les voix des personnages avec ce jeu (même voix par personnage)
  const voiceJob = actingRedo ? `acting:${actingRedo}` : redo;
  const { error: rpcError } = await db.rpc("retouch_video", { p_video: videoId, p_retouch: retouch, p_voice: voiceJob });
  if (rpcError) return { ok: false, message: rpcError.message };
  revalidatePath("/library");
  revalidatePath(`/library/${videoId}/retouche`);
  return {
    ok: true,
    message: actingRedo
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

export async function fetchRetouchState(videoId: string): Promise<RetouchState | null> {
  if (!UUID.test(videoId)) return null;
  return getRetouchState(videoId);
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
