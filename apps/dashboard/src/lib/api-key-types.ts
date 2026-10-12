/**
 * Suivi des clés API (docs/49 §9, migration 0044) : types partagés serveur / navigateur. Données : lib/api-keys.ts ;
 * écrit par le worker à chaque appel (services/worker/worker/keyusage.py).
 */

export type KeyStatus = "ok" | "quota_day" | "quota_minute" | "invalid" | "error" | "unused";
export type KeyPool = "voix" | "ia";

/** Une clé d'une liste, pour un modèle, aujourd'hui (jour de quota Google : minuit heure du Pacifique). */
export interface KeySlot {
  slot: number; // numéro dans sa liste (1 = la première)
  hint: string | null; // derniers caractères de la clé (Réglages)
  status: KeyStatus; // unused : pas appelée aujourd'hui
  calls: number;
  ok: number;
  failed: number;
  blockedUntil: string | null; // quota du jour : prochain minuit à Los Angeles
  lastOkAt: string | null;
  lastError: string | null;
}

/** Une liste de clés pour un modèle : la voix Gemini (clés réservées à la voix) ou un modèle de langue (Réglages → IA). */
export interface KeyGroup {
  pool: KeyPool;
  provider: string;
  model: string;
  slots: KeySlot[];
  current: number | null; // la clé qui a répondu en dernier
  down: number; // clés au quota du jour épuisé ou refusées
  limit: number | null; // limite par jour et par clé, lue dans un refus de Google (« limit: 10 requests per day »)
  okToday: number;
}

export interface KeyBoard {
  day: string; // jour de quota (AAAA-MM-JJ à Los Angeles)
  resetAt: string; // prochain minuit à Los Angeles
  groups: KeyGroup[];
}

export const EMPTY_KEY_BOARD: KeyBoard = { day: "", resetAt: "", groups: [] };

export const STATUS_LABEL: Record<KeyStatus, string> = {
  ok: "en service",
  quota_day: "quota du jour épuisé",
  quota_minute: "limite par minute",
  invalid: "refusée",
  error: "erreur",
  unused: "pas utilisée aujourd’hui",
};

export const POOL_LABEL: Record<KeyPool, string> = { voix: "Voix", ia: "IA" };

/** « 9 h », « 17 h 30 » à Paris. */
export function frenchHour(iso: string | null): string {
  if (!iso) return "";
  const [h, m] = new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Paris" }).split(":");
  return `${Number(h)} h${m === "00" ? "" : ` ${m}`}`;
}
