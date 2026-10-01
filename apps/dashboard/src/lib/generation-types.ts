/** Types de Réglages → Modèles de génération, partagés par le serveur (lecture du catalogue) et le composant client.
 * (Un fichier « use server » ne peut exporter que des fonctions : les types vivent ici.) */

export type GenerationKind = "image" | "video";
export type VoiceLang = "fr" | "en";

export interface CatalogEntry {
  /** Nom du workflow ComfyUI (services/worker/workflows/<name>.json). */
  name: string;
  kind: GenerationKind;
  label: string;
  detail: string;
  license: string;
  /** Licence compatible avec une chaîne monétisée (docs/14, ADR-007). */
  publishable: boolean;
  /** Fichiers de modèles cités par le workflow. */
  files: string[];
  /** Fichiers absents de ComfyUI ; null si ComfyUI est éteint (disponibilité inconnue). */
  missing: string[] | null;
}

/** Une voix de narration : « moteur:voix » (catalog.json → voices), avec les infos de son moteur (catalog.json → tts). */
export interface VoiceEntry {
  id: string;
  engine: string;
  label: string;
  engineLabel: string;
  detail: string;
  license: string;
  publishable: boolean;
  /** Fichiers du moteur absents de <YT2_HOME> (environnement Python, modèles) ; vide = installé. */
  missing: string[];
  /** Voix Gemini qui la remplace quand Gemini joue les voix (catalog.json → params.gemini) ; null sinon. */
  gemini: string | null;
}

/** Jeu des voix (catalog.json → acting, docs/41) : comment les voix Qwen dessinées disent leurs répliques. */
export interface ActingEntry {
  /** « neutral », « qwen3_emotion », « qwen3_instruct », « gemini ». */
  id: string;
  label: string;
  detail: string;
  /** Vaut aussi pour les récits (Gemini lit la narration avec la description de la voix). */
  narration: boolean;
  /** Fichiers du moteur absents de <YT2_HOME> ; vide = installé (ou rien à installer : en ligne, « neutral »). */
  missing: string[];
}

/** Une clé Gemini réservée à la voix (app_secrets gemini_voice_api_key, _2…) : son numéro et ses 4 derniers caractères. */
export interface VoiceKey {
  slot: number;
  hint: string;
}

export interface GenerationCatalog {
  image: CatalogEntry[];
  video: CatalogEntry[];
  voices: Record<VoiceLang, VoiceEntry[]>;
  acting: ActingEntry[];
  voiceKeys: VoiceKey[];
  comfyOnline: boolean;
}

export interface GenerationSettings {
  image_workflow: string;
  video_workflow: string;
  storyboard_candidates: number;
  /** Langue → « moteur:voix » (un nom seul, ancien format, est une voix Kokoro). */
  voices: Record<VoiceLang, string>;
  /** Jeu des voix (ActingEntry.id) : drames, et récits pour un jeu marqué « narration ». */
  voice_acting: string;
}

export const DEFAULT_GENERATION: GenerationSettings = {
  image_workflow: "zimage_turbo",
  video_workflow: "wan22_i2v_4step",
  storyboard_candidates: 2,
  voices: { fr: "kokoro:ff_siwis", en: "kokoro:af_heart" },
  voice_acting: "neutral",
};

/** « ff_siwis » (réglages d'avant les moteurs multiples) → « kokoro:ff_siwis ». */
export function normalizeVoiceId(id: string): string {
  const v = id.trim();
  return v && !v.includes(":") ? `kokoro:${v}` : v;
}

/** État d'un essai de voix (job voice_preview), lu toutes les secondes par le bouton « Écouter ». */
export interface VoicePreviewState {
  status: "queued" | "running" | "done" | "failed" | "cancelled" | "unknown";
  label: string | null;
  error: string | null;
  /** Rempli quand l'essai est prêt. */
  audioUrl: string | null;
  durationS: number | null;
  elapsedS: number | null;
}
