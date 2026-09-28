"use client";

import * as React from "react";
import Link from "next/link";
import { CalendarClock, CircleCheck, CircleX, Clapperboard, ExternalLink, Send, X } from "lucide-react";

import { approveVideo, rejectVideo, remountVideo, scheduleVideo } from "@/app/production/actions";
import { VideoStatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatDateTime } from "@/lib/format";
import type { Video, VideoStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const DECIDABLE = new Set<VideoStatus>(["review", "qa", "ready"]);

export function isDecidable(status: VideoStatus): boolean {
  return DECIDABLE.has(status);
}

/**
 * Deuxième porte humaine : autoriser la publication (prochain créneau libre de la chaîne), programmer à une date,
 * ou refuser. `onDone` est appelé après un geste réussi (rafraîchir la liste qui affiche la vidéo).
 */
export function VideoDecision({ videoId, onDone }: { videoId: string; onDone?: () => void }) {
  const [pending, startTransition] = React.useTransition();
  const [notice, setNotice] = React.useState<{ ok: boolean; message: string } | null>(null);
  const [date, setDate] = React.useState("");
  const run = (fn: () => Promise<{ ok: boolean; message: string }>) =>
    startTransition(async () => {
      const res = await fn();
      setNotice(res);
      if (res.ok) onDone?.();
    });

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={pending} onClick={() => run(() => approveVideo(videoId))}>
          <Send />
          Autoriser la publication
        </Button>
        <span className="text-muted-foreground text-xs">au prochain créneau libre de la chaîne</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Input type="datetime-local" className="w-56" value={date} onChange={(e) => setDate(e.target.value)} aria-label="Date de publication" />
        <Button size="sm" variant="outline" disabled={pending || !date} onClick={() => run(() => scheduleVideo(videoId, new Date(date).toISOString()))}>
          <CalendarClock />
          Programmer à cette date
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="text-destructive"
          disabled={pending}
          onClick={() => {
            const reason = window.prompt("Motif du refus (facultatif)") ?? "";
            run(() => rejectVideo(videoId, reason));
          }}
        >
          <X />
          Refuser
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ghost" disabled={pending} onClick={() => run(() => remountVideo(videoId))}>
          <Clapperboard />
          Refaire le montage
        </Button>
        <span className="text-muted-foreground text-xs">
          avec le modèle actuel de l’onglet{" "}
          <Link href="/montage" className="underline underline-offset-2">
            Montage
          </Link>{" "}
          (mêmes clips, même voix)
        </span>
      </div>
      {notice ? (
        <p className={cn("flex items-center gap-1.5 text-xs", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")} role="status">
          {notice.ok ? <CircleCheck className="size-3.5" /> : <CircleX className="size-3.5" />}
          {notice.message}
        </p>
      ) : null}
    </div>
  );
}

/** Vidéos d'une production (panneau de détail) : lecteur, créneau, et décision de publication. */
export function VideoPanel({ videos }: { videos: Video[] }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">Vidéo</h3>
      <ul className="flex flex-col gap-3">
        {videos.map((video) => {
          const asset = video.final_asset_id ?? video.preview_asset_id;
          return (
            <li key={video.id} className="flex flex-col gap-2 rounded-lg border p-3 text-sm">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="uppercase">
                  {video.lang}
                </Badge>
                <span className="min-w-0 flex-1 truncate font-medium">{video.title ?? "Sans titre"}</span>
                <VideoStatusBadge status={video.status} />
              </div>
              {asset ? (
                <video controls preload="metadata" playsInline className="mx-auto max-h-[420px] rounded-md bg-black" src={`/api/media/${asset}`} />
              ) : (
                <p className="text-muted-foreground text-xs">Pas encore de vidéo montée.</p>
              )}
              <p className="text-muted-foreground text-xs">
                {video.status === "scheduled" || video.status === "published"
                  ? `Publication : ${formatDateTime(video.youtube_publish_at ?? video.scheduled_at ?? video.published_at ?? "")}`
                  : video.scheduled_at
                    ? `Créneau : ${formatDateTime(video.scheduled_at)}`
                    : "Aucun créneau assigné"}
                {video.youtube_video_id ? (
                  <>
                    {" · "}
                    <a className="inline-flex items-center gap-1 underline" href={`https://youtube.com/shorts/${video.youtube_video_id}`} target="_blank" rel="noreferrer">
                      YouTube <ExternalLink className="size-3" />
                    </a>
                  </>
                ) : null}
              </p>
              {video.error ? <p className="text-destructive text-xs">{video.error}</p> : null}
              {isDecidable(video.status) ? <VideoDecision videoId={video.id} /> : null}
            </li>
          );
        })}
        {videos.length === 0 ? <li className="text-muted-foreground text-xs">La vidéo est créée une fois le script écrit.</li> : null}
      </ul>
    </section>
  );
}
