"use server";

/**
 * Page Vidéos longues (docs/63) : chaque bouton change la fiche long_videos ou met une tâche en file pour le worker
 * (long_write : écriture et publication ; long_make : images, clips, miniatures, voix, montage).
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { creationChannel, getChannelContext } from "@/lib/channel-server";
import {
  FORMAT_LABELS,
  PARA_KEY,
  parseLongSettings,
  voiceNeedsRedo,
  type LongFormat,
  type LongScript,
  type LongSettings,
  type LongVoice,
} from "@/lib/long-types";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { normalizeParams, parseProfiles, VOICE_MOD_PREFIX, type VoiceProfile } from "@/lib/voice-mods";

const UUID = /^[0-9a-f-]{36}$/i;

function fail(error: unknown): ActionResult {
  return { ok: false, message: error instanceof Error ? error.message : String((error as { message?: string })?.message ?? error) };
}

function refresh(id?: string) {
  revalidatePath("/long");
  if (id) revalidatePath(`/long/${id}`);
}

async function getLong(id: string) {
  if (!UUID.test(id)) throw new Error("Vidéo inconnue");
  const { data, error } = await supabaseAdmin().from("long_videos").select("*").eq("id", id).maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) throw new Error("Vidéo inconnue");
  return data;
}

async function pendingJob(id: string, type: string, action: string): Promise<{ id: string; status: string } | null> {
  const { data } = await supabaseAdmin()
    .from("jobs")
    .select("id, status")
    .eq("type", type)
    .eq("payload->>long_id", id)
    .eq("payload->>action", action)
    .in("status", ["queued", "running"])
    .limit(1);
  return data?.[0] ?? null;
}

async function enqueue(
  lv: { id: string; production_id: string | null; channel_id: string },
  type: "long_write" | "long_make",
  action: string,
  payload: Record<string, unknown> = {},
  priority = 40,
) {
  const res = await supabaseAdmin()
    .from("jobs")
    .insert({
      type,
      production_id: lv.production_id,
      channel_id: lv.channel_id,
      priority,
      max_attempts: 3,
      payload: { long_id: lv.id, action, source: "dashboard", ...payload },
    });
  if (res.error) throw new Error(res.error.message);
}

// ---- Sujets ---------------------------------------------------------------------------------------------------------

export async function proposeIdeas(count: number, note: string): Promise<ActionResult> {
  try {
    const channel = creationChannel(await getChannelContext());
    if (!channel) return { ok: false, message: "Aucune chaîne" };
    const db = supabaseAdmin();
    const { data: busy } = await db
      .from("jobs")
      .select("id")
      .eq("type", "long_write")
      .eq("payload->>action", "ideas")
      .in("status", ["queued", "running"])
      .limit(1);
    if (busy?.length) return { ok: false, message: "Des sujets sont déjà en cours de recherche" };
    const n = Math.max(3, Math.min(12, Math.round(count) || 6));
    const res = await db.from("jobs").insert({
      type: "long_write",
      channel_id: channel.id,
      priority: 20,
      max_attempts: 2,
      payload: { action: "ideas", count: n, note: note.trim().slice(0, 500), channel_id: channel.id, source: "dashboard" },
    });
    if (res.error) return { ok: false, message: res.error.message };
    refresh();
    return { ok: true, message: `${n} sujets demandés : ils arrivent dans une minute ou deux` };
  } catch (e) {
    return fail(e);
  }
}

export async function addOwnSubject(subject: string, format: LongFormat, notes: string): Promise<ActionResult> {
  try {
    const s = subject.trim();
    if (s.length < 8) return { ok: false, message: "Décris le sujet en une phrase" };
    if (!(format in FORMAT_LABELS)) return { ok: false, message: "Format inconnu" };
    const channel = creationChannel(await getChannelContext());
    if (!channel) return { ok: false, message: "Aucune chaîne" };
    const db = supabaseAdmin();
    const { data: settings } = await db.from("app_settings").select("value").eq("key", "long").maybeSingle();
    const ins = await db
      .from("long_videos")
      .insert({
        channel_id: channel.id,
        stage: "idea",
        format,
        origin: "manual",
        subject: s.slice(0, 500),
        notes: notes.trim().slice(0, 2000) || null,
        target_minutes: parseLongSettings(settings?.value).target_minutes,
      })
      .select("id, production_id, channel_id")
      .single();
    if (ins.error) return { ok: false, message: ins.error.message };
    await enqueue({ id: ins.data.id, production_id: null, channel_id: channel.id }, "long_write", "write", {}, 30);
    await db.from("long_videos").update({ stage: "writing" }).eq("id", ins.data.id);
    refresh();
    return { ok: true, message: "Sujet ajouté : le titre, la miniature et le script s’écrivent" };
  } catch (e) {
    return fail(e);
  }
}

export async function startWriting(id: string, notes = ""): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    if (await pendingJob(id, "long_write", "write")) return { ok: false, message: "Le script s’écrit déjà" };
    const db = supabaseAdmin();
    const update: Record<string, unknown> = { stage: "writing", error: null };
    if (notes.trim()) update.notes = notes.trim().slice(0, 2000);
    await db.from("long_videos").update(update).eq("id", id);
    await enqueue(lv, "long_write", "write", {}, 30);
    refresh(id);
    return { ok: true, message: "C’est parti : dossier, plan, chapitres, relecture (10 à 20 min)" };
  } catch (e) {
    return fail(e);
  }
}

export async function archiveLong(id: string): Promise<ActionResult> {
  try {
    await getLong(id);
    await supabaseAdmin().from("long_videos").update({ stage: "archived" }).eq("id", id);
    refresh(id);
    return { ok: true, message: "Écartée" };
  } catch (e) {
    return fail(e);
  }
}

// ---- Script ---------------------------------------------------------------------------------------------------------

export async function saveParagraph(id: string, key: string, text: string): Promise<ActionResult> {
  try {
    if (!PARA_KEY.test(key)) return { ok: false, message: "Paragraphe inconnu" };
    const lv = await getLong(id);
    const script = lv.script as LongScript | null;
    if (!script) return { ok: false, message: "Pas de script" };
    const clean = text.replace(/\s+/g, " ").trim();
    if (clean.length < 10) return { ok: false, message: "Texte trop court" };
    let found = false;
    for (const c of script.chapters) {
      for (const p of c.paragraphs) {
        if (p.key === key) {
          p.text = clean;
          p.words = clean.split(" ").length;
          found = true;
        }
      }
    }
    if (!found) return { ok: false, message: "Paragraphe introuvable" };
    script.words = script.chapters.reduce((n, c) => n + c.paragraphs.reduce((m, p) => m + (p.words ?? p.text.split(" ").length), 0), 0);
    script.minutes_at_150 = Math.round((script.words / 150) * 10) / 10;
    script.edited = true;
    const db = supabaseAdmin();
    await db.from("long_videos").update({ script }).eq("id", id);
    // une prise déjà faite sur l'ancien texte reste gardée, mais sa vérification ne vaut plus
    await db.from("long_takes").update({ status: "problem" }).eq("long_id", id).eq("para", key).eq("chosen", true).eq("status", "ok");
    refresh(id);
    return { ok: true, message: "Paragraphe enregistré" };
  } catch (e) {
    return fail(e);
  }
}

export async function rewriteChapter(id: string, chapter: number, note: string): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    if (!lv.script) return { ok: false, message: "Pas de script" };
    if (await pendingJob(id, "long_write", "chapter")) return { ok: false, message: "Un chapitre est déjà en réécriture" };
    await enqueue(lv, "long_write", "chapter", { chapter, note: note.trim().slice(0, 1500) }, 25);
    refresh(id);
    return { ok: true, message: `Chapitre ${chapter + 1} en réécriture` };
  } catch (e) {
    return fail(e);
  }
}

export async function rewriteAll(id: string, note: string): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    if (await pendingJob(id, "long_write", "write")) return { ok: false, message: "Le script s’écrit déjà" };
    const db = supabaseAdmin();
    const notes = [lv.notes, note.trim()].filter(Boolean).join("\n").slice(0, 2000);
    await db.from("long_videos").update({ script: null, review: null, stage: "writing", notes: notes || null, error: null }).eq("id", id);
    await enqueue(lv, "long_write", "write", {}, 30);
    refresh(id);
    return { ok: true, message: "Tout le script se réécrit avec ta remarque" };
  } catch (e) {
    return fail(e);
  }
}

export async function approveScript(id: string): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    if (!lv.script?.chapters?.length) return { ok: false, message: "Pas de script" };
    if (await pendingJob(id, "long_write", "chapter")) return { ok: false, message: "Attends la fin de la réécriture du chapitre" };
    const db = supabaseAdmin();
    await db.from("long_videos").update({ stage: "making", approved_at: new Date().toISOString(), error: null }).eq("id", id);
    if (!(await pendingJob(id, "long_write", "shots"))) await enqueue(lv, "long_write", "shots", {}, 35);
    refresh(id);
    return { ok: true, message: "Script validé : le réalisateur découpe les plans, puis les images partent. Le Studio voix est ouvert." };
  } catch (e) {
    return fail(e);
  }
}

// ---- Voix -----------------------------------------------------------------------------------------------------------

export async function chooseTake(id: string, takeId: string): Promise<ActionResult> {
  try {
    if (!UUID.test(takeId)) return { ok: false, message: "Prise inconnue" };
    const db = supabaseAdmin();
    const { data: t } = await db.from("long_takes").select("para").eq("id", takeId).eq("long_id", id).maybeSingle();
    if (!t) return { ok: false, message: "Prise inconnue" };
    await db.from("long_takes").update({ chosen: false }).eq("long_id", id).eq("para", t.para);
    await db.from("long_takes").update({ chosen: true }).eq("id", takeId);
    refresh(id);
    return { ok: true, message: "Prise gardée" };
  } catch (e) {
    return fail(e);
  }
}

/** Choix du modificateur pour cette vidéo. Si la voix finale est déjà faite autrement (Studio fermé), elle est refaite
 * sur les mêmes prises, puis le montage suit : rien à réenregistrer. */
