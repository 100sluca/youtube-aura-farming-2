import { Camera, Music2, Play } from "lucide-react";

import { cn } from "@/lib/utils";

/** Repères YouTube, TikTok et Instagram (onglets du Dashboard, Calendrier, Vue d'ensemble) : une pastille rouge « lecture »,
 * une note de musique, un appareil photo sur le dégradé d'Instagram. */
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

export function InstagramMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-flex size-4 shrink-0 items-center justify-center rounded-[4px] bg-gradient-to-tr from-[#f9a825] via-[#e1306c] to-[#833ab4] text-white", className)}
    >
      <Camera className="size-2.5" />
    </span>
  );
}
