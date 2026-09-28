/**
 * Storyboards favoris (migration 0011, docs/19-favoris.md) : garder un storyboard (idée, script, modèles et copie des
 * images retenues dans <DATA_DIR>/favorites/<id favori>/), recopier le choix d'images tant que la production existe,
 * le refaire (SQL restore_favorite), le retirer. Serveur uniquement.
 *
 * Les images sont copiées, pas référencées : abandonner le storyboard ou supprimer la vidéo efface le dossier de la
 * production, jamais celui du favori. Comme pour lib/files.ts, on n'efface qu'un dossier nommé exactement par
 * l'identifiant attendu, sous un dossier « favorites » (ou « productions » pour une copie ratée).
 */
import { randomUUID } from "node:crypto";
import { copyFile, mkdir, readdir, rm, stat } from "node:fs/promises";
import { basename, dirname, extname, join } from "node:path";

import { IS_MOCK } from "@/lib/data";
import type { Favorite } from "@/lib/favorite-types";
import { dataRoot, dataRootOf, removeOwnedDir } from "@/lib/files";
import { supabaseAdmin } from "@/lib/supabase-admin";
import type { ScriptV1 } from "@/lib/types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;

/** Image gardée telle qu'enregistrée en base (favorites.images). */
interface StoredImage {
  scene_index: number;
  path: string;
  width: number | null;
  height: number | null;
  bytes: number | null;
  source_asset: string | null; // asset d'origine : une image déjà copiée ne l'est pas deux fois
  meta: Record<string, unknown>;
}

export interface FavoriteResult {
  ok: boolean;
  message: string;
  /** Favori enregistré (garder) ou production créée (refaire). */
  id?: string;
}

const FAVORITES = "favorites";
const fail = (message: string): FavoriteResult => ({ ok: false, message });
const pad = (n: number) => String(n).padStart(2, "0");
const one = <T>(v: T | T[] | null | undefined): T | null => (Array.isArray(v) ? (v[0] ?? null) : (v ?? null));

async function exists(path: string): Promise<boolean> {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

async function sizeOf(path: string): Promise<number | null> {
  try {
    return (await stat(path)).size;
  } catch {
    return null;
  }
}

/** Dossier du favori si `path` est bien <racine>/favorites/<id>/<fichier>, sinon null. */
function ownedFavoriteDir(path: string, id: string): string | null {
  const dir = dirname(path);
  return basename(dir) === id && basename(dirname(dir)) === FAVORITES ? dir : null;
}

/** Ce qui sert à refaire ou à comprendre une image ; les chemins de l'ancienne production ne sont pas gardés. */
function keptMeta(meta: Row | null | undefined): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of ["seed", "prompt", "provider", "qc"]) if (meta?.[key] !== undefined) out[key] = meta[key];
  return out;
}

/**
 * Garde le storyboard d'une production (ou met à jour son favori) : copie de l'image retenue de chaque scène. Une
 * scène sans image retenue en ce moment (image refaite en cours, fichiers effacés) garde celle déjà copiée.
 */
