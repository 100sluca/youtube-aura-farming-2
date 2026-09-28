/**
 * Formats de vidéo dans le Dashboard (docs/25) : une couleur par format, la même dans le tableau et les graphiques.
 * Trois teintes catégorielles vérifiées (lisibles par un daltonien, clair et sombre : validateur de la compétence
 * dataviz, toutes paires) + un gris pour les vidéos mises en ligne à la main, dont on ne connaît pas le format.
 */
import type { ChartConfig } from "@/components/ui/chart";
import type { VideoOverview } from "@/lib/types";

export type FormatKey = "timelapse" | "tour" | "story" | "imported";

export const FORMAT_ORDER: FormatKey[] = ["timelapse", "tour", "story", "imported"];

export const FORMAT_LABELS: Record<FormatKey, string> = {
  timelapse: "Chantier",
  tour: "Visite",
  story: "Récit",
  imported: "À la main",
};

export const FORMAT_HINTS: Record<FormatKey, string> = {
  timelapse: "Chantier en accéléré",
  tour: "Visite de maison de luxe",
  story: "Récit narré",
  imported: "Mise en ligne à la main (importée) : format inconnu",
};

export const FORMAT_CHART_CONFIG = {
  timelapse: { label: FORMAT_LABELS.timelapse, theme: { light: "#2a78d6", dark: "#3987e5" } },
  tour: { label: FORMAT_LABELS.tour, theme: { light: "#eb6834", dark: "#d95926" } },
  story: { label: FORMAT_LABELS.story, theme: { light: "#1baf7a", dark: "#199e70" } },
  imported: { label: FORMAT_LABELS.imported, theme: { light: "#8a8984", dark: "#8a8984" } },
} satisfies ChartConfig;

/** Pastille de couleur hors graphique (classes écrites en entier pour Tailwind). */
export const FORMAT_DOT: Record<FormatKey, string> = {
  timelapse: "bg-[#2a78d6] dark:bg-[#3987e5]",
  tour: "bg-[#eb6834] dark:bg-[#d95926]",
  story: "bg-[#1baf7a] dark:bg-[#199e70]",
  imported: "bg-[#8a8984]",
};

export function formatKey(v: Pick<VideoOverview, "origin" | "recipe">): FormatKey {
  if (v.origin === "imported") return "imported";
  return v.recipe === "timelapse" || v.recipe === "tour" ? v.recipe : "story";
}
