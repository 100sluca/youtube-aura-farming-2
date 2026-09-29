/** Onglet TikTok du Dashboard (docs/39-tiktok-partout.md) : types partagés serveur / navigateur. Données : lib/tiktok-stats.ts.
 *
 * Mêmes idées que l'onglet YouTube (lib/stats-types.ts) : chaque vidéo sortie sur le compte avec ses chiffres, sa note par
 * rapport aux autres vidéos du compte (mêmes règles), les vues par jour d'après les relevés horaires. Ce que TikTok ne donne
 * pas (courbe de rétention, vues engagées) est remplacé par ce qu'il donne : part vue jusqu'au bout, provenance des vues. */
import type { LibraryItem } from "@/lib/library-types";
import type { StatsPeriod, Verdict } from "@/lib/stats-types";
import type { TikTokSource, TikTokStatus } from "@/lib/tiktok-types";
import type { VideoOverview } from "@/lib/types";
import type { DayViews } from "@/lib/views-series";

export interface TikTokAccountStats {
  id: string;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
  profile_url: string | null;
  /** Relié par l'appli TikTok for Business : temps regardé, part vue jusqu'au bout, provenance des vues. */
  business: boolean | null;
  followers: number | null;
  /** Abonnés gagnés sur 7 jours, d'après les relevés (null tant qu'on n'a pas une semaine de relevés). */
  followers_delta_7d: number | null;
  /** J'aime reçus par toutes les vidéos du compte. */
  likes: number | null;
  videos: number | null;
  fetched_at: string | null;
  zernio_synced_at: string | null;
  /** Chaînes YouTube reliées à ce compte (Réglages → TikTok). */
  channels: string[];
}

export interface TikTokStatsVideo {
  id: string; // tiktok_posts.id
  account_id: string;
  username: string;
  /** Vidéo de l'appli publiée sur TikTok (null : publiée à la main dans TikTok). */
  video_id: string | null;
  /** Sa fiche de la Bibliothèque, ouverte au clic. */
  item: LibraryItem | null;
  title: string;
  url: string | null;
  thumbnail: string | null;
  published_at: string;
  age_h: number;
  duration_s: number | null;
  /** « imported » : publiée à la main dans TikTok (format inconnu, en gris comme l'historique importé de YouTube). */
  origin: "app" | "imported";
  recipe: VideoOverview["recipe"] | null;
  series_name: string | null;
  views: number;
  /** Vue chez TikTok, pas encore dans les statistiques de Zernio (il repasse toutes les 90 min environ) : vues inconnues. */
  views_pending: boolean;
  likes: number;
  comments: number;
  shares: number;
  saves: number | null;
  reach: number | null;
  follows: number | null;
  profile_views: number | null;
  avg_watch_s: number | null;
  total_watch_s: number | null;
  completion_pct: number | null;
  /** Durée moyenne regardée ÷ durée de la vidéo (plus de 100 % : revue en boucle). */
  watched_pct: number | null;
  /** Part des vues venues du fil « Pour toi ». */
  for_you_pct: number | null;
  views_24h: number | null;
  views_7d: number | null;
  comparable_views: number;
  score: number | null;
  verdict: Verdict;
  like_rate_pct: number | null;
  engagement_pct: number | null; // (j'aime + commentaires + partages) ÷ vues
  /** La même vidéo sur YouTube : vues au dernier relevé (null si elle n'y est pas). */
  youtube_views: number | null;
  /** Rien de ce que TikTok for Business donne 24 à 48 h après la sortie n'est encore arrivé. */
  business_pending: boolean;
}

export interface TikTokTotals {
  videos: number;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  saves: number | null;
  follows: number | null;
  /** Moyennes pondérées par les vues, sur les vidéos où TikTok les a données. */
  watched_pct: number | null;
  completion_pct: number | null;
  avg_watch_s: number | null;
  for_you_pct: number | null;
  watch_hours: number | null;
  like_rate_pct: number | null;
  youtube_views: number | null;
}

/** Publication TikTok prévue (programmée chez Zernio ou en cours d'envoi), pas encore sortie. */
export interface TikTokUpcoming {
  video_id: string;
  title: string | null;
  scheduled_for: string | null;
  source: TikTokSource;
  username: string | null;
  status: TikTokStatus;
}

export interface TikTokStatsPage {
  period: StatsPeriod;
  /** Clé Zernio enregistrée (Réglages → TikTok). */
  configured: boolean;
  /** Comptes du périmètre (chaîne choisie en haut, sinon tous). */
  accounts: TikTokAccountStats[];
  /** Compte choisi dans l'onglet (?compte=), null : tous les comptes du périmètre. */
  account_id: string | null;
  videos: TikTokStatsVideo[];
  totals: TikTokTotals;
  median_views: number | null;
  upcoming: TikTokUpcoming[];
  daily: DayViews[];
  /** Premier relevé des vues : avant, les vues ne sont rangées dans aucun jour. */
  snapshots_since: string | null;
  sync: { active: boolean; since: string | null; last_done_at: string | null; last_error: string | null };
}