export async function setVoiceModifier(id: string, on: boolean, voice: string): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    const db = supabaseAdmin();
    const profiles = await voiceProfiles();
    if (on && voice.startsWith(VOICE_MOD_PREFIX) && !profiles.some((p) => VOICE_MOD_PREFIX + p.id === voice)) {
      return { ok: false, message: "Ce réglage n’existe plus : choisis-en un autre" };
    }
    const redo = voiceNeedsRedo(lv.voice as LongVoice | null, lv.voice_done_at, on, voice, profiles);
    if (redo) {
      const running = await pendingJob(id, "long_make", "voice");
      if (running?.status === "running") return { ok: false, message: "La voix finale est en cours : réessaie quand elle est finie" };
      const { data: video } = lv.video_id ? await db.from("videos").select("youtube_video_id").eq("id", lv.video_id).maybeSingle() : { data: null };
      if (video?.youtube_video_id) return { ok: false, message: "Vidéo déjà envoyée sur YouTube : la voix ne se refait plus ici" };
    }
    await db
      .from("long_videos")
      .update({ voice: { ...(lv.voice ?? {}), modifier: on, modifier_voice: voice } })
      .eq("id", id);
    if (redo && !(await pendingJob(id, "long_make", "voice"))) await enqueue(lv, "long_make", "voice", {}, 80);
    refresh(id);
    if (redo) {
      return {
        ok: true,
        message: on
          ? "Modificateur appliqué à tes prises : la voix puis le montage se refont (environ 30 min)"
          : "Ta voix telle quelle : la voix puis le montage se refont (environ 15 min)",
      };
    }
    return {
      ok: true,
      message: on ? "Modificateur de voix activé pour cette vidéo" : "Ta voix telle quelle pour cette vidéo",
    };
  } catch (e) {
    return fail(e);
  }
}

