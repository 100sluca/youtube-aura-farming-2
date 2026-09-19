"use server";

import { getVideoDetail } from "@/lib/data";
import type { VideoDetail } from "@/lib/data";

/** Détail d'une vidéo (métriques, rétention, commentaires, script) chargé à l'ouverture du panneau. */
export async function fetchVideoDetail(id: string): Promise<VideoDetail | null> {
  return getVideoDetail(id);
}
