/**
 * Vues et abonnés à jour (docs/25-dashboard-statistiques.md). Serveur uniquement.
 *
 * YouTube Analytics ne publie ses chiffres qu'avec 2 à 3 jours de retard. Les jours qu'il couvre (jusqu'à `through`)
 * viennent de lui ; les jours suivants sont estimés d'après les relevés horaires des compteurs publics (différence de
 * vues entre deux fins de journée, heure de Paris : vue v_video_daily_snapshots). Les vues que ni l'un ni l'autre ne
 * sait encore dater (relevés commencés après la mise en ligne) restent « à répartir » : comptées dans les totaux, dans
 * aucun jour. Le nombre d'abonnés vient toujours des relevés : Analytics ne donne que des gains et des pertes.
 */
import { now, parisAddDays, parisDayKey, parisStartOfDay } from "@/lib/format";
import { supabaseAdmin } from "@/lib/supabase-admin";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;
type Query = PromiseLike<{ data: unknown; error: { message?: string } | null }>;

async function rows(q: Query): Promise<Row[]> {
  const { data, error } = await q;
  if (error) throw new Error(error.message ?? String(error));
  return (data as Row[] | null) ?? [];
}

/** Toutes les lignes d'une requête, par pages de 1 000 (limite de PostgREST). */
async function allRows(page: (from: number, to: number) => Query): Promise<Row[]> {
  const out: Row[] = [];
  for (let from = 0; ; from += 1000) {
    const chunk = await rows(page(from, from + 999));
    out.push(...chunk);
    if (chunk.length < 1000) return out;
  }
}

const n0 = (v: unknown): number => (v === null || v === undefined || v === "" ? 0 : Number(v) || 0);

export interface DayViews {
  day: string; // YYYY-MM-DD, heure de Paris
  views: number | null; // null : ni Analytics ni les relevés ne le savent encore
  source: "analytics" | "estimate" | "unknown";
}

export interface ChannelViews {
  channel_id: string;
  days: DayViews[]; // du plus ancien au plus récent
  /** Dernier jour publié par YouTube Analytics (null : rien encore). */
  through: string | null;
  /** Vues YouTube Analytics par jour, fenêtre élargie (comparaison avec la période précédente). */
  analytics: Map<string, number>;
  /** Somme des compteurs publics des vidéos publiées. */
  views_now: number;
  /** Vues comptées après `through` (compteurs − totaux Analytics), qu'un jour les porte ou non. */
  after_through: number;
  /** Part de after_through qu'aucun jour ne porte encore. */
  unattributed: number;
}

/** Clés de jour (Paris) des `days` derniers jours, aujourd'hui compris, du plus ancien au plus récent. */
export function lastDays(days: number, from: Date = now()): string[] {
  const today = parisStartOfDay(from);
  return Array.from({ length: days }, (_, i) => parisDayKey(parisAddDays(today, i - days + 1)));
}

const previousDay = (day: string): string => parisDayKey(parisAddDays(`${day}T12:00:00Z`, -1));

/** Vues par jour de chaque chaîne sur les `days` derniers jours (+ `extraDays` d'Analytics avant, pour comparer). */
export async function channelViews(channelIds: string[], days: number, extraDays = 0): Promise<Map<string, ChannelViews>> {
  const out = new Map<string, ChannelViews>();
  if (channelIds.length === 0) return out;
  const db = supabaseAdmin();
  const keys = lastDays(days);
  const wideStart = lastDays(days + extraDays)[0];

  const [metrics, videos, latest] = await Promise.all([
    allRows((a, b) =>
      db.from("channel_metrics_daily").select("channel_id, day, views").in("channel_id", channelIds).gte("day", wideStart).order("day").range(a, b),
    ),
    allRows((a, b) =>
      db
        .from("v_video_overview")
        .select("id, channel_id, published_at, views, analytics_views")
        .in("channel_id", channelIds)
        .eq("status", "published")
        .not("published_at", "is", null)
        .range(a, b),
    ),
    Promise.all(
      channelIds.map((id) => rows(db.from("channel_metrics_daily").select("day").eq("channel_id", id).order("day", { ascending: false }).limit(1))),
    ),
  ]);
  const through = new Map(channelIds.map((id, i) => [id, (latest[i][0]?.day as string | undefined) ?? null]));

  // Relevés de fin de journée, depuis la veille du premier jour à estimer
  const firstEstimated = channelIds
    .map((id) => {
      const t = through.get(id);
      return t && t >= keys[0] ? t : previousDay(keys[0]);
    })
    .sort()[0];
  const snaps = await allRows((a, b) =>
    db.from("v_video_daily_snapshots").select("video_id, channel_id, day, views").in("channel_id", channelIds).gte("day", firstEstimated).range(a, b),
  );
  const endOfDay = new Map<string, number>(); // `${video}|${day}` → vues au dernier relevé du jour
  for (const s of snaps) endOfDay.set(`${s.video_id}|${s.day}`, n0(s.views));

  for (const id of channelIds) {
    const t = through.get(id) ?? null;
    const analytics = new Map<string, number>();
    for (const m of metrics) if (m.channel_id === id) analytics.set(m.day, n0(m.views));
    const vids = videos
      .filter((v) => v.channel_id === id)
      .map((v) => ({ id: v.id as string, views: n0(v.views), analyticsViews: n0(v.analytics_views), pubDay: parisDayKey(v.published_at as string) }));

    const dayViews = keys.map((day): DayViews => {
      if (t && day <= t) return { day, views: analytics.get(day) ?? 0, source: "analytics" };
      let total = 0;
      for (const v of vids) {
        if (v.pubDay > day) continue; // pas encore en ligne ce jour-là
        const end = endOfDay.get(`${v.id}|${day}`);
        const start = v.pubDay === day ? 0 : endOfDay.get(`${v.id}|${previousDay(day)}`);
        if (end === undefined || start === undefined) return { day, views: null, source: "unknown" };
        total += Math.max(0, end - start); // les compteurs publics redescendent parfois (vues retirées)
      }
      return { day, views: total, source: "estimate" };
    });

    const viewsNow = vids.reduce((s, v) => s + v.views, 0);
    const afterThrough = vids.reduce((s, v) => s + Math.max(0, v.views - v.analyticsViews), 0);
    const estimated = dayViews.filter((d) => d.source === "estimate").reduce((s, d) => s + (d.views ?? 0), 0);
    out.set(id, {
      channel_id: id,
      days: dayViews,
      through: t,
      analytics,
      views_now: viewsNow,
      after_through: afterThrough,
      unattributed: Math.max(0, afterThrough - estimated),
    });
  }
  return out;
}

