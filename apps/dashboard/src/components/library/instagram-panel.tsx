"use client";

import * as React from "react";
import Link from "next/link";
import { Camera, CircleCheck, CircleX, ExternalLink, Send } from "lucide-react";

import { publishOnInstagram } from "@/app/library/instagram-actions";
import { ToneBadge, type Tone } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import { INSTAGRAM_STATUS_LABELS, type InstagramStatus, type LibraryInstagram } from "@/lib/instagram-types";

const TONES: Record<InstagramStatus, Tone> = {
  sending: "running",
  scheduled: "info",
  pending: "running",
  publishing: "running",
  processing: "running",
  uploading: "running",
  published: "success",
  failed: "danger",
  cancelled: "neutral",
};

/** Fiche d'une vidéo → Instagram (docs/48) : état de son Reel par Zernio, lien, et « Publier sur Instagram ». */
export function InstagramPanel({ videoId, initial, canPublish }: { videoId: string; initial: LibraryInstagram; canPublish: boolean }) {
  const [updated, setInstagram] = React.useState<LibraryInstagram | null>(null);
  const instagram = updated ?? initial;
  const [notice, setNotice] = React.useState<{ ok: boolean; message: string } | null>(null);
  const [pending, startTransition] = React.useTransition();

  const state = instagram.state;
  const retry = state?.status === "failed" || state?.status === "cancelled" || state?.status === "sending";
  const showButton = canPublish && !instagram.pending && (!state || retry);
  const who = `@${state?.username ?? instagram.username ?? "?"}`;
  const publish = () =>
    startTransition(async () => {
      const res = await publishOnInstagram(videoId);
      setNotice(res);
      if (res.ok && res.instagram) setInstagram(res.instagram);
    });

  return (
    <section className="flex flex-col gap-2">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <Camera className="size-4" />
        Instagram
        {state ? <ToneBadge tone={TONES[state.status]}>{INSTAGRAM_STATUS_LABELS[state.status]}</ToneBadge> : null}
        {instagram.pending && state?.status !== "scheduled" ? <ToneBadge tone="running">En file</ToneBadge> : null}
      </h3>
      <p className="text-muted-foreground text-xs">
        {state?.status === "scheduled" && state.scheduled_for
          ? `Le Reel sortira sur ${who} le ${formatDateTime(state.scheduled_for)}, à la même heure que sur YouTube.`
          : state?.status === "published"
            ? `Reel publié sur ${who}${state.published_at ? ` le ${formatDateTime(state.published_at)}` : ""}${state.url ? "" : " · lien pas encore donné par Instagram"}.`
            : state?.status === "failed"
              ? `Refusé : ${state.error ?? "raison inconnue"}`
              : !state && instagram.username
                ? `Pas encore sur Instagram. Compte relié : @${instagram.username}.`
                : !state
                  ? "Pas encore sur Instagram, et aucun compte Instagram n’est relié à cette chaîne."
                  : "Envoi en cours par le worker."}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {state?.url ? (
          <Button variant="outline" size="sm" asChild>
            <a href={state.url} target="_blank" rel="noreferrer noopener">
              <ExternalLink />
              Ouvrir sur Instagram
            </a>
          </Button>
        ) : null}
        {showButton && instagram.username ? (
          <Button size="sm" variant={retry ? "outline" : "default"} disabled={pending} onClick={publish}>
            <Send />
            {retry ? "Réessayer sur Instagram" : "Publier sur Instagram"}
          </Button>
        ) : null}
        {!instagram.username ? (
          <Button size="sm" variant="ghost" asChild>
            <Link href="/settings#instagram">Relier un compte Instagram</Link>
          </Button>
        ) : null}
      </div>
      {notice ? (
        <p className={`flex items-center gap-1.5 text-xs ${notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`} role="status">
          {notice.ok ? <CircleCheck className="size-3.5 shrink-0" /> : <CircleX className="size-3.5 shrink-0" />}
          {notice.message}
        </p>
      ) : null}
    </section>
  );
}
