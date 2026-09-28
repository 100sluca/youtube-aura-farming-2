import Link from "next/link";
import { ArrowDown, ArrowRight, Bot, Code, Cpu, Hand, Repeat, type LucideIcon } from "lucide-react";

import {
  AGENT_BY_KEY,
  LEARNING_LOOP,
  PIPELINE,
  type PipelineStep,
  type StepKind,
  type WaitingKey,
} from "@/lib/agent-catalog";
import type { PipelineLive, PromptState } from "@/lib/agent-types";
import { cn } from "@/lib/utils";

const KIND: Record<StepKind, { label: string; icon: LucideIcon; card: string; tone: string }> = {
  agent: {
    label: "Agent IA",
    icon: Bot,
    card: "border-violet-500/40 bg-violet-500/10 hover:border-violet-500/70",
    tone: "text-violet-700 dark:text-violet-300",
  },
  model: { label: "Modèle local", icon: Cpu, card: "border-sky-500/40 bg-sky-500/10 hover:border-sky-500/70", tone: "text-sky-700 dark:text-sky-300" },
  code: { label: "Programme", icon: Code, card: "bg-muted/40 hover:border-foreground/30", tone: "text-muted-foreground" },
  human: { label: "Toi", icon: Hand, card: "border-amber-500/50 bg-amber-500/10 hover:border-amber-500/80", tone: "text-amber-700 dark:text-amber-300" },
};

const WAITING: Record<WaitingKey, [string, string]> = {
  concepts: ["idée à trier", "idées à trier"],
  storyboards: ["storyboard à valider", "storyboards à valider"],
  videos_review: ["vidéo à autoriser", "vidéos à autoriser"],
  scheduled: ["vidéo programmée", "vidéos programmées"],
  published: ["vidéo publiée", "vidéos publiées"],
};

/** Nom court d'un scénariste dans l'étape « Scénariste » (« Scénariste · histoires » → « histoires »). */
function shortName(key: string): string {
  const name = AGENT_BY_KEY[key]?.name ?? key;
  return name.includes(" · ") ? name.split(" · ")[1] : name;
}

function versionLabel(state: PromptState | undefined): string {
  const v = state?.active;
  if (!v) return "texte du code";
  return `v${v.version} · ${v.origin === "code" ? "texte du code" : v.origin === "human" ? "ta version" : "version proposée"}`;
}

function StepCard({ step, live, prompts }: { step: PipelineStep; live: PipelineLive; prompts: Record<string, PromptState> }) {
  const kind = KIND[step.kind];
  const Icon = kind.icon;
  const single = step.agents?.length === 1 ? step.agents[0] : null;
  const href = single ? `/agents/${single}` : step.href;
  const jobs = (step.jobs ?? []).reduce(
    (acc, t) => ({ running: acc.running + (live.jobs[t]?.running ?? 0), queued: acc.queued + (live.jobs[t]?.queued ?? 0) }),
    { running: 0, queued: 0 },
  );
  const waiting = step.waiting ? live.waiting[step.waiting] : 0;
  const body = (
    <>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className={cn("flex items-center gap-1 text-[11px] font-semibold tracking-wide uppercase", kind.tone)}>
          <Icon className="size-3.5" />
          {kind.label}
        </span>
        {step.only ? <span className="text-muted-foreground rounded border px-1.5 text-[11px]">{step.only}</span> : null}
      </div>
      <p className="font-medium">{step.title}</p>
      <p className="text-muted-foreground text-xs leading-relaxed">{step.detail}</p>
      <div className="mt-auto flex flex-col gap-1 pt-1 text-xs">
        {step.model ? (
          <span className="flex items-start gap-1.5">
            <Cpu className="text-muted-foreground mt-0.5 size-3.5 shrink-0" />
            <span>{live.models[step.model]}</span>
          </span>
        ) : null}
        {single ? <span className="text-muted-foreground">Prompt {versionLabel(prompts[single])}</span> : null}
        {jobs.running || jobs.queued ? (
          <span className="flex items-center gap-1.5 font-medium text-emerald-700 dark:text-emerald-400">
            <span className="relative flex size-2">
              {jobs.running ? <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500 opacity-60" /> : null}
              <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
            </span>
            {[jobs.running ? `${jobs.running} en cours` : "", jobs.queued ? `${jobs.queued} en file` : ""].filter(Boolean).join(" · ")}
          </span>
        ) : null}
        {step.waiting && waiting ? (
          <span className="font-medium">
            {waiting} {WAITING[step.waiting][waiting > 1 ? 1 : 0]}
          </span>
        ) : null}
      </div>
    </>
  );
  const box = cn("flex h-full min-h-36 flex-col gap-1.5 rounded-lg border p-3 text-sm transition-colors", kind.card);
  if (step.agents && step.agents.length > 1) {
    return (
      <div className={box}>
        {body}
        <div className="flex flex-wrap gap-1.5 pt-1">
          {step.agents.map((key) => (
            <Link
              key={key}
              href={`/agents/${key}`}
              className="bg-background/70 hover:bg-background rounded-md border px-2 py-1 text-xs font-medium transition-colors"
            >
              {shortName(key)} <span className="text-muted-foreground font-normal">· {versionLabel(prompts[key]).split(" · ")[0]}</span>
            </Link>
          ))}
        </div>
      </div>
    );
  }
  return href ? (
    <Link href={href} className={cn(box, "focus-visible:ring-ring/50 outline-none focus-visible:ring-[3px]")}>
      {body}
    </Link>
  ) : (
    <div className={box}>{body}</div>
  );
}

function StepArrow() {
  return (
    <span aria-hidden className="text-muted-foreground flex items-center justify-center">
      <ArrowDown className="size-4 sm:hidden" />
      <ArrowRight className="hidden size-4 sm:block" />
    </span>
  );
}

function Steps({ steps, live, prompts }: { steps: PipelineStep[]; live: PipelineLive; prompts: Record<string, PromptState> }) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-stretch">
      {steps.map((step, i) => (
        <div key={step.id} className="flex flex-col gap-2 sm:min-w-52 sm:flex-1 sm:basis-52 sm:flex-row">
          <div className="min-w-0 flex-1">
            <StepCard step={step} live={live} prompts={prompts} />
          </div>
          {i < steps.length - 1 ? <StepArrow /> : null}
        </div>
      ))}
    </div>
  );
}

