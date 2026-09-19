import { TriangleAlert } from "lucide-react";

import { ToneBadge, type Tone } from "@/components/status-badge";
import { NOW } from "@/lib/format";
import type { ScheduleSlot, VideoStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export const SLOT_STATUS: Record<VideoStatus, { label: string; tone: Tone }> = {
  published: { label: "Publiée", tone: "success" },
  scheduled: { label: "Programmée", tone: "info" },
  ready: { label: "Prête", tone: "success" },
  uploading: { label: "Envoi en cours", tone: "running" },
  pending: { label: "Planifiée", tone: "neutral" },
  rendering: { label: "Planifiée", tone: "neutral" },
  qa: { label: "Planifiée", tone: "neutral" },
  review: { label: "Planifiée", tone: "neutral" },
  failed: { label: "Échec", tone: "danger" },
  unpublished: { label: "Dépubliée", tone: "warning" },
};

const H48 = 48 * 3_600_000;

export function SlotCell({ slot }: { slot: ScheduleSlot | undefined }) {
  if (!slot) return null;
  const at = new Date(slot.at).getTime();
  const isPast = at <= NOW.getTime();
  const soon = !isPast && at - NOW.getTime() < H48;

  if (!slot.video) {
    if (isPast) {
      return <p className="text-muted-foreground/60 text-xs">Non publié</p>;
    }
    return (
      <div
        className={cn(
          "flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-xs",
          soon
            ? "border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400"
            : "text-muted-foreground border-dashed"
        )}
      >
        {soon ? <TriangleAlert className="size-3.5 shrink-0" /> : null}
        {soon ? "Vide · sous 48 h" : "Vide"}
      </div>
    );
  }

  const status = SLOT_STATUS[slot.video.status];
  return (
    <div className="flex flex-col gap-1.5">
      <p className="line-clamp-2 text-xs leading-snug font-medium" title={slot.video.title ?? undefined}>
        {slot.video.title ?? "Sans titre"}
      </p>
      <ToneBadge tone={status.tone} className="w-fit">
        {status.label}
      </ToneBadge>
    </div>
  );
}
