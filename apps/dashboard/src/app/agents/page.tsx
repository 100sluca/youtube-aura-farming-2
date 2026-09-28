import type { Metadata } from "next";

import { AgentList } from "@/components/agents/agent-list";
import { AgentsTabs } from "@/components/agents/agents-tabs";
import { PipelineDiagram } from "@/components/agents/pipeline-diagram";
import { PageHeader } from "@/components/page-header";
import { getAgentActivity, getPipelineLive, getPromptStates } from "@/lib/agents";

export const metadata: Metadata = { title: "Agents" };

export default async function AgentsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const [prompts, activity, live] = await Promise.all([getPromptStates(), getAgentActivity(), getPipelineLive()]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader description="Les agents IA qui écrivent et contrôlent tes vidéos, avec leur prompt système, et la chaîne complète de fabrication, de l’idée à la publication. Un prompt modifié ici sert dès la tâche suivante ; l’historique garde toutes les versions." />
      <AgentsTabs
        initial={params.vue === "chaine" ? "chaine" : "agents"}
        agents={<AgentList prompts={prompts} activity={activity} />}
        chain={<PipelineDiagram live={live} prompts={prompts} />}
      />
    </div>
  );
}
