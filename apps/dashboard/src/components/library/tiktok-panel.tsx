"use client";

import * as React from "react";
import Link from "next/link";
import { CircleCheck, CircleX, ExternalLink, Music2, Send } from "lucide-react";

import { publishOnTikTok } from "@/app/library/tiktok-actions";
import { ToneBadge, type Tone } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import { TIKTOK_STATUS_LABELS, type LibraryTikTok, type TikTokStatus } from "@/lib/tiktok-types";

const TONES: Record<TikTokStatus, Tone> = {
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

/** Fiche d'une vidéo → TikTok (docs/36) : état de sa publication par Zernio, lien, et « Publier sur TikTok ». */
export function TikTokPanel({ videoId, initial, canPublish }: { videoId: string; initial: LibraryTikTok; canPublish: boolean }) {
  // état renvoyé par « Publier sur TikTok » ; sinon celui de la fiche (le parent remonte ce panneau à chaque vidéo)
  const [updated, setTiktok] = React.useState<LibraryTikTok | null>(null);
  const tiktok = updated ?? initial;
  const [notice, setNotice] = React.useState<{ ok: boolean; message: string } | null>(null);
  const [pending, startTransition] = React.useTransition();

  const state = tiktok.state;
  const retry = state?.status === "failed" || state?.status === "cancelled" || state?.status === "sending";
  const showButton = canPublish && !tiktok.pending && (!state || retry);
  const publish = () =>
    startTransition(async () => {
      const res = await publishOnTikTok(videoId);
      setNotice(res);
      if (res.ok && res.tiktok) setTiktok(res.tiktok);
    });

  return (
    <section className="flex flex-col gap-2">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <Music2 className="size-4" />
        TikTok
        {state ? <ToneBadge tone={TONES[state.status]}>{state.draft && state.status === "published" ? "Brouillon envoyé" : TIKTOK_STATUS_LABELS[state.status]}</ToneBadge> : null}
        {tiktok.pending && state?.status !== "scheduled" ? <ToneBadge tone="running">En file</ToneBadge> : null}
      </h3>
      <p className="text-muted-foreground text-xs">
        {state?.status === "scheduled" && state.scheduled_for
          ? `Sortira sur @${state.username ?? tiktok.username ?? "?"} le ${formatDateTime(state.scheduled_for)}, à la même heure que sur YouTube.`
          : state?.status === "published"
            ? state.draft
              ? "Dans la boîte de réception TikTok : la publication se termine dans l’appli."
              : `Publiée sur @${state.username ?? tiktok.username ?? "?"}${state.published_at ? ` le ${formatDateTime(state.published_at)}` : ""}${state.url ? "" : " · lien pas encore donné par TikTok"}.`
            : state?.status === "failed"
              ? `Refusée : ${state.error ?? "raison inconnue"}`
              : !state && tiktok.username
                ? `Pas encore sur TikTok. Compte relié : @${tiktok.username}.`
                : !state
                  ? "Pas encore sur TikTok, et aucun compte TikTok n’est relié à cette chaîne."
                  : "Envoi en cours par le worker."}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {state?.url ? (
          <Button variant="outline" size="sm" asChild>
            <a href={state.url} target="_blank" rel="noreferrer noopener">
              <ExternalLink />
              Ouvrir sur TikTok
            </a>
          </Button>
        ) : null}
        {showButton && tiktok.username ? (
          <Button size="sm" variant={retry ? "outline" : "default"} disabled={pending} onClick={publish}>
            <Send />
            {retry ? "Réessayer sur TikTok" : "Publier sur TikTok"}
          </Button>
        ) : null}
        {!tiktok.username ? (
          <Button size="sm" variant="ghost" asChild>
            <Link href="/settings#tiktok">Relier un compte TikTok</Link>
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