// ---- Studio du modificateur de voix (docs/67) ---------------------------------------------------------------------

async function voiceProfiles(): Promise<VoiceProfile[]> {
  const { data } = await supabaseAdmin().from("app_settings").select("value").eq("key", "voice_mods").maybeSingle();
  return parseProfiles(data?.value);
}

async function writeVoiceProfiles(profiles: VoiceProfile[]) {
  const { error } = await supabaseAdmin()
    .from("app_settings")
    .upsert({ key: "voice_mods", value: { profiles }, updated_at: new Date().toISOString() }, { onConflict: "key" });
  if (error) throw new Error(error.message);
  revalidatePath("/long/voix");
  revalidatePath("/long");
}

/** Enregistre un réglage du modificateur (nouveau si id est vide) ; renvoie son id. */
export async function saveVoiceProfile(id: string, name: string, params: unknown): Promise<ActionResult & { id?: string }> {
  try {
    const label = name.trim().slice(0, 60);
    if (!label) return { ok: false, message: "Donne un nom à ce réglage" };
    const profiles = await voiceProfiles();
    const pid = id && profiles.some((p) => p.id === id) ? id : crypto.randomUUID().slice(0, 8);
    const profile: VoiceProfile = { id: pid, name: label, params: normalizeParams(params), updated_at: new Date().toISOString() };
    const next = profiles.some((p) => p.id === pid) ? profiles.map((p) => (p.id === pid ? profile : p)) : [...profiles, profile];
    await writeVoiceProfiles(next);
    return { ok: true, message: `Réglage « ${label} » enregistré`, id: pid };
  } catch (e) {
    return fail(e);
  }
}

