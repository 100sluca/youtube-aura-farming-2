"use client";

import { Star } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Étoile d'un storyboard (docs/19) : allumée, il est gardé dans Favoris avec ses images, même s'il est abandonné. */
export function FavoriteStar({
  on,
  disabled,
  onToggle,
  withLabel = false,
  className,
}: {
  on: boolean;
  disabled?: boolean;
  onToggle: () => void;
  withLabel?: boolean;
  className?: string;
}) {
  const label = on ? "Retirer des favoris" : "Garder en favori";
  return (
    <Button
      type="button"
      variant={withLabel ? "outline" : "ghost"}
      size={withLabel ? "sm" : "icon-sm"}
      disabled={disabled}
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
      aria-pressed={on}
      aria-label={label}
      title={on ? "Gardé dans Favoris : cliquer pour le retirer" : "Garder ce storyboard dans Favoris (idée, script et images)"}
      className={cn(on && "text-amber-500 hover:text-amber-600", className)}
    >
      <Star className={cn(on && "fill-current")} />
      {withLabel ? (on ? "En favori" : "Garder en favori") : null}
    </Button>
  );
}
