import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Eye, FileText, Info, Workflow } from "lucide-react";

import { ActivityLine } from "@/components/agents/agent-list";
import { AgentBadgeIcon } from "@/components/agents/agent-icon";
import { PromptWorkbench } from "@/components/agents/prompt-workbench";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AGENT_BY_KEY, CONSIGNE_BY_KEY, LEARNING_LOOP, PIPELINE, promptName } from "@/lib/agent-catalog";
import type { AgentActivity } from "@/lib/agent-types";
import { getAgentActivity, getLlmLabels, getPromptState } from "@/lib/agents";

export async function generateMetadata({ params }: { params: Promise<{ key: string }> }): Promise<Metadata> {
  const { key } = await params;
  return { title: promptName(key) };
}

/** L'étape de la chaîne où intervient un agent (« 2 · Écriture »). */
function stageOf(key: string): string | null {
  const i = PIPELINE.findIndex((s) => s.steps.some((step) => step.agents?.includes(key)));
  if (i >= 0) return `Étape ${i + 1} · ${PIPELINE[i].title}`;
  return LEARNING_LOOP.some((step) => step.agents?.includes(key)) ? "Boucle d’apprentissage" : null;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <h4 className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">{title}</h4>
      <div className="text-sm leading-relaxed">{children}</div>
    </div>
  );
}

export default async function AgentPage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = await params;
  const agent = AGENT_BY_KEY[key];
  const consigne = CONSIGNE_BY_KEY[key];
  const noActivity: Record<string, AgentActivity> = {};
  const [state, activity, labels] = await Promise.all([
    getPromptState(key),
    agent ? getAgentActivity() : Promise.resolve(noActivity),
    getLlmLabels(),
  ]);
  if (!agent && !consigne && state.versions.length === 0) notFound();
  const stage = agent ? stageOf(key) : null;

  return (
    <div className="flex flex-col gap-6">
      <Link href="/agents" className="text-muted-foreground hover:text-foreground flex w-fit items-center gap-1.5 text-sm">
        <ArrowLeft className="size-4" />
        Tous les agents
      </Link>

      <header className="flex items-start gap-4">
        {agent ? (
          <AgentBadgeIcon icon={agent.icon} className="size-11" />
        ) : (
          <span className="bg-muted text-muted-foreground flex size-11 shrink-0 items-center justify-center rounded-lg">
            <FileText className="size-5" />
          </span>
        )}
        <div className="flex min-w-0 flex-col gap-1">
          <h2 className="flex flex-wrap items-center gap-2 text-2xl font-semibold tracking-tight">
            {agent?.name ?? consigne?.name ?? key}
            {agent?.vision ? (
              <span className="text-muted-foreground flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-normal">
                <Eye className="size-3.5" />
                modèle de vision
              </span>
            ) : null}
          </h2>
          <p className="text-muted-foreground max-w-3xl text-sm">
            {agent?.summary ?? consigne?.summary ?? "Prompt enregistré par le code du worker, pas encore décrit dans cet onglet."}
            {agent?.scope ? ` ${agent.scope}${/[.…!?]$/.test(agent.scope) ? "" : "."}` : ""}
          </p>
        </div>
      </header>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <PromptWorkbench promptKey={key} kind={consigne ? "consigne" : "agent"} state={state} />

        <aside className="flex flex-col gap-4 xl:sticky xl:top-20">
          {agent ? (
            <Card className="gap-4">
              <CardHeader>
                <CardTitle className="text-base">Comment il travaille</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                {stage ? (
                  <Link href="/agents?vue=chaine" className="flex w-fit items-center gap-1.5 text-sm font-medium underline-offset-4 hover:underline">
                    <Workflow className="size-4" />
                    {stage}
                  </Link>
                ) : null}
                <Section title="Quand">{agent.when}</Section>
                <Section title="Modèle">
                  {agent.vision ? labels.vision : labels.llm}{" "}
                  <Link href="/settings" className="text-muted-foreground underline underline-offset-4">
                    (Réglages)
                  </Link>
                </Section>
                <Section title="Ce qu’il reçoit avec son prompt">
                  <ul className="flex list-disc flex-col gap-1 pl-4">
                    {agent.inputs.map((input) => (
                      <li key={input}>{input}</li>
                    ))}
                    {agent.consignes.map((c) => (
                      <li key={c}>
                        La consigne commune{" "}
                        <Link href={`/agents/${c}`} className="font-medium underline underline-offset-4">
                          {promptName(c)}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </Section>
                <Section title="Ce qu’il rend">{agent.output}</Section>
                <Section title="Ensuite">{agent.then}</Section>
                <Section title="Activité">
                  <ActivityLine activity={activity[key]} vision={agent.vision} />
                </Section>
              </CardContent>
            </Card>
          ) : null}

          {consigne ? (
            <Card className="gap-4">
              <CardHeader>
                <CardTitle className="text-base">Où elle sert</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <Section title="Reçue par">
                  <ul className="flex flex-col gap-1">
                    {consigne.usedBy.map((a) => (
                      <li key={a}>
                        <Link href={`/agents/${a}`} className="font-medium underline underline-offset-4">
                          {promptName(a)}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </Section>
                {consigne.note ? (
                  <p className="flex items-start gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 p-3 text-xs leading-relaxed">
                    <Info className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
                    {consigne.note}
                  </p>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
