/**
 * Reels Instagram par Zernio (docs/48-publication-instagram.md) : types partagés serveur / navigateur. Données :
 * lib/instagram.ts.
 *
 * app_settings « instagram » relie chaque chaîne YouTube à un compte Instagram professionnel connecté à Zernio (la clé
 * Zernio est celle de TikTok) ; videos.instagram garde l'état du Reel de chaque vidéo (steps/instagram_publish.py).
 */
import { TIKTOK_STATUS_LABELS, type TikTokAccount, type TikTokStatus } from "@/lib/tiktok-types";

export interface InstagramChannelLink {
  account_id: string;
  username: string;
  /** Chaque Short programmé sur YouTube part aussi en Reel, à la même heure. */
  enabled: boolean;
  /** Activation : seuls les créneaux qui suivent partent tout seuls. */
  enabled_at: string | null;
}

export interface InstagramSettings {
  channels: Record<string, InstagramChannelLink>;
  /** Le Reel paraît aussi dans la grille du profil (sinon seulement dans l'onglet Reels). */
  share_to_feed: boolean;
  /** Étiquette « IA » de Meta : coupée par défaut, comme sur TikTok. */
  ai_label: boolean;
}

export const DEFAULT_INSTAGRAM: InstagramSettings = { channels: {}, share_to_feed: true, ai_label: false };

/** Compte Instagram connecté à Zernio ; `kind` : MEDIA_CREATOR, BUSINESS… (un compte personnel ne publie pas). */
export type InstagramAccount = TikTokAccount & { kind: string | null };

export type InstagramStatus = TikTokStatus;

export interface VideoInstagram {
  status: InstagramStatus;
  url: string | null;
  scheduled_for: string | null;
  published_at: string | null;
  username: string | null;
  error: string | null;
  source: "auto" | "bibliothèque" | "cli";
}

/** Reel d'une vidéo, pour sa fiche dans la Bibliothèque. */
export interface LibraryInstagram {
  state: VideoInstagram | null;
  /** Compte Instagram relié à la chaîne de la vidéo (Réglages → Instagram), sinon null. */
  username: string | null;
  /** Une publication est en file ou en cours dans le worker. */
  pending: boolean;
}

export const INSTAGRAM_STATUS_LABELS: Record<InstagramStatus, string> = {
  ...TIKTOK_STATUS_LABELS,
  processing: "Traitement par Instagram",
  uploading: "Envoi à Instagram",
  scheduled: "Programmé",
  published: "Publié",
  cancelled: "Annulé",
};

const str = (x: unknown): string | null => (typeof x === "string" && x ? x : null);
const bool = (x: unknown, d: boolean): boolean => (typeof x === "boolean" ? x : d);

export function parseInstagramSettings(raw: unknown): InstagramSettings {
  const v = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const channels: Record<string, InstagramChannelLink> = {};
  for (const [id, c] of Object.entries((v.channels ?? {}) as Record<string, Record<string, unknown>>)) {
    if (!c || typeof c !== "object" || !str(c.account_id)) continue;
    channels[id] = { account_id: String(c.account_id), username: str(c.username) ?? "", enabled: bool(c.enabled, false), enabled_at: str(c.enabled_at) };
  }
  return { channels, share_to_feed: bool(v.share_to_feed, DEFAULT_INSTAGRAM.share_to_feed), ai_label: bool(v.ai_label, DEFAULT_INSTAGRAM.ai_label) };
}

export function parseVideoInstagram(raw: unknown): VideoInstagram | null {
  if (!raw || typeof raw !== "object") return null;
  const v = raw as Record<string, unknown>;
  const status = (str(v.status) ?? "pending") as InstagramStatus;
  return {
    status: status in INSTAGRAM_STATUS_LABELS ? status : "pending",
    url: str(v.url),
    scheduled_for: str(v.scheduled_for),
    published_at: str(v.published_at),
    username: str(v.username),
    error: str(v.error),
    source: (["bibliothèque", "cli"] as const).find((s) => s === v.source) ?? "auto",
  };
}
