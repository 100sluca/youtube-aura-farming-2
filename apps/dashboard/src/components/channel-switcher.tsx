"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { parseChannel } from "@/lib/channel";

/** Filtre global Toutes / FR / EN, persisté dans `?channel=`. */
export function ChannelSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const value = parseChannel(searchParams.get("channel")) ?? "all";

  function onValueChange(next: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (next === "all") params.delete("channel");
    else params.set("channel", next);
    const qs = params.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  }

  return (
    <Tabs value={value} onValueChange={onValueChange}>
      <TabsList aria-label="Chaîne">
        <TabsTrigger value="all">Toutes</TabsTrigger>
        <TabsTrigger value="fr">FR</TabsTrigger>
        <TabsTrigger value="en">EN</TabsTrigger>
      </TabsList>
    </Tabs>
  );
}
