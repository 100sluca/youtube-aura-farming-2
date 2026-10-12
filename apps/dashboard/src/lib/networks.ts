/**
 * Chaque compte, réseau par réseau (docs/62-reseaux-et-comptes.md) : vues des 7 derniers jours (et des 7 d'avant),
 * abonnés, vidéos sorties, vues par jour sur 28 jours, pour chaque chaîne YouTube, chaque compte TikTok et chaque compte
 * Instagram (celui des Shorts et celui de « Paf, j'achète »). Sert à la Vue d'ensemble et au haut du Dashboard.
 * Serveur uniquement.
 *
 * YouTube : YouTube Analytics puis les compteurs relevés chaque heure (lib/views-series.ts). TikTok et Instagram : les
 * relevés des vidéos ; vues sur 7 jours = vues d'aujourd'hui − vues au relevé d'il y a 7 jours (0 pour une vidéo plus
 * récente), ce qui marche dès le premier relevé, et vues par jour d'après les fins de journée (lib/post-daily-views.ts).
 */
import { IS_MOCK } from "@/lib/data";
import { now, parisDayKey } from "@/lib/format";
import { getInstagramAccounts } from "@/lib/instagram-stats";
import { PAF_ACCOUNT } from "@/lib/instagram-stats-types";
import type { NetworkAccount } from "@/lib/network-types";
import { postDailyViews, type SocialPlatform } from "@/lib/post-daily-views";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { getTikTokSettings } from "@/lib/tiktok";
import type { Channel } from "@/lib/types";
import { channelCounters, channelViews, lastDays, weekViews, type DayViews } from "@/lib/views-series";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;
type Query = PromiseLike<{ data: unknown; error: { message?: string } | null }>;

async function rows(q: Query): Promise<Row[]> {
  const { data, error } = await q;
  if (error) throw new Error(error.message ?? String(error));
  return (data as Row[] | null) ?? [];
}

const DAYS = 28;
const num = (v: unknown): number | null => (v === null || v === undefined || v === "" ? null : Number(v));

/** Somme des jours connus d'une tranche ; null si aucun ne l'est, ou si `strict` et qu'un seul manque. */
function sumDays(days: DayViews[], strict = false): number | null {
  const known = days.filter((d) => d.views !== null);
  if (!known.length || (strict && known.length < days.length)) return null;
  return known.reduce((s, d) => s + (d.views ?? 0), 0);
}

type SocialPost = { id: string; published_at: string; views: number };

/** Vues d'une vidéo à la fin du jour `cut` (heure de Paris) : 0 si elle est sortie après ; sinon le dernier relevé du jour
 * ou d'avant ; à défaut (relevés commencés plus tard), le premier relevé, et la valeur n'est qu'une borne (`exact` faux). */
function viewsAt(post: SocialPost, series: { day: string; views: number }[], cut: string): { views: number; exact: boolean } {
  if (parisDayKey(post.published_at) > cut) return { views: 0, exact: true };
  const before = series.filter((s) => s.day <= cut).at(-1);
  if (before) return { views: before.views, exact: true };
  return { views: series[0]?.views ?? post.views, exact: false };
}

