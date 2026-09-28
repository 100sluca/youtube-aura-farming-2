/** Gemini en ligne (docs/17-gemini-en-ligne.md) : types partagés par le serveur et les composants client.
 * Réglages séparés des modèles locaux : app_settings « gemini » (réglages) et « gemini_status » (écrit par le worker). */

/** Nom du fournisseur vidéo d'une production fabriquée par Gemini (productions.video_provider). */
export const GEMINI_PROVIDER = "gemini_web";

export const GEMINI_DURATIONS = ["auto", "4", "6", "8", "10"] as const;
export type GeminiDuration = (typeof GEMINI_DURATIONS)[number];

export interface GeminiSettings {
  /** Numéro du compte Google dans le Chrome dédié (…/u/<n>/app) : 0 = le premier connecté. */
  authuser: number;
  /** Libellé du modèle à choisir dans l'appli Gemini (ex. « 3.5 Flash ») ; vide = celui que Gemini propose. */
  model: string;
  /** auto = la plus courte des durées proposées (4, 6, 8, 10 s) qui couvre la scène. */
  duration: GeminiDuration;
}

export const DEFAULT_GEMINI: GeminiSettings = { authuser: 0, model: "", duration: "auto" };

/** Dernier résultat du pilote Gemini, écrit par le worker (worker/providers/gemini_web.py). */
export interface GeminiStatus {
  at: string | null;
  ok: boolean | null;
  message: string | null;
  /** Limite atteinte : aucun clip n'est demandé avant cette heure (ISO). */
  quota_until: string | null;
  last_clip_at: string | null;
}

/** Ce que le serveur du dashboard voit du Chrome dédié. */
export interface GeminiBrowserInfo {
  chrome: string | null;
  profile: string | null;
  profileExists: boolean;
  port: number;
  running: boolean;
  /** Cookies de session Google présents (lu seulement quand Chrome tourne ; null = inconnu). */
  signedIn: boolean | null;
}

/** Quota constaté chez Luca (Google AI Pro, 26/09/2026) : ≈ 8 vidéos d'affilée, puis Gemini passe sur Flash-Lite et
 * ne propose plus la vidéo pendant quelques heures (docs/17 §2). */
export const GEMINI_QUOTA_NOTE = "Google AI Pro : ≈ 8 vidéos d'affilée, puis quelques heures d'attente";

/** Attente estimée pour n clips : une rafale de 8, puis ≈ 5 h avant la suivante (estimation grossière). */
export function geminiEtaHours(clips: number): number {
  return Math.max(0, Math.ceil(clips / 8) - 1) * 5;
}
