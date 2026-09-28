import Link from "next/link";
import { ChevronRight, Eye, FileText, TriangleAlert, WandSparkles } from "lucide-react";

import { AgentBadgeIcon } from "@/components/agents/agent-icon";
import { AGENTS, CONSIGNES, PROMPT_KEYS, promptName } from "@/lib/agent-catalog";
import type { AgentActivity, PromptState } from "@/lib/agent-types";
import { formatNumber, formatRelative } from "@/lib/format";

function plural(n: number, one: string, many: string): string {
  return `${formatNumber(n)} ${n > 1 ? many : one}`;
}

/** « v2 · texte du code · 1 358 caractères » */
export function PromptLine({ state }: { state: PromptState | undefined }) {
  const v = state?.active;
  return (
    <span className="text-muted-foreground text-xs">
      {v
        ? `Version ${v.version} · ${v.origin === "code" ? "texte du code" : v.origin === "human" ? "ta version" : "proposée par l’agent amélioration"} · ${plural(v.content.length, "caractère", "caractères")}`
        : "Texte du code (le worker l’enregistre à son prochain démarrage)"}
    </span>
  );
}

/** Alertes d'un prompt : le code a changé depuis la version active, propositions de l'agent amélioration. */
export function PromptFlags({ state }: { state: PromptState | undefined }) {
  if (!state?.codeUpdate && !state?.proposals.length) return null;
  return (
    <span className="flex flex-wrap gap-1.5">
      {state.codeUpdate ? (
        <span className="flex items-center gap-1 rounded-md border border-amber-500/50 bg-amber-500/10 px-1.5 py-0.5 text-[11px] font-medium text-amber-700 dark:text-amber-300">
          <TriangleAlert className="size-3" />
          Nouveau texte du code
        </span>
      ) : null}
      {state.proposals.length ? (
        <span className="flex items-center gap-1 rounded-md border border-violet-500/50 bg-violet-500/10 px-1.5 py-0.5 text-[11px] font-medium text-violet-700 dark:text-violet-300">
          <WandSparkles className="size-3" />
          {plural(state.proposals.length, "proposition", "propositions")}
        </span>
      ) : null}
    </span>
  );
}

export function ActivityLine({ activity, vision }: { activity: AgentActivity | undefined; vision?: boolean }) {
  if (!activity) return <span className="text-muted-foreground text-xs">Rien ces 7 derniers jours</span>;
  const parts = vision
    ? [plural(activity.checked ?? 0, "verdict", "verdicts"), activity.refused ? plural(activity.refused, "refus", "refus") : ""]
    : [
        plural(activity.done, "tâche terminée", "tâches terminées"),
        activity.failed ? plural(activity.failed, "échec", "échecs") : "",
        activity.running ? `${activity.running} en cours` : "",
        activity.queued ? `${activity.queued} en file` : "",
      ];
  return (
    <span className="text-muted-foreground text-xs">
      {parts.filter(Boolean).join(" · ")} ces 7 derniers jours{activity.lastAt ? ` · dernier passage ${formatRelative(activity.lastAt)}` : ""}
    </span>
  );
}

/** Les agents du pipeline, dans l'ordre de la chaîne, puis les consignes communes, puis les clés que le worker a
 * enregistrées sans qu'elles soient encore décrites dans lib/agent-catalog.ts (une nouvelle recette, par exemple). */
export function AgentList({ prompts, activity }: { prompts: Record<string, PromptState>; activity: Record<string, AgentActivity> }) {
  const others = Object.keys(prompts)
    .filter((k) => !PROMPT_KEYS.includes(k))
    .sort();
  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3">
        <div>
          <h3 className="text-base font-semibold">Agents</h3>
          <p className="text-muted-foreground text-sm">
            Chacun reçoit son prompt système, puis les données de la tâche. Ouvre un agent pour lire et modifier son prompt.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {AGENTS.map((agent) => (
            <Link
              key={agent.key}
              href={`/agents/${agent.key}`}
              className="bg-card hover:border-foreground/30 focus-visible:ring-ring/50 group flex flex-col gap-3 rounded-xl border p-4 transition-colors outline-none focus-visible:ring-[3px]"
            >
              <div className="flex items-start gap-3">
                <AgentBadgeIcon icon={agent.icon} />
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="flex items-center gap-2 font-medium">
                    {agent.name}
                    {agent.vision ? (
                      <span className="text-muted-foreground flex items-center gap-1 rounded border px-1.5 text-[11px] font-normal">
                        <Eye className="size-3" />
                        vision
                      </span>
                    ) : null}
                  </span>
                  {agent.scope ? <span className="text-muted-foreground text-xs">{agent.scope}</span> : null}
                </div>
                <ChevronRight className="text-muted-foreground size-4 shrink-0 transition-transform group-hover:translate-x-0.5" />
              </div>
              <p className="text-sm">{agent.summary}</p>
              <div className="mt-auto flex flex-col gap-1.5">
                <PromptFlags state={prompts[agent.key]} />
                <PromptLine state={prompts[agent.key]} />
                <ActivityLine activity={activity[agent.key]} vision={agent.vision} />
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <div>
          <h3 className="text-base font-semibold">Consignes communes</h3>
          <p className="text-muted-foreground text-sm">
            Des blocs de règles ajoutés au message de plusieurs agents, avec les données de la tâche. Les modifier change tous les agents qui les reçoivent.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {CONSIGNES.map((c) => (
            <Link
              key={c.key}
              href={`/agents/${c.key}`}
              className="bg-card hover:border-foreground/30 focus-visible:ring-ring/50 group flex flex-col gap-2 rounded-xl border p-4 transition-colors outline-none focus-visible:ring-[3px]"
            >
              <div className="flex items-center gap-3">
                <span className="bg-muted text-muted-foreground flex size-9 shrink-0 items-center justify-center rounded-lg">
                  <FileText className="size-4" />
                </span>
                <span className="min-w-0 flex-1 font-medium">{c.name}</span>
                <ChevronRight className="text-muted-foreground size-4 shrink-0 transition-transform group-hover:translate-x-0.5" />
              </div>
              <p className="text-sm">{c.summary}</p>
              <p className="text-muted-foreground text-xs">Reçue par : {c.usedBy.map(promptName).join(", ")}</p>
              <div className="mt-auto flex flex-col gap-1.5">
                <PromptFlags state={prompts[c.key]} />
                <PromptLine state={prompts[c.key]} />
              </div>
            </Link>
          ))}
        </div>
      </section>

      {others.length ? (
        <section className="flex flex-col gap-3">
          <div>
            <h3 className="text-base font-semibold">Autres prompts du worker</h3>
            <p className="text-muted-foreground text-sm">Enregistrés par le code du worker, pas encore décrits dans cet onglet.</p>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {others.map((key) => (
              <Link
                key={key}
                href={`/agents/${key}`}
                className="bg-card hover:border-foreground/30 focus-visible:ring-ring/50 flex flex-col gap-1.5 rounded-xl border p-4 transition-colors outline-none focus-visible:ring-[3px]"
              >
                <span className="font-mono text-sm font-medium">{key}</span>
                <PromptFlags state={prompts[key]} />
                <PromptLine state={prompts[key]} />
              </Link>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
