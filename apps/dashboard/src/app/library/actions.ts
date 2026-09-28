"use server";

/**
 * Gestes de la Bibliothèque : détail d'une vidéo (stats, fabrication, clips déjà faits) et suppression pour libérer
 * le disque, vidéos de l'appli comme démos et essais faits hors de l'appli (docs/28).
 */
import { revalidatePath } from "next/cache";

import type { ActionResult } from "@/app/production/actions";
import { deleteLibraryVideo } from "@/lib/deletion";
import { removeDemo } from "@/lib/demos";
import { formatBytes } from "@/lib/format";
import { getLibraryDetail } from "@/lib/library";
import type { LibraryDetail } from "@/lib/library-types";

export async function fetchLibraryDetail(videoId: string, productionId: string | null, withClips = false): Promise<LibraryDetail> {
  return getLibraryDetail(videoId, productionId, withClips);
}

/** Supprime une ou plusieurs vidéos : fichiers seuls pour celles déjà sur YouTube, tout le reste sinon. */
export async function deleteVideos(ids: string[]): Promise<ActionResult> {
  let freed = 0;
  let done = 0;
  const errors: string[] = [];
  for (const id of ids.slice(0, 200)) {
    const res = await deleteLibraryVideo(id);
    if (res.ok) {
      done += 1;
      freed += res.freed;
    } else errors.push(res.message);
  }
  revalidatePath("/", "layout");
  if (ids.length === 1) {
    const one = errors[0];
    return one ? { ok: false, message: one } : { ok: true, message: `Supprimée · ${formatBytes(freed)} libérés sur le PC` };
  }
  const summary = `${done} vidéo${done > 1 ? "s" : ""} supprimée${done > 1 ? "s" : ""} · ${formatBytes(freed)} libérés`;
  return errors.length ? { ok: done > 0, message: `${summary} · ${errors.length} refus : ${[...new Set(errors)].join(" ; ")}` } : { ok: true, message: summary };
}

/** Supprime le dossier entier d'une démo ou d'un essai (vidéos, clips, images, journaux). */
export async function deleteDemo(id: string): Promise<ActionResult> {
  try {
    const freed = await removeDemo(id);
    revalidatePath("/library");
    return { ok: true, message: `Dossier supprimé · ${formatBytes(freed)} libérés sur le PC` };
  } catch (error) {
    return { ok: false, message: error instanceof Error ? error.message : String(error) };
  }
}
