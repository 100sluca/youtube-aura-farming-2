/**
 * Helpers de formatage (fr-FR, fuseau Europe/Paris).
 *
 * Tout est déterministe : l'« instant courant » est une date d'ancrage fixe
 * (`NOW`), les nombres sont formatés à la main (pas de dépendance à la version
 * ICU du runtime) et les dates sont converties en heure de Paris via `Intl`
 * avant d'être formatées par date-fns — le rendu serveur et le rendu client
 * produisent donc exactement la même chaîne (pas de hydration mismatch).
 */
import { format as dfFormat, formatDistanceStrict } from "date-fns";
import { fr } from "date-fns/locale";

export const ANCHOR_ISO = "2026-09-19T12:00:00Z";
/** Date d'ancrage du tableau de bord (remplacée par `new Date()` une fois branché). */
export const NOW = new Date(ANCHOR_ISO);

/** L'instant courant : figé sur l'ancre en mode démo, l'heure réelle sinon (données Supabase). */
export function now(): Date {
  return process.env.NEXT_PUBLIC_MOCK === "1" || !process.env.NEXT_PUBLIC_SUPABASE_URL ? NOW : new Date();
}
export const TIMEZONE = "Europe/Paris";

const NBSP = " ";
const NNBSP = " ";

/* ------------------------------------------------------------------------ */
/* Fuseau horaire                                                            */
/* ------------------------------------------------------------------------ */

export interface ZonedParts {
  year: number;
  month: number; // 1-12
  day: number;
  hour: number;
  minute: number;
  second: number;
}

const partsFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: TIMEZONE,
  hourCycle: "h23",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

function toDate(value: string | Date): Date {
  return value instanceof Date ? value : new Date(value);
}

/** Composants « muraux » (heure de Paris) d'un instant. */
export function parisParts(value: string | Date): ZonedParts {
  const parts = partsFormatter.formatToParts(toDate(value));
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((p) => p.type === type)?.value ?? "0");
  return {
    year: get("year"),
    month: get("month"),
    day: get("day"),
    hour: get("hour") % 24,
    minute: get("minute"),
    second: get("second"),
  };
}

/**
 * Date « murale » : mêmes composants que l'heure de Paris, exprimés dans le
 * fuseau du runtime. À n'utiliser que pour le formatage (date-fns).
 */
