"use client";

import * as React from "react";
import { ArrowRight, Check, CircleStop, Eye, Hourglass, Link2, LoaderCircle, TriangleAlert, X } from "lucide-react";

import { stopRework } from "@/app/production/actions";
import { ConfirmButton } from "@/components/confirm-button";
import { GeminiSendButton } from "@/components/create/gemini-send-button";
import { FavoriteStar } from "@/components/favorites/favorite-star";
import { CharacterStrip } from "@/components/create/character-strip";
import { StoryboardPanel, frenchList, reworkSummary, storyboardComplete } from "@/components/production/storyboard-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { formatRelative, formatTime } from "@/lib/format";
import type { ProductionCard } from "@/lib/types";

/** Planche d'un storyboard prêt : une image par scène ; ✓ lance la fabrication d'une traite, ✗ abandonne la vidéo,
 * Gemini fait fabriquer les clips par Gemini en ligne au lieu du modèle local (docs/17), l'étoile le garde dans
 * Favoris avec ses images, même abandonné (docs/19). */
export function StoryboardReviewCard({
  card,
  disabled,
  favorite,
  geminiQuotaUntil,
  onOpen,
  onApprove,
  onGemini,
  onAbandon,
  onToggleFavorite,
}: {
  card: ProductionCard;
  disabled: boolean;
  favorite: boolean;
  geminiQuotaUntil?: string | null;
  onOpen: () => void;
  onApprove: () => void;
  onGemini: () => void;
  onAbandon: () => void;
  onToggleFavorite: () => void;
}) {
  const scenes = card.storyboard ?? [];
  // Les passages (visites) relient deux pièces sans image propre : on ne les numérote pas et on les montre en flèche
  const shots = scenes.filter((s) => !s.passage);
  const shotNumber = new Map(shots.map((s, i) => [s.index, i + 1]));
  const passages = scenes.length - shots.length;
  const allChosen = storyboardComplete(scenes);
  const working = scenes.some((s) => s.busy); // Refaire ou Réinventer en cours : valider attendrait l'ancienne image
  const rework = reworkSummary(scenes, shotNumber);
  const problems = shots.flatMap((s) =>
    (s.candidates.find((c) => c.selected)?.qc?.problems ?? []).map((p) => `Scène ${shotNumber.get(s.index)} : ${p}`),
  );
  return (
    <li className="bg-card flex min-w-0 flex-col gap-3 rounded-xl border p-4 shadow-xs">
      <div className="flex flex-wrap items-start gap-2">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h3 className="leading-snug font-semibold">{card.concept?.title ?? "Vidéo sans titre"}</h3>
          {/* « prêt il y a 24 secondes » : l'heure relative change entre le rendu serveur et le navigateur */}
          <p className="text-muted-foreground text-xs" suppressHydrationWarning>
            {[
              card.production.series_name,
              `${shots.length} scènes${passages ? ` · ${passages} passages` : ""}`,
              `prêt ${formatRelative(card.production.updated_at)}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <Badge className="bg-amber-500 text-white">à regarder</Badge>
        <FavoriteStar on={favorite} disabled={disabled} onToggle={onToggleFavorite} className="-my-1.5 -mr-2" />
      </div>

      <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
        {scenes.map((scene) => {
          if (scene.passage) {
            return (
              <span
                key={scene.index}
                className="text-muted-foreground flex w-5 shrink-0 items-center justify-center"
                title="Passage vers la pièce suivante : le clip relie deux images, rien à choisir"
                aria-label="passage vers la pièce suivante"
              >
                <ArrowRight className="size-4" />
              </span>
            );
          }
          const pick = scene.candidates.find((c) => c.selected) ?? scene.candidates[0];
          return (
            <button
              key={scene.index}
              type="button"
              onClick={onOpen}
              className="group relative h-40 w-[5.625rem] shrink-0 overflow-hidden rounded-md border"
              aria-label={`Scène ${shotNumber.get(scene.index)}`}
            >
              {pick ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={`/api/media/${pick.asset_id}`} alt="" className="size-full object-cover transition-transform group-hover:scale-105" loading="lazy" />
              ) : (
                <span className="bg-muted text-muted-foreground flex size-full flex-col items-center justify-center gap-1 p-1 text-center text-[10px]">
                  <Link2 className="size-4" />
                  {scene.continues_previous ? "suite du clip précédent" : "pas d’image"}
                </span>
              )}
              <span className="absolute bottom-1 left-1 rounded bg-black/60 px-1 text-[10px] font-medium text-white tabular-nums">{shotNumber.get(scene.index)}</span>
              {pick?.qc && !pick.qc.ok ? <TriangleAlert className="absolute top-1 right-1 size-4 rounded-full bg-white p-0.5 text-amber-600" /> : null}
              {scene.busy ? (
                <span
                  className="absolute inset-0 flex items-center justify-center bg-black/45 text-white"
                  title={scene.busy === "reinvent" ? "Scène en cours de réinvention" : "Nouvelles images en cours"}
                >
                  <LoaderCircle className="size-5 animate-spin" />
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      {problems.length > 0 ? (
        <div className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
          <ul className="flex flex-col gap-0.5">
            {problems.slice(0, 4).map((p) => (
              <li key={p}>{p}</li>
            ))}
            {problems.length > 4 ? <li>… et {problems.length - 4} autre(s)</li> : null}
          </ul>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={onOpen}>
          <Eye />
          Regarder et choisir
        </Button>
        <ConfirmButton
          variant="ghost"
          size="sm"
          disabled={disabled}
          onConfirm={onAbandon}
          confirmLabel={favorite ? "Confirmer l’abandon (le favori reste)" : "Confirmer l’abandon"}
        >
          <X />
          Abandonner
        </ConfirmButton>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <GeminiSendButton scenes={scenes} disabled={disabled || !allChosen || working} quotaUntil={geminiQuotaUntil} onSend={onGemini} />
          <Button
            size="sm"
            disabled={disabled || !allChosen || working}
            onClick={onApprove}
            className="bg-emerald-600 text-white hover:bg-emerald-700 dark:bg-emerald-600 dark:hover:bg-emerald-500"
          >
            <Check />
            Valider et fabriquer
          </Button>
        </div>
      </div>
      {working ? (
        <div className="text-muted-foreground -mt-1 flex flex-wrap items-center justify-end gap-x-2 gap-y-1 text-right text-xs" role="status">
          {rework.queued ? <Hourglass className="size-3.5 shrink-0" /> : <LoaderCircle className="size-3.5 shrink-0 animate-spin" />}
          <span>
            {`Plan${rework.shots.length > 1 ? "s" : ""} ${frenchList(rework.shots)} : nouvelles images ${rework.queued ? "en file (la carte graphique finit d’abord son calcul en cours)" : "en cours"}`}
            {rework.reasons.length ? ` · pourquoi : ${rework.reasons.join(" ; ")}` : ""}
          </span>
          {rework.stoppable ? <StopReworkButton productionId={card.production.id} /> : null}
        </div>
      ) : null}
      {geminiQuotaUntil ? (
        <p className="text-muted-foreground -mt-1 text-right text-xs">Limite Gemini atteinte : les clips Gemini reprendront vers {formatTime(geminiQuotaUntil)}.</p>
      ) : null}
    </li>
  );
}

/** « Arrêter » les Refaire de ce storyboard (docs/16 §3) : les images affichées restent et « Valider » se débloque. */
function StopReworkButton({ productionId }: { productionId: string }) {
  const [pending, startTransition] = React.useTransition();
  const [message, setMessage] = React.useState<string | null>(null);
  if (message) return <span>{message}</span>;
  return (
    <Button
      variant="outline"
      size="sm"
      className="h-7 text-xs"
      disabled={pending}
      onClick={() => startTransition(async () => setMessage((await stopRework(productionId)).message))}
    >
      <CircleStop />
      Arrêter et garder ces images
    </Button>
  );
}

/** Le storyboard en grand : choisir une autre image, refaire une scène, le garder en favori, puis valider. */
export function StoryboardSheet({
  card,
  favorite,
  disabled,
  geminiQuotaUntil,
  onClose,
  onToggleFavorite,
}: {
  card: ProductionCard | null;
  favorite: boolean;
  disabled: boolean;
  geminiQuotaUntil?: string | null;
  onClose: () => void;
  onToggleFavorite: () => void;
}) {
  return (
    <Sheet
      open={card !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-3xl">
        {card ? (
          <>
            <SheetHeader className="border-b pr-12">
              <div className="flex items-start gap-2">
                <SheetTitle className="flex-1 leading-snug">{card.concept?.title ?? "Storyboard"}</SheetTitle>
                <FavoriteStar on={favorite} disabled={disabled} onToggle={onToggleFavorite} withLabel className="-my-1 shrink-0" />
              </div>
              <SheetDescription>
                Une image par scène : clique sur une autre image pour la retenir, « Refaire » en génère de nouvelles, « Réinventer » fait réécrire une scène
                hors sujet (autre plan, narration raccord, nouvelles images). Le bouton vert lance les clips, la voix et le montage d’une traite ; le bouton
                Gemini fait fabriquer les clips par Gemini en ligne. L’étoile le garde dans Favoris, images comprises.
              </SheetDescription>
            </SheetHeader>
            <ScrollArea className="min-h-0 flex-1">
              <div className="flex flex-col gap-6 p-4">
                {card.characters?.length ? (
                  <CharacterStrip productionId={card.production.id} status={card.production.status} characters={card.characters} />
                ) : null}
                <StoryboardPanel
                  productionId={card.production.id}
                  status={card.production.status}
                  scenes={card.storyboard ?? []}
                  geminiQuotaUntil={geminiQuotaUntil}
                />
              </div>
            </ScrollArea>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