export async function deleteVoiceProfile(id: string): Promise<ActionResult> {
  try {
    const profiles = await voiceProfiles();
    const gone = profiles.find((p) => p.id === id);
    if (!gone) return { ok: false, message: "Réglage inconnu" };
    const { data: used } = await supabaseAdmin()
      .from("long_videos")
      .select("id")
      .eq("voice->>modifier_voice", VOICE_MOD_PREFIX + id)
      .not("stage", "in", "(done,archived)")
      .limit(1);
    if (used?.length) return { ok: false, message: "Une vidéo en cours utilise ce réglage : choisis-en un autre pour elle d’abord" };
    await writeVoiceProfiles(profiles.filter((p) => p.id !== id));
    return { ok: true, message: `Réglage « ${gone.name} » supprimé` };
  } catch (e) {
    return fail(e);
  }
}

export async function finishRecording(id: string): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    const keys = ((lv.script as LongScript | null)?.chapters ?? []).flatMap((c) => c.paragraphs.map((p) => p.key));
    const { data: takes } = await supabaseAdmin().from("long_takes").select("para, status").eq("long_id", id).eq("chosen", true);
    const have = new Set((takes ?? []).filter((t) => t.status !== "failed").map((t) => t.para));
    const missing = keys.filter((k) => !have.has(k));
    if (missing.length) return { ok: false, message: `Il manque ${missing.length} paragraphe(s) à enregistrer` };
    if ((takes ?? []).some((t) => t.status === "checking")) return { ok: false, message: "Attends la fin des vérifications en cours" };
    await supabaseAdmin().from("long_videos").update({ voice_done_at: new Date().toISOString() }).eq("id", id);
    if (!(await pendingJob(id, "long_make", "voice"))) await enqueue(lv, "long_make", "voice", {}, 80);
    refresh(id);
    return { ok: true, message: "Voix terminée : nettoyage, puis montage dès que les images sont prêtes" };
  } catch (e) {
    return fail(e);
  }
}

/** Rouvre le Studio voix d'une vidéo déjà montée (la vidéo actuelle reste visible jusqu'au nouveau montage) ;
 * `clear` : efface aussi toutes les prises (fichiers compris) pour repartir de zéro. */
export async function reopenStudio(id: string, clear: boolean): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    const db = supabaseAdmin();
    const { data: video } = lv.video_id ? await db.from("videos").select("youtube_video_id").eq("id", lv.video_id).maybeSingle() : { data: null };
    if (video?.youtube_video_id) return { ok: false, message: "Vidéo déjà envoyée sur YouTube : la voix ne se refait plus ici" };
    if (await pendingJob(id, "long_make", "voice")) return { ok: false, message: "La voix finale est en cours" };
    let removed = 0;
    if (clear) {
      const { data: takes } = await db.from("long_takes").select("path").eq("long_id", id);
      const { unlink } = await import("node:fs/promises");
      for (const t of takes ?? []) {
        if (lv.dir && typeof t.path === "string" && t.path.toLowerCase().startsWith(String(lv.dir).toLowerCase())) {
          await unlink(t.path).catch(() => undefined);
          removed += 1;
        }
      }
      await db.from("long_takes").delete().eq("long_id", id);
    }
    await db.from("long_videos").update({ voice_done_at: null, stage: "making" }).eq("id", id);
    refresh(id);
    return { ok: true, message: clear ? `Studio voix rouvert, ${removed} prise(s) effacée(s)` : "Studio voix rouvert : tes prises sont gardées" };
  } catch (e) {
    return fail(e);
  }
}

// ---- Images, miniatures, montage ------------------------------------------------------------------------------------

export async function redoShot(id: string, idx: number): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    const db = supabaseAdmin();
    const { data: s } = await db.from("long_shots").select("chapter, kind").eq("long_id", id).eq("idx", idx).maybeSingle();
    if (!s) return { ok: false, message: "Plan inconnu" };
    await db
      .from("long_shots")
      .update({ image_path: null, clip_path: null, status: "todo", qc: null, attempts: 0, error: null })
      .eq("long_id", id)
      .eq("idx", idx);
    await enqueue(lv, "long_make", "images", { chapter: s.chapter }, 70);
    if (s.kind === "clip") await enqueue(lv, "long_make", "clip", { idx }, 72);
    refresh(id);
    return { ok: true, message: `Plan ${idx + 1} refait` };
  } catch (e) {
    return fail(e);
  }
}

