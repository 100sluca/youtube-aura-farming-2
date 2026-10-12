/**
 * Vues par jour d'un ensemble de vidéos TikTok ou de Reels Instagram (docs/39, docs/62), d'après les relevés horaires
 * du worker : différence entre deux fins de journée (heure de Paris). Pas d'équivalent de YouTube Analytics : tout est
 * estimé d'après les relevés. Serveur uniquement.
 */
import { parisAddDays, parisDayKey } from "@/lib/format";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { lastDays, type DayViews } from "@/lib/views-series";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;
type Query = PromiseLike<{ data: unknown; error: { message?: string } | null }>;

async function rows(q: Query): Promise<Row[]> {
  const { data, error } = await q;
  if (error) throw new Error(error.message ?? String(error));
  return (data as Row[] | null) ?? [];
}

async function allRows(page: (from: number, to: number) => Query): Promise<Row[]> {
  const out: Row[] = [];
  for (let from = 0; ; from += 1000) {
    const chunk = await rows(page(from, from + 999));
    out.push(...chunk);
    if (chunk.length < 1000) return out;
  }
}

const previousDay = (day: string): string => parisDayKey(parisAddDays(`${day}T12:00:00Z`, -1));

export type SocialPlatform = "tiktok" | "instagram";

/** Un jour reste « inconnu » s'il manque un relevé pour une vidéo déjà en ligne ; une vidéo retirée (plus relevée) ne
 * compte plus. `since` : premier relevé, avant lequel aucune vue n'est rangée dans un jour. */
export async function postDailyViews(
  platform: SocialPlatform,
  posts: { id: string; published_at: string }[],
  days: number,
): Promise<{ daily: DayViews[]; since: string | null }> {
  const keys = lastDays(days);
  if (!posts.length) return { daily: keys.map((day) => ({ day, views: 0, source: "estimate" as const })), since: null };
  const db = supabaseAdmin();
  const ids = posts.map((p) => p.id);
  const [snaps, first] = await Promise.all([
    allRows((a, b) => db.from(`v_${platform}_post_daily_snapshots`).select("post_id, day, views").in("post_id", ids).gte("day", previousDay(keys[0])).range(a, b)),
    rows(db.from(`${platform}_post_snapshots`).select("taken_at").in("post_id", ids).order("taken_at").limit(1)),
  ]);
  const endOfDay = new Map<string, number>();
  const lastSeen = new Map<string, string>();
  let latest = "";
  for (const s of snaps) {
    endOfDay.set(`${s.post_id}|${s.day}`, Number(s.views ?? 0));
    if ((lastSeen.get(s.post_id) ?? "") < s.day) lastSeen.set(s.post_id, s.day);
    if (s.day > latest) latest = s.day;
  }
  const vids = posts.map((p) => ({ id: p.id, pubDay: parisDayKey(p.published_at) }));
  const daily = keys.map((day): DayViews => {
    if (!latest || day > latest) return { day, views: null, source: "unknown" }; // pas encore de relevé ce jour-là
    let total = 0;
    for (const v of vids) {
      if (v.pubDay > day) continue;
      const end = endOfDay.get(`${v.id}|${day}`);
      if (end === undefined && (lastSeen.get(v.id) ?? "") < day) continue; // plus relevée : retirée
      const start = v.pubDay === day ? 0 : endOfDay.get(`${v.id}|${previousDay(day)}`);
      if (end === undefined || start === undefined) return { day, views: null, source: "unknown" };
      total += Math.max(0, end - start); // les compteurs publics redescendent parfois
    }
    return { day, views: total, source: "estimate" };
  });
  return { daily, since: (first[0]?.taken_at as string | undefined) ?? null };
}
