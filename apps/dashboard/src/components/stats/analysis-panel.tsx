"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Brain, Check, CircleCheck, CircleX, FlaskConical, Lightbulb, Loader2, Pencil, Sparkles, ThumbsDown, ThumbsUp, X } from "lucide-react";

import { decideLesson, runAnalysis } from "@/app/dashboard/actions";
import type { ActionResult } from "@/app/production/actions";
import { VERDICT_TONES } from "@/components/stats/stats-table";
import { ToneBadge, type Tone } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime, formatNumber } from "@/lib/format";
import { LESSON_TARGET_LABELS, RECIPE_LABELS, VERDICT_LABELS, type Lesson, type StatsPage, type Verdict } from "@/lib/stats-types";
import { cn } from "@/lib/utils";

const CONFIDENCE_TONES: Record<string, Tone> = { faible: "neutral", moyenne: "info", bonne: "success" };

function ConfidenceBadge({ value }: { value: string }) {
  return (
    <ToneBadge tone={CONFIDENCE_TONES[value] ?? "neutral"} className="px-1.5 py-0 text-[11px]">
      confiance {value}
    </ToneBadge>
  );
}

function Notice({ notice }: { notice: ActionResult | null }) {
  if (!notice) return null;
  return (
    <p className={cn("flex items-center gap-1.5 text-xs", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")} role="status">
      {notice.ok ? <CircleCheck className="size-3.5" /> : <CircleX className="size-3.5" />}
      {notice.message}
    </p>
  );
}

/** Une leçon proposée : ✓ la donne aux agents (texte modifiable avant), ✗ l'écarte. */
function ProposedLesson({ lesson, onDone }: { lesson: Lesson; onDone: (n: ActionResult) => void }) {
  const [editing, setEditing] = React.useState(false);
  const [text, setText] = React.useState(lesson.rule);
  const [pending, startTransition] = React.useTransition();
  const decide = (decision: "active" | "rejected") =>
    startTransition(async () => onDone(await decideLesson(lesson.id, decision, decision === "active" && text !== lesson.rule ? text : undefined)));
  return (
    <li className="flex flex-col gap-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <ToneBadge tone={lesson.target === "production" ? "warning" : "running"} className="px-1.5 py-0 text-[11px]">
          {LESSON_TARGET_LABELS[lesson.target]}
        </ToneBadge>
        {lesson.recipe ? (
          <ToneBadge tone="neutral" className="px-1.5 py-0 text-[11px]">
            {RECIPE_LABELS[lesson.recipe] ?? lesson.recipe}
          </ToneBadge>
        ) : null}
        <ConfidenceBadge value={lesson.confidence} />
      </div>
      {editing ? (
        <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} className="text-sm" aria-label="Texte de la leçon" />
      ) : (
        <p className="text-sm font-medium">{text}</p>
      )}
      {lesson.why ? <p className="text-muted-foreground text-xs">Pourquoi : {lesson.why}</p> : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={pending || text.trim().length < 3} onClick={() => decide("active")}>
          {pending ? <Loader2 className="animate-spin" /> : <Check />}
          {lesson.target === "production" ? "Noter" : "Valider"}
        </Button>
        <Button size="sm" variant="outline" disabled={pending} onClick={() => decide("rejected")}>
          <X />
          Écarter
        </Button>
        {!editing ? (
          <Button size="sm" variant="ghost" disabled={pending} onClick={() => setEditing(true)}>
            <Pencil />
            Modifier
          </Button>
        ) : null}
      </div>
    </li>
  );
}

const VERDICT_ORDER: Verdict[] = ["top", "moyen", "flop", "trop récente"];

/** « Ce qui marche, et pourquoi » : le dernier rapport de l'agent analyste et ses leçons à valider. */
export function AnalysisPanel({ analysis }: { analysis: StatsPage["analysis"] }) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [notice, setNotice] = React.useState<ActionResult | null>(null);
  const report = analysis.report;
  const running = pending || analysis.running;
  const done = (n: ActionResult) => {
    setNotice(n);
    router.refresh();
  };

  return (
    <Card id="analyse" className="scroll-mt-20">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Brain className="size-5 text-violet-600 dark:text-violet-300" />
          Ce qui marche, et pourquoi
        </CardTitle>
        <CardDescription>
          L’agent analyste compare les vidéos qui marchent et les autres (accroche, titre, rythme des plans, format, voix, hashtags, heure…) et en tire des
          leçons. Celles que tu valides sont données à l’agent idées, aux scénaristes et à l’agent SEO pour les prochaines vidéos.
        </CardDescription>
        <CardAction>
          <Button
            size="sm"
            variant="outline"
            disabled={running || !analysis.channel_id}
            onClick={() => startTransition(async () => done(await runAnalysis(analysis.channel_id!)))}
          >
            {running ? <Loader2 className="animate-spin" /> : <Sparkles />}
            {running ? "Analyse en cours…" : "Analyser maintenant"}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <Notice notice={notice} />
        {!report ? (
          <p className="text-muted-foreground text-sm">
            {analysis.channel_id
              ? "Pas encore d’analyse : clique « Analyser maintenant » (elle tourne aussi chaque dimanche à 5 h)."
              : "Connecte une chaîne YouTube (Réglages → Chaînes) pour analyser ses vidéos."}
          </p>
        ) : (
          <>
            <p className="text-muted-foreground text-xs">
              Analyse du {formatDateTime(report.created_at)} · {formatNumber(report.videos)} vidéo{report.videos > 1 ? "s" : ""}, dont {formatNumber(report.judged)} jugée
              {report.judged > 1 ? "s" : ""} (plus de 24 h){report.median_views !== null ? ` · médiane ${formatNumber(report.median_views)} vues` : ""}
            </p>
            {report.summary ? (
              <p className="text-base leading-relaxed">{report.summary}</p>
            ) : (
              <p className="text-muted-foreground text-sm">Pas encore assez de vidéos pour comparer : il en faut au moins deux publiées depuis plus de 24 h.</p>
            )}

            {report.diagnoses.length ? (
              <section className="grid gap-3 md:grid-cols-2">
                {VERDICT_ORDER.flatMap((verdict) => report.diagnoses.filter((d) => d.verdict === verdict)).map((d) => (
                  <article key={d.video_id} className="flex flex-col gap-2 rounded-lg border p-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="line-clamp-2 text-sm font-medium">{d.title}</p>
                      <ToneBadge tone={VERDICT_TONES[d.verdict]} className="shrink-0">
                        {VERDICT_LABELS[d.verdict]}
                        {d.score !== null && d.verdict !== "trop récente" ? ` ×${formatNumber(d.score, d.score >= 10 ? 0 : 2)}` : ""}
                      </ToneBadge>
                    </div>
                    <p className="text-sm">{d.why}</p>
                    {d.worked.length ? (
                      <ul className="flex flex-col gap-1 text-xs">
                        {d.worked.map((w) => (
                          <li key={w} className="flex gap-1.5">
                            <ThumbsUp className="mt-0.5 size-3 shrink-0 text-emerald-600 dark:text-emerald-400" />
                            {w}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    {d.missed.length ? (
                      <ul className="flex flex-col gap-1 text-xs">
                        {d.missed.map((m) => (
                          <li key={m} className="flex gap-1.5">
                            <ThumbsDown className="mt-0.5 size-3 shrink-0 text-red-600 dark:text-red-400" />
                            {m}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </article>
                ))}
              </section>
            ) : null}

            {report.patterns.length ? (
              <section className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold">Ce qui distingue les vidéos qui marchent</h3>
                <ul className="flex flex-col gap-2">
                  {report.patterns.map((p) => (
                    <li key={p.finding} className="flex gap-2 text-sm">
                      <Lightbulb className="mt-0.5 size-3.5 shrink-0 text-amber-600 dark:text-amber-400" />
                      <div className="flex flex-col gap-1">
                        <p>
                          {p.finding} <ConfidenceBadge value={p.confidence} />
                        </p>
                        {p.evidence ? <p className="text-muted-foreground text-xs">{p.evidence}</p> : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </>
        )}

        {analysis.proposed.length ? (
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Leçons à valider ({analysis.proposed.length})</h3>
            <p className="text-muted-foreground text-xs">
              ✓ : l’agent visé la reçoit à chaque tâche, dès maintenant. ✗ : elle est écartée. Tu peux corriger le texte avant de valider. Une nouvelle
              analyse remplace les leçons encore en attente.
            </p>
            <ul className="grid gap-3 lg:grid-cols-2">
              {analysis.proposed.map((l) => (
                <ProposedLesson key={l.id} lesson={l} onDone={done} />
              ))}
            </ul>
          </section>
        ) : null}

        {analysis.active.length ? (
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Leçons en service ({analysis.active.length})</h3>
            <ul className="divide-y rounded-lg border">
              {analysis.active.map((l) => (
                <ActiveLesson key={l.id} lesson={l} onDone={done} />
              ))}
            </ul>
          </section>
        ) : null}

        {report?.experiments.length ? (
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Expériences à mener</h3>
            <ul className="flex flex-col gap-2">
              {report.experiments.map((e) => (
                <li key={e.hypothesis} className="flex gap-2 text-sm">
                  <FlaskConical className="mt-0.5 size-3.5 shrink-0 text-sky-600 dark:text-sky-400" />
                  <span>
                    {e.hypothesis}
                    {e.test ? <span className="text-muted-foreground"> — {e.test}</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ActiveLesson({ lesson, onDone }: { lesson: Lesson; onDone: (n: ActionResult) => void }) {
  const [pending, startTransition] = React.useTransition();
  return (
    <li className="flex flex-wrap items-center gap-3 p-3">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <ToneBadge tone={lesson.target === "production" ? "warning" : "running"} className="px-1.5 py-0 text-[11px]">
            {LESSON_TARGET_LABELS[lesson.target]}
          </ToneBadge>
          {lesson.recipe ? (
            <ToneBadge tone="neutral" className="px-1.5 py-0 text-[11px]">
              {RECIPE_LABELS[lesson.recipe] ?? lesson.recipe}
            </ToneBadge>
          ) : null}
        </div>
        <p className="text-sm">{lesson.rule}</p>
      </div>
      <Button size="sm" variant="ghost" disabled={pending} onClick={() => startTransition(async () => onDone(await decideLesson(lesson.id, "retired")))}>
        {pending ? <Loader2 className="animate-spin" /> : <X />}
        Retirer
      </Button>
    </li>
  );
}
