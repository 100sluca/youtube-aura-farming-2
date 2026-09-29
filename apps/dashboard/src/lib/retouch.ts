/**
 * Retouche d'une vidéo montée (Bibliothèque → Retoucher, docs/34-retouche.md) : ce que l'écran montre — pour chaque scène,
 * ce que dit la voix et ce que le montage automatique affiche, la retouche enregistrée, les musiques et les niveaux du
 * modèle de montage, les voix proposées, la narration pour l'écoute — et où en est la vidéo pendant qu'elle est refaite.
 * Serveur uniquement (clé service role).
 */
import { promises as fs } from "node:fs";

import { readDefaults } from "@/lib/font-files";
import { getGenerationCatalog } from "@/lib/generation-data";
import type { VoiceLang } from "@/lib/generation-types";
import { completeTemplate } from "@/lib/montage";
import { MONTAGE_FORMATS, type MontageFormat, type MontageTemplate } from "@/lib/montage-types";
import { audioConstants, chooseTrack, measureLoudness, syncTracks } from "@/lib/music-library";
import {
  RETOUCHABLE_STATUSES,
  type RetouchData,
  type RetouchJob,
  type RetouchPageData,
  type RetouchScene,
  type RetouchState,
} from "@/lib/retouch-types";
import { supabaseAdmin } from "@/lib/supabase-admin";
import type { VideoStatus } from "@/lib/types";

type Json = Record<string, unknown>;
const isObject = (v: unknown): v is Json => typeof v === "object" && v !== null && !Array.isArray(v);
const one = <T,>(v: T | T[] | null | undefined): T | null => (Array.isArray(v) ? (v[0] ?? null) : (v ?? null));
const UUID = /^[0-9a-f-]{36}$/i;

type TimelineScene = { index: number; speech_start?: number | null; speech_end?: number | null; words?: { text: string; start: number; end: number }[] };
type ScriptJson = {
  scenes?: { index: number; narration?: Json }[];
  hook_title?: Json;
  metadata?: Record<string, { title?: string }>;
  music_mood?: string | null;
};

function langText(v: unknown, lang: string): string {
  if (!isObject(v)) return "";
  const text = v[lang];
  return typeof text === "string" ? text.trim() : "";
}

