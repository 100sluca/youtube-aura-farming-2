"use client";

import * as React from "react";
import { ArrowRight, CircleCheck, CircleStop, CircleX, Clapperboard, Hourglass, LoaderCircle, RefreshCw, TriangleAlert, WandSparkles } from "lucide-react";

import { approveStoryboard, pickStoryboard, redoStoryboard, reinventScene, stopRework } from "@/app/production/actions";
import { GeminiSendButton } from "@/components/create/gemini-send-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { ProductionStatus, StoryboardScene } from "@/lib/types";
import { cn } from "@/lib/utils";

export const ROLE_LABELS: Record<string, string> = {
  hook: "accroche",
  setup: "mise en place",
  reveal: "révélation",
  escalation: "montée",
  payoff: "réponse",
  loop: "boucle",
};

/** Scènes qui doivent avoir une image retenue avant de valider : celles qui en ont reçu, et les scènes réinventées
 * (elles ont toujours leur propre image, même si ses nouvelles images n'ont pas pu se faire). */
export function storyboardComplete(scenes: StoryboardScene[]): boolean {
  return scenes
    .filter((s) => !s.passage && (s.candidates.length > 0 || s.reinvented))
    .every((s) => s.candidates.some((c) => c.selected));
}

/** « 2, 9, 10 et 11 » */
export function frenchList(items: (string | number)[]): string {
  return items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} et ${items.at(-1)}`;
}

/** Ce que Création dit d'un Refaire en file ou en cours (docs/16 §3) : quels plans, en file ou en cours, pourquoi (quand
 * ce n'est pas Luca qui l'a demandé), et s'il peut être arrêté (« Arrêter » : les images affichées restent). */
export function reworkSummary(scenes: StoryboardScene[], shotNumber: Map<number, number>) {
  const busy = scenes.filter((s) => s.busy && !s.passage);
  return {
    shots: busy.map((s) => shotNumber.get(s.index) ?? s.index),
    queued: busy.length > 0 && busy.every((s) => s.busy_state === "queued"),
    reasons: [...new Set(busy.map((s) => s.busy_reason).filter((r): r is string => Boolean(r)))],
    stoppable: busy.some((s) => s.busy_job),
  };
}

/** Première porte humaine : une image par scène, à choisir puis à valider avant toute animation (modèle local, ou
 * Gemini en ligne avec le bouton Gemini, docs/17). Une scène qui ne colle pas au sujet se réinvente : le scénariste la
 * réécrit (plan, narration, texte à l'écran) raccord avec les autres, puis ses images sont refaites (docs/27). */
export function StoryboardPanel({
  productionId,
  status,
  scenes,
  geminiQuotaUntil,
}: {
  productionId: string;
  status: ProductionStatus;
  scenes: StoryboardScene[];
  geminiQuotaUntil?: string | null;
}) {
  const [pending, startTransition] = React.useTransition();
  const [notice, setNotice] = React.useState<{ ok: boolean; message: string } | null>(null);
  const [editing, setEditing] = React.useState<number | null>(null);
  const [note, setNote] = React.useState("");
  const run = (fn: () => Promise<{ ok: boolean; message: string }>) => startTransition(async () => setNotice(await fn()));
  const reviewable = status === "storyboard_review";
  const allChosen = storyboardComplete(scenes);
  const working = scenes.some((s) => s.busy);
  // Numéros = rang parmi les scènes à image (les scripts numérotent à partir de 0 ou de 1 ; les passages des visites
  // n'ont pas d'image). La liste complète reste passée au bouton Gemini, qui compte les clips.
  const shotNumber = new Map(scenes.filter((s) => !s.passage).map((s, i) => [s.index, i + 1]));
  const rework = reworkSummary(scenes, shotNumber);
  // un même Refaire couvre souvent plusieurs plans : « Arrêter » sur l'un les arrête tous, on le dit
  const jobShots = new Map<string, number[]>();
  for (const s of scenes) {
    if (s.busy_job) jobShots.set(s.busy_job, [...(jobShots.get(s.busy_job) ?? []), shotNumber.get(s.index) ?? s.index]);
  }

  const reinvent = (sceneIndex: number) => {
    const text = note;
    setEditing(null);
    setNote("");
    run(() => reinventScene(productionId, sceneIndex, text));
  };

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">Storyboard</h3>
        {reviewable ? <Badge className="bg-amber-500 text-white">à valider</Badge> : null}
      </div>
      <ul className="flex flex-col gap-3">
        {scenes.map((scene) => {
          if (scene.passage) {
            return (
              <li key={scene.index} className="text-muted-foreground flex items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-xs">
                <ArrowRight className="size-3.5 shrink-0" />
                Passage vers la pièce suivante : le clip relie la fin de la pièce précédente à l’image de la suivante, rien à choisir.
              </li>
            );
          }
          const n = shotNumber.get(scene.index);
          const chainedOnly = scene.candidates.length === 0 && scene.continues_previous && !scene.reinvented;
          const actions = !chainedOnly && (reviewable || scene.candidates.length > 0);
          const problems = scene.candidates.find((c) => c.selected)?.qc?.problems ?? [];
          return (
            <li key={scene.index} className="flex flex-col gap-2 rounded-lg border p-3">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-medium">Scène {n}</span>
                {scene.role ? <Badge variant="outline">{ROLE_LABELS[scene.role] ?? scene.role}</Badge> : null}
                {scene.continues_previous ? <Badge variant="secondary">continuité : part du clip précédent</Badge> : null}
                {scene.reinvented ? (
                  <Badge variant="secondary">
                    <WandSparkles />
                    réinventée
                  </Badge>
                ) : null}
              </div>
              {scene.narration ? <p className="text-sm leading-snug">« {scene.narration} »</p> : null}
              <p className="text-muted-foreground line-clamp-2 text-xs" title={scene.visual_prompt}>
                {scene.idea ?? scene.visual_prompt}
              </p>
              {chainedOnly ? (
                <p className="text-muted-foreground text-xs">Pas d’image : le clip enchaînera sur le précédent.</p>
              ) : !actions ? (
                <p className="text-muted-foreground text-xs">Images pas encore générées.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {scene.candidates.map((c, k) => (
                    <button
                      key={c.asset_id}
                      type="button"
                      disabled={pending}
                      onClick={() => run(() => pickStoryboard(productionId, scene.index, c.asset_id))}
                      className={cn(
                        "relative overflow-hidden rounded-md border-2 transition-colors",
                        c.selected ? "border-emerald-500" : "border-transparent hover:border-muted-foreground/40",
                      )}
                      aria-label={`Scène ${n}, image ${k + 1}${c.selected ? " (retenue)" : ""}`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={`/api/media/${c.asset_id}`} alt="" className="h-48 w-27 object-cover" loading="lazy" />
                      {c.selected ? <CircleCheck className="absolute top-1 right-1 size-4 rounded-full bg-white text-emerald-600" /> : null}
                      {c.qc && !c.qc.ok ? (
                        <TriangleAlert
                          className="absolute top-1 left-1 size-4 rounded-full bg-white p-0.5 text-amber-600"
                          aria-label={`Contrôle automatique : ${c.qc.problems.join(" ; ")}`}
                        />
                      ) : null}
                    </button>
                  ))}
                  {scene.candidates.length === 0 && !scene.busy ? (
                    <p className="text-muted-foreground self-center text-xs">Pas d’image pour l’instant : « Refaire » en demande.</p>
                  ) : null}
                  <div className="flex flex-col items-start gap-1 self-end">
                    <Button variant="ghost" size="sm" disabled={pending || Boolean(scene.busy)} onClick={() => run(() => redoStoryboard(productionId, [scene.index]))}>
                      <RefreshCw />
                      Refaire
                    </Button>
                    {reviewable ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={pending || Boolean(scene.busy)}
                        aria-expanded={editing === scene.index}
                        onClick={() => setEditing(editing === scene.index ? null : scene.index)}
                        title="Le scénariste réécrit la scène (plan, narration, texte à l’écran), raccord avec les autres, puis de nouvelles images sont faites"
                      >
                        <WandSparkles />
                        Réinventer
                      </Button>
                    ) : null}
                  </div>
                  {scene.busy ? (
                    <div className="text-muted-foreground flex w-full flex-wrap items-center gap-x-2 gap-y-1 text-xs" role="status">
                      <span className="flex items-center gap-1.5">
                        {scene.busy_state === "queued" ? <Hourglass className="size-3.5 shrink-0" /> : <LoaderCircle className="size-3.5 shrink-0 animate-spin" />}
                        {scene.busy_state === "queued"
                          ? `${scene.busy === "reinvent" ? "Réinvention" : "Nouvelles images"} en file : la carte graphique finit d’abord son calcul en cours`
                          : scene.busy === "reinvent"
                            ? "Le scénariste réinvente la scène, puis ses nouvelles images arrivent…"
                            : "Nouvelles images en cours…"}
                      </span>
                      {scene.busy_reason ? <span>Pourquoi : {scene.busy_reason}</span> : null}
                      {scene.busy_job ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 px-1.5 text-xs"
                          disabled={pending}
                          onClick={() => run(() => stopRework(productionId, scene.busy_job ?? undefined))}
                          title="Les images affichées restent et tu peux valider"
                        >
                          <CircleStop />
                          {(jobShots.get(scene.busy_job)?.length ?? 0) > 1 ? `Arrêter (plans ${frenchList(jobShots.get(scene.busy_job) ?? [])})` : "Arrêter"}
                        </Button>
                      ) : null}
                    </div>
                  ) : null}
                  {problems.length ? <p className="w-full text-xs text-amber-700 dark:text-amber-400">Contrôle automatique : {problems.join(" ; ")}</p> : null}
                  {editing === scene.index ? (
                    <form
                      className="bg-muted/40 flex w-full flex-col gap-2 rounded-md border border-dashed p-2.5"
                      onSubmit={(event) => {
                        event.preventDefault();
                        reinvent(scene.index);
                      }}
                    >
                      <label htmlFor={`reinvent-${productionId}-${scene.index}`} className="text-xs font-medium">
                        Qu’est-ce qui ne va pas ? <span className="text-muted-foreground font-normal">(facultatif)</span>
                      </label>
                      <Textarea
                        id={`reinvent-${productionId}-${scene.index}`}
                        value={note}
                        onChange={(event) => setNote(event.target.value)}
                        maxLength={500}
                        rows={2}
                        autoFocus
                        placeholder="Ex. : ce plan n’a rien à voir avec le sujet ; montrer plutôt…"
                      />
                      <p className="text-muted-foreground text-xs">
                        Le scénariste invente un autre plan pour cette scène, avec sa narration et son texte à l’écran, raccord avec les autres scènes ; ses
                        images actuelles sont remplacées.
                      </p>
                      <div className="flex flex-wrap gap-2">
                        <Button type="submit" size="sm" disabled={pending}>
                          <WandSparkles />
                          Réinventer la scène
                        </Button>
                        <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(null)}>
                          Annuler
                        </Button>
                      </div>
                    </form>
                  ) : null}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {reviewable ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            disabled={pending || !allChosen || working}
            onClick={() => run(() => approveStoryboard(productionId))}
            className="bg-emerald-600 text-white hover:bg-emerald-700 dark:bg-emerald-600 dark:hover:bg-emerald-500"
          >
            <Clapperboard />
            Valider et fabriquer la vidéo
          </Button>
          <GeminiSendButton
            scenes={scenes}
            size="default"
            disabled={pending || !allChosen || working}
            quotaUntil={geminiQuotaUntil}
            onSend={() => run(() => approveStoryboard(productionId, "gemini"))}
          />
          {working ? (
            <span className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
              {rework.stoppable
                ? `Plan${rework.shots.length > 1 ? "s" : ""} ${frenchList(rework.shots)} en train d’être refait${rework.shots.length > 1 ? "s" : ""} : valider quand ${rework.shots.length > 1 ? "ils sont arrivés" : "il est arrivé"}, ou arrêter pour garder les images affichées.`
                : "Des images sont en cours : valider quand elles sont arrivées."}
              {rework.stoppable ? (
                <Button variant="outline" size="sm" disabled={pending} onClick={() => run(() => stopRework(productionId))}>
                  <CircleStop />
                  Arrêter et garder ces images
                </Button>
              ) : null}
            </span>
          ) : !allChosen ? (
            <span className="text-muted-foreground text-xs">Choisir une image pour chaque scène.</span>
          ) : null}
        </div>
      ) : null}
      {notice ? (
        <p className={cn("flex items-center gap-1.5 text-xs", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")} role="status">
          {notice.ok ? <CircleCheck className="size-3.5" /> : <CircleX className="size-3.5" />}
          {notice.message}
        </p>
      ) : null}
    </section>
  );
}
