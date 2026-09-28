"use client";

import * as React from "react";

import { GeminiLogo } from "@/components/gemini-logo";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatTime } from "@/lib/format";
import { GEMINI_QUOTA_NOTE, geminiEtaHours } from "@/lib/gemini-types";
import type { StoryboardScene } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Clips « première + dernière image » (chantier en accéléré, passages d'une visite) : Gemini reçoit les deux images,
 * au mieux, sans garantie de finir exactement sur la seconde (docs/17). C'est un essai, pas un refus. */
export function geminiFirstLastCount(scenes: StoryboardScene[]): number {
  return scenes.filter((s) => s.clip_mode === "flf").length;
}

/**
 * À côté de « Valider et fabriquer » : les clips sont fabriqués par Gemini en ligne (abonnement Google AI) au lieu
 * du modèle local ; voix et montage restent sur le PC (docs/17). Deux clics, car chaque clip consomme le quota.
 */
export function GeminiSendButton({
  scenes,
  disabled,
  quotaUntil,
  onSend,
  size = "sm",
}: {
  scenes: StoryboardScene[];
  disabled: boolean;
  quotaUntil?: string | null;
  onSend: () => void;
  size?: "sm" | "default";
}) {
  const [armed, setArmed] = React.useState(false);
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  React.useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);
  const clips = scenes.length;
  const firstLast = geminiFirstLastCount(scenes);
  const eta = geminiEtaHours(clips);
  const help = [
    `Fabriquer les ${clips} clips avec Gemini (en ligne) au lieu du modèle local. ${GEMINI_QUOTA_NOTE}${eta ? ` : ≈ ${eta} h pour ${clips} clips` : ""}.`,
    firstLast
      ? `Essai : ${firstLast} clip${firstLast > 1 ? "s doivent" : " doit"} finir sur l’image suivante (chantier, passages) ; Gemini reçoit l’image de départ et celle d’arrivée, sans garantie qu’il finisse exactement dessus.`
      : "",
    quotaUntil ? `Limite atteinte : reprise vers ${formatTime(quotaUntil)}.` : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex">
          <Button
            type="button"
            variant="outline"
            size={size}
            disabled={disabled}
            aria-label={armed ? `Confirmer : ${clips} clips fabriqués par Gemini` : "Fabriquer avec Gemini"}
            className={cn(armed && "border-violet-500 bg-violet-500/10 text-violet-700 hover:bg-violet-500/15 dark:text-violet-300")}
            onClick={(event) => {
              event.stopPropagation();
              if (timer.current) clearTimeout(timer.current);
              if (armed) {
                setArmed(false);
                onSend();
                return;
              }
              setArmed(true);
              timer.current = setTimeout(() => setArmed(false), 5000);
            }}
          >
            <GeminiLogo />
            {armed ? `Confirmer${firstLast ? " l’essai" : ""} : ${clips} clips → Gemini` : firstLast ? "Gemini (essai)" : "Gemini"}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-72">{help}</TooltipContent>
    </Tooltip>
  );
}
