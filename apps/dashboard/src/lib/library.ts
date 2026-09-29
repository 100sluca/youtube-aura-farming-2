/**
 * Bibliothèque : toutes les vidéos de l'appli, montées ou encore en fabrication (docs/28), et les vidéos importées de
 * YouTube, avec la place qu'elles occupent sur le PC. Serveur uniquement.
 */
import { IS_MOCK, getProductionCard, getVideoDetail } from "@/lib/data";
import { mapOverview } from "@/lib/data/supabase";
import { favoriteProductions } from "@/lib/favorites";
import { dataRoot, videoFootprint } from "@/lib/files";
import { PRODUCTION_STATUS_LABELS } from "@/lib/labels";
import type { LibraryClip, LibraryDetail, LibraryItem, LibraryMaking } from "@/lib/library-types";
import { getVideoInsight } from "@/lib/insights";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { allTasks } from "@/lib/task-types";
import { getTaskBoard } from "@/lib/tasks";
import { getLibraryTikTok, getTikTokBriefs } from "@/lib/tiktok";
import type { ProductionStatus, VideoOverview } from "@/lib/types";

/** Vidéo de l'appli dont le montage n'existe pas encore (script, storyboard, clips en cours, ou fabrication arrêtée). */
function unfinished(v: VideoOverview): boolean {
  return v.origin !== "imported" && Boolean(v.production_id) && !v.final_asset_id && !v.files_deleted_at;
}

/** Où en sont les vidéos pas encore montées : étape, avancement et fin estimée du gestionnaire de tâches, vignette. */
async function makingOf(videos: VideoOverview[]): Promise<Map<string, LibraryMaking>> {
  const out = new Map<string, LibraryMaking>();
  const prodIds = [...new Set(videos.map((v) => v.production_id).filter((id): id is string => Boolean(id)))];
  if (prodIds.length === 0) return out;
  const db = supabaseAdmin();
  const [board, images, prods] = await Promise.all([
    getTaskBoard(),
    db.from("assets").select("id, production_id, scene_index, selected").in("production_id", prodIds).eq("kind", "storyboard").order("scene_index").order("created_at"),
    db.from("productions").select("id, concepts(title)").in("id", prodIds),
  ]);
  const tasks = new Map(allTasks(board).map((t) => [t.id, t]));
  const cover = new Map<string, { id: string; selected: boolean }>();
  for (const a of images.data ?? []) {
    const cur = cover.get(a.production_id);
    if (!cur || (a.selected && !cur.selected)) cover.set(a.production_id, { id: a.id, selected: Boolean(a.selected) });
  }
  const conceptTitle = new Map(
    (prods.data ?? []).map((p) => {
      const c = p.concepts as { title: string } | { title: string }[] | null;
      return [p.id as string, (Array.isArray(c) ? c[0]?.title : c?.title) ?? null];
    }),
  );
  for (const v of videos) {
    const pid = v.production_id as string;
    const task = tasks.get(pid);
    // Hors du gestionnaire de tâches (échec ou arrêt de plus de 14 jours, archivée) : le statut de la production suffit
    const status = (task?.status ?? v.production_status ?? "failed") as ProductionStatus;
    out.set(v.id, {
      status,
      stage: task?.stage ?? PRODUCTION_STATUS_LABELS[status] ?? "Pas finie",
      progress_pct: task?.progress_pct ?? 0,
      running: task?.running ?? false,
      eta_at: task?.eta_at ?? null,
      cover_asset_id: cover.get(pid)?.id ?? task?.cover_asset_id ?? null,
      concept_title: conceptTitle.get(pid) ?? task?.title ?? null,
    });
  }
  return out;
}

export async function getLibrary(channelId?: string): Promise<{ items: LibraryItem[]; totalBytes: number }> {
  if (IS_MOCK) return { items: [], totalBytes: 0 };
  let query = supabaseAdmin().from("v_video_overview").select("*").order("created_at", { ascending: false }).limit(500);
  if (channelId) query = query.eq("channel_id", channelId);
  const { data, error } = await query;
  if (error) throw new Error(error.message);
  const videos = (data ?? []).map(mapOverview);
  const [root, making, tiktok] = await Promise.all([dataRoot(), makingOf(videos.filter(unfinished)), getTikTokBriefs().catch(() => new Map())]);
  const items = await Promise.all(
    videos.map(async (v): Promise<LibraryItem> => {
      const size = v.origin === "imported" || v.files_deleted_at ? 0 : await videoFootprint(root, v.id, v.production_id);
      return { ...v, size_bytes: size, making: making.get(v.id) ?? null, tiktok: tiktok.get(v.id) ?? null };
    }),
  );
  // Plus récent d'abord : date de publication, sinon de programmation, sinon de fabrication
  const when = (v: LibraryItem) => v.published_at ?? v.youtube_publish_at ?? v.scheduled_at ?? v.created_at ?? "";
  items.sort((a, b) => when(b).localeCompare(when(a)));
  return { items, totalBytes: items.reduce((s, v) => s + v.size_bytes, 0) };
}

/** Clips déjà fabriqués d'une production, dans l'ordre des scènes (le plus récent d'une scène refaite). */
async function productionClips(productionId: string): Promise<LibraryClip[]> {
  const { data } = await supabaseAdmin()
    .from("assets")
    .select("id, scene_index")
    .eq("production_id", productionId)
    .eq("kind", "clip")
    .order("scene_index")
    .order("created_at", { ascending: false });
  const seen = new Set<number | null>();
  const clips: LibraryClip[] = [];
  for (const a of data ?? []) {
    const scene = (a.scene_index as number | null) ?? null;
    if (scene !== null && seen.has(scene)) continue;
    seen.add(scene);
    clips.push({ asset_id: a.id as string, scene_index: scene });
  }
  return clips;
}

export async function getLibraryDetail(videoId: string, productionId: string | null, withClips = false): Promise<LibraryDetail> {
  const [detail, production, favorites, clips] = await Promise.all([
    getVideoDetail(videoId),
    productionId ? getProductionCard(productionId) : Promise.resolve(null),
    productionId ? favoriteProductions([productionId]) : Promise.resolve([]),
    withClips && productionId ? productionClips(productionId) : Promise.resolve(undefined),
  ]);
  const video = detail?.video;
  const [insight, tiktok] = await Promise.all([
    video?.youtube_video_id ? getVideoInsight(videoId, video.channel_id) : Promise.resolve(null),
    video && video.origin !== "imported" && video.final_asset_id ? getLibraryTikTok(videoId, video.channel_id) : Promise.resolve(null),
  ]);
  return { detail, production, favorite: favorites.length > 0, insight, clips, tiktok };
}
