/**
 * TikTok par Zernio (docs/36-publication-tiktok.md) : types partagés serveur / navigateur. Données : lib/tiktok.ts.
 *
 * app_settings « tiktok » relie chaque chaîne YouTube à un compte TikTok connecté à Zernio ; videos.tiktok garde l'état
 * de la publication de chaque vidéo (écrit par le worker, steps/tiktok_publish.py).
 */

export interface TikTokChannelLink {
  account_id: string;
  username: string;
  /** Chaque Short programmé sur YouTube part aussi sur TikTok, à la même heure. */
  enabled: boolean;
  /** Activation : seuls les créneaux qui suivent partent tout seuls (rien d'ancien n'est republié en rafale). */
  enabled_at: string | null;
  /** Rattrapage (docs/39) : les vidéos déjà sorties sur YouTube partent une par une dans les créneaux restés vides. */
  backlog: boolean;
}

export interface TikTokSettings {
  /** id de la chaîne YouTube → compte TikTok. */
  channels: Record<string, TikTokChannelLink>;
  allow_comment: boolean;
  allow_duet: boolean;
  allow_stitch: boolean;
  /** Étiquette « contenu généré par IA » de TikTok : coupée par défaut (choix de Luca le 29/09). */
  ai_label: boolean;
}

export const DEFAULT_TIKTOK: TikTokSettings = { channels: {}, allow_comment: true, allow_duet: true, allow_stitch: true, ai_label: false };

export interface TikTokAccount {
  id: string;
  username: string;
  displayName: string;
  avatar: string | null;
  active: boolean;
}

export type TikTokStatus = "sending" | "scheduled" | "pending" | "publishing" | "processing" | "uploading" | "published" | "failed" | "cancelled";

/** D'où vient la publication : créneau YouTube (auto), rattrapage d'une ancienne vidéo, Bibliothèque, terminal, ou publiée
 * à la main dans l'appli TikTok (reconnue par le relevé des stats à sa légende, docs/39). */
export type TikTokSource = "auto" | "rattrapage" | "bibliothèque" | "cli" | "manuel";

export interface VideoTikTok {
  status: TikTokStatus;
  url: string | null;
  scheduled_for: string | null;
  published_at: string | null;
  username: string | null;
  error: string | null;
  draft: boolean;
  source: TikTokSource;
}

/** Résumé TikTok d'une vidéo pour les listes : vignettes de la Bibliothèque, tableau YouTube du Dashboard (docs/39). */
export interface TikTokBrief {
  status: TikTokStatus;
  draft: boolean;
  source: TikTokSource;
  scheduled_for: string | null;
  url: string | null;
  /** Vues TikTok au dernier relevé des stats (null tant que la vidéo n'a pas été relevée). */
  views: number | null;
}

/** Publication TikTok d'une vidéo de l'appli dans le Calendrier (docs/39) : programmée, sortie, en échec, ou seulement
 * prévue par le rattrapage (`forecast` : le créneau est vide, il la recevra si aucune nouvelle vidéo ne le prend). */
export interface TikTokCalendarItem {
  video_id: string;
  channel_id: string;
  title: string | null;
  /** Heure de sortie sur TikTok (ISO). */
  at: string;
  status: TikTokStatus;
  draft: boolean;
  source: TikTokSource;
  url: string | null;
  error: string | null;
  forecast?: boolean;
}

/** Vidéo en attente de rattrapage (vue v_tiktok_backlog, migration 0026) : déjà sortie sur YouTube, jamais sur TikTok. */
export interface TikTokBacklogVideo {
  id: string;
  channel_id: string;
  title: string | null;
  published_at: string | null;
}

/** Publication TikTok d'une vidéo, pour sa fiche dans la Bibliothèque. */
export interface LibraryTikTok {
  state: VideoTikTok | null;
  /** Compte TikTok relié à la chaîne de la vidéo (Réglages → TikTok), sinon null. */
  username: string | null;
  /** Une publication est en file ou en cours dans le worker. */
  pending: boolean;
}

export const TIKTOK_STATUS_LABELS: Record<TikTokStatus, string> = {
  sending: "Envoi à Zernio",
  scheduled: "Programmée",
  pending: "En attente",
  publishing: "Publication en cours",
  processing: "Traitement par TikTok",
  uploading: "Envoi à TikTok",
  published: "Publiée",
  failed: "Échec",
  cancelled: "Annulée",
};

const str = (x: unknown): string | null => (typeof x === "string" && x ? x : null);
const bool = (x: unknown, d: boolean): boolean => (typeof x === "boolean" ? x : d);

export function parseTikTokSettings(raw: unknown): TikTokSettings {
  const v = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const channels: Record<string, TikTokChannelLink> = {};
  for (const [id, c] of Object.entries((v.channels ?? {}) as Record<string, Record<string, unknown>>)) {
    if (!c || typeof c !== "object" || !str(c.account_id)) continue;
    channels[id] = {
      account_id: String(c.account_id),
      username: str(c.username) ?? "",
      enabled: bool(c.enabled, false),
      enabled_at: str(c.enabled_at),
      backlog: bool(c.backlog, false),
    };
  }
  return {
    channels,
    allow_comment: bool(v.allow_comment, DEFAULT_TIKTOK.allow_comment),
    allow_duet: bool(v.allow_duet, DEFAULT_TIKTOK.allow_duet),
    allow_stitch: bool(v.allow_stitch, DEFAULT_TIKTOK.allow_stitch),
    ai_label: bool(v.ai_label, DEFAULT_TIKTOK.ai_label),
  };
}

export function parseVideoTikTok(raw: unknown): VideoTikTok | null {
  if (!raw || typeof raw !== "object") return null;
  const v = raw as Record<string, unknown>;
  const status = (str(v.status) ?? "pending") as TikTokStatus;
  return {
    status: status in TIKTOK_STATUS_LABELS ? status : "pending",
    url: str(v.url),
    scheduled_for: str(v.scheduled_for),
    published_at: str(v.published_at),
    username: str(v.username),
    error: str(v.error),
    draft: v.draft === true,
    source: (["rattrapage", "bibliothèque", "cli", "manuel"] as const).find((s) => s === v.source) ?? "auto",
  };
}
