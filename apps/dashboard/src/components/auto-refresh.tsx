"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

/** Recharge les données serveur de la page à intervalle régulier (onglet visible seulement), comme le suivi de MJClipIt. */
export function AutoRefresh({ seconds = 5 }: { seconds?: number }) {
  const router = useRouter();
  React.useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") router.refresh();
    }, seconds * 1000);
    return () => clearInterval(timer);
  }, [router, seconds]);
  return null;
}
