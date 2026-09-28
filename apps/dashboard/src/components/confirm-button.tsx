"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";

/** Délai minimal entre les deux clics : un double-clic ne doit jamais valider un geste destructif d'un coup. */
const MIN_CONFIRM_MS = 600;

/**
 * Bouton à deux temps pour les gestes irréversibles (arrêter, supprimer, abandonner) : le premier clic demande
 * confirmation, le second agit ; sans second clic, il revient à l'état initial après quelques secondes. Un second
 * clic trop rapproché (double-clic) est ignoré.
 */
export function ConfirmButton({
  onConfirm,
  confirmLabel = "Confirmer ?",
  children,
  ...props
}: Omit<React.ComponentProps<typeof Button>, "onClick"> & { onConfirm: () => void; confirmLabel?: React.ReactNode }) {
  const [armed, setArmed] = React.useState(false);
  const armedAt = React.useRef(0);
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  React.useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);
  return (
    <Button
      {...props}
      variant={armed ? "destructive" : props.variant}
      onClick={(event) => {
        event.stopPropagation();
        if (armed) {
          if (event.timeStamp - armedAt.current < MIN_CONFIRM_MS) return; // double-clic : on attend un vrai second clic
          if (timer.current) clearTimeout(timer.current);
          setArmed(false);
          onConfirm();
          return;
        }
        armedAt.current = event.timeStamp;
        setArmed(true);
        timer.current = setTimeout(() => setArmed(false), 4000);
      }}
    >
      {armed ? confirmLabel : children}
    </Button>
  );
}
