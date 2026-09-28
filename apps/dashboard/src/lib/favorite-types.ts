/** Storyboards favoris : types partagés serveur / navigateur (migration 0011, docs/19). Données : lib/favorites.ts. */
import type { ChannelLang, ProductionStatus, ScriptV1 } from "@/lib/types";

/** Image gardée d'une scène : copie dans DATA_DIR/favorites/<id>/, servie par /api/favorites/<id>/<file>. */
export interface FavoriteImage {
  scene_index: number;
  file: string;
  qc?: { ok: boolean; problems: string[] } | null;
}

export interface Favorite {
  id: string;
  title: string;
  hook: string | null;
  premise: string | null;
  series_name: string | null;
  recipe: string | null;
  channel_name: string | null;
  lang: ChannelLang | null;
  image_workflow: string | null;
  video_provider: string | null;
  script: ScriptV1;
  images: FavoriteImage[];
  /** Production d'origine, tant qu'elle existe (abandonnée ou supprimée : null). */
  production_id: string | null;
  original_status: ProductionStatus | null;
  remade_count: number;
  remade_at: string | null;
  created_at: string;
}

export function favoriteImageUrl(favoriteId: string, file: string): string {
  return `/api/favorites/${favoriteId}/${file}`;
}

/** Où en est l'original : pour ne pas refaire par mégarde un storyboard qui attend encore dans Création. */
export function originalLabel(status: ProductionStatus | null): string {
  switch (status) {
    case null:
      return "original abandonné ou supprimé";
    case "storyboard_review":
      return "l’original attend encore dans Création";
    case "draft":
    case "scripting":
    case "generating":
    case "assembling":
      return "l’original est en fabrication";
    case "ready":
      return "l’original est dans la Bibliothèque";
    case "cancelled":
      return "l’original est arrêté";
    default:
      return "";
  }
}
