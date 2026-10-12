/**
 * Modificateur de voix réglé par Luca (docs/67, docs/68) : une modification légère qui reste sa voix, sans conversion
 * vers une autre voix. Mêmes réglages et mêmes bornes que services/worker/worker/longform/voice_mod.py (PARAMS). Les
 * réglages enregistrés vivent dans app_settings.voice_mods ; une vidéo longue en choisit un par
 * voice.modifier_voice = "reglage:<id>".
 */

/** « naturel » : vocodeur pc-NSF-HiFiGAN (par défaut) ; « praat » : PSOLA. Rubber Band, retiré le 05/10, devient « naturel ». */
export type VoiceModEngine = "naturel" | "praat";

export interface VoiceModParams {
  pitch_st: number;
  formant_pct: number;
  range_pct: number;
  speed_pct: number;
  warmth_db: number;
  presence_db: number;
  air_db: number;
  density: number;
  room: number;
  engine: VoiceModEngine;
}

export type VoiceModKey = Exclude<keyof VoiceModParams, "engine">;

export interface VoiceProfile {
  id: string;
  name: string;
  params: VoiceModParams;
  updated_at?: string;
}

export const VOICE_MOD_PREFIX = "reglage:";

export interface VoiceModField {
  key: VoiceModKey;
  label: string;
  hint: string;
  min: number;
  max: number;
  step: number;
  neutral: number;
  unit: string;
  group: "voix" | "son";
}

export const VOICE_MOD_FIELDS: VoiceModField[] = [
  { key: "pitch_st", label: "Hauteur", hint: "Plus grave à gauche, plus aiguë à droite.", min: -4, max: 4, step: 0.1, neutral: 0, unit: "demi-ton", group: "voix" },
  { key: "formant_pct", label: "Timbre", hint: "La taille de la voix : plus ample à gauche, plus claire à droite.", min: -12, max: 12, step: 0.5, neutral: 0, unit: "%", group: "voix" },
  { key: "range_pct", label: "Intonation", hint: "La mélodie des phrases : plus plate à gauche, plus chantante à droite.", min: 50, max: 150, step: 1, neutral: 100, unit: "%", group: "voix" },
  { key: "speed_pct", label: "Débit", hint: "La vitesse de lecture ; les images suivent.", min: 85, max: 115, step: 1, neutral: 100, unit: "%", group: "voix" },
  { key: "warmth_db", label: "Chaleur", hint: "Les graves, vers 160 Hz.", min: -6, max: 6, step: 0.5, neutral: 0, unit: "dB", group: "son" },
  { key: "presence_db", label: "Présence", hint: "Le médium qui rapproche la voix, vers 3 kHz.", min: -6, max: 6, step: 0.5, neutral: 0, unit: "dB", group: "son" },
  { key: "air_db", label: "Brillance", hint: "Les aigus et le souffle, vers 8,5 kHz.", min: -6, max: 6, step: 0.5, neutral: 0, unit: "dB", group: "son" },
  { key: "density", label: "Densité", hint: "Un compresseur : une voix plus égale, plus « radio ».", min: 0, max: 100, step: 5, neutral: 0, unit: "%", group: "son" },
  { key: "room", label: "Pièce", hint: "Un peu de la résonance d’une petite pièce.", min: 0, max: 100, step: 5, neutral: 0, unit: "%", group: "son" },
];

export const VOICE_MOD_ENGINES: { id: VoiceModEngine; label: string; hint: string }[] = [
  {
    id: "naturel",
    label: "Naturelle (vocodeur)",
    hint: "Ta voix refaite par un vocodeur avec une autre hauteur et un autre timbre : la texture reste, même en bougeant le timbre. Essai en 3 à 5 s.",
  },
  {
    id: "praat",
    label: "Praat",
    hint: "Ta forme d’onde recopiée période par période : juste pour la hauteur, un peu rêche dès qu’on touche au timbre. Essai en 1 s.",
  },
];

export const NEUTRAL_PARAMS: VoiceModParams = {
  ...(Object.fromEntries(VOICE_MOD_FIELDS.map((f) => [f.key, f.neutral])) as Record<VoiceModKey, number>),
  engine: "naturel",
};

export function normalizeParams(raw: unknown): VoiceModParams {
  const r = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const out = { ...NEUTRAL_PARAMS };
  for (const f of VOICE_MOD_FIELDS) {
    const v = Number(r[f.key]);
    out[f.key] = Number.isFinite(v) ? Math.round(Math.min(f.max, Math.max(f.min, v)) * 100) / 100 : f.neutral;
  }
  out.engine = r.engine === "praat" ? "praat" : "naturel";
  return out;
}

export function parseProfiles(value: unknown): VoiceProfile[] {
  const list = (value as { profiles?: unknown } | null)?.profiles;
  if (!Array.isArray(list)) return [];
  return list
    .filter((p): p is Record<string, unknown> => Boolean(p) && typeof p === "object" && typeof (p as { id?: unknown }).id === "string")
    .map((p) => ({
      id: String(p.id),
      name: typeof p.name === "string" && p.name.trim() ? p.name : "Sans nom",
      params: normalizeParams(p.params),
      updated_at: typeof p.updated_at === "string" ? p.updated_at : undefined,
    }));
}

export function sameParams(a: unknown, b: unknown): boolean {
  const x = normalizeParams(a);
  const y = normalizeParams(b);
  return x.engine === y.engine && VOICE_MOD_FIELDS.every((f) => x[f.key] === y[f.key]);
}

export function isNeutral(p: VoiceModParams): boolean {
  return VOICE_MOD_FIELDS.every((f) => p[f.key] === f.neutral);
}

/** « +1,5 demi-ton », « −5 % », « 100 % », « +2 dB ». */
export function formatModValue(f: VoiceModField, v: number): string {
  const n = Math.abs(v).toLocaleString("fr-FR", { maximumFractionDigits: 1 });
  const signed = f.neutral === 0 && f.min < 0;
  const sign = signed ? (v > 0 ? "+" : v < 0 ? "−" : "") : v < 0 ? "−" : "";
  const unit = f.unit === "demi-ton" ? (Math.abs(v) >= 2 ? " demi-tons" : " demi-ton") : ` ${f.unit}`;
  return `${sign}${n}${unit}`;
}

/** Extrait enregistré dans le Studio (<données>/voix-studio/extraits). */
export const SAMPLE_NAME = /^extrait_\d{13}\.(webm|ogg|m4a|wav)$/;
/** Fichier d'essai fait par le worker (<données>/voix-studio/essais) : original nettoyé ou essai d'un réglage. */
export const TRIAL_NAME = /^[0-9a-f]{12}_(original|[0-9a-f]{12})\.wav$/;
