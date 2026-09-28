import {
  Bot,
  CalendarDays,
  ChartColumnBig,
  Clapperboard,
  LayoutDashboard,
  LibraryBig,
  Settings,
  Sparkles,
  Star,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

/** Menu de gauche (docs/16, docs/19, docs/22, docs/23) : on crée, on retrouve, on garde ce qu'on aime, on planifie, on
 * règle les agents et leurs prompts, et le modèle de montage. La fabrication se suit dans le panneau « Tâches ». */
export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Vue d’ensemble", icon: LayoutDashboard },
  { href: "/dashboard", label: "Dashboard", icon: ChartColumnBig }, // stats de chaque vidéo + agent analyste (docs/25)
  { href: "/create", label: "Création", icon: Sparkles },
  { href: "/library", label: "Bibliothèque", icon: LibraryBig },
  { href: "/favorites", label: "Favoris", icon: Star },
  { href: "/calendar", label: "Calendrier", icon: CalendarDays },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/montage", label: "Montage", icon: Clapperboard },
  { href: "/settings", label: "Réglages", icon: Settings },
];

export function isNavActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function pageTitle(pathname: string): string {
  return NAV_ITEMS.find((item) => isNavActive(pathname, item.href))?.label ?? "YouTube 2.0";
}