export function toParisWallClock(value: string | Date): Date {
  const p = parisParts(value);
  return new Date(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
}

/** Décalage de Paris par rapport à UTC (minutes) à un instant donné. */
export function parisOffsetMinutes(value: string | Date): number {
  const date = toDate(value);
  const p = parisParts(date);
  const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  return Math.round((asUtc - date.getTime()) / 60_000);
}

/** Instant UTC correspondant à une date/heure murale de Paris. */
export function parisDateTime(
  year: number,
  month: number,
  day: number,
  hour = 0,
  minute = 0
): Date {
  const guess = Date.UTC(year, month - 1, day, hour, minute);
  const offset = parisOffsetMinutes(new Date(guess));
  let result = guess - offset * 60_000;
  const offset2 = parisOffsetMinutes(new Date(result));
  if (offset2 !== offset) result = guess - offset2 * 60_000;
  return new Date(result);
}

/** Minuit (heure de Paris) du jour contenant l'instant donné. */
export function parisStartOfDay(value: string | Date): Date {
  const p = parisParts(value);
  return parisDateTime(p.year, p.month, p.day);
}

/** Ajoute `n` jours civils (heure de Paris conservée, DST inclus). */
export function parisAddDays(value: string | Date, n: number): Date {
  const p = parisParts(value);
  return parisDateTime(p.year, p.month, p.day + n, p.hour, p.minute);
}

/** Clé de jour « YYYY-MM-DD » en heure de Paris. */
export function parisDayKey(value: string | Date): string {
  const p = parisParts(value);
  return `${p.year}-${String(p.month).padStart(2, "0")}-${String(p.day).padStart(2, "0")}`;
}

/** Instant d'un créneau « HH:mm » (heure de Paris) pour le jour donné. */
export function parisSlot(day: string | Date, slot: string): Date {
  const p = parisParts(day);
  const [h, m] = slot.split(":").map(Number);
  return parisDateTime(p.year, p.month, p.day, h, m);
}

/** Lundi (minuit Paris) de la semaine contenant l'instant donné. */
export function parisStartOfWeek(value: string | Date): Date {
  const start = parisStartOfDay(value);
  const wall = toParisWallClock(start);
  const dow = (wall.getDay() + 6) % 7; // 0 = lundi
  return parisAddDays(start, -dow);
}

/* ------------------------------------------------------------------------ */
/* Dates                                                                     */
/* ------------------------------------------------------------------------ */

/** Formate une date en heure de Paris avec un motif date-fns (locale fr). */
export function formatDate(value: string | Date, pattern = "d MMM yyyy"): string {
  return dfFormat(toParisWallClock(value), pattern, { locale: fr });
}

/** « sam. 19 sept., 14:00 » */
export function formatDateTime(value: string | Date): string {
  return formatDate(value, "EEE d MMM, HH:mm");
}

/** « 14:00 » */
export function formatTime(value: string | Date): string {
  return formatDate(value, "HH:mm");
}

/** « il y a 3 heures » / « dans 2 jours » (relatif à la date d'ancrage). */
export function formatRelative(value: string | Date, base: Date = now()): string {
  return formatDistanceStrict(toDate(value), base, { addSuffix: true, locale: fr });
}

/** Durée d'une vidéo « 0:42 ». */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

/** « 25 min » / « 1 h 10 » */
export function formatMinutes(minutes: number | null | undefined): string {
  if (minutes == null) return "—";
  const m = Math.max(0, Math.round(minutes));
  if (m < 60) return `${m}${NBSP}min`;
  const h = Math.floor(m / 60);
  const rest = m % 60;
  return rest === 0 ? `${h}${NBSP}h` : `${h}${NBSP}h${NBSP}${String(rest).padStart(2, "0")}`;
}

/* ------------------------------------------------------------------------ */
/* Nombres                                                                   */
/* ------------------------------------------------------------------------ */

function groupThousands(int: string): string {
  return int.replace(/\B(?=(\d{3})+(?!\d))/g, NNBSP);
}

function trimZeros(s: string): string {
  return s.replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1").replace(".", ",");
}

/** « 12 345 » (séparateur fr-FR). */
export function formatNumber(n: number | null | undefined, digits = 0): string {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n < 0 ? "−" : "";
  const abs = Math.abs(n);
  const fixed = abs.toFixed(digits);
  const [int, dec] = fixed.split(".");
  return `${sign}${groupThousands(int)}${dec ? "," + dec : ""}`;
}

/** « 12,3 k » / « 1,2 M ». */
export function formatCompact(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n < 0 ? "−" : "";
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${sign}${trimZeros((abs / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1))}${NBSP}M`;
  if (abs >= 1_000) return `${sign}${trimZeros((abs / 1_000).toFixed(abs >= 10_000 ? 0 : 1))}${NBSP}k`;
  return `${sign}${formatNumber(abs)}`;
}

/** `value` exprimé en pourcentage (0-100) → « 68,4 % ». */
export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${trimZeros(value.toFixed(digits)) || "0"}${NBSP}%`;
}

/** « +12 % » / « −3 % ». */
export function formatSignedPercent(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${trimZeros(Math.abs(value).toFixed(digits)) || "0"}${NBSP}%`;
}

/** « +123 » / « −4 ». */
export function formatSigned(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : n < 0 ? "−" : "";
  return `${sign}${formatNumber(Math.abs(n))}`;
}

/** « 1 240 h ». */
export function formatHours(hours: number | null | undefined): string {
  if (hours == null || Number.isNaN(hours)) return "—";
  return `${formatNumber(Math.round(hours))}${NBSP}h`;
}

/** Taille de fichier : « 850 Ko », « 48 Mo », « 1,2 Go ». */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || Number.isNaN(bytes)) return "—";
  if (bytes < 1024 * 1024) return `${Math.max(0, Math.round(bytes / 1024))}${NBSP}Ko`;
  if (bytes < 1024 ** 3) return `${Math.round(bytes / 1024 ** 2)}${NBSP}Mo`;
  return `${trimZeros((bytes / 1024 ** 3).toFixed(1))}${NBSP}Go`;
}

/** Pourcentage borné 0-100 pour une barre de progression. */
export function clampPct(value: number): number {
  return Math.max(0, Math.min(100, value));
}