/** Vues des 7 derniers jours : Analytics pour les jours qu'il couvre, les compteurs pour tout ce qui a suivi. La
 * période précédente (7 jours d'avant) n'est connue que si Analytics couvre toute la période. */
export function weekViews(cv: ChannelViews): { views: number; previous: number | null; estimated: boolean } {
  const week = lastDays(7);
  const before = lastDays(14).slice(0, 7);
  const t = cv.through;
  const covered = week.filter((d) => t && d <= t).reduce((s, d) => s + (cv.analytics.get(d) ?? 0), 0);
  const previous = t && t >= before[before.length - 1] ? before.reduce((s, d) => s + (cv.analytics.get(d) ?? 0), 0) : null;
  return { views: covered + cv.after_through, previous, estimated: !t || t < week[week.length - 1] };
}

export interface ChannelCounters {
  channel_id: string;
  subscribers: number | null;
  /** Dernier relevé des compteurs. */
  taken_at: string | null;
  /** Abonnés gagnés sur 7 jours : relevés, sinon YouTube Analytics ; null si on ne sait pas. */
  delta_7d: number | null;
}

/** Abonnés de chaque chaîne (dernier relevé) et leur évolution sur 7 jours. */
export async function channelCounters(channelIds: string[]): Promise<Map<string, ChannelCounters>> {
  const db = supabaseAdmin();
  const weekAgo = new Date(now().getTime() - 7 * 86_400_000).toISOString();
  const week = lastDays(7);
  const result = await Promise.all(
    channelIds.map(async (id): Promise<ChannelCounters> => {
      const [last, old, oldestVideo, gains] = await Promise.all([
        rows(db.from("channel_snapshots").select("subscribers, taken_at").eq("channel_id", id).order("taken_at", { ascending: false }).limit(1)),
        rows(db.from("channel_snapshots").select("subscribers").eq("channel_id", id).lte("taken_at", weekAgo).order("taken_at", { ascending: false }).limit(1)),
        rows(db.from("videos").select("published_at").eq("channel_id", id).eq("status", "published").not("published_at", "is", null).order("published_at").limit(1)),
        rows(db.from("channel_metrics_daily").select("day, subscribers_gained, subscribers_lost").eq("channel_id", id).gte("day", week[0])),
      ]);
      const subs = last[0]?.subscribers === null || last[0]?.subscribers === undefined ? null : n0(last[0].subscribers);
      let delta: number | null = null;
      if (subs !== null && old[0]?.subscribers !== null && old[0]?.subscribers !== undefined) delta = subs - n0(old[0].subscribers);
      else if (subs !== null && oldestVideo[0] && oldestVideo[0].published_at >= weekAgo) delta = subs; // chaîne lancée cette semaine
      else if (gains.length) delta = gains.reduce((s, g) => s + n0(g.subscribers_gained) - n0(g.subscribers_lost), 0);
      return { channel_id: id, subscribers: subs, taken_at: (last[0]?.taken_at as string | undefined) ?? null, delta_7d: delta };
    }),
  );
  return new Map(result.map((r) => [r.channel_id, r]));
}
