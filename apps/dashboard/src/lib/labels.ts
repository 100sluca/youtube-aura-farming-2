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

export const CHANNEL_LABELS: Record<ChannelLang, string> = { fr: "FR", en: "EN" };

export const VIDEO_STATUS_LABELS: Record<VideoStatus, string> = {
  pending: "En attente",
  rendering: "Rendu",
  qa: "Contrôle qualité",
  review: "Revue",
  ready: "Prête",
  uploading: "Envoi",
  scheduled: "Programmée",
  published: "Publiée",
  failed: "Échec",
  unpublished: "Dépubliée",
};

export const PRODUCTION_STATUS_LABELS: Record<ProductionStatus, string> = {
  draft: "Brouillon",
  scripting: "Script",
  generating: "Génération",
  assembling: "Assemblage",
  ready: "Prête",
  failed: "En échec",
  archived: "Archivée",
};

export const JOB_TYPE_LABELS: Record<JobType, string> = {
  ideate: "Idéation",
  script: "Écriture du script",
  generate_clip: "Génération de clip",
  tts: "Voix off (TTS)",
  assemble: "Assemblage",
  qa: "Contrôle qualité",
  upload: "Envoi YouTube",
  sync_metrics: "Synchro métriques",
  sync_retention: "Synchro rétention",
  sync_comments: "Synchro commentaires",
  improve: "Amélioration",
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
