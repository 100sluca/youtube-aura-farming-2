/**
 * Lecture serveur des vidéos longues (docs/63) : la liste de la page, la fiche d'une vidéo (script, plans, prises,
 * tâches) et l'état léger que relit le Studio voix. Serveur uniquement.
 */
import { creationChannel, getChannelContext } from "@/lib/channel-server";
import { IS_MOCK } from "@/lib/data";
import { dataRoot } from "@/lib/files";
import {
  allParagraphs,
  chapterLabel,
  DEFAULT_LONG_SETTINGS,
  parseLongSettings,
  titleOf,
  type LongCard,
  type LongDetail,
  type LongJob,
  type LongOverview,
  type LongShot,
  type LongTake,
  type LongVideo,
} from "@/lib/long-types";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { parseProfiles, SAMPLE_NAME, type VoiceProfile } from "@/lib/voice-mods";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;

const JOB_TYPES = ["long_write", "long_make", "long_take"];

function toJob(j: Row): LongJob {
  const p = (j.payload ?? {}) as Row;
  return {
    id: j.id,
    type: j.type,
    action: String(p.action ?? (j.type === "long_take" ? "take" : "")),
    status: j.status,
    progress: j.progress ?? null,
    label: j.progress_label ?? null,
    long_id: p.long_id ?? null,
  };
}

export async function longJobs(longId?: string): Promise<LongJob[]> {
  let q = supabaseAdmin()
    .from("jobs")
    .select("id, type, status, payload, progress, progress_label, created_at")
    .in("type", JOB_TYPES)
    .in("status", ["queued", "running"])
    .order("created_at");
  if (longId) q = q.eq("payload->>long_id", longId);
  else q = q.or("payload->>action.is.null,payload->>action.neq.voice_mod"); // essais du Studio du modificateur : quelques secondes, hors liste
  const { data } = await q.limit(500);
  return (data ?? []).map(toJob);
}

export async function getLongSettings() {
  const { data } = await supabaseAdmin().from("app_settings").select("value").eq("key", "long").maybeSingle();
  return parseLongSettings(data?.value);
}

export async function getLongOverview(): Promise<LongOverview> {
  if (IS_MOCK) return { channelId: null, cards: [], jobs: [], settings: DEFAULT_LONG_SETTINGS, voiceProfiles: [] };
  const channel = creationChannel(await getChannelContext());
  const db = supabaseAdmin();
  let q = db
    .from("long_videos")
    .select("id, stage, format, subject, idea, packaging, script, thumbnail, error, created_at, approved_at, voice_done_at, video_id")
    .neq("stage", "archived")
    .order("created_at", { ascending: false })
    .limit(200);
  if (channel) q = q.eq("channel_id", channel.id);
  const [rows, jobs, settings, voiceProfiles] = await Promise.all([q, longJobs(), getLongSettings(), getVoiceProfiles()]);
  if (rows.error) throw new Error(`long_videos : ${rows.error.message} (migration 0054 appliquée ?)`);
  const list = (rows.data ?? []) as Row[];
  const ids = list.map((r) => r.id);
  const videoIds = list.map((r) => r.video_id).filter(Boolean);
  const [takes, shots, videos] = await Promise.all([
    ids.length ? db.from("long_takes").select("long_id, para, status, chosen").in("long_id", ids).eq("chosen", true) : { data: [] },
    ids.length ? db.from("long_shots").select("long_id, status, image_path, kind, clip_path").in("long_id", ids) : { data: [] },
    videoIds.length ? db.from("videos").select("id, scheduled_at, youtube_video_id").in("id", videoIds) : { data: [] },
  ]);
  const okTakes = new Map<string, Set<string>>();
  for (const t of (takes.data ?? []) as Row[]) {
    if (t.status === "failed") continue;
    if (!okTakes.has(t.long_id)) okTakes.set(t.long_id, new Set());
    okTakes.get(t.long_id)!.add(t.para);
  }
  const shotCount = new Map<string, { total: number; done: number }>();
  for (const s of (shots.data ?? []) as Row[]) {
    const c = shotCount.get(s.long_id) ?? { total: 0, done: 0 };
    c.total += 1;
    if (s.image_path || s.clip_path) c.done += 1;
    shotCount.set(s.long_id, c);
  }
  const videoById = new Map(((videos.data ?? []) as Row[]).map((v) => [v.id, v]));
  const cards: LongCard[] = list.map((r) => {
    const paragraphs = ((r.script?.chapters ?? []) as Row[]).reduce((n, c) => n + (c.paragraphs?.length ?? 0), 0);
    const v = r.video_id ? videoById.get(r.video_id) : null;
    return {
      id: r.id,
      stage: r.stage,
      format: r.format,
      subject: r.subject,
      title: titleOf(r as LongVideo),
      idea: r.idea ?? null,
      words: r.script?.words ?? null,
      paragraphs,
      takes_ok: okTakes.get(r.id)?.size ?? 0,
      shots_total: shotCount.get(r.id)?.total ?? 0,
      shots_done: shotCount.get(r.id)?.done ?? 0,
      thumb: Boolean(r.thumbnail?.candidates?.length),
      error: r.error ?? null,
      created_at: r.created_at,
      approved_at: r.approved_at ?? null,
      voice_done_at: r.voice_done_at ?? null,
      scheduled_at: v?.scheduled_at ?? null,
      youtube_video_id: v?.youtube_video_id ?? null,
    };
  });
  return { channelId: channel?.id ?? null, cards, jobs, settings, voiceProfiles };
}

