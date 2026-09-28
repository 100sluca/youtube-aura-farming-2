/**
 * Couche de lecture Supabase (locale, service role) : les dix fonctions du contrat, plus les séries.
 *
 * Le dashboard tourne sur le PC de Luca, sans connexion (`DASHBOARD_AUTH=none`) : les Server Components
 * lisent avec la clé service role, qui ne quitte jamais le serveur Next.js. Les vues `v_*` viennent des
 * migrations (0001 : v_video_overview, v_production_progress ; 0004 : v_concept_overview,
 * v_production_overview). Les colonnes `numeric` arrivent en chaînes : `num()` les convertit.
 */
import { JOB_TYPE_LABELS } from "@/lib/labels";
import { parisAddDays, parisSlot, parisStartOfDay } from "@/lib/format";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { channelCounters, channelViews, lastDays, weekViews } from "@/lib/views-series";
import type {
  CastMember,
  Channel,
  CharacterSheet,
  Concept,
  DailyViewsPoint,
  Job,
  JobType,
  OverviewKpis,
  Production,
  ProductionCard,
  ScheduleSlot,
  ScriptV1,
  Series,
  StoryboardScene,
  Video,
  VideoFormat,
  VideoOverview,
} from "@/lib/types";

import type {
  CategorySummary,
  DataSource,
  ExperimentSummary,
  FormatSummary,
  VideoComment,
  VideoDetail,
} from "./contract";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;

function num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
const n0 = (v: unknown): number => num(v) ?? 0;

async function rows(q: PromiseLike<{ data: unknown; error: { message?: string } | null }>): Promise<Row[]> {
  const { data, error } = await q;
  if (error) throw new Error(error.message ?? String(error));
  return (data as Row[] | null) ?? [];
}

async function one(q: PromiseLike<{ data: unknown; error: { message?: string } | null }>): Promise<Row | null> {
  const { data, error } = await q;
  if (error) throw new Error(error.message ?? String(error));
  return (data as Row | null) ?? null;
}

const dayKey = (d: Date): string => d.toISOString().slice(0, 10);
const daysAgo = (n: number): Date => new Date(Date.now() - n * 86_400_000);

export function mapChannel(r: Row): Channel {
  return {
    id: r.id,
    slug: r.slug,
    name: r.name,
    lang: r.lang,
    youtube_channel_id: r.youtube_channel_id ?? null,
    timezone: r.timezone,
    publish_slots: ((r.publish_slots as string[] | null) ?? []).map((s) => String(s).slice(0, 5)),
    auto_publish: Boolean(r.auto_publish),
    is_active: Boolean(r.is_active),
    youtube_title: r.youtube_title ?? null,
    youtube_thumbnail_url: r.youtube_thumbnail_url ?? null,
    history_imported_at: r.history_imported_at ?? null,
    last_series_id: r.last_series_id ?? null,
    created_at: r.created_at,
  };
}

export function mapOverview(r: Row): VideoOverview {
  return {
    id: r.id,
    production_id: r.production_id ?? null,
    channel_id: r.channel_id,
    channel_slug: r.channel_slug,
    lang: r.lang,
    format: r.format ?? null,
    status: r.status,
    title: r.title ?? null,
    category: r.category ?? null,
    scheduled_at: r.scheduled_at ?? null,
    youtube_video_id: r.youtube_video_id ?? null,
    youtube_publish_at: r.youtube_publish_at ?? null,
    published_at: r.published_at ?? null,
    duration_s: num(r.duration_s),
    views: n0(r.views),
    likes: n0(r.likes),
    comments: n0(r.comments),
    shares: num(r.shares),
    subscribers_gained: num(r.subscribers_gained),
    average_view_pct: num(r.average_view_pct),
    channel_name: r.channel_name ?? undefined,
    origin: r.origin ?? "app",
    created_at: r.created_at ?? undefined,
    error: r.error ?? null,
    description: r.description ?? null,
    final_asset_id: r.final_asset_id ?? null,
    preview_asset_id: r.preview_asset_id ?? null,
    poster_asset_id: r.poster_asset_id ?? null,
    thumbnail_url: r.thumbnail_url ?? null,
    files_deleted_at: r.files_deleted_at ?? null,
    series_slug: r.series_slug ?? null,
    series_name: r.series_name ?? null,
    hook: r.hook ?? null,
    production_status: r.production_status ?? null,
    engaged_views: num(r.engaged_views),
    average_view_duration_s: num(r.average_view_duration_s),
    hook_retention_pct: num(r.hook_retention_pct),
    end_retention_pct: num(r.end_retention_pct),
    views_24h: num(r.views_24h),
    views_7d: num(r.views_7d),
    subscribers_lost: num(r.subscribers_lost),
    estimated_minutes_watched: num(r.estimated_minutes_watched),
    stats_fetched_at: r.stats_fetched_at ?? null,
    analytics_through: r.analytics_through ?? null,
    recipe: r.recipe ?? null,
    video_provider: r.video_provider ?? null,
    image_workflow: r.image_workflow ?? null,
    tags: (r.tags as string[] | null) ?? [],
    music_track: r.music_track ?? null,
    music_title: r.music_title ?? null,
  };
}

