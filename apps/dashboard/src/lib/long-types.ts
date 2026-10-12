/**
 * Vidéos longues « histoire et mystères » narrées par Luca (docs/63-videos-longues.md) : types et libellés partagés par
 * la page, ses actions et ses routes. Miroir des tables long_videos, long_shots, long_takes (migration 0054).
 */

import { sameParams, VOICE_MOD_PREFIX, type VoiceProfile } from "@/lib/voice-mods";

export type LongStage = "idea" | "writing" | "script" | "making" | "assembling" | "review" | "done" | "archived" | "failed";
export type LongFormat = "mystere" | "epoque" | "libre";

export const STAGE_LABELS: Record<LongStage, string> = {
  idea: "Sujet proposé",
  writing: "Écriture du script",
  script: "Script à relire",
  making: "Fabrication et voix",
  assembling: "Montage",
  review: "Prête à regarder",
  done: "Programmée",
  archived: "Écartée",
  failed: "En échec",
};

export const FORMAT_LABELS: Record<LongFormat, string> = {
  mystere: "Mystère",
  epoque: "Ta vie à l’époque",
  libre: "Libre",
};

export const FORMAT_HINTS: Record<LongFormat, string> = {
  mystere: "Une énigme réelle menée comme une enquête : ce qu’on croyait, les indices, la révélation.",
  epoque: "« Tu as 14 ans, nous sommes en 1347… » : une condition dure vécue en deuxième personne.",
  libre: "Un sujet d’histoire raconté librement.",
};

export const WEEKDAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];

export interface ThumbConcept {
  idea?: string;
  prompt: string;
  text?: string;
  text_side?: "left" | "right" | "top" | "bottom";
}

export interface LongIdea {
  subject: string;
  format: LongFormat;
  title: string;
  alt_titles?: string[];
  hook?: string;
  promise?: string;
  angle?: string;
  why?: string;
  thumbnail?: ThumbConcept;
  wikipedia?: string[];
  wikipedia_en?: string[];
  score?: number;
  /** Vidéos qui ont déjà marché sur ce sujet (relevées par la page Recherche). */
  proof?: { title: string; views?: number | null; channel?: string; url?: string }[];
  new_angle?: string;
}

export interface LongParagraph {
  key: string;
  text: string;
  show?: string;
  words?: number;
}

export interface LongChapter {
  index: number;
  title: string;
  question?: string;
  paragraphs: LongParagraph[];
}

export interface LongProblem {
  chapter: number;
  paragraph?: number | null;
  problem: string;
  fix?: string;
}

export interface LongScript {
  central_idea?: string;
  engine?: string;
  protagonist?: string;
  stakes?: string;
  promise?: string;
  ending?: string;
  chapters: LongChapter[];
  words?: number;
  minutes_at_150?: number;
  lint?: LongProblem[];
  design_bible?: string | null;
  edited?: boolean;
  factcheck?: FactCheckSummary | null;
}

export type FactStatus = "confirmed" | "hypothesis" | "unsupported" | "contradicted";

export interface FactCheckSummary {
  total: number;
  confirmed: number;
  hypothesis: number;
  unsupported: number;
  contradicted: number;
  summary?: string;
  corrected?: string[];
  claims?: { chapter: number; paragraph?: number | null; claim: string; status: FactStatus; source?: string; fix?: string }[];
}

export interface DossierSource {
  n: number;
  title: string;
  url: string;
  lang: string;
  label?: string;
}

export interface LongPackaging {
  titles: { title: string; angle?: string }[];
  chosen: number;
  description: string;
  tags?: string[];
  hashtags?: string[];
  pinned_comment?: string;
  thumbnails?: ThumbConcept[];
  music_mood?: string | null;
  final_title?: string;
  final_description?: string;
}

export interface ThumbCandidate {
  file?: string;
  idea?: string;
  text?: string;
  side?: string;
  score?: number;
  note?: string;
  /** Gardée par Luca : jamais remplacée quand on en propose d'autres. */
  kept?: boolean;
  /** Retenue pour le test A/B de YouTube (3 au plus). */
  ab?: boolean;
  round?: number;
}

export interface LongThumbnail {
  candidates?: ThumbCandidate[];
  chosen?: number;
  picked_by?: string;
}

export interface LongVoice {
  modifier?: boolean;
  modifier_voice?: string;
  /** Ce que la voix finale a réellement reçu (le choix ci-dessus peut avoir changé depuis) ; params : le réglage du
   * Studio du modificateur au moment de la voix (docs/67). */
  made_with?: { modifier: boolean; voice: string; params?: unknown; cleaning?: number };
  paragraphs?: Record<string, { duration_s: number; original?: string }>;
  done_at?: number;
}