function toShot(s: Row): LongShot {
  return {
    idx: s.idx,
    chapter: s.chapter,
    para: s.para,
    at_word: s.at_word,
    kind: s.kind,
    visual_prompt: s.visual_prompt,
    motion: s.motion ?? null,
    status: s.status,
    has_image: Boolean(s.image_path),
    has_clip: Boolean(s.clip_path),
    qc: s.qc ?? null,
    error: s.error ?? null,
    updated_at: s.updated_at,
  };
}

export function toTake(t: Row): LongTake {
  return {
    id: t.id,
    para: t.para,
    take: t.take,
    status: t.status,
    chosen: t.chosen,
    duration_s: t.duration_s != null ? Number(t.duration_s) : null,
    check: t.check_result
      ? {
          ratio: t.check_result.ratio,
          missing: t.check_result.missing,
          extra: t.check_result.extra,
          heard: t.check_result.heard,
          unchecked: t.check_result.unchecked,
          silent: t.check_result.silent,
        }
      : null,
    created_at: t.created_at,
  };
}

export async function getLongTakes(longId: string): Promise<LongTake[]> {
  const { data } = await supabaseAdmin()
    .from("long_takes")
    .select("id, para, take, status, chosen, duration_s, check_result, created_at")
    .eq("long_id", longId)
    .order("take", { ascending: false });
  return ((data ?? []) as Row[]).map(toTake);
}

export async function getLongDetail(id: string): Promise<LongDetail | null> {
  if (IS_MOCK || !/^[0-9a-f-]{36}$/i.test(id)) return null;
  const db = supabaseAdmin();
  const { data: row, error } = await db.from("long_videos").select("*").eq("id", id).maybeSingle();
  if (error) throw new Error(`long_videos : ${error.message}`);
  if (!row) return null;
  const [shots, takes, jobs, video, settings, longCfg, styleJob, voiceProfiles] = await Promise.all([
    db.from("long_shots").select("*").eq("long_id", id).order("idx"),
    getLongTakes(id),
    longJobs(id),
    row.video_id
      ? db.from("videos").select("status, youtube_video_id, scheduled_at, duration_s").eq("id", row.video_id).maybeSingle()
      : Promise.resolve({ data: null }),
    getLongSettings(),
    db.from("app_settings").select("value").eq("key", "long").maybeSingle(),
    db.from("jobs").select("id").eq("type", "long_write").eq("payload->>action", "thumb_style").in("status", ["queued", "running"]).limit(1),
    getVoiceProfiles(),
  ]);
  const v = video.data as Row | null;
  const style = (longCfg.data?.value as Row | null)?.thumb_style ?? null;
  return {
    video: row as LongVideo,
    shots: ((shots.data ?? []) as Row[]).map(toShot),
    takes,
    jobs,
    final: v ? { status: v.status, youtube_video_id: v.youtube_video_id, scheduled_at: v.scheduled_at, duration_s: v.duration_s } : null,
    nextSlot: nextSlot(settings.weekdays, settings.hour),
    thumbStyle: style?.style ? { style: style.style, rules: style.rules ?? [], n: style.n, at: style.at } : null,
    thumbStyleRunning: Boolean(styleJob.data?.length),
    voiceProfiles,
  };
}