export function PipelineLegend() {
  return (
    <div className="flex flex-wrap gap-2 text-xs">
      {(["agent", "model", "code", "human"] as StepKind[]).map((k) => {
        const kind = KIND[k];
        const Icon = kind.icon;
        const hint = { agent: "prompt modifiable", model: "carte graphique", code: "étape automatique", human: "ta validation" }[k];
        return (
          <span key={k} className={cn("flex items-center gap-1.5 rounded-md border px-2 py-1", kind.card)}>
            <Icon className={cn("size-3.5", kind.tone)} />
            <span className="font-medium">{kind.label}</span>
            <span className="text-muted-foreground">· {hint}</span>
          </span>
        );
      })}
    </div>
  );
}

/** La chaîne de production d'une vidéo, de l'idée à la publication, avec ce qui tourne et ce qui attend en direct. */
export function PipelineDiagram({ live, prompts }: { live: PipelineLive; prompts: Record<string, PromptState> }) {
  return (
    <div className="flex flex-col gap-4">
      <PipelineLegend />
      <ol className="flex flex-col">
        {PIPELINE.map((stage, i) => (
          <li key={stage.id} className="flex flex-col">
            <section className="bg-card rounded-xl border p-4" aria-labelledby={`stage-${stage.id}`}>
              <header className="mb-3 flex items-baseline gap-3">
                <span className="bg-primary text-primary-foreground flex size-7 shrink-0 items-center justify-center self-center rounded-full text-sm font-semibold tabular-nums">
                  {i + 1}
                </span>
                <h3 id={`stage-${stage.id}`} className="text-base font-semibold">
                  {stage.title}
                </h3>
                <p className="text-muted-foreground text-sm">{stage.summary}</p>
              </header>
              <Steps steps={stage.steps} live={live} prompts={prompts} />
            </section>
            {i < PIPELINE.length - 1 ? (
              <span aria-hidden className="text-muted-foreground flex justify-center py-1.5">
                <ArrowDown className="size-5" />
              </span>
            ) : null}
          </li>
        ))}
      </ol>
      <section className="rounded-xl border border-dashed border-violet-500/50 p-4" aria-labelledby="stage-loop">
        <header className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="flex size-7 shrink-0 items-center justify-center self-center rounded-full bg-violet-500/15 text-violet-700 dark:text-violet-300">
            <Repeat className="size-4" />
          </span>
          <h3 id="stage-loop" className="text-base font-semibold">
            Boucle d’apprentissage
          </h3>
          <p className="text-muted-foreground text-sm">
            Les vidéos publiées renseignent trois agents qui ajustent le début de la chaîne : leçons que tu valides, idées, scripts, SEO et prompts.
          </p>
        </header>
        <div className="grid gap-2 md:grid-cols-2">
          {LEARNING_LOOP.map((step) => (
            <StepCard key={step.id} step={step} live={live} prompts={prompts} />
          ))}
        </div>
      </section>
    </div>
  );
}