/** worker/hooktitle.py : clean_hook (guillemets, hashtags, espaces, point final ; une majuscule en tête). */
function cleanHook(text: string): string {
  const t = text
    .replace(/#[\p{L}\p{N}_]+/gu, "")
    .replace(/[«»"“”]/g, "")
    .replace(/[ \t\r\n]+/g, " ")
    .trim()
    .replace(/^['’ ]+|['’ ]+$/g, "")
    .replace(/(?<![.!?])\.$/, "")
    .trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

function retouchOf(value: unknown): RetouchData {
  if (!isObject(value)) return {};
  const out: RetouchData = {};
  if (typeof value.hook_title === "string") out.hook_title = value.hook_title;
  if (isObject(value.hook_display)) {
    const d = value.hook_display.duration_s;
    out.hook_display = { duration_s: typeof d === "number" && d > 0 ? d : null };
  }
  if (isObject(value.subtitles)) {
    out.subtitles = Object.fromEntries(Object.entries(value.subtitles).filter((e): e is [string, string] => typeof e[1] === "string"));
  }
  if (isObject(value.music)) {
    out.music = {
      track: typeof value.music.track === "string" ? value.music.track : null,
      start_s: typeof value.music.start_s === "number" ? value.music.start_s : null,
    };
  }
  if (isObject(value.audio)) {
    out.audio = Object.fromEntries(Object.entries(value.audio).filter((e): e is [string, number] => typeof e[1] === "number"));
  }
  if (typeof value.voice === "string") out.voice = value.voice;
  return out;
}

/** Voix, montage et contrôle de la dernière retouche (ou du dernier « Refaire le montage ») : les jobs créés ensemble
 * par retouch_video / remount_video ont la même date de création. */
export async function getRetouchState(videoId: string): Promise<RetouchState> {
  const db = supabaseAdmin();
  const [{ data: v }, { data: rows }] = await Promise.all([
    db.from("videos").select("status, error, final_asset_id, poster_asset_id, duration_s").eq("id", videoId).maybeSingle(),
    db
      .from("jobs")
      .select("id, type, status, progress, progress_label, error, created_at, finished_at, payload")
      .eq("video_id", videoId)
      .in("type", ["tts", "assemble", "qa"])
      .order("created_at", { ascending: false })
      .limit(12),
  ]);
  type Row = {
    id: string;
    type: RetouchJob["type"];
    status: RetouchJob["status"];
    progress: number;
    progress_label: string | null;
    error: string | null;
    created_at: string;
    finished_at: string | null;
    payload: { retouch?: boolean } | null;
  };
  const jobs = (rows ?? []) as Row[];
  const last = jobs.find((j) => j.type === "assemble");
  const order = { tts: 0, assemble: 1, qa: 2 };
  const group = last ? jobs.filter((j) => j.created_at === last.created_at).sort((a, b) => order[a.type] - order[b.type]) : [];
  const qa = group.find((j) => j.type === "qa");
  return {
    status: (v?.status ?? "failed") as VideoStatus,
    error: (v?.error as string | null) ?? null,
    finalAssetId: (v?.final_asset_id as string | null) ?? null,
    posterAssetId: (v?.poster_asset_id as string | null) ?? null,
    durationS: v?.duration_s === null || v?.duration_s === undefined ? null : Number(v.duration_s),
    jobs: group.map((j) => ({ id: j.id, type: j.type, status: j.status, progress: j.progress ?? 0, label: j.progress_label, error: j.error })),
    busy: jobs.some((j) => j.status === "queued" || j.status === "running"),
    retouch: Boolean(last?.payload?.retouch),
    doneAt: group.length && group.every((j) => j.status === "done") ? (qa?.finished_at ?? last?.finished_at ?? null) : null,
  };
}

function blockedReason(v: Json, state: RetouchState): string | null {
  if (v.origin === "imported" || !v.production_id) return "Vidéo importée de YouTube : elle n’a pas été fabriquée ici, il n’y a rien à remonter.";
  if (v.files_deleted_at) return "Fichiers effacés du PC : il n’y a plus rien à remonter.";
  if (v.youtube_video_id) {
    return "Déjà envoyée sur YouTube, qui ne permet pas d’en remplacer le fichier : la retouche se fait avant l’envoi (vidéo à valider, ou autorisée mais pas encore partie).";
  }
  if (!v.final_asset_id) return "Pas encore montée : la retouche s’ouvre à la fin de sa fabrication.";
  if (!state.busy && !RETOUCHABLE_STATUSES.includes(v.status as VideoStatus)) return `Vidéo « ${String(v.status)} » : elle ne peut pas être retouchée pour l’instant.`;
  return null;
}

async function narrationOf(videoId: string, words: [number, number][], knownLufs: number | null): Promise<RetouchPageData["voice"]["narration"]> {
  const { data } = await supabaseAdmin()
    .from("assets")
    .select("id, local_path")
    .eq("video_id", videoId)
    .eq("kind", "narration")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  const file = data?.local_path as string | undefined;
  const st = file ? await fs.stat(file).catch(() => null) : null;
  if (!data || !file || !st || st.size < 2000 || !words.length) return null;
  const lufs = knownLufs ?? (await measureLoudness(file))?.lufs ?? null;
  return { url: `/api/media/${data.id as string}`, lufs, words };
}

export async function getRetouchPage(videoId: string): Promise<RetouchPageData | null> {
  if (!UUID.test(videoId)) return null;
  const db = supabaseAdmin();
  const { data: v } = await db.from("videos").select("*, channels(name)").eq("id", videoId).maybeSingle();
  if (!v) return null;
  const pid = (v.production_id as string | null) ?? null;
  const lang: VoiceLang = v.lang === "en" ? "en" : "fr";

  const [prod, saved, lastMontage, defaults, catalog, library, constants, state] = await Promise.all([
    pid ? db.from("productions").select("script, series(recipe, music_moods)").eq("id", pid).maybeSingle() : Promise.resolve({ data: null }),
    db.from("montage_templates").select("name, template").eq("is_default", true).maybeSingle(),
    db.from("jobs").select("result").eq("video_id", videoId).eq("type", "assemble").eq("status", "done").order("finished_at", { ascending: false }).limit(1).maybeSingle(),
    readDefaults(),
    getGenerationCatalog(),
    syncTracks(),
    audioConstants(),
    getRetouchState(videoId),
  ]);

  const script = (prod.data?.script ?? {}) as ScriptJson;
  const series = one(prod.data?.series as { recipe: string | null; music_moods: string[] | null } | { recipe: string | null; music_moods: string[] | null }[] | null);
  const format: MontageFormat = MONTAGE_FORMATS.includes(series?.recipe as MontageFormat) ? (series?.recipe as MontageFormat) : "story";
  const origin = completeTemplate(defaults.template as MontageTemplate, defaults.template);
  const template = saved.data ? completeTemplate(origin, saved.data.template) : origin;
  const voiced = v.format === "A_voiceover";
  const retouch = retouchOf(v.retouch);

  // Textes du dernier montage sans retouche (résultat du job assemble, docs/34) ; montage plus ancien : la voix
  const texts = isObject(lastMontage.data?.result) && isObject(lastMontage.data.result.texts) ? lastMontage.data.result.texts : {};
  const autoSubtitles = isObject(texts.subtitles) ? texts.subtitles : {};
  const timeline = (isObject(v.timeline) && Array.isArray(v.timeline.scenes) ? v.timeline.scenes : []) as TimelineScene[];
  const narrationByIndex = new Map((script.scenes ?? []).map((s, pos) => [s.index, { pos, text: langText(s.narration, lang) }]));
  const scenes: RetouchScene[] = timeline
    .filter((s) => (s.words ?? []).length > 0)
    .map((s) => {
      const words = s.words ?? [];
      const spokenWords = words.map((w) => w.text).join(" ");
      const auto = autoSubtitles[String(s.index)];
      return {
        index: s.index,
        position: narrationByIndex.get(s.index)?.pos ?? s.index,
        start: Number(s.speech_start ?? words[0].start),
        end: Number(s.speech_end ?? words[words.length - 1].end),
        spoken: narrationByIndex.get(s.index)?.text || spokenWords,
        auto: typeof auto === "string" && auto ? auto : spokenWords,
        edited: retouch.subtitles?.[String(s.index)] ?? null,
      };
    });

  const hookAuto =
    typeof texts.hook === "string" && texts.hook ? texts.hook : cleanHook(langText(script.hook_title, lang) || script.metadata?.[lang]?.title || String(v.title ?? ""));

  const tracks = library.tracks;
  const autoTrack = chooseTrack(tracks, format, script.music_mood ?? null, pid ?? videoId, series?.music_moods ?? [], constants);
  const words = timeline.flatMap((s) => (s.words ?? []).map((w) => [Number(w.start), Number(w.end)] as [number, number]));
  const audioMix = isObject(v.audio_mix) ? v.audio_mix : {};
  const narration = voiced ? await narrationOf(videoId, words, typeof audioMix.narration_lufs === "number" ? audioMix.narration_lufs : null) : null;
  const sample = (script.scenes ?? []).map((s) => langText(s.narration, lang)).find((t) => t.split(/\s+/).length >= 6) ?? "";

  return {
    video: {
      id: videoId,
      title: (v.title as string | null) ?? "Vidéo sans titre",
      lang,
      format,
      voiced,
      channelName: one(v.channels as { name: string } | { name: string }[] | null)?.name ?? null,
      youtubeVideoId: (v.youtube_video_id as string | null) ?? null,
    },
    blocked: blockedReason(v, state),
    hook: { auto: hookAuto, shown: template.hook.formats.includes(format), templateDurationS: template.hook.duration_s ?? null },
    subtitlesShown: voiced && template.subtitles.enabled,
    scenes: scenes.sort((a, b) => a.position - b.position),
    retouch,
    template: { name: (saved.data?.name as string | undefined) ?? "Modèle d’origine", audio: template.audio },
    music: { tracks, constants, current: (v.music_track as string | null) ?? null, auto: autoTrack, error: library.error },
    voice: {
      current: v.tts_provider && v.tts_voice ? `${v.tts_provider as string}:${v.tts_voice as string}` : null,
      entries: catalog.voices[lang],
      narration,
      sample,
    },
    state,
  };
}