/** Vues d'un compte TikTok ou Instagram : par jour sur 28 jours, sur les 7 derniers jours et les 7 d'avant, sur 28 jours. */
async function socialSeries(platform: SocialPlatform, posts: SocialPost[]) {
  const { daily } = await postDailyViews(platform, posts, DAYS);
  const ids = posts.map((p) => p.id);
  const snaps = ids.length
    ? await rows(
        supabaseAdmin()
          .from(`v_${platform}_post_daily_snapshots`)
          .select("post_id, day, views")
          .in("post_id", ids)
          .gte("day", lastDays(DAYS + 8)[0])
          .order("day")
          .limit(10_000),
      ).catch(() => [] as Row[])
    : [];
  const series = new Map<string, { day: string; views: number }[]>();
  for (const s of snaps) series.set(s.post_id as string, [...(series.get(s.post_id as string) ?? []), { day: String(s.day), views: Number(s.views ?? 0) }]);
  const [cut28, cut14, cut7] = [lastDays(DAYS + 1)[0], lastDays(15)[0], lastDays(8)[0]];
  let week = 0;
  let previous = 0;
  let month = 0;
  let exact = true;
  for (const p of posts) {
    const s = series.get(p.id) ?? [];
    const [at7, at14, at28] = [viewsAt(p, s, cut7), viewsAt(p, s, cut14), viewsAt(p, s, cut28)];
    week += Math.max(0, p.views - at7.views); // les compteurs publics redescendent parfois
    previous += Math.max(0, at7.views - at14.views);
    month += Math.max(0, p.views - at28.views);
    exact &&= at7.exact && at14.exact;
  }
  const weekAgo = now().getTime() - 7 * 86_400_000;
  return {
    daily: daily.map((d) => ({ day: d.day, views: d.views })),
    views_7d: posts.length ? week : 0,
    views_prev_7d: exact ? previous : null,
    views_28d: posts.length ? month : 0,
    posts_7d: posts.filter((p) => new Date(p.published_at).getTime() >= weekAgo).length,
  };
}

/** Une carte par compte, dans l'ordre YouTube, TikTok, Instagram (« Paf, j'achète » en dernier). Chaîne choisie en haut :
 * ses comptes reliés, plus « Paf, j'achète » qui ne dépend d'aucune chaîne. */
