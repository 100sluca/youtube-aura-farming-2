/** Formatage en français, heure de Paris. */

const TZ = "Europe/Paris";
const NBSP = " ";
const nf = new Intl.NumberFormat("fr-FR");

export const isNum = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

/** Espace insécable ordinaire entre les milliers (l'espace fine de fr-FR n'a pas de largeur dans certaines polices). */
export const fmt = (n: number | null | undefined): string => (isNum(n) ? nf.format(Math.round(n)).replace(/ /g, NBSP) : "—");

export function compact(n: number | null | undefined): string {
  if (!isNum(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e6) return `${(n / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(".", ",")}${NBSP}M`;
  if (a >= 1e4) return `${Math.round(n / 1e3)}${NBSP}k`;
  return fmt(n);
}

export const pct = (n: number | null | undefined, digits = 0): string => (isNum(n) ? `${n.toFixed(digits).replace(".", ",")}${NBSP}%` : "—");

export const euros = (n: number | null | undefined): string =>
  isNum(n) ? `${n < 10 ? n.toFixed(2).replace(".", ",") : fmt(n)}${NBSP}€` : "—";

export const signed = (n: number | null | undefined): string => (isNum(n) ? `${n > 0 ? "+" : n < 0 ? "−" : "±"}${fmt(Math.abs(n))}` : "—");

export function duration(s: number | null | undefined): string {
  if (!isNum(s)) return "—";
  if (s >= 60) return `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, "0")}`;
  return `${s.toFixed(s < 10 ? 1 : 0).replace(".", ",")} s`;
}

const dayKey = (d: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);

export function time(iso: string): string {
  return new Intl.DateTimeFormat("fr-FR", { timeZone: TZ, hour: "2-digit", minute: "2-digit" }).format(new Date(iso)).replace(":", " h ");
}

export function dayLabel(iso: string): string {
  const k = dayKey(new Date(iso));
  if (k === dayKey(new Date())) return "aujourd’hui";
  if (k === dayKey(new Date(Date.now() + 86_400_000))) return "demain";
  if (k === dayKey(new Date(Date.now() - 86_400_000))) return "hier";
  return new Intl.DateTimeFormat("fr-FR", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" }).format(new Date(iso));
}

export const when = (iso: string | null | undefined): string => (iso ? `${dayLabel(iso)} à ${time(iso)}` : "—");

/** « 4 oct. » pour une clé de jour AAAA-MM-JJ. */
export const shortDay = (day: string): string =>
  new Intl.DateTimeFormat("fr-FR", { timeZone: "UTC", day: "numeric", month: "short" }).format(new Date(`${day}T12:00:00Z`));

export function ago(iso: string | null | undefined): string {
  if (!iso) return "jamais";
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (m < 1) return "à l’instant";
  if (m < 60) return `il y a ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `il y a ${h} h${m % 60 ? ` ${String(m % 60).padStart(2, "0")}` : ""}`;
  const d = Math.floor(h / 24);
  return `il y a ${d} jour${d > 1 ? "s" : ""}`;
}

/** « vers 22 h 10 » aujourd'hui, « demain vers 01 h 05 » sinon. */
export function eta(iso: string | null | undefined): string | null {
  if (!iso) return null;
  return dayKey(new Date(iso)) === dayKey(new Date()) ? `vers ${time(iso)}` : `${dayLabel(iso)} vers ${time(iso)}`;
}

export const minutesSince = (iso: string | null | undefined): number => (iso ? (Date.now() - new Date(iso).getTime()) / 60_000 : Infinity);

export const sum = (list: (number | null | undefined)[]): number => list.reduce<number>((s, n) => s + (isNum(n) ? n : 0), 0);

/** Lien ou image venus de l'instantané : seulement en http(s). */
export const safeUrl = (u: string | null | undefined): string | undefined => (typeof u === "string" && /^https?:\/\//i.test(u) ? u : undefined);
