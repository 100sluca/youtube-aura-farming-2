import { Badge } from "@/components/ui/badge";
import { CHANNEL_LABELS } from "@/lib/labels";
import type { ChannelLang } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ChannelBadge({ lang, className }: { lang: ChannelLang; className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "font-semibold tracking-wide",
        lang === "fr" ? "border-chart-1/50 text-chart-1" : "border-chart-2/50 text-chart-2",
        className
      )}
    >
      {CHANNEL_LABELS[lang]}
    </Badge>
  );
}
