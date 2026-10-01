"use client";

/**
 * Corriger un plan d'une vidéo montée (Bibliothèque → Retoucher → Plans, docs/38 §6). Demande de Luca (29/09) devant
 * « Mamie Pomme » : regarder la vidéo d'une traite avec le numéro du plan affiché, puis dire en une phrase ce qui ne va
 * pas sur un plan (« c'est l'ananas qui parle, pas la mère ») et le faire refaire : son clip (le modèle vidéo refait
 * l'animation avec la consigne) et/ou sa réplique (nouvelle prise de la même voix). La vidéo est ensuite remontée avec
 * les voix recalées sur les bouches, et revient à valider.
 */
import * as React from "react";
import { Clapperboard, History, LoaderCircle, Mic, Play } from "lucide-react";

import { redoPlan } from "@/app/library/retouch-actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { formatDuration } from "@/lib/audio-mix";
import { formatDateTime } from "@/lib/format";
import type { RetouchPlan } from "@/lib/retouch-types";
import { cn } from "@/lib/utils";

type Result = { ok: boolean; message: string };

/** Le plan affiché à l'instant `t` de la vidéo montée. */
export function planAt(plans: RetouchPlan[], t: number): RetouchPlan | null {
  return plans.find((p) => t >= p.start - 0.001 && t < p.end) ?? (plans.length && t >= plans[plans.length - 1].start ? plans[plans.length - 1] : null);
}

const excerpt = (text: string, n = 42) => (text.length > n ? `${text.slice(0, n - 1).trimEnd()}…` : text);

