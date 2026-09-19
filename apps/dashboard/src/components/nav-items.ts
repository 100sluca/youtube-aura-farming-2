import {
  Bell,
  CalendarDays,
  Factory,
  Film,
  FlaskConical,
  LayoutDashboard,
  Lightbulb,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Vue d’ensemble", icon: LayoutDashboard },
  { href: "/videos", label: "Vidéos publiées", icon: Film },
  { href: "/production", label: "Production", icon: Factory },
  { href: "/calendar", label: "Calendrier", icon: CalendarDays },
  { href: "/ideas", label: "Idées", icon: Lightbulb },
  { href: "/experiments", label: "Expériences", icon: FlaskConical },
  { href: "/alerts", label: "Alertes", icon: Bell },
  { href: "/settings", label: "Réglages", icon: Settings },
];

export function isNavActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function pageTitle(pathname: string): string {
  return NAV_ITEMS.find((item) => isNavActive(pathname, item.href))?.label ?? "YouTube 2.0";
}
