import { Badge } from "@/components/ui/badge";
import {
  CONCEPT_STATUS_LABELS,
  JOB_STATUS_LABELS,
  PRODUCTION_STATUS_LABELS,
  SEVERITY_LABELS,
  VIDEO_STATUS_LABELS,
} from "@/lib/labels";
import type { AlertSeverity, ConceptStatus, JobStatus, ProductionStatus, VideoStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "running";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "border-border bg-muted/60 text-muted-foreground",
  success: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  warning: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  danger: "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400",
  info: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-400",
  running: "border-violet-500/40 bg-violet-500/10 text-violet-700 dark:text-violet-400",
};

export function ToneBadge({
  tone,
  className,
  children,
  ...props
}: React.ComponentProps<typeof Badge> & { tone: Tone }) {
  return (
    <Badge variant="outline" className={cn(TONE_CLASSES[tone], className)} {...props}>
      {children}
    </Badge>
  );
}

export const VIDEO_STATUS_TONES: Record<VideoStatus, Tone> = {
  pending: "neutral",
  rendering: "running",
  qa: "running",
  review: "info",
  ready: "success",
  uploading: "running",
  scheduled: "info",
  published: "success",
  failed: "danger",
  unpublished: "warning",
};

export const PRODUCTION_STATUS_TONES: Record<ProductionStatus, Tone> = {
  draft: "neutral",
  scripting: "running",
  generating: "running",
  assembling: "running",
  ready: "success",
  failed: "danger",
  archived: "neutral",
};

export const JOB_STATUS_TONES: Record<JobStatus, Tone> = {
  queued: "neutral",
  running: "running",
  done: "success",
  failed: "danger",
  cancelled: "warning",
};

export const CONCEPT_STATUS_TONES: Record<ConceptStatus, Tone> = {
  proposed: "info",
  approved: "success",
  rejected: "danger",
  used: "neutral",
};

export const SEVERITY_TONES: Record<AlertSeverity, Tone> = {
  info: "info",
  warning: "warning",
  error: "danger",
};

export function VideoStatusBadge({ status, className }: { status: VideoStatus; className?: string }) {
  return (
    <ToneBadge tone={VIDEO_STATUS_TONES[status]} className={className}>
      {VIDEO_STATUS_LABELS[status]}
    </ToneBadge>
  );
}

export function ProductionStatusBadge({ status, className }: { status: ProductionStatus; className?: string }) {
  return (
    <ToneBadge tone={PRODUCTION_STATUS_TONES[status]} className={className}>
      {PRODUCTION_STATUS_LABELS[status]}
    </ToneBadge>
  );
}

export function JobStatusBadge({ status, className }: { status: JobStatus; className?: string }) {
  return (
    <ToneBadge tone={JOB_STATUS_TONES[status]} className={className}>
      {JOB_STATUS_LABELS[status]}
    </ToneBadge>
  );
}

export function ConceptStatusBadge({ status, className }: { status: ConceptStatus; className?: string }) {
  return (
    <ToneBadge tone={CONCEPT_STATUS_TONES[status]} className={className}>
      {CONCEPT_STATUS_LABELS[status]}
    </ToneBadge>
  );
}

export function SeverityBadge({ severity, className }: { severity: AlertSeverity; className?: string }) {
  return (
    <ToneBadge tone={SEVERITY_TONES[severity]} className={className}>
      {SEVERITY_LABELS[severity]}
    </ToneBadge>
  );
}
