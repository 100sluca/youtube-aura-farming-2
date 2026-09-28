/** Bibliothèque : types et regroupements partagés serveur / navigateur. Données : lib/library.ts. */
import type { VideoDetail } from "@/lib/data/contract";
import type { VideoInsight } from "@/lib/stats-types";
import type { ProductionCard, ProductionStatus, VideoOverview } from "@/lib/types";

export interface LibraryItem extends VideoOverview {
  /** Place occupée sur le PC (dossier de la vidéo + dossier de sa production), en octets. */
  size_bytes: number;
  /** Vidéo de l'appli pas encore montée (docs/28) : où en est sa fabrication. Absent une fois le montage fini. */
  making?: LibraryMaking | null;
}

/** Fabrication d'une vidéo pas encore montée, avec les mots du gestionnaire de tâches (lib/tasks.ts). */
export interface LibraryMaking {
  /** Statut de la production (« failed » aussi quand un job a définitivement échoué et que plus rien ne tourne). */
  status: ProductionStatus;
  /** « Storyboard à valider », « Clip 3 sur 6 », « En file · clip 1 sur 7 », « Arrêtée »… */
  stage: string;
  progress_pct: number;
  /** Un calcul tourne pour elle : il faut l'arrêter avant de la supprimer. */
  running: boolean;
  /** Fin estimée (ISO), d'après les durées mesurées des tâches précédentes. */
  eta_at: string | null;
  /** Image du storyboard qui sert de vignette (la première retenue, sinon la première faite). */
  cover_asset_id: string | null;
  /** Titre de l'idée : la vidéo n'a son propre titre qu'après l'agent SEO. */
  concept_title: string | null;
}

/** Clip déjà fabriqué d'une vidéo pas encore montée. */
export interface LibraryClip {
  asset_id: string;
  scene_index: number | null;
}

export interface LibraryDetail {
  detail: VideoDetail | null;
  production: ProductionCard | null;
  /** Storyboard gardé dans Favoris (docs/19). */
  favorite?: boolean;
  /** Avis de l'agent analyste sur cette vidéo (docs/25). */
  insight?: VideoInsight | null;
  /** Clips déjà faits, pour une vidéo pas encore montée (docs/28). */
  clips?: LibraryClip[];
}

export type LibraryGroup = "a_valider" | "en_cours" | "programmees" | "publiees" | "refusees" | "autres";

export const LIBRARY_GROUPS: { id: LibraryGroup; label: string }[] = [
  { id: "a_valider", label: "À valider" },
  { id: "en_cours", label: "En fabrication" },
  { id: "programmees", label: "Programmées" },
  { id: "publiees", label: "Publiées" },
  { id: "refusees", label: "Refusées" },
  { id: "autres", label: "Autres" },
];

export function libraryGroup(v: Pick<LibraryItem, "status" | "error" | "making">): LibraryGroup {
  // Pas encore montée, qu'elle avance, attende le ✓ du storyboard ou soit arrêtée (son badge le dit)
  if (v.making) return "en_cours";
  if (v.status === "review" || v.status === "qa") return "a_valider";
  if (v.status === "ready" || v.status === "uploading" || v.status === "scheduled") return "programmees";
  if (v.status === "published") return "publiees";
  if (v.status === "failed" && (v.error ?? "").startsWith("Refusée")) return "refusees";
  return "autres";
}

export function isLibraryGroup(value: unknown): value is LibraryGroup {
  return typeof value === "string" && LIBRARY_GROUPS.some((g) => g.id === value);
}