/** Voix finale faite : avec ou sans modificateur, et vers quelle voix. Avant le 05/10, déduit des paragraphes (une voix
 * modifiée garde le chemin de l'originale). */
/** Version du nettoyage des prises (services/worker/worker/longform/voice.py, CLEANING_VERSION) : 2 = coupe sur la voix,
 * bruit des pauses baissé, DeepFilterNet si la pièce est bruyante (docs/68). */
export const VOICE_CLEANING_VERSION = 2;

/** La voix finale a été nettoyée par une version plus ancienne : la refaire améliore les coutures entre paragraphes. */
export function voiceCleaningOutdated(v: LongVoice | null | undefined): boolean {
  const made = voiceMadeWith(v);
  return Boolean(made) && (made!.cleaning ?? 1) < VOICE_CLEANING_VERSION;
}

export function voiceMadeWith(v: LongVoice | null | undefined): { modifier: boolean; voice: string; params?: unknown; cleaning?: number } | null {
  if (!v?.done_at) return null;
  if (v.made_with) return v.made_with;
  const modified = Object.values(v.paragraphs ?? {}).some((p) => Boolean(p.original));
  return { modifier: modified, voice: modified ? (v.modifier_voice ?? "") : "" };
}

/** La voix finale déjà faite diffère du choix (modificateur, voix d'arrivée, ou réglage modifié depuis dans le
 * Studio du modificateur) : il faut la refaire sur les mêmes prises. */
export function voiceNeedsRedo(
  v: LongVoice | null | undefined,
  voiceDoneAt: string | null,
  on: boolean,
  voice: string,
  profiles: VoiceProfile[],
): boolean {
  const made = voiceMadeWith(v);
  if (!voiceDoneAt || !made) return false;
  if ((made.cleaning ?? 1) < VOICE_CLEANING_VERSION) return true;
  if (made.modifier !== on) return true;
  if (!on) return false;
  if (made.voice !== voice) return true;
  if (!voice.startsWith(VOICE_MOD_PREFIX)) return false;
  const profile = profiles.find((p) => VOICE_MOD_PREFIX + p.id === voice);
  return Boolean(profile) && !sameParams(profile!.params, made.params);
}

export interface LongTimeline {
  total_s?: number;
  chapters?: { at: number; title: string }[];
}

export interface LongVideo {
  id: string;
  channel_id: string;
  production_id: string | null;
  video_id: string | null;
  stage: LongStage;
  format: LongFormat;
  origin: string;
  subject: string;
  idea: LongIdea | null;
  script: LongScript | null;
  review: { ok?: boolean; problems?: LongProblem[]; strengths?: string } | null;
  packaging: LongPackaging | null;
  thumbnail: LongThumbnail | null;
  dossier: { sources?: DossierSource[]; chars?: number } | null;
  voice: LongVoice | null;
  timeline: LongTimeline | null;
  target_minutes: number;
  notes: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  voice_done_at: string | null;
  rendered_at: string | null;
}

export interface LongShot {
  idx: number;
  chapter: number;
  para: string;
  at_word: number;
  kind: "image" | "clip" | "map";
  visual_prompt: string;
  motion: string | null;
  status: string;
  has_image: boolean;
  has_clip: boolean;
  qc: { ok?: boolean; problem?: string; redone?: boolean; first_problem?: string } | null;
  error: string | null;
  updated_at: string;
}

export type TakeStatus = "checking" | "ok" | "problem" | "failed";

export interface LongTake {
  id: string;
  para: string;
  take: number;
  status: TakeStatus;
  chosen: boolean;
  duration_s: number | null;
  check: { ratio?: number; missing?: string[]; extra?: string[]; heard?: string; unchecked?: boolean; silent?: boolean } | null;
  created_at: string;
}

export interface LongJob {
  id: string;
  type: string;
  action: string;
  status: "queued" | "running";
  progress: number | null;
  label: string | null;
  long_id: string | null;
}

export interface LongSettings {
  weekdays: number[];
  hour: string;
  target_minutes: number;
  formats: LongFormat[];
  voice_modifier: boolean;
  modifier_voice: string;
  /** Le texte lu gravé en bas de l'image (docs/63 §12). */
  subtitles: boolean;
}

