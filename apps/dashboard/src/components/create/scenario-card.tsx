"use client";

import * as React from "react";
import Link from "next/link";
import { CircleCheck, CircleX, Clapperboard, Eye, LoaderCircle, RotateCcw, Send } from "lucide-react";

import { relaunchScenario, submitScenario } from "@/app/create/scenario-actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  SCENARIO_DURATIONS,
  SCENARIO_SPEECH,
  SCENARIO_STYLES,
  type ScenarioItem,
  type ScenarioSpeech,
  type ScenarioStyle,
} from "@/lib/scenario-types";
import { cn } from "@/lib/utils";

const STAGE: Record<string, string> = {
  draft: "en file",
  scripting: "l’équipe écrit",
  generating: "images et clips",
  storyboard_review: "storyboard à valider",
  assembling: "montage",
  ready: "prête",
  failed: "ratée",
  cancelled: "arrêtée",
  archived: "archivée",
};

const STYLE_LABEL = Object.fromEntries(SCENARIO_STYLES.map((s) => [s.value, s.label])) as Record<string, string>;
const SPEECH_LABEL = Object.fromEntries(SCENARIO_SPEECH.map((s) => [s.value, s.label])) as Record<string, string>;

const PLACEHOLDER =
  "Ex. : un chien immobile sur le canapé suit son maître des yeux. Le maître range son gâteau au frigo et s’en va. Dès qu’il a le dos tourné, le chien ouvre le frigo, croque dans le gâteau, cache les indices et retourne sur le canapé dans la même pose…";

type Notice = { ok: boolean; message: string };

/**
 * Mon scénario (docs/59) : Luca écrit une idée ou un scénario libre ; une équipe d'agents (metteur en scène, scénariste,
 * relecteur de fidélité) le met en forme, puis le storyboard arrive dans Création, à valider comme les autres. Dessous,
 * ses derniers scénarios : où en est chacun, et ce que l'équipe en a compris.
 */
