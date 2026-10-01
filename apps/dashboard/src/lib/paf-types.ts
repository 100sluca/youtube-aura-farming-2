/**
 * « Paf, j'achète » (docs/50-paf-j-achete.md) : types partagés serveur / navigateur. Données : lib/paf.ts ; envoi :
 * worker/paf.py et steps/paf_publish.py.
 *
 * La même vidéo part chaque vendredi à 7 h (heure de Paris) en Reel sur un compte Instagram à part, par un second
 * compte Zernio (sa propre clé, app_secrets « zernio_paf_api_key »).
 */
import type { InstagramAccount } from "@/lib/instagram-types";

export const PAF_SECRET = "zernio_paf_api_key";
export const PAF_SETTINGS_KEY = "paf_j_achete";
export const PAF_FOLDER = "paf-j-achete";

export interface PafSettings {
  enabled: boolean;
  /** Activation : seuls les vendredis qui suivent partent. */
  enabled_at: string | null;
  account_id: string;
  username: string;
  /** Légendes possibles : une est tirée au sort juste avant chaque envoi (jamais celle du vendredi d’avant). */
  captions: string[];
  /** Le Reel paraît aussi dans la grille du profil. */
  share_to_feed: boolean;
}

export const DEFAULT_PAF: PafSettings = { enabled: false, enabled_at: null, account_id: "", username: "", captions: [], share_to_feed: true };

export function parsePafSettings(raw: unknown): PafSettings {
  const v = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  return {
    enabled: v.enabled === true,
    enabled_at: typeof v.enabled_at === "string" ? v.enabled_at : null,
    account_id: typeof v.account_id === "string" ? v.account_id : "",
    username: typeof v.username === "string" ? v.username : "",
    // ancien réglage : une seule légende (« caption »)
    captions: (Array.isArray(v.captions) ? v.captions : typeof v.caption === "string" ? [v.caption] : []).filter((c): c is string => typeof c === "string" && c.trim() !== ""),
    share_to_feed: v.share_to_feed !== false,
  };
}

export type PafStatus = "queued" | "sending" | "scheduled" | "pending" | "publishing" | "processing" | "uploading" | "published" | "failed" | "cancelled";

export const PAF_STATUS_LABELS: Record<PafStatus, string> = {
  queued: "Préparée",
  sending: "Envoi à Zernio",
  scheduled: "Programmée",
  pending: "En attente",
  publishing: "Publication en cours",
  processing: "Traitement par Instagram",
  uploading: "Envoi à Instagram",
  published: "Publiée",
  failed: "Échec",
  cancelled: "Annulée",
};

/** Une ligne de paf_posts : un vendredi. */
export interface PafPost {
  friday: string; // AAAA-MM-JJ
  status: PafStatus;
  scheduled_for: string | null;
  url: string | null;
  error: string | null;
  file_name: string | null;
  /** Légende tirée au sort pour ce vendredi. */
  caption: string | null;
  username: string | null;
  published_at: string | null;
}

export interface PafVideo {
  name: string;
  size: number;
  modified: string;
}

export interface PafOverview {
  settings: PafSettings;
  keyHint: string | null;
  /** <DATA_DIR>/paf-j-achete, null si le dossier de données est inconnu. */
  folder: string | null;
  video: PafVideo | null;
  /** Prochain vendredi 7 h visé (ISO). */
  nextSlot: string;
  posts: PafPost[];
  /** Un job paf_publish en file ou en cours, avec son libellé. */
  job: { status: string; label: string | null; error: string | null } | null;
}

export type PafAccount = InstagramAccount;