export const DEFAULT_LONG_SETTINGS: LongSettings = {
  weekdays: [2, 4, 6],
  hour: "17:00",
  target_minutes: 22,
  formats: ["mystere", "epoque"],
  voice_modifier: false,
  modifier_voice: "qwen3:narrateur",
  subtitles: true,
};

export function parseLongSettings(value: unknown): LongSettings {
  const v = (value ?? {}) as Partial<LongSettings>;
  return {
    weekdays: Array.isArray(v.weekdays) && v.weekdays.length ? v.weekdays.map(Number).filter((d) => d >= 1 && d <= 7) : DEFAULT_LONG_SETTINGS.weekdays,
    hour: typeof v.hour === "string" && /^\d{1,2}:\d{2}$/.test(v.hour) ? v.hour : DEFAULT_LONG_SETTINGS.hour,
    target_minutes: Number(v.target_minutes) >= 8 && Number(v.target_minutes) <= 60 ? Number(v.target_minutes) : DEFAULT_LONG_SETTINGS.target_minutes,
    formats: Array.isArray(v.formats) && v.formats.length ? (v.formats.filter((f) => f in FORMAT_LABELS) as LongFormat[]) : DEFAULT_LONG_SETTINGS.formats,
    voice_modifier: Boolean(v.voice_modifier),
    modifier_voice: typeof v.modifier_voice === "string" && v.modifier_voice ? v.modifier_voice : DEFAULT_LONG_SETTINGS.modifier_voice,
    subtitles: v.subtitles !== false,
  };
}

/** Voix d'arrivée possibles du modificateur : voix Qwen dessinées (aucune personne réelle). */
export const MODIFIER_VOICES: { id: string; label: string }[] = [
  { id: "qwen3:narrateur", label: "Narrateur grave (homme)" },
  { id: "qwen3:mystere", label: "Récit mystérieux (homme)" },
  { id: "qwen3:energique_h", label: "Présentateur dynamique (homme)" },
  { id: "qwen3:perso_papi", label: "Vieil homme bienveillant" },
  { id: "qwen3:narratrice", label: "Conteuse chaleureuse (femme)" },
];

export interface LongCard {
  id: string;
  stage: LongStage;
  format: LongFormat;
  subject: string;
  title: string;
  idea: LongIdea | null;
  words: number | null;
  paragraphs: number;
  takes_ok: number;
  shots_total: number;
  shots_done: number;
  thumb: boolean;
  error: string | null;
  created_at: string;
  approved_at: string | null;
  voice_done_at: string | null;
  scheduled_at: string | null;
  youtube_video_id: string | null;
}

export interface LongOverview {
  channelId: string | null;
  cards: LongCard[];
  jobs: LongJob[];
  settings: LongSettings;
  /** Réglages du Studio du modificateur de voix (docs/67). */
  voiceProfiles: VoiceProfile[];
}

export interface LongDetail {
  video: LongVideo;
  shots: LongShot[];
  takes: LongTake[];
  jobs: LongJob[];
  final: { status: string; youtube_video_id: string | null; scheduled_at: string | null; duration_s: number | null } | null;
  nextSlot: string;
  /** Style des miniatures relevé sur celles qui marchent dans la niche (« Étudier les miniatures de la niche »). */
  thumbStyle: { style: string; rules: string[]; n?: number; at?: string } | null;
  thumbStyleRunning: boolean;
  /** Réglages du Studio du modificateur de voix (docs/67). */
  voiceProfiles: VoiceProfile[];
}

export function titleOf(v: Pick<LongVideo, "packaging" | "idea" | "subject">): string {
  const p = v.packaging;
  if (p?.final_title) return p.final_title;
  if (p?.titles?.length) return p.titles[Math.min(p.chosen ?? 0, p.titles.length - 1)].title;
  return v.idea?.title || v.subject;
}

export function allParagraphs(script: LongScript | null): (LongParagraph & { chapter: number; chapterTitle: string })[] {
  return (script?.chapters ?? []).flatMap((c) => c.paragraphs.map((p) => ({ ...p, chapter: c.index, chapterTitle: c.title })));
}

/** Minutes de micro estimées : la durée lue à 150 mots par minute, × 1,6 pour les reprises. */
export function readingMinutes(words: number | null | undefined): number {
  return words ? Math.round((words / 150) * 1.6) : 0;
}

export const PARA_KEY = /^c\d{1,2}p\d{1,3}$/;

/** Le chapitre 0 est l'ouverture (la 1re minute) ; les suivants gardent leur numéro. */
export function chapterLabel(index: number): string {
  return index === 0 ? "Ouverture" : `Chapitre ${index}`;
}
