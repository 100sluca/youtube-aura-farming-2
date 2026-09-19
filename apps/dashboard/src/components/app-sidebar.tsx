"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Clapperboard } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { NAV_ITEMS, isNavActive } from "@/components/nav-items";
import { cn } from "@/lib/utils";

export function SidebarBrand() {
  return (
    <Link href="/" className="flex h-14 items-center gap-2.5 border-b px-4">
      <span className="bg-sidebar-primary text-sidebar-primary-foreground flex size-8 items-center justify-center rounded-lg">
        <Clapperboard className="size-4" />
      </span>
      <span className="flex flex-col leading-tight">
        <span className="text-sm font-semibold">YouTube 2.0</span>
        <span className="text-muted-foreground text-[11px]">Usine à Shorts · FR + EN</span>
      </span>
    </Link>
  );
}

export function SidebarNav({
  openAlerts,
  onNavigate,
}: {
  openAlerts: number;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  return (
    <nav aria-label="Navigation principale" className="flex flex-col gap-1 p-3">
      {NAV_ITEMS.map((item) => {
        const active = isNavActive(pathname, item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-sidebar-ring flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors outline-none focus-visible:ring-2",
              active && "bg-sidebar-accent text-sidebar-accent-foreground"
            )}
          >
            <Icon className="size-4 shrink-0" />
            <span className="truncate">{item.label}</span>
            {item.href === "/alerts" && openAlerts > 0 ? (
              <Badge variant="destructive" className="ml-auto h-5 min-w-5 px-1.5 tabular-nums">
                {openAlerts}
              </Badge>
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}

export function AppSidebar({ openAlerts }: { openAlerts: number }) {
  return (
    <aside className="bg-sidebar text-sidebar-foreground border-sidebar-border sticky top-0 hidden h-svh w-64 shrink-0 flex-col border-r md:flex">
      <SidebarBrand />
      <SidebarNav openAlerts={openAlerts} />
      <div className="text-muted-foreground mt-auto border-t p-4 text-xs leading-relaxed">
        <p className="font-medium">Mode démo</p>
        <p>Données factices, ancrées au 19 sept. 2026.</p>
      </div>
    </aside>
  );
}
