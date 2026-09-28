import { ChannelSwitcher } from "@/components/channel-switcher";
import { MobileNav } from "@/components/mobile-nav";
import { PageTitle } from "@/components/page-title";
import { TaskManager } from "@/components/tasks/task-manager";
import { ThemeToggle } from "@/components/theme-toggle";
import { getChannelContext } from "@/lib/channel-server";

/** En-tête : chaîne affichée, gestionnaire de tâches, thème clair / sombre. */
export async function AppHeader() {
  const { channels, selected } = await getChannelContext();
  return (
    <header className="bg-background/95 supports-[backdrop-filter]:bg-background/80 sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b px-4 backdrop-blur md:px-6">
      <MobileNav />
      <PageTitle />
      <div className="ml-auto flex items-center gap-2">
        <ChannelSwitcher channels={channels} selected={selected?.slug ?? null} />
        <TaskManager />
        <ThemeToggle />
      </div>
    </header>
  );
}