function mapVideo(r: Row): Video {
  return {
    id: r.id,
    production_id: r.production_id,
    channel_id: r.channel_id,
    lang: r.lang,
    format: r.format,
    status: r.status,
    title: r.title ?? null,
    description: r.description ?? null,
    tags: (r.tags as string[] | null) ?? [],
    duration_s: num(r.duration_s),
    scheduled_at: r.scheduled_at ?? null,
    youtube_video_id: r.youtube_video_id ?? null,
    youtube_publish_at: r.youtube_publish_at ?? null,
    published_at: r.published_at ?? null,
    error: r.error ?? null,
    created_at: r.created_at,
    updated_at: r.updated_at,
    final_asset_id: r.final_asset_id ?? null,
    preview_asset_id: r.preview_asset_id ?? null,
  };
}

function mapJob(r: Row): Job {
  return {
    id: r.id,
    type: r.type,
    status: r.status,
    priority: n0(r.priority),
    production_id: r.production_id ?? null,
    video_id: r.video_id ?? null,
    channel_id: r.channel_id ?? null,
    progress: n0(r.progress),
    progress_label: r.progress_label ?? null,
    attempts: n0(r.attempts),
    max_attempts: n0(r.max_attempts),
    run_after: r.run_after,
    locked_by: r.locked_by ?? null,
    started_at: r.started_at ?? null,
    finished_at: r.finished_at ?? null,
    error: r.error ?? null,
    created_at: r.created_at,
  };
}

export function mapConcept(r: Row): Concept {
  return {
    id: r.id,
    title: r.title,
    hook: r.hook ?? null,
    category: r.category ?? null,
    premise: r.premise ?? null,
    visual_beats: (r.visual_beats as string[] | null) ?? [],
    source: r.source,
    score: num(r.score),
    status: r.status,
    created_at: r.created_at,
    angle: r.angle ?? null,
    series_slug: r.series_slug ?? null,
    series_name: r.series_name ?? null,
    facts_count: n0(r.facts_count),
    production_id: r.production_id ?? null,
    channel_id: r.channel_id ?? null,
  };
}

async function getChannelsRaw(): Promise<Channel[]> {
  return (await rows(supabaseAdmin().from("channels").select("*").order("created_at").order("slug"))).map(mapChannel);
}

const sceneList = (j: Row): number[] => ((j.payload?.scenes ?? []) as unknown[]).map(Number);

/** Scène en cours de Refaire (nouvelles images) ou de Réinventer (réécrite puis illustrée : payload reinvent, puis
 * reinvented une fois le script enregistré par le worker), avec ce qu'il faut pour le dire et l'arrêter (docs/16 §3). */
function sceneWork(
  jobs: Row[],
  index: number,
  cast: CastMember[],
): Pick<StoryboardScene, "busy" | "busy_state" | "busy_reason" | "busy_job"> {
  const job = jobs.find((j) => (j.status === "queued" || j.status === "running") && sceneList(j).includes(index));
  if (!job) return { busy: null };
  const rewrite = Boolean(job.payload?.reinvent || job.payload?.reinvented);
  const names = ((job.payload?.characters ?? []) as unknown[]).map((k) => cast.find((m) => m.key === String(k))?.name ?? String(k));
  const note = typeof job.payload?.note === "string" && job.payload.note.trim() ? `ta remarque : « ${job.payload.note.trim()} »` : null;
  const reason =
    typeof job.payload?.reason === "string" && job.payload.reason.trim()
      ? job.payload.reason.trim()
      : names.length
        ? `nouvelle fiche de ${names.join(", ")}`
        : note;
  return {
    busy: rewrite ? "reinvent" : "redo",
    busy_state: job.status === "running" ? "running" : "queued",
    busy_reason: reason,
    // un Réinventer commencé a déjà effacé les anciennes images : l'arrêter laisserait la scène vide
    busy_job: rewrite && job.status === "running" ? null : (job.id as string),
  };
}

