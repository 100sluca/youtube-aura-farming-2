/** Chaque compte, réseau par réseau (docs/62-reseaux-et-comptes.md) : types partagés serveur / navigateur. Données :
 * lib/networks.ts. Une carte par chaîne YouTube, par compte TikTok et par compte Instagram (dont « Paf, j'achète »), dans
 * la Vue d'ensemble et en haut du Dashboard, où un clic ouvre l'onglet du réseau sur ce compte. */

export type NetworkPlatform = "youtube" | "tiktok" | "instagram";

export interface NetworkAccount {
  /** « youtube:<id chaîne> », « tiktok:<id> », « instagram:<id> » ou « instagram:paf ». */
  key: string;
  platform: NetworkPlatform;
  /** Valeur de ?compte= (TikTok, Instagram) ou ?chaine= (YouTube) dans le Dashboard. */
  account: string | null;
  name: string;
  /** Rôle en deux mots : « Chaîne YouTube », « Mêmes vidéos », « Vidéo du vendredi ». */
  role: string;
  avatar_url: string | null;
  connected: boolean;
  /** Ce qui cloche (compte pas relié, « Paf, j'achète » sur le compte des Shorts…). */
  warning: string | null;
  followers: number | null;
  followers_delta_7d: number | null;
  /** Vues des 7 derniers jours (null : pas encore de relevé daté) et des 7 jours d'avant (null : inconnues). */
  views_7d: number | null;
  views_prev_7d: number | null;
  views_28d: number | null;
  /** Vidéos sorties ces 7 derniers jours. */
  posts_7d: number;
  /** Vues par jour sur 28 jours, du plus ancien au plus récent (null : jour inconnu). */
  daily: { day: string; views: number | null }[];
  /** Vues 7 j estimées d'après les relevés horaires (YouTube : en attendant Analytics). */
  estimated: boolean;
}

export const NETWORK_LABELS: Record<NetworkPlatform, string> = { youtube: "YouTube", tiktok: "TikTok", instagram: "Instagram" };
