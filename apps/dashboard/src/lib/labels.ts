/** Libellés français des énumérations du domaine + décor des catégories. */
import type {
  AlertSeverity,
  ChannelLang,
  ConceptStatus,
  JobStatus,
  JobType,
  ProductionStatus,
  VideoFormat,
  VideoStatus,
} from "@/lib/types";

export interface CategoryMeta {
  label: string;
  emoji: string;
  /** Classes Tailwind `from-* to-*` du poster dégradé. */
  gradient: string;
}

export const CATEGORIES: Record<string, CategoryMeta> = {
  secret_passages: { label: "Passages secrets", emoji: "🚪", gradient: "from-amber-500 to-rose-800" },
  space_optimization: { label: "Optimisation d’espace", emoji: "📐", gradient: "from-sky-500 to-indigo-800" },
  pool: { label: "Piscine", emoji: "🏊", gradient: "from-cyan-400 to-blue-800" },
  container: { label: "Container", emoji: "📦", gradient: "from-orange-500 to-amber-900" },
  hidden_cinema: { label: "Cinéma caché", emoji: "🎬", gradient: "from-fuchsia-600 to-purple-950" },
  slat_wall: { label: "Mur tasseaux + LED", emoji: "🪵", gradient: "from-yellow-500 to-orange-800" },
  smart_furniture: { label: "Mobilier motorisé", emoji: "🛋️", gradient: "from-emerald-500 to-teal-900" },
  office_pod: { label: "Pod bureau jardin", emoji: "🏡", gradient: "from-lime-500 to-green-900" },
  concrete_epoxy: { label: "Béton / époxy", emoji: "🪨", gradient: "from-slate-400 to-slate-900" },
  under_stairs: { label: "Sous escalier", emoji: "🍷", gradient: "from-red-500 to-rose-950" },
  ceiling_storage: { label: "Rangement plafond", emoji: "⬆️", gradient: "from-violet-500 to-indigo-950" },
  zen_bathroom: { label: "Salle de bain zen", emoji: "🛁", gradient: "from-teal-400 to-cyan-900" },
};

const UNKNOWN_CATEGORY: CategoryMeta = { label: "Autre", emoji: "🎞️", gradient: "from-zinc-500 to-zinc-800" };

export function categoryMeta(category: string | null | undefined): CategoryMeta {
  return (category && CATEGORIES[category]) || UNKNOWN_CATEGORY;
}

export function categoryLabel(category: string | null | undefined): string {
  return categoryMeta(category).label;
}

export const FORMAT_LABELS: Record<VideoFormat, { short: string; long: string; description: string }> = {
  A_voiceover: {
    short: "A · voix",
    long: "Format A — voix off",
    description: "Narration IA (TTS) par-dessus les clips générés.",
  },
  B_visual: {
    short: "B · visuel",
    long: "Format B — visuel",
    description: "Visuel pur, foley et SFX, texte à l’écran.",
  },
};

/** Langue d'une chaîne : voix, sous-titres et métadonnées de ses vidéos. */
export const LANG_LABELS: Record<ChannelLang, string> = { fr: "Français", en: "Anglais" };

export const VIDEO_STATUS_LABELS: Record<VideoStatus, string> = {
  pending: "En attente",
  rendering: "Rendu",
  qa: "Contrôle qualité",
  review: "À valider",
  ready: "Prête",
  uploading: "Envoi",
  scheduled: "Programmée",
  published: "Publiée",
  failed: "Échec",
  unpublished: "Privée",
};

export const PRODUCTION_STATUS_LABELS: Record<ProductionStatus, string> = {
  draft: "Brouillon",
  scripting: "Script",
  storyboard_review: "Storyboard à valider",
  generating: "Génération",
  assembling: "Assemblage",
  ready: "Prête",
  failed: "En échec",
  archived: "Archivée",
  cancelled: "Arrêtée",
};

export const JOB_TYPE_LABELS: Record<JobType, string> = {
  import_channel: "Import de l’historique YouTube",
  ideate: "Idéation",
  script: "Écriture du script",
  storyboard: "Images du storyboard",
  render: "Lancement du rendu",
  generate_clip: "Génération de clip",
  tts: "Voix off (TTS)",
  seo: "Titre et description (SEO)",
  strategy: "Stratégie",
  assemble: "Assemblage",
  qa: "Contrôle qualité",
  upload: "Envoi YouTube",
  sync_metrics: "Synchro métriques",
  sync_retention: "Synchro rétention",
  sync_comments: "Synchro commentaires",
  improve: "Amélioration",
  voice_preview: "Essai de voix",
  montage_preview: "Rendu exact du montage",
  analyze: "Analyse des vidéos",
  tiktok_publish: "Publication TikTok",
  sync_tiktok: "Synchro stats TikTok",
};

export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  queued: "En file",
  running: "En cours",
  done: "Terminé",
  failed: "Échec",
  cancelled: "Annulé",
};

export const CONCEPT_STATUS_LABELS: Record<ConceptStatus, string> = {
  proposed: "Proposée",
  approved: "Approuvée",
  rejected: "Rejetée",
  used: "Utilisée",
};

export const CONCEPT_SOURCE_LABELS: Record<"agent" | "manual" | "clone", string> = {
  agent: "Agent",
  manual: "Manuel",
  clone: "Clone",
};

export const SEVERITY_LABELS: Record<AlertSeverity, string> = {
  info: "Info",
  warning: "Avertissement",
  error: "Erreur",
};

/** Modèle vidéo d'une production (productions.video_provider) : workflow ComfyUI local, ou Gemini en ligne (docs/17). */
export function videoProviderLabel(provider: string): string {
  return provider === "gemini_web" ? "Gemini en ligne" : provider.replace(/^comfy_/, "");
}
