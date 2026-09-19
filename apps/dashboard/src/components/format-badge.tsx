import { Clapperboard, Mic } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { FORMAT_LABELS } from "@/lib/labels";
import type { VideoFormat } from "@/lib/types";
import { cn } from "@/lib/utils";

export function FormatBadge({ format, className }: { format: VideoFormat; className?: string }) {
  const Icon = format === "A_voiceover" ? Mic : Clapperboard;
  return (
    <Badge variant="secondary" className={cn("gap-1", className)} title={FORMAT_LABELS[format].description}>
      <Icon />
      {FORMAT_LABELS[format].short}
    </Badge>
  );
}