/** Dernière réinvention de la scène, avec son nouveau plan (jobs triés du plus ancien au plus récent). */
function sceneReinvention(jobs: Row[], index: number): { idea: string | null } | null {
  for (const j of [...jobs].reverse()) {
    const hit = ((j.payload?.reinvented ?? []) as { scene?: unknown; idea?: string }[]).find((e) => Number(e.scene) === index);
    if (hit) return { idea: hit.idea?.trim() || null };
  }
  return null;
}

/** Cartes de production (storyboard, vidéos, jobs) : les plus récentes, ou celles demandées. */
export async function productionCards(ids?: string[]): Promise<ProductionCard[]> {
  const db = supabaseAdmin();
  const base = db.from("v_production_overview").select("*");
  const prods = await rows(
    ids ? base.in("id", ids) : base.neq("status", "archived").order("updated_at", { ascending: false }).limit(60),
  );
  if (prods.length === 0) return [];
  const prodIds = prods.map((p) => p.id as string);
  const videos = (await rows(db.from("videos").select("*").in("production_id", prodIds).order("lang"))).map(mapVideo);
  const videoIds = videos.map((v) => v.id);
  const jobQuery = db.from("jobs").select("*").order("created_at");
  const jobRows = await rows(
    videoIds.length ? jobQuery.or(`production_id.in.(${prodIds.join(",")}),video_id.in.(${videoIds.join(",")})`) : jobQuery.in("production_id", prodIds),
  );
  const jobs = jobRows.map(mapJob);
  // Refaire / Réinventer une scène : jobs storyboard limités à quelques scènes (payload.scenes, docs/27)
  const sceneJobs = jobRows.filter((j) => j.type === "storyboard" && Array.isArray(j.payload?.scenes));
  const sb = await rows(
    db.from("assets").select("id, production_id, scene_index, selected, meta, created_at").in("production_id", prodIds).eq("kind", "storyboard").order("created_at"),
  );
  // Drames (docs/35) : la fiche retenue de chaque personnage, et les personnages en cours de refaçon
  const sheets = await rows(
    db.from("assets").select("id, production_id, meta").in("production_id", prodIds).eq("kind", "character").eq("selected", true).order("created_at"),
  );
  const redoing = jobRows.filter((j) => j.type === "storyboard" && ["queued", "running"].includes(j.status) && Array.isArray(j.payload?.characters));

  return prods.map((p): ProductionCard => {
    const script = (p.script as ScriptV1 | null) ?? null;
    const lang = videos.find((v) => v.production_id === p.id)?.lang;
    const mine = sceneJobs.filter((j) => j.production_id === p.id);
    const busyKeys = new Set(redoing.filter((j) => j.production_id === p.id).flatMap((j) => (j.payload.characters as unknown[]).map(String)));
    const characters: CharacterSheet[] = (script?.cast ?? []).map((m) => ({
      key: m.key,
      name: m.name,
      role: m.role || null,
      look: m.look,
      asset_id: (sheets.filter((a) => a.production_id === p.id && a.meta?.key === m.key).at(-1)?.id as string | undefined) ?? null,
      busy: busyKeys.has(m.key),
    }));
    const storyboard: StoryboardScene[] = script
      ? script.scenes.map((s) => {
          const reinvention = sceneReinvention(mine, s.index);
          return {
            index: s.index,
            role: s.role ?? null,
            visual_prompt: s.visual_prompt,
            narration: (lang ? s.narration?.[lang] : Object.values(s.narration ?? {})[0]) || null,
            continues_previous: Boolean(s.continues_previous),
            clip_mode: s.clip_mode ?? "i2v",
            passage: Boolean(s.passage),
            ...sceneWork(mine, s.index, script.cast ?? []),
            reinvented: reinvention !== null,
            idea: reinvention?.idea ?? null,
            candidates: sb
              .filter((a) => a.production_id === p.id && a.scene_index === s.index)
              .map((a) => ({ asset_id: a.id, selected: Boolean(a.selected), seed: num(a.meta?.seed), qc: a.meta?.qc ?? null })),
          };
        })
      : [];
    const production: Production = {
      id: p.id, concept_id: p.concept_id ?? null, format: p.format, status: p.status, script,
      target_duration_s: n0(p.target_duration_s), style_preset: p.style_preset ?? null, video_provider: p.video_provider ?? null,
      image_workflow: p.image_workflow ?? null,
      error: p.error ?? null, created_at: p.created_at, updated_at: p.updated_at,
      series_slug: p.series_slug ?? null, series_name: p.series_name ?? null, lint: (p.lint as string[] | null) ?? [],
      channel_id: p.channel_id ?? null, channel_name: p.channel_name ?? null,
    };
    const currentJob = p.current_job as JobType | null;
    return {
      production,
      concept: p.concept_id ? { id: p.concept_id, title: p.title ?? "Sans titre", hook: p.hook ?? null, category: p.category ?? null } : null,
      videos: videos.filter((v) => v.production_id === p.id),
      jobs: jobs.filter((j) => j.production_id === p.id || videos.some((v) => v.id === j.video_id && v.production_id === p.id)),
      progress_pct: n0(p.progress_pct),
      current_step: currentJob ? `${JOB_TYPE_LABELS[currentJob] ?? currentJob}${p.current_label ? ` · ${p.current_label}` : ""}` : null,
      eta_minutes: null,
      storyboard,
      ...(characters.length ? { characters } : {}),
    };
  });
}