export async function saveFavorite(productionId: string): Promise<FavoriteResult> {
  if (IS_MOCK) return fail("Indisponible en mode démo");
  const db = supabaseAdmin();
  const { data: p, error } = await db
    .from("productions")
    .select(
      "id, concept_id, series_id, channel_id, format, target_duration_s, style_preset, image_workflow, video_provider, script, lint, concepts(title, hook, premise, category, angle, visual_beats, facts, sources)",
    )
    .eq("id", productionId)
    .maybeSingle();
  if (error) return fail(error.message);
  if (!p) return fail("Production introuvable");
  if (!p.script) return fail("Pas encore de script : rien à garder");
  const [assets, existing] = await Promise.all([
    db
      .from("assets")
      .select("id, scene_index, local_path, width, height, meta, created_at")
      .eq("production_id", productionId)
      .eq("kind", "storyboard")
      .eq("selected", true)
      .order("created_at", { ascending: false }),
    db.from("favorites").select("id, images").eq("production_id", productionId).maybeSingle(),
  ]);
  if (assets.error) return fail(assets.error.message);
  if (existing.error) return fail(existing.error.message);

  const id: string = existing.data?.id ?? randomUUID();
  const images = new Map<number, StoredImage>();
  for (const img of (existing.data?.images ?? []) as StoredImage[]) images.set(img.scene_index, img);
  // Une image retenue par scène : la plus récente si le worker en a retenu deux
  const picks = new Map<number, Row>();
  for (const a of assets.data ?? []) if (a.local_path && a.scene_index !== null && !picks.has(a.scene_index)) picks.set(a.scene_index, a);
  const root = [...picks.values()].map((a) => dataRootOf(a.local_path)).find(Boolean) ?? null;
  const dir = root ? join(root, FAVORITES, id) : null;

  for (const a of picks.values()) {
    const kept = images.get(a.scene_index);
    if (kept && kept.source_asset === a.id && (await exists(kept.path))) continue;
    if (!dir) break;
    await mkdir(dir, { recursive: true });
    const path = join(dir, `scene_${pad(a.scene_index)}_${String(a.id).slice(0, 8)}${extname(a.local_path) || ".png"}`);
    try {
      await copyFile(a.local_path, path);
    } catch {
      continue; // image absente du disque : on garde l'éventuelle copie précédente
    }
    images.set(a.scene_index, {
      scene_index: a.scene_index,
      path,
      width: a.width ?? null,
      height: a.height ?? null,
      bytes: await sizeOf(path),
      source_asset: a.id,
      meta: keptMeta(a.meta),
    });
  }

  const concept = one(p.concepts as Row | Row[] | null);
  const row = {
    production_id: productionId,
    concept_id: p.concept_id,
    series_id: p.series_id,
    channel_id: p.channel_id,
    title: concept?.title ?? "Vidéo sans titre",
    concept: concept
      ? {
          hook: concept.hook ?? null,
          premise: concept.premise ?? null,
          category: concept.category ?? null,
          angle: concept.angle ?? null,
          visual_beats: concept.visual_beats ?? [],
          facts: concept.facts ?? [],
          sources: concept.sources ?? [],
        }
      : {},
    format: p.format,
    target_duration_s: p.target_duration_s,
    style_preset: p.style_preset,
    image_workflow: p.image_workflow,
    video_provider: p.video_provider,
    script: p.script,
    lint: p.lint,
    images: [...images.values()].sort((a, b) => a.scene_index - b.scene_index),
  };
  const saved = existing.data ? await db.from("favorites").update(row).eq("id", id) : await db.from("favorites").insert({ id, ...row });
  if (saved.error) {
    if (!existing.data && dir) await rm(dir, { recursive: true, force: true });
    return fail(saved.error.message);
  }
  // Copies d'un ancien choix d'images : effacées
  if (dir) {
    const keep = new Set(row.images.map((i) => basename(i.path)));
    const files = await readdir(dir).catch(() => [] as string[]);
    await Promise.all(files.filter((f) => !keep.has(f)).map((f) => rm(join(dir, f), { force: true })));
  }
  const n = row.images.length;
  return {
    ok: true,
    id,
    message: existing.data
      ? "Favori mis à jour"
      : `Gardé dans Favoris : l’idée, le script${n ? ` et ${n} image${n > 1 ? "s" : ""}` : ""}, même si tu abandonnes ce storyboard`,
  };
}

/** Après un changement du choix d'images (ou avant l'effacement de la production) : le favori suit. Ne lève jamais. */
export async function syncFavorite(productionId: string): Promise<void> {
  if (IS_MOCK) return;
  try {
    const { data } = await supabaseAdmin().from("favorites").select("id").eq("production_id", productionId).maybeSingle();
    if (data) await saveFavorite(productionId);
  } catch {
    // un favori pas recopié ne doit pas empêcher le geste en cours (choisir, valider, supprimer)
  }
}

export async function removeFavorite(id: string): Promise<FavoriteResult> {
  if (IS_MOCK) return fail("Indisponible en mode démo");
  const db = supabaseAdmin();
  const { data: f, error } = await db.from("favorites").select("id, images").eq("id", id).maybeSingle();
  if (error) return fail(error.message);
  if (!f) return fail("Favori introuvable");
  const del = await db.from("favorites").delete().eq("id", id);
  if (del.error) return fail(del.error.message);
  const known = ((f.images ?? []) as StoredImage[]).map((i) => ownedFavoriteDir(i.path, id)).find(Boolean);
  const root = known ? null : await dataRoot();
  const dir = known ?? (root ? join(root, FAVORITES, id) : null);
  if (dir && basename(dir) === id && basename(dirname(dir)) === FAVORITES) await rm(dir, { recursive: true, force: true });
  return { ok: true, message: "Retiré des favoris" };
}

/** Production ayant un favori, parmi celles données (étoiles de Création). */
export async function favoriteProductions(productionIds: string[]): Promise<string[]> {
  if (IS_MOCK || productionIds.length === 0) return [];
  const { data } = await supabaseAdmin().from("favorites").select("production_id").in("production_id", productionIds);
  return (data ?? []).map((r) => r.production_id as string);
}

