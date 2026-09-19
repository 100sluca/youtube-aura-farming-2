import { Suspense } from "react";

import { ChannelSwitcher } from "@/components/channel-switcher";
import { MobileNav } from "@/components/mobile-nav";
import { PageTitle } from "@/components/page-title";
import { ThemeToggle } from "@/components/theme-toggle";
import { Skeleton } from "@/components/ui/skeleton";

export function AppHeader({ openAlerts }: { openAlerts: number }) {
  return (
    <header className="bg-background/95 supports-[backdrop-filter]:bg-background/80 sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b px-4 backdrop-blur md:px-6">
      <MobileNav openAlerts={openAlerts} />
      <PageTitle />
      <div className="ml-auto flex items-center gap-2">
        <Suspense fallback={<Skeleton className="h-9 w-40 rounded-lg" />}>
          <ChannelSwitcher />
        </Suspense>
        <ThemeToggle />
      </div>
    </header>
  );
}
