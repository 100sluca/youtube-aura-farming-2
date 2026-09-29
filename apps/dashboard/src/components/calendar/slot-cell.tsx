import { TriangleAlert } from "lucide-react";

import { TikTokMark, YouTubeMark } from "@/components/platform-marks";
import { ToneBadge, type Tone } from "@/components/status-badge";
import { formatTime, now } from "@/lib/format";
import type { TikTokCalendarItem, TikTokStatus } from "@/lib/tiktok-types";
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

/** État d'une publication TikTok dans le Calendrier (docs/39). */
export const TIKTOK_SLOT_STATUS: Record<TikTokStatus, { label: string; tone: Tone }> = {
  sending: { label: "Envoi", tone: "running" },
  scheduled: { label: "Programmée", tone: "info" },
  pending: { label: "Envoi", tone: "running" },
  publishing: { label: "Envoi", tone: "running" },
  processing: { label: "Envoi", tone: "running" },
  uploading: { label: "Envoi", tone: "running" },
  published: { label: "Publiée", tone: "success" },
  failed: { label: "Échec", tone: "danger" },
  cancelled: { label: "Annulée", tone: "neutral" },
};

const H48 = 48 * 3_600_000;

/** Une publication TikTok : pastille TikTok + état ; le titre seulement si ce n'est pas la vidéo YouTube du créneau. */
export function TikTokLine({ item, showTitle, showTime = false }: { item: TikTokCalendarItem; showTitle: boolean; showTime?: boolean }) {
  const status = item.draft && item.status === "published" ? { label: "Brouillon", tone: "neutral" as Tone } : TIKTOK_SLOT_STATUS[item.status];
  const label = item.forecast ? "Rattrapage prévu" : item.source === "rattrapage" && item.status === "scheduled" ? "Rattrapage" : status.label;
  const hint = item.forecast
    ? "Créneau vide : le rattrapage y enverra cette ancienne vidéo, sauf si une nouvelle vidéo le prend d’ici là"
    : item.error
      ? `TikTok : ${item.error}`
      : `TikTok : ${status.label.toLowerCase()}${item.source === "rattrapage" ? " (rattrapage d’une vidéo déjà sortie sur YouTube)" : ""}`;
  const badge = (
    <ToneBadge tone={item.forecast ? "neutral" : item.source === "rattrapage" && item.status === "scheduled" ? "info" : status.tone} className={cn("px-1.5 py-0 text-[10px]", item.forecast && "border-dashed")}>
      {label}
    </ToneBadge>
  );
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", item.forecast && "opacity-70")} title={hint}>
      {showTitle ? <p className="line-clamp-2 text-xs leading-snug font-medium">{item.title ?? "Sans titre"}</p> : null}
      <div className="flex items-center gap-1">
        <TikTokMark className="size-3.5" />
        {showTime ? <span className="text-muted-foreground text-[10px] tabular-nums">{formatTime(item.at)}</span> : null}
        {item.url ? (
          <a href={item.url} target="_blank" rel="noreferrer noopener" className="hover:opacity-80" aria-label="Ouvrir sur TikTok">
            {badge}
          </a>
        ) : (
          badge
        )}
      </div>
    </div>
  );
}

export function SlotCell({ slot, tiktok = [] }: { slot: ScheduleSlot | undefined; tiktok?: TikTokCalendarItem[] }) {
  if (!slot) return null;
  const at = new Date(slot.at).getTime();
  const isPast = at <= now().getTime();
  const soon = !isPast && at - now().getTime() < H48;
  const mirror = slot.video ? tiktok.filter((t) => t.video_id === slot.video?.id) : [];
  const others = tiktok.filter((t) => !mirror.includes(t));

  if (!slot.video) {
    return (
      <div className="flex flex-col gap-1.5">
        {isPast ? (
          <p className="text-muted-foreground/60 text-xs">Non publié</p>
        ) : (
          <div
            className={cn(
              "flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-xs",
              soon ? "border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400" : "text-muted-foreground border-dashed",
            )}
          >
            {soon ? <TriangleAlert className="size-3.5 shrink-0" /> : null}
            {soon ? "Vide · sous 48 h" : "Vide"}
          </div>
        )}
        {others.map((t) => (
          <TikTokLine key={t.video_id} item={t} showTitle />
        ))}
      </div>
    );
  }

  const status = SLOT_STATUS[slot.video.status];
  return (
    <div className="flex flex-col gap-1.5">
      <p className="line-clamp-2 text-xs leading-snug font-medium" title={slot.video.title ?? undefined}>
        {slot.video.title ?? "Sans titre"}
      </p>
      <div className="flex items-center gap-1" title={`YouTube : ${status.label.toLowerCase()}`}>
        <YouTubeMark className="size-3.5" />
        <ToneBadge tone={status.tone} className="w-fit">
          {status.label}
        </ToneBadge>
      </div>
      {mirror.map((t) => (
        <TikTokLine key={t.video_id} item={t} showTitle={false} showTime={Math.abs(new Date(t.at).getTime() - at) >= 10 * 60_000} />
      ))}
      {others.map((t) => (
        <TikTokLine key={t.video_id} item={t} showTitle />
      ))}
    </div>
  );
}
