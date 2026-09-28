import {
  Brain,
  Clapperboard,
  ClipboardCheck,
  Hammer,
  House,
  Lightbulb,
  ScanEye,
  ScrollText,
  Search,
  TrendingUp,
  WandSparkles,
  type LucideIcon,
} from "lucide-react";

import type { AgentIcon as AgentIconName } from "@/lib/agent-catalog";
import { cn } from "@/lib/utils";

export const AGENT_ICONS: Record<AgentIconName, LucideIcon> = {
  idea: Lightbulb,
  story: ScrollText,
  review: ClipboardCheck,
  timelapse: Hammer,
  tour: House,
  seo: Search,
  strategy: TrendingUp,
  improve: WandSparkles,
  analyst: Brain,
  keyframe: ScanEye,
  clip: Clapperboard,
};

/** Pastille d'un agent : son icône sur fond violet (couleur des agents IA dans la chaîne de production). */
export function AgentBadgeIcon({ icon, className }: { icon: AgentIconName; className?: string }) {
  const Icon = AGENT_ICONS[icon];
  return (
    <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg bg-violet-500/15 text-violet-600 dark:text-violet-300", className)}>
      <Icon className="size-4" />
    </span>
  );
}
