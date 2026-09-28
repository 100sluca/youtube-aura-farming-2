/**
 * Supprimer une vidéo ou une production (Bibliothèque, gestionnaire de tâches, storyboard abandonné dans Création).
 * Serveur uniquement.
 *
 * Règle : une vidéo déjà envoyée sur YouTube n'est jamais supprimée de YouTube ni de la base (ses stats restent) ;
 * seuls ses fichiers quittent le PC (SQL forget_video_files). Une vidéo qui n'est pas sur YouTube disparaît avec sa
 * production (SQL delete_production : vidéos, images, clips, tâches). On lit les chemins avant d'effacer la base,
 * puis on efface les dossiers.
 */
import { syncFavorite } from "@/lib/favorites";
import { formatBytes } from "@/lib/format";
import { ownedDirs, removeOwnedDir } from "@/lib/files";
import { supabaseAdmin } from "@/lib/supabase-admin";

export interface DeletionResult {
  ok: boolean;
  message: string;
  freed: number;
}

const fail = (message: string): DeletionResult => ({ ok: false, message, freed: 0 });

/** Production entière (pas encore sur YouTube). conceptStatus : ce que devient l'idée (inchangée par défaut). */
export async function deleteProduction(
  productionId: string,
  conceptStatus: "rejected" | "proposed" | null = null,
): Promise<DeletionResult> {
  const db = supabaseAdmin();
  const { data: prod, error } = await db.from("productions").select("id, concept_id").eq("id", productionId).maybeSingle();
  if (error) return fail(error.message);
  if (!prod) return fail("Production introuvable");
  const { data: videos } = await db.from("videos").select("id, youtube_video_id").eq("production_id", productionId);
  if ((videos ?? []).some((v) => v.youtube_video_id)) {
    return fail("Déjà envoyée sur YouTube : seuls ses fichiers peuvent être effacés (depuis la Bibliothèque)");
  }
  // delete_production refuse aussi, avec un message moins parlant (Bibliothèque, docs/28 : vidéos en fabrication)
  const { count: running } = await db.from("jobs").select("id", { count: "exact", head: true }).eq("production_id", productionId).eq("status", "running");
  if (running) return fail("En pleine fabrication : l’arrêter d’abord, puis supprimer");
  // Storyboard en favori : ses images sont recopiées avant l'effacement (le favori ne dépend pas de la production)
  await syncFavorite(productionId);
  const dirs = await Promise.all([
    ownedDirs({ videoId: null, productionId }),
    ...(videos ?? []).map((v) => ownedDirs({ videoId: v.id as string, productionId })),
  ]);
  const del = await db.rpc("delete_production", { p_production: productionId, p_reject_concept: conceptStatus === "rejected" });
  if (del.error) return fail(del.error.message);
  if (conceptStatus === "proposed" && prod.concept_id) {
    await db.from("concepts").update({ status: "proposed" }).eq("id", prod.concept_id).eq("status", "used");
  }
  let freed = 0;
  freed += await removeOwnedDir(dirs[0].production, productionId);
  for (const [i, v] of (videos ?? []).entries()) freed += await removeOwnedDir(dirs[i + 1].video, v.id as string);
  return { ok: true, message: `Supprimée · ${formatBytes(freed)} libérés`, freed };
}

/** Vidéo de la bibliothèque : fichiers seuls si elle est sur YouTube, sinon toute sa production. */
export async function deleteLibraryVideo(videoId: string): Promise<DeletionResult> {
  const db = supabaseAdmin();
  const { data: v, error } = await db
    .from("videos")
    .select("id, production_id, status, youtube_video_id, origin, files_deleted_at")
    .eq("id", videoId)
    .maybeSingle();
  if (error) return fail(error.message);
  if (!v) return fail("Vidéo introuvable");
  if (v.origin === "imported") return fail("Vidéo importée de YouTube : aucun fichier sur le PC");
  if (v.status === "uploading") return fail("Envoi YouTube en cours : réessayer dans une minute");
  if (!v.youtube_video_id) {
    if (!v.production_id) return fail("Vidéo sans production");
    return deleteProduction(v.production_id);
  }
  if (v.files_deleted_at) return { ok: true, message: "Fichiers déjà effacés", freed: 0 };
  // Sur YouTube : on garde la vidéo et ses stats, on efface ses fichiers (et ceux de la production si plus rien ne s'en sert)
  const { data: siblings } = v.production_id
    ? await db.from("videos").select("id").eq("production_id", v.production_id).neq("id", videoId).is("files_deleted_at", null)
    : { data: [] };
  const lastOne = (siblings ?? []).length === 0;
  const dirs = await ownedDirs({ videoId, productionId: lastOne ? v.production_id : null });
  const res = await db.rpc("forget_video_files", { p_video: videoId });
  if (res.error) return fail(res.error.message);
  let freed = await removeOwnedDir(dirs.video, videoId);
  if (lastOne && v.production_id) freed += await removeOwnedDir(dirs.production, v.production_id);
  return { ok: true, message: `Fichiers effacés du PC · ${formatBytes(freed)} libérés (la vidéo reste sur YouTube)`, freed };
}