export function ScenarioCard({ channelId, channelName, items }: { channelId: string; channelName: string; items: ScenarioItem[] }) {
  const [pending, startTransition] = React.useTransition();
  const [text, setText] = React.useState("");
  const [title, setTitle] = React.useState("");
  const [style, setStyle] = React.useState<ScenarioStyle>("auto");
  const [speech, setSpeech] = React.useState<ScenarioSpeech>("auto");
  const [duration, setDuration] = React.useState<number>(0);
  const [notice, setNotice] = React.useState<Notice | null>(null);
  const tooShort = text.trim().length < 20;

  const submit = () =>
    startTransition(async () => {
      const res = await submitScenario(channelId, { text, title, style, speech, durationS: duration });
      setNotice(res);
      if (res.ok) {
        setText("");
        setTitle("");
      }
    });

  const relaunch = (conceptId: string) =>
    startTransition(async () => {
      setNotice(await relaunchScenario(conceptId, channelId));
    });

  return (
    <Card className="py-5">
      <CardContent className="flex flex-col gap-4">
        <div className="flex items-start gap-3">
          <Clapperboard className="text-muted-foreground mt-0.5 size-5 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="font-medium">Mon scénario</p>
            <p className="text-muted-foreground text-sm">
              Écris ton idée avec tes mots. L’équipe (metteur en scène, scénariste, relecteur) la met en forme sans la trahir : personnages, plans, style ;
              puis le storyboard arrive ici, à valider comme les autres. Pour « {channelName} ».
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={PLACEHOLDER}
            rows={6}
            className="min-h-32 resize-y"
            aria-label="Ton scénario"
            disabled={pending}
          />
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)_auto_auto] xl:items-end">
            <Field label="Titre (facultatif)">
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="L’équipe en trouve un" maxLength={80} disabled={pending} />
            </Field>
            <Field label="Style">
              <Select value={style} onValueChange={(v) => setStyle(v as ScenarioStyle)}>
                <SelectTrigger className="w-full" aria-label="Style visuel">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SCENARIO_STYLES.map((s) => (
                    <SelectItem key={s.value} value={s.value}>
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Paroles">
              <Select value={speech} onValueChange={(v) => setSpeech(v as ScenarioSpeech)}>
                <SelectTrigger className="w-full" aria-label="Paroles">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SCENARIO_SPEECH.map((s) => (
                    <SelectItem key={s.value} value={s.value}>
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Durée">
              <div className="bg-muted inline-flex rounded-lg p-0.5" role="radiogroup" aria-label="Durée">
                {SCENARIO_DURATIONS.map((d) => (
                  <button
                    key={d}
                    type="button"
                    role="radio"
                    aria-checked={duration === d}
                    onClick={() => setDuration(d)}
                    className={cn(
                      "h-8 rounded-md px-2.5 text-sm font-medium tabular-nums transition-colors",
                      duration === d ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {d === 0 ? "Auto" : `${d} s`}
                  </button>
                ))}
              </div>
            </Field>
            <Button disabled={pending || tooShort} onClick={submit}>
              {pending ? <LoaderCircle className="animate-spin" /> : <Send />}
              Confier à l’équipe
            </Button>
          </div>
        </div>

        {notice ? <p className={cn("text-sm", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")}>{notice.message}</p> : null}

        {items.length > 0 ? (
          <ul className="flex flex-col divide-y rounded-xl border">
            {items.map((item) => (
              <ScenarioRow key={item.conceptId} item={item} disabled={pending} onRelaunch={() => relaunch(item.conceptId)} />
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <span className="text-muted-foreground text-xs font-medium">{label}</span>
      {children}
    </div>
  );
}

function ScenarioRow({ item, disabled, onRelaunch }: { item: ScenarioItem; disabled: boolean; onRelaunch: () => void }) {
  const status = item.status ?? "draft";
  const done = status === "ready" || status === "archived";
  const broken = status === "failed" || status === "cancelled";
  const plan = item.plan;
  return (
    <li className="flex flex-col gap-2 px-4 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {done ? (
          <CircleCheck className="size-4 shrink-0 text-emerald-500" />
        ) : broken ? (
          <CircleX className="text-destructive size-4 shrink-0" />
        ) : status === "storyboard_review" ? (
          <Eye className="size-4 shrink-0 text-amber-500" />
        ) : (
          <LoaderCircle className="text-muted-foreground size-4 shrink-0 animate-spin" />
        )}
        <span className="min-w-0 flex-1 truncate font-medium">{item.title}</span>
        <span className="text-muted-foreground shrink-0 text-xs">{STAGE[status] ?? status}</span>
        {status === "storyboard_review" ? (
          <Button asChild variant="outline" size="sm">
            <a href="#storyboards">Regarder</a>
          </Button>
        ) : null}
        {item.videoId && (done || status === "assembling") ? (
          <Button asChild variant="outline" size="sm">
            <Link href={`/library?video=${item.videoId}`}>Bibliothèque</Link>
          </Button>
        ) : null}
        {broken || !item.productionId ? (
          <Button variant="outline" size="sm" disabled={disabled} onClick={onRelaunch}>
            <RotateCcw />
            Relancer
          </Button>
        ) : null}
      </div>
      {broken && item.error ? <p className="text-destructive text-xs">{item.error}</p> : null}
      <details className="group">
        <summary className="text-muted-foreground hover:text-foreground cursor-pointer text-xs">
          {plan ? "Ce que l’équipe a compris" : "Ton scénario"}
        </summary>
        <div className="mt-2 flex flex-col gap-3 text-xs leading-relaxed">
          {plan ? (
            <>
              {plan.logline ? <p className="text-sm">{plan.logline}</p> : null}
              <p className="text-muted-foreground">
                {[plan.genre, plan.style ? STYLE_LABEL[plan.style] ?? plan.style : null, plan.speech ? SPEECH_LABEL[plan.speech] ?? plan.speech : null, plan.duration_s ? `${plan.duration_s} s` : null]
                  .filter(Boolean)
                  .join(" · ")}
                {plan.hook_title ? ` · titre d’accroche : « ${plan.hook_title} »` : ""}
              </p>
              {plan.cast?.length ? (
                <div>
                  <p className="font-medium">Personnages</p>
                  <ul className="text-muted-foreground list-disc pl-4">
                    {plan.cast.map((m) => (
                      <li key={m.key}>
                        <span className="text-foreground">{m.name}</span>
                        {m.role ? ` · ${m.role}` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {plan.beats?.length ? (
                <div>
                  <p className="font-medium">L’histoire, temps par temps</p>
                  <ol className="list-decimal pl-4">
                    {plan.beats.map((b, k) => (
                      <li key={k}>
                        {b.what}
                        {b.from_text ? <span className="text-muted-foreground"> · « {b.from_text} »</span> : <span className="text-muted-foreground"> · ajouté par l’équipe</span>}
                      </li>
                    ))}
                  </ol>
                </div>
              ) : null}
              {plan.choices?.length ? (
                <div>
                  <p className="font-medium">Ce que l’équipe a décidé</p>
                  <ul className="text-muted-foreground list-disc pl-4">
                    {plan.choices.map((c, k) => (
                      <li key={k}>{c}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {plan.risks?.length ? (
                <div>
                  <p className="font-medium">Points délicats à filmer</p>
                  <ul className="text-muted-foreground list-disc pl-4">
                    {plan.risks.map((r, k) => (
                      <li key={k}>{r}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          ) : null}
          <div>
            {plan ? <p className="font-medium">Ton texte</p> : null}
            <p className="text-muted-foreground whitespace-pre-line">{item.text}</p>
          </div>
        </div>
      </details>
    </li>
  );
}