export async function getNetworkAccounts(channels: Channel[], selected: Channel | undefined): Promise<NetworkAccount[]> {
  if (IS_MOCK) return [];
  const db = supabaseAdmin();
  const ytScope = (selected ? [selected] : channels.filter((c) => c.is_active)).filter((c) => c.youtube_channel_id);
  const weekAgoIso = new Date(now().getTime() - 7 * 86_400_000).toISOString();
  const ids = ytScope.map((c) => c.id);

  const [views, counters, recent, tiktokSettings, tiktokRows, tiktokPosts, instagram, igPosts] = await Promise.all([
    channelViews(ids, DAYS, 7),
    channelCounters(ids),
    ids.length ? rows(db.from("videos").select("channel_id").in("channel_id", ids).eq("status", "published").gte("published_at", weekAgoIso)) : Promise.resolve([] as Row[]),
    getTikTokSettings(),
    rows(db.from("tiktok_accounts").select("*").order("username")).catch(() => [] as Row[]),
    // « live » : lue en direct, vues pas encore relevées (sync_status vide pour TikTok : `neq` l'écarterait)
    rows(db.from("tiktok_posts").select("id, account_id, published_at, views").not("published_at", "is", null).or("sync_status.is.null,sync_status.neq.live")).catch(
      () => [] as Row[],
    ),
    getInstagramAccounts(channels),
    rows(db.from("instagram_posts").select("id, account_id, published_at, views").not("published_at", "is", null).or("sync_status.is.null,sync_status.neq.live")).catch(
      () => [] as Row[],
    ),
  ]);

  const out: NetworkAccount[] = [];

  // YouTube : une carte par chaîne connectée
  for (const c of ytScope) {
    const cv = views.get(c.id);
    const counter = counters.get(c.id);
    const week = cv ? weekViews(cv) : null;
    out.push({
      key: `youtube:${c.id}`,
      platform: "youtube",
      account: c.slug,
      name: c.name,
      role: "Chaîne YouTube",
      avatar_url: c.youtube_thumbnail_url ?? null,
      connected: true,
      warning: null,
      followers: counter?.subscribers ?? null,
      followers_delta_7d: counter?.delta_7d ?? null,
      views_7d: week?.views ?? null,
      views_prev_7d: week?.previous ?? null,
      views_28d: cv ? (sumDays(cv.days) ?? 0) + cv.unattributed : null,
      posts_7d: recent.filter((r) => r.channel_id === c.id).length,
      daily: cv?.days.map((d) => ({ day: d.day, views: d.views })) ?? lastDays(DAYS).map((day) => ({ day, views: null })),
      estimated: week?.estimated ?? false,
    });
  }

  // TikTok : les comptes reliés à la chaîne choisie, sinon tous
  const tiktokLinked = new Map<string, string[]>();
  for (const [cid, link] of Object.entries(tiktokSettings.channels)) if (link.account_id) tiktokLinked.set(link.account_id, [...(tiktokLinked.get(link.account_id) ?? []), cid]);
  const tiktokScope = selected ? tiktokRows.filter((a) => tiktokLinked.get(a.id as string)?.includes(selected.id)) : tiktokRows;
  for (const a of tiktokScope) {
    const posts = tiktokPosts.filter((p) => p.account_id === a.id).map((p) => ({ id: p.id as string, published_at: p.published_at as string, views: Number(p.views ?? 0) }));
    const old = await rows(db.from("tiktok_account_snapshots").select("followers").eq("account_id", a.id).lte("taken_at", weekAgoIso).order("taken_at", { ascending: false }).limit(1)).catch(
      () => [] as Row[],
    );
    const followers = num(a.followers);
    out.push({
      key: `tiktok:${a.id}`,
      platform: "tiktok",
      account: a.id as string,
      name: `@${a.username}`,
      role: "Mêmes vidéos",
      avatar_url: (a.avatar_url as string | null) ?? null,
      connected: true,
      warning: null,
      followers,
      followers_delta_7d: followers !== null && old[0] && num(old[0].followers) !== null ? followers - (num(old[0].followers) ?? 0) : null,
      estimated: true,
      ...(await socialSeries("tiktok", posts)),
    });
  }
  if (!tiktokScope.length) {
    out.push(placeholder("tiktok", "TikTok", "Mêmes vidéos", "Pas encore de compte relevé : Réglages → TikTok, clé Zernio et compte relié à la chaîne."));
  }

  // Instagram : le compte des Shorts (relié à la chaîne choisie, sinon tous), puis « Paf, j'achète »
  const igScope = instagram.accounts.filter((a) => !selected || a.paf || a.channels.includes(selected.name));
  const igSorted = [...igScope.filter((a) => !a.paf || a.channels.length), ...igScope.filter((a) => a.paf && !a.channels.length)];
  for (const a of igSorted) {
    if (!a.connected) {
      out.push({ ...placeholder("instagram", "Paf, j’achète", "Vidéo du vendredi", a.warning), account: PAF_ACCOUNT, key: "instagram:paf" });
      continue;
    }
    const posts = igPosts.filter((p) => p.account_id === a.id).map((p) => ({ id: p.id as string, published_at: p.published_at as string, views: Number(p.views ?? 0) }));
    out.push({
      key: `instagram:${a.id}`,
      platform: "instagram",
      account: a.id,
      name: `@${a.username}`,
      role: a.paf && !a.channels.length ? "Vidéo du vendredi" : "Mêmes vidéos",
      avatar_url: a.avatar_url,
      connected: true,
      warning: a.warning,
      followers: a.followers,
      followers_delta_7d: a.followers_delta_7d,
      estimated: true,
      ...(await socialSeries("instagram", posts)),
    });
  }
  if (!igSorted.some((a) => !a.paf || a.channels.length)) {
    const at = out.findIndex((a) => a.platform === "instagram");
    const card = placeholder("instagram", "Instagram", "Mêmes vidéos", "Pas encore de compte relevé : Réglages → Instagram, compte relié à la chaîne.");
    if (at < 0) out.push(card);
    else out.splice(at, 0, card);
  }
  return out;
}

function placeholder(platform: NetworkAccount["platform"], name: string, role: string, warning: string | null): NetworkAccount {
  return {
    key: `${platform}:aucun`,
    platform,
    account: null,
    name,
    role,
    avatar_url: null,
    connected: false,
    warning,
    followers: null,
    followers_delta_7d: null,
    views_7d: null,
    views_prev_7d: null,
    views_28d: null,
    posts_7d: 0,
    daily: lastDays(DAYS).map((day) => ({ day, views: null })),
    estimated: true,
  };
}
