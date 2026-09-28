"use client";

import * as React from "react";
import { Clapperboard, FlaskConical } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export type LibraryTab = "videos" | "demos";

/** Les deux vues de la Bibliothèque ; la vue choisie est gardée dans l'adresse (?vue=demos) pour le retour arrière. */
export function LibraryTabs({
  initial,
  videoCount,
  demoCount,
  videos,
  demos,
}: {
  initial: LibraryTab;
  videoCount: number;
  demoCount: number;
  videos: React.ReactNode;
  demos: React.ReactNode;
}) {
  const [view, setView] = React.useState<LibraryTab>(initial);
  return (
    <Tabs
      value={view}
      onValueChange={(v) => {
        const next = v === "demos" ? "demos" : "videos";
        setView(next);
        const url = new URL(window.location.href);
        if (next === "demos") url.searchParams.set("vue", "demos");
        else url.searchParams.delete("vue");
        window.history.replaceState(null, "", url);
      }}
      className="gap-4"
    >
      <TabsList>
        <TabsTrigger value="videos" className="px-3">
          <Clapperboard />
          Vidéos <span className="tabular-nums opacity-70">{videoCount}</span>
        </TabsTrigger>
        <TabsTrigger value="demos" className="px-3">
          <FlaskConical />
          Démos et essais <span className="tabular-nums opacity-70">{demoCount}</span>
        </TabsTrigger>
      </TabsList>
      <TabsContent value="videos">{videos}</TabsContent>
      <TabsContent value="demos">{demos}</TabsContent>
    </Tabs>
  );
}
