import { Suspense } from "react";

import { ChannelSwitcher } from "@/components/channel-switcher";
import { MobileNav } from "@/components/mobile-nav";
import { PageTitle } from "@/components/page-title";
import { TaskManager } from "@/components/tasks/task-manager";
import { ThemeToggle } from "@/components/theme-toggle";
import { Skeleton } from "@/components/ui/skeleton";
import { getChannelContext } from "@/lib/channel-server";

/** Sélecteur de chaîne : seule partie de l'en-tête qui lit la base. */
async function HeaderChannelSwitcher() {
  const { channels, selected } = await getChannelContext();
  return <ChannelSwitcher channels={channels} selected={selected?.slug ?? null} />;
}

/**
 * En-tête : chaîne affichée, gestionnaire de tâches, thème clair / sombre. Le sélecteur de chaîne est dans son propre
 * Suspense : une lecture de la base dans la mise en page bloquerait sinon chaque changement de page et les écrans de
 * chargement (loading.tsx) ne s'afficheraient pas (docs/56-dashboard-rapide.md).
 */
export function AppHeader() {
  return (
    <header className="bg-background/95 supports-[backdrop-filter]:bg-background/80 sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b px-4 backdrop-blur md:px-6">
      <MobileNav />
      <PageTitle />
      <div className="ml-auto flex items-center gap-2">
        <Suspense fallback={<Skeleton className="h-8 w-14 sm:w-44" />}>
          <HeaderChannelSwitcher />
        </Suspense>
        <TaskManager />
        <ThemeToggle />
      </div>
    </header>
  );
}