export function PlansPanel({
  videoId,
  plans,
  now,
  locked,
  confirm,
  onSeek,
  onResult,
}: {
  videoId: string;
  plans: RetouchPlan[];
  now: number;
  locked: boolean;
  confirm?: string | null; // vidéo déjà programmée sur YouTube : question posée avant de la refaire (docs/44)
  onSeek: (t: number) => void;
  onResult: (res: Result) => void;
}) {
  const [follow, setFollow] = React.useState(true);
  const [chosen, setChosen] = React.useState<number | null>(null);
  const [note, setNote] = React.useState("");
  const [pending, startTransition] = React.useTransition();
  const current = planAt(plans, now);

  // Le plan affiché suit la tête de lecture (« Suivre la vidéo »), sauf dès qu'une consigne est en cours d'écriture :
  // elle ne doit pas partir sur un autre plan parce que la vidéo a avancé
  const picked = plans.find((p) => p.index === chosen) ?? null;
  const plan = (follow && !note.trim() ? current : (picked ?? current)) ?? plans[0];
  if (!plan) return <p className="text-muted-foreground text-sm">Pas de plans pour cette vidéo.</p>;

  const choose = (value: string) => {
    const next = plans.find((p) => String(p.index) === value);
    if (!next) return;
    setChosen(next.index);
    setNote("");
    onSeek(next.start);
  };
  const write = (value: string) => {
    if (!note.trim()) setChosen(plan.index);
    setNote(value);
  };
  const send = (clip: boolean, voice: boolean) => {
    if (confirm && !window.confirm(confirm)) return;
    startTransition(async () => {
      const res = await redoPlan(videoId, { scene: plan.index, clip, voice, note });
      onResult(res);
      if (res.ok) setNote("");
    });
  };
  const busy = locked || pending;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground text-[11px] leading-snug">
        Regarde la vidéo : le numéro du plan s’affiche dessus et ce menu le suit. Sur un plan qui ne va pas, dis en une phrase ce qu’il faut changer, puis refais
        son clip ou sa voix. La vidéo est remontée avec les voix recalées sur les bouches et revient à valider.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Select value={String(plan.index)} onValueChange={choose}>
          <SelectTrigger className="h-9 min-w-0 flex-1" aria-label="Plan">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="max-h-96">
            {plans.map((p) => (
              <SelectItem key={p.index} value={String(p.index)}>
                <span className="font-medium">Plan {p.position + 1}</span>
                <span className="text-muted-foreground text-xs">
                  {" "}
                  · {p.speaker ?? "sans réplique"}
                  {p.line ? ` · « ${excerpt(p.line)} »` : ""}
                  {p.corrections.length ? ` · ${p.corrections.length} correction${p.corrections.length > 1 ? "s" : ""}` : ""}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="flex items-center gap-2 text-xs">
          <Switch checked={follow} onCheckedChange={setFollow} aria-label="Suivre la vidéo" />
          Suivre la vidéo
        </label>
      </div>

      <section className="flex flex-col gap-3 rounded-lg border p-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant={current?.index === plan.index ? "default" : "secondary"}>Plan {plan.position + 1}</Badge>
          <span className="text-muted-foreground tabular-nums">
            {formatDuration(plan.start)} → {formatDuration(plan.end)}
          </span>
          <Button type="button" size="sm" variant="ghost" className="ml-auto h-7 px-2" onClick={() => onSeek(plan.start)}>
            <Play className="size-3.5" />
            Voir dans la vidéo
          </Button>
        </div>
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_9rem]">
          <div className="flex min-w-0 flex-col gap-1.5 text-sm">
            <p>
              <span className="text-muted-foreground">Qui parle : </span>
              <span className="font-medium">{plan.speaker ?? "personne (plan sans réplique)"}</span>
            </p>
            {plan.characters.length ? (
              <p>
                <span className="text-muted-foreground">À l’image : </span>
                {plan.characters.join(", ")}
              </p>
            ) : null}
            {plan.line ? <p className="leading-snug">« {plan.line} »</p> : null}
          </div>
          {plan.clipAssetId ? (
            <figure className="flex flex-col gap-1">
              <video
                key={plan.clipAssetId}
                src={`/api/media/${plan.clipAssetId}`}
                controls
                playsInline
                preload="metadata"
                className="aspect-[9/16] w-full rounded-md bg-black object-contain"
              />
              <figcaption className="text-muted-foreground text-[10px] leading-tight">Le clip brut, avec la voix du modèle vidéo : on voit quelle bouche bouge.</figcaption>
            </figure>
          ) : null}
        </div>

        <Textarea
          rows={2}
          value={note}
          disabled={busy}
          maxLength={600}
          onChange={(e) => write(e.target.value)}
          placeholder="Ta consigne pour ce plan. Ex. : c’est l’ananas qui parle, pas la mère : la mère se tait."
          aria-label="Consigne pour ce plan"
          className="text-sm"
        />
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => send(true, false)} disabled={busy}>
            {pending ? <LoaderCircle className="animate-spin" /> : <Clapperboard />}
            Refaire le clip
          </Button>
          <Button variant="outline" onClick={() => send(false, true)} disabled={busy || !plan.line}>
            <Mic />
            Nouvelle prise de voix
          </Button>
        </div>
        <p className="text-muted-foreground text-[11px] leading-snug">
          <strong>Refaire le clip</strong> : le modèle vidéo refait l’animation du plan avec ta consigne (qui parle, qui se tait, gestes, regard), ≈ 7 min sur la carte
          graphique, puis la voix est recalée sur la bouche. <strong>Nouvelle prise de voix</strong> : la même voix redit la réplique autrement ; ta consigne peut demander
          un autre débit ou une prononciation (« dis A-pi »), pas une émotion. Dans les deux cas la vidéo est remontée et revient à valider.
        </p>
      </section>

      {plan.corrections.length ? (
        <section className="flex flex-col gap-1.5">
          <h4 className="flex items-center gap-1.5 text-xs font-semibold">
            <History className="size-3.5" />
            Déjà demandé sur ce plan
          </h4>
          <ol className="flex flex-col gap-1 text-xs">
            {[...plan.corrections].reverse().map((c, i) => (
              <li key={`${c.at}-${i}`} className="text-muted-foreground flex flex-wrap gap-x-2">
                <span className="tabular-nums">{c.at ? formatDateTime(c.at) : ""}</span>
                <span className="text-foreground">{[c.clip ? "clip" : "", c.voice ? "voix" : ""].filter(Boolean).join(" + ")}</span>
                {c.note ? <span className="min-w-0 break-words">« {c.note} »</span> : <span>sans consigne</span>}
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}

/** Le repère posé sur la vidéo : le plan à l'écran et qui parle. */
export function PlanBadge({ plan }: { plan: RetouchPlan | null }) {
  if (!plan) return null;
  return (
    <div
      className={cn(
        "pointer-events-none absolute top-2 left-2 z-10 flex max-w-[85%] items-center gap-1 rounded-md bg-black/70 px-2 py-1 text-[11px] font-medium text-white",
      )}
      aria-live="off"
    >
      <span>Plan {plan.position + 1}</span>
      {plan.speaker ? <span className="truncate font-normal opacity-80">· {plan.speaker}</span> : null}
    </div>
  );
}