/** Prochain jour de sortie des vidéos longues (Réglages), à l'heure de Paris, au moins 3 h plus tard (ISO local). */
export function nextSlot(weekdays: number[], hour: string): string {
  const [hh, mm] = hour.split(":").map(Number);
  const start = new Date(Date.now() + 3 * 3600 * 1000);
  for (let i = 0; i < 30; i++) {
    const d = new Date(start.getTime() + i * 86400000);
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Paris", year: "numeric", month: "2-digit", day: "2-digit", weekday: "short" }).formatToParts(d);
    const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
    const wd = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].indexOf(get("weekday")) + 1;
    if (!weekdays.includes(wd)) continue;
    const local = `${get("year")}-${get("month")}-${get("day")}T${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
    if (i === 0 && new Date(`${local}:00+02:00`).getTime() < start.getTime()) continue;
    return local;
  }
  return "";
}

// ---- Studio du modificateur de voix (docs/67) ----------------------------------------------------------------------

export async function getVoiceProfiles(): Promise<VoiceProfile[]> {
  const { data } = await supabaseAdmin().from("app_settings").select("value").eq("key", "voice_mods").maybeSingle();
  return parseProfiles(data?.value);
}

export interface VoiceStudioSource {
  id: string;
  title: string;
  takes: { id: string; label: string }[];
}

export interface VoiceStudioData {
  profiles: VoiceProfile[];
  /** Vidéos longues qui ont des prises gardées, les plus récentes d'abord. */
  sources: VoiceStudioSource[];
  /** Extraits enregistrés dans le Studio, les plus récents d'abord. */
  samples: { name: string; at: string }[];
}

export async function getVoiceStudio(): Promise<VoiceStudioData> {
  if (IS_MOCK) return { profiles: [], sources: [], samples: [] };
  const db = supabaseAdmin();
  const [profiles, takes, root] = await Promise.all([
    getVoiceProfiles(),
    db.from("long_takes").select("id, long_id, para, created_at").eq("chosen", true).neq("status", "failed").order("created_at", { ascending: false }).limit(800),
    dataRoot(),
  ]);
  const byVideo = new Map<string, Row[]>();
  for (const t of (takes.data ?? []) as Row[]) byVideo.set(t.long_id, [...(byVideo.get(t.long_id) ?? []), t]);
  const ids = [...byVideo.keys()];
  const { data: videos } = ids.length
    ? await db.from("long_videos").select("id, subject, idea, packaging, script, created_at").in("id", ids).order("created_at", { ascending: false })
    : { data: [] };
  const sources = ((videos ?? []) as Row[]).map((v) => {
    const order = allParagraphs(v.script);
    const have = new Map((byVideo.get(v.id) ?? []).map((t) => [t.para as string, t.id as string]));
    return {
      id: v.id as string,
      title: titleOf(v as LongVideo),
      takes: order
        .filter((p) => have.has(p.key))
        .map((p) => {
          const n = Number(p.key.split("p")[1]) + 1;
          const start = p.text.split(/\s+/).slice(0, 7).join(" ");
          return { id: have.get(p.key)!, label: `${chapterLabel(p.chapter)} · § ${n} — « ${start}… »` };
        }),
    };
  });
  let samples: { name: string; at: string }[] = [];
  if (root) {
    const { readdir, stat } = await import("node:fs/promises");
    const { join } = await import("node:path");
    const folder = join(root, "voix-studio", "extraits");
    const names = (await readdir(folder).catch(() => [] as string[])).filter((n) => SAMPLE_NAME.test(n));
    samples = (await Promise.all(names.map(async (n) => ({ name: n, at: (await stat(join(folder, n))).mtime.toISOString() }))))
      .sort((a, b) => b.at.localeCompare(a.at))
      .slice(0, 12);
  }
  return { profiles, sources, samples };
}

