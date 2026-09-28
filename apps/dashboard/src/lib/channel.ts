/**
 * Chaîne sélectionnée dans l'en-tête (« Toutes » ou une chaîne) : mémorisée dans un cookie, lue côté serveur par
 * lib/channel-server.ts, posée par l'action selectChannel (app/channel-actions.ts). Ce module reste utilisable
 * côté client (pas d'accès aux cookies ici).
 */

export const CHANNEL_COOKIE = "yt2_channel";
export const ALL_CHANNELS = "all";

/** Couleurs des chaînes (palette des graphiques), attribuées par le slug : même couleur partout. */
const PALETTE = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];

export function channelColor(slug: string): string {
  let h = 0;
  for (const ch of slug) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

/** Initiales d'une chaîne pour son avatar (« Chaîne de test » → « CT »). */
export function channelInitials(name: string): string {
  const words = name
    .replace(/[^A-Za-zÀ-ÖØ-öø-ÿ0-9\s]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 2 || /\d/.test(w));
  const letters = (words.length ? words : name.split(/\s+/)).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "");
  return letters.join("") || "?";
}

/** Slug d'une nouvelle chaîne à partir de son nom (« Ma chaîne 2 » → « ma-chaine-2 »). */
export function slugify(name: string): string {
  return (
    name
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 32) || "chaine"
  );
}
