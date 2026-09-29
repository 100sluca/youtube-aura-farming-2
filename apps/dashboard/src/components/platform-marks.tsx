import { Music2, Play } from "lucide-react";

import { cn } from "@/lib/utils";

/** Repères YouTube et TikTok (onglets du Dashboard, Calendrier) : une pastille rouge « lecture », une note de musique. */
export function YouTubeMark({ className }: { className?: string }) {
  return (
    <span aria-hidden className={cn("inline-flex size-4 shrink-0 items-center justify-center rounded-[4px] bg-[#e62117] text-white", className)}>
      <Play className="size-2.5 fill-current" />
    </span>
  );
}

export function TikTokMark({ className }: { className?: string }) {
  return (
    <span aria-hidden className={cn("inline-flex size-4 shrink-0 items-center justify-center rounded-[4px] bg-foreground text-background", className)}>
      <Music2 className="size-2.5" />
    </span>
  );
}
