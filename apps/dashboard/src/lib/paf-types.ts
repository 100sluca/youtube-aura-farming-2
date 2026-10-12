/**
 * « Paf, j'achète » (docs/50-paf-j-achete.md) : types partagés serveur / navigateur. Données : lib/paf.ts ; envoi :
 * worker/paf.py et steps/paf_publish.py.
 *
 * La même vidéo part chaque vendredi à l'heure choisie (7 h par défaut, heure de Paris) en Reel sur un compte Instagram
 * à part, par un second compte Zernio (sa propre clé, app_secrets « zernio_paf_api_key »).
 */
import type { InstagramAccount } from "@/lib/instagram-types";

export const PAF_SECRET = "zernio_paf_api_key";
export const PAF_SETTINGS_KEY = "paf_j_achete";
export const PAF_FOLDER = "paf-j-achete";
export const PAF_DEFAULT_HOUR = "07:00";
/** Écrit dans une légende, remplacé par la date du vendredi (« vendredi 16 octobre »). */
export const PAF_DATE_TAG = "{date}";

/** Date du vendredi dans la légende : non, en première ligne, en dernière ligne (avant les hashtags), ou seule. */
export type PafDateMode = "off" | "start" | "end" | "only";
export const PAF_DATE_MODES: { value: PafDateMode; label: string }[] = [
  { value: "off", label: "Non (seulement là où {date} est écrit)" },
  { value: "start", label: "En première ligne" },
  { value: "end", label: "En dernière ligne (avant les hashtags)" },
  { value: "only", label: "La date seule, sans les légendes" },
];

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
  /** Heure de publication du vendredi, « HH:mm » heure de Paris. */
  hour: string;
  /** Date du vendredi écrite d’office dans la légende. */
  date_caption: PafDateMode;
}

export const DEFAULT_PAF: PafSettings = {
  enabled: false,
  enabled_at: null,
  account_id: "",
  username: "",
  captions: [],
  share_to_feed: true,
  hour: PAF_DEFAULT_HOUR,
  date_caption: "off",
};

const HOUR_RE = /^([01]?\d|2[0-3]):([0-5]\d)$/;

/** « 9:30 » → « 09:30 » ; null si illisible. */
export function normalizePafHour(raw: unknown): string | null {
  const m = HOUR_RE.exec(String(raw ?? "").trim());
  return m ? `${m[1].padStart(2, "0")}:${m[2]}` : null;
}

/** « 07:00 » → « 7 h », « 09:30 » → « 9 h 30 » (même écriture que worker/paf.py hour_label). */
export function pafHourLabel(hour: string): string {
  const [h, m] = (normalizePafHour(hour) ?? PAF_DEFAULT_HOUR).split(":").map(Number);
  return m ? `${h} h ${String(m).padStart(2, "0")}` : `${h} h`;
}

const MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];

/** « 2026-10-16 » → « vendredi 16 octobre » (« 1er » le premier du mois), comme worker/paf.py date_label. */
export function pafDateLabel(friday: string): string {
  const [, month, day] = friday.split("-").map(Number);
  return `vendredi ${day === 1 ? "1er" : day} ${MONTHS[month - 1]}`;
}

const hashtagsOnly = (line: string) => {
  const words = line.split(/\s+/).filter(Boolean);
  return words.length > 0 && words.every((w) => w.startsWith("#"));
};

/** Légende envoyée pour ce vendredi : même règle que worker/paf.py render_caption (aperçu de l’onglet). */
export function renderPafCaption(caption: string, friday: string, mode: PafDateMode): string {
  const label = pafDateLabel(friday);
  const title = label[0].toUpperCase() + label.slice(1);
  if (mode === "only") return title;
  const text = caption.split(PAF_DATE_TAG).join(label).trim();
  if ((mode !== "start" && mode !== "end") || caption.includes(PAF_DATE_TAG)) return text;
  if (!text) return title;
  if (mode === "start") return `${title}\n${text}`;
  const lines = text.split("\n");
  if (lines.length > 1 && hashtagsOnly(lines[lines.length - 1])) return [...lines.slice(0, -1), title, lines[lines.length - 1]].join("\n");
  return `${text}\n${title}`;
}

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
    hour: normalizePafHour(v.hour) ?? PAF_DEFAULT_HOUR,
    date_caption: PAF_DATE_MODES.some((m) => m.value === v.date_caption) ? (v.date_caption as PafDateMode) : "off",
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
  /** Prochain vendredi visé, à l’heure choisie (ISO). */
  nextSlot: string;
  /** Ce vendredi-là, AAAA-MM-JJ (jour de Paris). */
  nextFriday: string;
  posts: PafPost[];
  /** Un job paf_publish en file ou en cours, avec son libellé. */
  job: { status: string; label: string | null; error: string | null } | null;
}

/** `sameAsMain` : c'est l'Instagram du compte Zernio principal (@arzakparker), branché une seconde fois par erreur. */
export type PafAccount = InstagramAccount & { sameAsMain?: boolean };