export async function redoThumbnails(id: string): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    if (await pendingJob(id, "long_make", "thumbnails")) return { ok: false, message: "Les miniatures se refont déjà" };
    await enqueue(lv, "long_make", "thumbnails", {}, 60);
    refresh(id);
    return { ok: true, message: "Nouvelles miniatures en cours" };
  } catch (e) {
    return fail(e);
  }
}

export async function chooseThumbnail(id: string, index: number): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    const current = (lv.thumbnail ?? {}) as { candidates?: { kept?: boolean }[] };
    // la principale est forcément gardée : on ne la perd pas en en demandant d'autres
    const candidates = (current.candidates ?? []).map((c, i) => (i === index ? { ...c, kept: true } : c));
    await supabaseAdmin()
      .from("long_videos")
      .update({ thumbnail: { ...current, candidates, chosen: index, picked_by: "luca" } })
      .eq("id", id);
    refresh(id);
    return { ok: true, message: `Miniature ${index + 1} choisie comme principale (et gardée)` };
  } catch (e) {
    return fail(e);
  }
}

type Candidate = { file?: string; kept?: boolean; ab?: boolean; score?: number };

/** Change une miniature (gardée, test A/B, retirée) en repartant de l'état en base. */
async function editThumbnails(id: string, fn: (cands: Candidate[], chosen: number) => { cands: Candidate[]; chosen: number; message: string }) {
  const lv = await getLong(id);
  const current = (lv.thumbnail ?? {}) as { candidates?: Candidate[]; chosen?: number; picked_by?: string };
  const out = fn([...(current.candidates ?? [])], current.chosen ?? 0);
  await supabaseAdmin()
    .from("long_videos")
    .update({ thumbnail: { ...current, candidates: out.cands, chosen: out.chosen } })
    .eq("id", id);
  refresh(id);
  return { ok: true as const, message: out.message };
}

export async function toggleKeepThumbnail(id: string, index: number): Promise<ActionResult> {
  try {
    return await editThumbnails(id, (cands, chosen) => {
      if (!cands[index]) throw new Error("Miniature inconnue");
      cands[index] = { ...cands[index], kept: !cands[index].kept };
      return { cands, chosen, message: cands[index].kept ? "Miniature gardée : elle ne sera jamais remplacée" : "Miniature plus gardée" };
    });
  } catch (e) {
    return fail(e);
  }
}

export async function toggleAbThumbnail(id: string, index: number): Promise<ActionResult> {
  try {
    return await editThumbnails(id, (cands, chosen) => {
      if (!cands[index]) throw new Error("Miniature inconnue");
      const on = !cands[index].ab;
      if (on && cands.filter((c) => c.ab).length >= 3) throw new Error("3 miniatures au plus pour le test A/B : décoche-en une d’abord");
      cands[index] = { ...cands[index], ab: on, kept: on ? true : cands[index].kept };
      return { cands, chosen, message: on ? "Ajoutée au test A/B (et gardée)" : "Retirée du test A/B" };
    });
  } catch (e) {
    return fail(e);
  }
}

export async function dropThumbnail(id: string, index: number): Promise<ActionResult> {
  try {
    return await editThumbnails(id, (cands, chosen) => {
      if (!cands[index]) throw new Error("Miniature inconnue");
      if (cands[index].kept) throw new Error("Cette miniature est gardée : décoche « Garder » d’abord");
      const next = cands.filter((_, i) => i !== index);
      const newChosen = chosen === index ? 0 : chosen > index ? chosen - 1 : chosen;
      return { cands: next, chosen: Math.min(newChosen, Math.max(0, next.length - 1)), message: "Miniature retirée" };
    });
  } catch (e) {
    return fail(e);
  }
}

export async function moreThumbnails(id: string, count = 3): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    if (!lv.packaging) return { ok: false, message: "Pas encore d’emballage : le script doit être écrit" };
    if (await pendingJob(id, "long_make", "thumbnails")) return { ok: false, message: "Des miniatures se font déjà" };
    await enqueue(lv, "long_make", "thumbnails", { more: Math.max(1, Math.min(6, count)) }, 60);
    refresh(id);
    return { ok: true, message: `${count} nouvelles miniatures en cours, dans le style de la niche ; celles qui existent restent` };
  } catch (e) {
    return fail(e);
  }
}