export const supabaseSource: DataSource = {
  async getChannels() {
    return getChannelsRaw();
  },

  async getOverviewKpis(channel) {
    const db = supabaseAdmin();
    const channels = await getChannelsRaw();
    const chosen = channel ? channels.filter((c) => c.slug === channel) : channels;
    const ids = chosen.map((c) => c.id);
    const empty: OverviewKpis = {
      subscribers: 0, subscribers_delta_7d: 0, views_7d: 0, views_7d_delta_pct: null, average_view_pct_28d: null,
      watch_hours_28d: 0, published_7d: 0, pipeline: { generating: 0, ready: 0, scheduled: 0, failed: 0 },
      ypp: { subs_target: 1000, views_90d: 0, views_90d_target: 10_000_000 },
    };
    if (ids.length === 0) return empty;

    // Abonnés et vues à jour (docs/25) : relevés horaires des compteurs + YouTube Analytics, publié 2 à 3 jours après
    const [daily, counters, series] = await Promise.all([
      rows(db.from("channel_metrics_daily").select("day, estimated_minutes_watched").in("channel_id", ids).gte("day", dayKey(daysAgo(28)))),
      channelCounters(ids),
      channelViews(ids, 28, 7),
    ]);
    const d28 = dayKey(daysAgo(28));
    let minutes28 = 0;
    for (const r of daily) if (r.day >= d28) minutes28 += n0(r.estimated_minutes_watched);
    const weeks = [...series.values()].map(weekViews);
    const views7 = weeks.reduce((s, w) => s + w.views, 0);
    const viewsPrev7 = weeks.every((w) => w.previous !== null) ? weeks.reduce((s, w) => s + (w.previous ?? 0), 0) : null;
    const counterList = [...counters.values()];
    const throughs = [...series.values()].map((c) => c.through);
    const takenAt = counterList.map((c) => c.taken_at).filter((t): t is string => Boolean(t)).sort();

    const videos = await rows(db.from("videos").select("id, status, published_at, scheduled_at").in("channel_id", ids));
    const videoIds = videos.map((v) => v.id as string);
    let pct28: number | null = null;
    let views90 = 0;
    if (videoIds.length) {
      const vmd = await rows(
        db.from("video_metrics_daily").select("video_id, day, views, average_view_pct").in("video_id", videoIds).gte("day", dayKey(daysAgo(90))),
      );
      let w = 0;
      let wp = 0;
      for (const r of vmd) {
        views90 += n0(r.views);
        if (r.day >= d28 && r.average_view_pct !== null) {
          w += n0(r.views);
          wp += n0(r.views) * n0(r.average_view_pct);
        }
      }
      pct28 = w > 0 ? Math.round((wp / w) * 100) / 100 : null;
    }

    const prods = (await rows(db.from("productions").select("id, status, channel_id").not("status", "in", "(archived,cancelled)"))).filter(
      (p) => !channel || ids.includes(p.channel_id),
    );
    const sinceIso = daysAgo(7).toISOString();
    return {
      subscribers: counterList.reduce((a, c) => a + (c.subscribers ?? 0), 0),
      subscribers_delta_7d: counterList.reduce((a, c) => a + (c.delta_7d ?? 0), 0),
      subscribers_delta_known: counterList.every((c) => c.delta_7d !== null),
      views_7d: views7,
      views_7d_delta_pct: viewsPrev7 ? Math.round(((views7 - viewsPrev7) / viewsPrev7) * 1000) / 10 : null,
      views_7d_estimated: weeks.some((w) => w.estimated),
      analytics_through: throughs.every(Boolean) ? (throughs as string[]).sort()[0] : null,
      counters_at: takenAt.length ? takenAt[takenAt.length - 1] : null,
      unattributed_views: [...series.values()].reduce((s, c) => s + c.unattributed, 0),
      average_view_pct_28d: pct28,
      watch_hours_28d: Math.round(minutes28 / 60),
      published_7d: videos.filter((v) => v.published_at && v.published_at >= sinceIso).length,
      pipeline: {
        generating: prods.filter((p) => ["draft", "scripting", "generating", "assembling"].includes(p.status)).length,
        ready: videos.filter((v) => v.status === "review" || v.status === "qa").length, // à valider
        scheduled: videos.filter((v) => v.status === "ready" || v.status === "uploading" || v.status === "scheduled").length,
        failed: prods.filter((p) => p.status === "failed").length + videos.filter((v) => v.status === "failed").length,
      },
      ypp: { subs_target: 1000, views_90d: views90, views_90d_target: 10_000_000 },
    };
  },

  async getDailyViews(days) {
    // YouTube Analytics jusqu'au dernier jour publié, puis estimation d'après les relevés horaires (docs/25) :
    // estimated = 1 sur un jour estimé, missing = 1 sur un jour que personne ne connaît encore (compté 0)
    const channels = await getChannelsRaw();
    const series = await channelViews(channels.map((c) => c.id), days);
    return lastDays(days).map((day, i): DailyViewsPoint => {
      const point: DailyViewsPoint = { day };
      for (const c of channels) {
        const d = series.get(c.id)?.days[i];
        point[c.slug] = d?.views ?? 0;
        if (d && d.source !== "analytics") point.estimated = 1;
        if (d?.source === "unknown") point.missing = 1;
      }
      return point;
    });
  },

  async getVideoDetail(id) {
    const db = supabaseAdmin();
    const row = await one(db.from("v_video_overview").select("*").eq("id", id).maybeSingle());
    if (!row) return null;
    const video = mapOverview(row);
    const [daily, retention, comments, prod] = await Promise.all([
      rows(db.from("video_metrics_daily").select("*").eq("video_id", id).order("day", { ascending: false }).limit(14)),
      rows(db.from("video_retention").select("curve").eq("video_id", id).order("fetched_at", { ascending: false }).limit(1)),
      rows(db.from("video_comments").select("*").eq("video_id", id).order("published_at", { ascending: false }).limit(20)),
      video.production_id ? one(db.from("productions").select("script").eq("id", video.production_id).maybeSingle()) : Promise.resolve(null),
    ]);
    const detail: VideoDetail = {
      video,
      daily: daily.reverse().map((r) => ({
        video_id: r.video_id, day: r.day, views: n0(r.views), likes: n0(r.likes), comments: n0(r.comments), shares: n0(r.shares),
        subscribers_gained: n0(r.subscribers_gained), average_view_duration_s: num(r.average_view_duration_s),
        average_view_pct: num(r.average_view_pct),
      })),
      retention: ((retention[0]?.curve as Row[] | undefined) ?? []).map((p) => ({ t: n0(p.t), w: n0(p.w), rel: p.rel })),
      comments: comments.map(
        (r): VideoComment => ({ id: r.id, author: r.author ?? "", text: r.text ?? "", like_count: n0(r.like_count), published_at: r.published_at ?? r.fetched_at }),
      ),
      script: (prod?.script as ScriptV1 | null) ?? null,
    };
    return detail;
  },

  async listProductions() {
    return productionCards();
  },

  async getProductionCard(id) {
    return (await productionCards([id]))[0] ?? null;
  },

  async getSchedule(fromISO, days) {
    const channels = await getChannelsRaw();
    const start = parisStartOfDay(fromISO);
    const end = parisAddDays(start, days);
    const startIso = start.toISOString();
    const videos = await rows(
      supabaseAdmin()
        .from("videos")
        .select("id, title, status, format, youtube_video_id, channel_id, scheduled_at, youtube_publish_at, published_at")
        .in("status", ["ready", "uploading", "scheduled", "published", "unpublished"])
        .or(`scheduled_at.gte.${startIso},youtube_publish_at.gte.${startIso},published_at.gte.${startIso}`),
    );
    const slugOf = new Map(channels.map((c) => [c.id, c.slug]));
    const index = new Map<string, ScheduleSlot["video"]>();
    for (const v of videos) {
      const ts = v.youtube_publish_at ?? v.scheduled_at ?? v.published_at;
      const at = ts ? new Date(ts) : null;
      if (!at || at >= end) continue;
      index.set(`${slugOf.get(v.channel_id)}|${at.toISOString()}`, {
        id: v.id, title: v.title ?? null, status: v.status, format: v.format as VideoFormat, youtube_video_id: v.youtube_video_id ?? null,
      });
    }
    const slots: ScheduleSlot[] = [];
    for (let d = 0; d < days; d++) {
      const day = parisAddDays(start, d);
      for (const c of channels.filter((ch) => ch.is_active)) {
        for (const slot of c.publish_slots) {
          const at = parisSlot(day, slot).toISOString();
          slots.push({ channel_slug: c.slug, at, video: index.get(`${c.slug}|${at}`) ?? null });
        }
      }
    }
    return slots.sort((a, b) => a.at.localeCompare(b.at));
  },

  async listConcepts() {
    return (
      await rows(supabaseAdmin().from("v_concept_overview").select("*").order("created_at", { ascending: false }).limit(200))
    ).map(mapConcept);
  },

  async getExperimentSummary() {
    const published = (await rows(supabaseAdmin().from("v_video_overview").select("*").eq("status", "published"))).map(mapOverview);
    const summarize = <K extends string>(key: (v: VideoOverview) => K | null) => {
      const groups = new Map<K, VideoOverview[]>();
      for (const v of published) {
        const k = key(v);
        if (!k) continue;
        groups.set(k, [...(groups.get(k) ?? []), v]);
      }
      return [...groups.entries()].map(([k, items]) => {
        const views = items.reduce((a, v) => a + v.views, 0);
        const pcts = items.map((v) => v.average_view_pct).filter((x): x is number => x !== null);
        const subs = items.reduce((a, v) => a + (v.subscribers_gained ?? 0), 0);
        return {
          key: k,
          videos: items.length,
          avg_view_pct: pcts.length ? Math.round((pcts.reduce((a, b) => a + b, 0) / pcts.length) * 10) / 10 : 0,
          views_per_video: items.length ? Math.round(views / items.length) : 0,
          subs_per_1k_views: views > 0 ? Math.round((subs / views) * 10000) / 10 : 0,
        };
      });
    };
    const byFormat: FormatSummary[] = summarize((v) => v.format).map((g) => ({
      format: g.key, videos: g.videos, avg_view_pct: g.avg_view_pct, views_per_video: g.views_per_video, subs_per_1k_views: g.subs_per_1k_views,
    }));
    const byCategory: CategorySummary[] = summarize((v) => v.category)
      .map((g) => ({ category: g.key, videos: g.videos, avg_view_pct: g.avg_view_pct, views_per_video: g.views_per_video }))
      .sort((a, b) => b.avg_view_pct - a.avg_view_pct);
    const summary: ExperimentSummary = { byFormat, byCategory };
    return summary;
  },

  async listSeries() {
    return (await rows(supabaseAdmin().from("series").select("*").order("slug"))).map(
      (r): Series => ({
        id: r.id, slug: r.slug, name: r.name, source: r.source, is_active: Boolean(r.is_active), weight: n0(r.weight), style_preset: r.style_preset ?? null,
        recipe: r.recipe ?? "story",
      }),
    );
  },
};
