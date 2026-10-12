/** Onglet Instagram du Dashboard (docs/62-reseaux-et-comptes.md) : types partagés serveur / navigateur. Données :
 * lib/instagram-stats.ts ; relevé : worker/steps/sync_instagram.py (tables instagram_* de la migration 0052).
 *
 * Mêmes idées que l'onglet TikTok : chaque Reel sorti avec ses chiffres, sa note par rapport aux autres Reels du compte
 * (mêmes règles que YouTube), les vues par jour d'après les relevés horaires. Deux comptes : @arzakparker (mêmes vidéos
 * que YouTube et TikTok) et « Paf, j'achète » (la vidéo du vendredi, docs/50), relevés par deux comptes Zernio. */
import type { LibraryItem } from "@/lib/library-types";
import type { StatsPeriod, Verdict } from "@/lib/stats-types";
import type { VideoOverview } from "@/lib/types";
import type { DayViews } from "@/lib/views-series";

export interface InstagramAccountStats {
  /** Id Instagram du compte ; « paf » pour le compte de « Paf, j'achète » pas encore relevé. */
  id: string;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
  profile_url: string | null;
  /** MEDIA_CREATOR, BUSINESS… */
  account_type: string | null;
  followers: number | null;
  followers_delta_7d: number | null;
  media_count: number | null;
  /** Compte entier sur 28 jours (Instagram, jusqu'à 48 h de retard) : Reels, publications, stories, profil. */
  views_28d: number | null;
  reach_28d: number | null;
  interactions_28d: number | null;
  fetched_at: string | null;
  /** Chaînes YouTube dont les Shorts partent sur ce compte (Réglages → Instagram). */
  channels: string[];
  /** Compte choisi dans l'onglet « Paf, j'achète ». */
  paf: boolean;
  /** Relevé au moins une fois (false : compte attendu mais pas encore connecté à Zernio). */
  connected: boolean;
  /** Ce qui cloche dans le branchement (compte de « Paf, j'achète » = celui des Shorts…). */
  warning: string | null;
}

export interface InstagramStatsVideo {
  id: string; // instagram_posts.id (id Instagram du Reel)
  account_id: string;
  username: string;
  video_id: string | null;
  /** Fiche de la Bibliothèque, ouverte au clic (vidéo de l'appli). */
  item: LibraryItem | null;
  /** Vendredi de « Paf, j'achète » qui l'a publié (AAAA-MM-JJ). */
  paf_friday: string | null;
  title: string;
  url: string | null;
  thumbnail: string | null;
  published_at: string;
  age_h: number;
  duration_s: number | null;
  /** « imported » : pas une vidéo de l'appli (à la main ou « Paf, j'achète »), en gris. */
  origin: "app" | "imported";
  recipe: VideoOverview["recipe"] | null;
  series_name: string | null;
  views: number;
  /** Vu en direct chez Instagram, pas encore dans les statistiques de Zernio : vues inconnues. */
  views_pending: boolean;
  reach: number | null;
  likes: number;
  comments: number;
  shares: number;
  saves: number | null;
  avg_watch_s: number | null;
  total_watch_s: number | null;
  /** Durée moyenne regardée ÷ durée de la vidéo (plus de 100 % : revu en boucle). */
  watched_pct: number | null;
  /** Spectateurs encore là après 3 secondes (100 − part partie avant, estimation de Meta) : l'accroche. */
  hook_pct: number | null;
  views_24h: number | null;
  views_7d: number | null;
  comparable_views: number;
  score: number | null;
  verdict: Verdict;
  like_rate_pct: number | null;
  engagement_pct: number | null; // (j'aime + commentaires + partages + enregistrements) ÷ vues
  /** La même vidéo sur YouTube et sur TikTok : vues au dernier relevé (null si elle n'y est pas). */
  youtube_views: number | null;
  tiktok_views: number | null;
}

export interface InstagramTotals {
  videos: number;
  views: number;
  reach: number | null;
  likes: number;
  comments: number;
  shares: number;
  saves: number | null;
  /** Moyennes pondérées par les vues, sur les Reels où Instagram les a données. */
  watched_pct: number | null;
  hook_pct: number | null;
  avg_watch_s: number | null;
  watch_hours: number | null;
  like_rate_pct: number | null;
}

/** Reel prévu (programmé chez Zernio ou en cours d'envoi), pas encore sorti. */
export interface InstagramUpcoming {
  key: string;
  /** Vidéo de l'appli (null : vendredi de « Paf, j'achète »). */
  video_id: string | null;
  title: string;
  scheduled_for: string | null;
  username: string | null;
  paf: boolean;
}

export interface InstagramStatsPage {
  period: StatsPeriod;
  /** Une clé Zernio enregistrée (Réglages → TikTok, ou onglet Paf, j'achète). */
  configured: boolean;
  accounts: InstagramAccountStats[];
  /** Compte choisi dans l'onglet (?compte=), null : tous les comptes du périmètre. */
  account_id: string | null;
  videos: InstagramStatsVideo[];
  totals: InstagramTotals;
  median_views: number | null;
  upcoming: InstagramUpcoming[];
  daily: DayViews[];
  snapshots_since: string | null;
  sync: { active: boolean; since: string | null; last_done_at: string | null; last_error: string | null };
}

export const PAF_ACCOUNT = "paf";

/** Nom court d'un compte Instagram dans les choix : @nom, ou « Paf, j'achète » tant qu'il n'a pas de compte à lui. */
export function instagramLabel(a: Pick<InstagramAccountStats, "username" | "paf" | "connected">): string {
  if (!a.connected) return "Paf, j’achète";
  return a.username ? `@${a.username}` : "?";
}