export async function studyNicheThumbnails(): Promise<ActionResult> {
  try {
    const db = supabaseAdmin();
    const { data } = await db.from("jobs").select("id").eq("type", "long_write").eq("payload->>action", "thumb_style").in("status", ["queued", "running"]).limit(1);
    if (data?.length) return { ok: false, message: "L’étude des miniatures est déjà en cours" };
    const res = await db.from("jobs").insert({ type: "long_write", priority: 30, max_attempts: 2, payload: { action: "thumb_style", source: "dashboard" } });
    if (res.error) return { ok: false, message: res.error.message };
    refresh();
    return { ok: true, message: "La vision étudie les miniatures qui marchent dans la niche (une minute)" };
  } catch (e) {
    return fail(e);
  }
}

export async function savePublishing(id: string, title: string, description: string): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    const t = title.trim();
    if (t.length < 5 || t.length > 100) return { ok: false, message: "Titre de 5 à 100 caractères" };
    await supabaseAdmin()
      .from("long_videos")
      .update({ packaging: { ...(lv.packaging ?? {}), final_title: t, final_description: description.trim().slice(0, 4000) } })
      .eq("id", id);
    refresh(id);
    return { ok: true, message: "Titre et description enregistrés" };
  } catch (e) {
    return fail(e);
  }
}

export async function renderAgain(id: string): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    if (await pendingJob(id, "long_make", "render")) return { ok: false, message: "Le montage est déjà en file" };
    await enqueue(lv, "long_make", "render", {}, 80);
    refresh(id);
    return { ok: true, message: "Montage relancé" };
  } catch (e) {
    return fail(e);
  }
}

/** Envoi sur YouTube ; `again` : nouvel envoi après la suppression de l'ancien dans Studio (le worker le vérifie). */
export async function schedulePublish(id: string, localIso: string, again = false): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    if (!lv.video_id) return { ok: false, message: "La vidéo n’est pas encore montée" };
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(localIso)) return { ok: false, message: "Date invalide" };
    if (await pendingJob(id, "long_write", "publish")) return { ok: false, message: "L’envoi est déjà en cours" };
    // heure de Paris → instant précis (décalage du jour choisi)
    const probe = new Date(`${localIso}:00Z`);
    const paris = new Date(probe.toLocaleString("en-US", { timeZone: "Europe/Paris" }));
    const offsetMs = paris.getTime() - new Date(probe.toLocaleString("en-US", { timeZone: "UTC" })).getTime();
    const at = new Date(probe.getTime() - offsetMs);
    if (at.getTime() < Date.now() + 15 * 60 * 1000) return { ok: false, message: "Choisis une date dans au moins 15 minutes" };
    await enqueue(lv, "long_write", "publish", { publish_at: at.toISOString(), ...(again ? { again: true } : {}) }, 30);
    refresh(id);
    return { ok: true, message: `${again ? "Nouvel envoi" : "Envoi"} sur YouTube en cours (vidéo privée programmée, miniature posée)` };
  } catch (e) {
    return fail(e);
  }
}

/** Repose la miniature choisie sur la vidéo déjà envoyée (après un refus de YouTube, ou une autre miniature choisie). */
export async function resendThumbnail(id: string): Promise<ActionResult> {
  try {
    const lv = await getLong(id);
    if (await pendingJob(id, "long_write", "thumbnail")) return { ok: false, message: "La miniature part déjà" };
    await enqueue(lv, "long_write", "thumbnail", {}, 30);
    refresh(id);
    return { ok: true, message: "Miniature en cours d’envoi sur YouTube" };
  } catch (e) {
    return fail(e);
  }
}

// ---- Réglages -------------------------------------------------------------------------------------------------------

export async function saveLongSettings(settings: LongSettings): Promise<ActionResult> {
  try {
    const value = parseLongSettings(settings);
    const db = supabaseAdmin();
    const { data } = await db.from("app_settings").select("value").eq("key", "long").maybeSingle();
    const res = await db
      .from("app_settings")
      .upsert({ key: "long", value: { ...(data?.value ?? {}), ...value }, updated_at: new Date().toISOString() });
    if (res.error) return { ok: false, message: res.error.message };
    refresh();
    return { ok: true, message: "Réglages enregistrés" };
  } catch (e) {
    return fail(e);
  }
}