/**
 * Refaire un favori : nouvelle production pour sa chaîne, avec ses images (copiées dans le dossier de la nouvelle
 * production, puis enregistrées avec elle par restore_favorite) ou avec de nouvelles images (réglages actuels).
 */
export async function restoreFavorite(id: string, keepImages: boolean, channelId: string | null): Promise<FavoriteResult> {
  if (IS_MOCK) return fail("Indisponible en mode démo");
  const db = supabaseAdmin();
  const { data: f, error } = await db.from("favorites").select("id, images").eq("id", id).maybeSingle();
  if (error) return fail(error.message);
  if (!f) return fail("Favori introuvable");

  const productionId = randomUUID();
  const images: Omit<StoredImage, "source_asset">[] = [];
  let dir: string | null = null;
  if (keepImages) {
    const stored = (f.images ?? []) as StoredImage[];
    const root = stored.map((i) => (ownedFavoriteDir(i.path, id) ? dirname(dirname(dirname(i.path))) : null)).find(Boolean) ?? null;
    if (root) {
      dir = join(root, "productions", productionId);
      const sdir = join(dir, "storyboard");
      await mkdir(sdir, { recursive: true });
      for (const img of stored) {
        const seed = typeof img.meta?.seed === "number" ? img.meta.seed : Math.floor(Math.random() * 2 ** 31);
        const path = join(sdir, `scene_${pad(img.scene_index)}_${seed}${extname(img.path) || ".png"}`);
        try {
          await copyFile(img.path, path);
        } catch {
          continue; // copie absente : le worker refera cette scène
        }
        images.push({ scene_index: img.scene_index, path, width: img.width, height: img.height, bytes: img.bytes, meta: img.meta ?? {} });
      }
    }
    if (images.length === 0) {
      if (dir) await removeOwnedDir(dir, productionId);
      return fail("Images du favori introuvables sur le disque : refaire avec de nouvelles images");
    }
  }
  const { error: rpcError } = await db.rpc("restore_favorite", {
    p_favorite: id,
    p_production: productionId,
    p_images: images,
    p_channel: channelId,
  });
  if (rpcError) {
    if (dir) await removeOwnedDir(dir, productionId);
    return fail(rpcError.message);
  }
  return {
    ok: true,
    id: productionId,
    message: keepImages
      ? "C’est reparti avec ces images : le storyboard revient dans Création, prêt à valider, dès que la carte graphique est libre"
      : "C’est reparti avec de nouvelles images (modèles des réglages actuels) : storyboard à regarder dans Création dans quelques minutes",
  };
}

export async function listFavorites(channelId?: string): Promise<Favorite[]> {
  if (IS_MOCK) return [];
  let query = supabaseAdmin()
    .from("favorites")
    .select("*, series(name, recipe), channels(name, lang), productions(status)")
    .order("created_at", { ascending: false })
    .limit(500);
  // La chaîne de l'en-tête, plus les favoris dont la chaîne a été supprimée
  if (channelId) query = query.or(`channel_id.eq.${channelId},channel_id.is.null`);
  const { data, error } = await query;
  if (error) throw new Error(error.message);
  return (data ?? []).map((r: Row): Favorite => {
    const series = one(r.series as Row | Row[] | null);
    const channel = one(r.channels as Row | Row[] | null);
    return {
      id: r.id,
      title: r.title,
      hook: r.concept?.hook ?? null,
      premise: r.concept?.premise ?? null,
      series_name: series?.name ?? null,
      recipe: series?.recipe ?? null,
      channel_name: channel?.name ?? null,
      lang: channel?.lang ?? null,
      image_workflow: r.image_workflow ?? null,
      video_provider: r.video_provider ?? null,
      script: r.script as ScriptV1,
      images: ((r.images ?? []) as StoredImage[]).map((i) => ({
        scene_index: i.scene_index,
        file: basename(i.path),
        qc: (i.meta?.qc as { ok: boolean; problems: string[] } | undefined) ?? null,
      })),
      production_id: r.production_id ?? null,
      original_status: one(r.productions as Row | Row[] | null)?.status ?? null,
      remade_count: r.remade_count ?? 0,
      remade_at: r.remade_at ?? null,
      created_at: r.created_at,
    };
  });
}

/** Chemin d'une image gardée, pour /api/favorites/<id>/<fichier> : jamais pris dans la requête, cherché en base. */
export async function favoriteImagePath(id: string, file: string): Promise<string | null> {
  if (IS_MOCK) return null;
  const { data } = await supabaseAdmin().from("favorites").select("images").eq("id", id).maybeSingle();
  const img = ((data?.images ?? []) as StoredImage[]).find((i) => basename(i.path) === file);
  return img && ownedFavoriteDir(img.path, id) ? img.path : null;
}
