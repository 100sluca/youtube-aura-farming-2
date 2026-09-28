"use client";

import * as React from "react";

import { setAutoPublish } from "@/app/settings/actions";
import { Switch } from "@/components/ui/switch";

export function AutoPublishSwitch({ id, slug, defaultChecked }: { id: string; slug: string; defaultChecked: boolean }) {
  const [checked, setChecked] = React.useState(defaultChecked);
  const [pending, startTransition] = React.useTransition();
  const [message, setMessage] = React.useState<string | null>(null);
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
      <div className="flex flex-col gap-0.5">
        <label htmlFor={id} className="text-sm font-medium">
          Publication automatique (sans validation)
        </label>
        <p className="text-muted-foreground text-xs">
          {checked
            ? "Les Shorts prêtes sont envoyées sur YouTube dès qu’un créneau est libre."
            : "Chaque Short attend ton autorisation dans la Bibliothèque (filtre « À valider »)."}
        </p>
        {message ? <p className="text-xs text-emerald-600 dark:text-emerald-400">{message}</p> : null}
      </div>
      <Switch
        id={id}
        checked={checked}
        disabled={pending}
        onCheckedChange={(value) => {
          setChecked(value);
          startTransition(async () => {
            const res = await setAutoPublish(slug, value);
            setMessage(res.message);
            if (!res.ok) setChecked(!value);
          });
        }}
        aria-label="Publication automatique"
      />
    </div>
  );
}
