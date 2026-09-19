"use client";

import * as React from "react";

import { Switch } from "@/components/ui/switch";

export function AutoPublishSwitch({ id, defaultChecked }: { id: string; defaultChecked: boolean }) {
  const [checked, setChecked] = React.useState(defaultChecked);
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
      <div className="flex flex-col gap-0.5">
        <label htmlFor={id} className="text-sm font-medium">
          Publication automatique (sans validation)
        </label>
        <p className="text-muted-foreground text-xs">
          {checked
            ? "Les Shorts prêtes sont envoyées sur YouTube dès qu’un créneau est libre."
            : "Chaque Short passe en Contrôle / revue et un e-mail est envoyé à adresse@example.com."}
        </p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={setChecked} aria-label="Publication automatique" />
    </div>
  );
}
