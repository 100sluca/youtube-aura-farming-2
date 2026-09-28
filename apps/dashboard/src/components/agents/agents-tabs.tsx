"use client";

import * as React from "react";
import { Bot, Workflow } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export type AgentsView = "agents" | "chaine";

/** Les deux vues de l'onglet Agents ; la vue choisie est gardée dans l'adresse (?vue=chaine) pour le retour arrière. */
export function AgentsTabs({ initial, agents, chain }: { initial: AgentsView; agents: React.ReactNode; chain: React.ReactNode }) {
  const [view, setView] = React.useState<AgentsView>(initial);
  return (
    <Tabs
      value={view}
      onValueChange={(v) => {
        const next = v === "chaine" ? "chaine" : "agents";
        setView(next);
        const url = new URL(window.location.href);
        if (next === "chaine") url.searchParams.set("vue", "chaine");
        else url.searchParams.delete("vue");
        window.history.replaceState(null, "", url);
      }}
      className="gap-4"
    >
      <TabsList>
        <TabsTrigger value="agents" className="px-3">
          <Bot />
          Agents<span className="hidden sm:inline"> et prompts</span>
        </TabsTrigger>
        <TabsTrigger value="chaine" className="px-3">
          <Workflow />
          Chaîne<span className="hidden sm:inline"> de production</span>
        </TabsTrigger>
      </TabsList>
      <TabsContent value="agents">{agents}</TabsContent>
      <TabsContent value="chaine">{chain}</TabsContent>
    </Tabs>
  );
}
