"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, CircleCheck, CircleX, Copy, ExternalLink, HardDrive, PenLine, Play, Square, Trash2 } from "lucide-react";

import { toggleFavorite } from "@/app/favorites/actions";
import { deleteVideos, fetchLibraryDetail } from "@/app/library/actions";
import { remakeProduction } from "@/app/production/actions";
import { resumeProduction, stopProduction } from "@/app/tasks/actions";
import { ChannelBadge } from "@/components/channel-badge";
import { ConfirmButton } from "@/components/confirm-button";
import { FavoriteStar } from "@/components/favorites/favorite-star";
import { TikTokPanel } from "@/components/library/tiktok-panel";
import { VideoStats } from "@/components/library/video-stats";
import { VideoDecision, isDecidable } from "@/components/production/video-panel";
import { PRODUCTION_STATUS_TONES, ToneBadge, VideoStatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { formatBytes, formatDateTime, formatDuration } from "@/lib/format";
import { videoProviderLabel } from "@/lib/labels";
import type { LibraryClip, LibraryDetail, LibraryItem, LibraryMaking } from "@/lib/library-types";
import { cn } from "@/lib/utils";

type Notice = { ok: boolean; message: string };

/** Titre de la vidéo (agent SEO), sinon celui de l'idée tant que la vidéo est en fabrication. */
export function libraryTitle(v: LibraryItem): string {
  return v.title ?? v.making?.concept_title ?? "Sans titre";
}

/** « Publiée le … », « Programmée le … », « Finie le … » : la date qui compte pour cette vidéo. */
export function dateLine(v: LibraryItem): string {
  if (v.making) {
    if (v.making.eta_at) return `Fin estimée ${formatDateTime(v.making.eta_at)}`;
    return v.created_at ? `Commencée le ${formatDateTime(v.created_at)}` : "";
  }
  if (v.status === "published" && v.published_at) return `Publiée le ${formatDateTime(v.published_at)}`;
  const slot = v.youtube_publish_at ?? v.scheduled_at;
  if ((v.status === "scheduled" || v.status === "ready" || v.status === "uploading") && slot) return `Programmée le ${formatDateTime(slot)}`;
  if (v.status === "unpublished") return "Privée sur YouTube";
  return v.created_at ? `Fabriquée le ${formatDateTime(v.created_at)}` : "";
}

function Player({ item }: { item: LibraryItem }) {
  const file = !item.files_deleted_at && item.origin !== "imported" ? (item.final_asset_id ?? item.preview_asset_id) : null;
  if (file) {
    return (
      <video
        key={file}
        controls
        preload="metadata"
        playsInline
        poster={item.poster_asset_id ? `/api/media/${item.poster_asset_id}` : undefined}
        className="mx-auto max-h-[60vh] w-auto rounded-lg bg-black"
        src={`/api/media/${file}`}
      />
    );
  }
  if (item.youtube_video_id) {
    return (
      <iframe
        title={item.title ?? "Vidéo YouTube"}
        src={`https://www.youtube-nocookie.com/embed/${item.youtube_video_id}`}
        className="mx-auto aspect-[9/16] max-h-[60vh] w-full max-w-[340px] rounded-lg bg-black"
        allow="accelerometer; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
      />
    );
  }
  return <p className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-sm">Fichier effacé du PC.</p>;
}

const STOPPABLE = new Set(["draft", "scripting", "generating", "assembling"]);

/** Retouche à la main (docs/34) : vidéo de l'appli montée, fichiers sur le PC, pas encore envoyée sur YouTube. */
function canRetouch(v: LibraryItem): boolean {
  return (
    v.origin !== "imported" &&
    !v.files_deleted_at &&
    Boolean(v.final_asset_id) &&
    !v.youtube_video_id &&
    ["review", "qa", "ready", "failed", "rendering"].includes(v.status)
  );
}

/** Vidéo pas encore montée (docs/28) : où en est sa fabrication, ses clips déjà faits, et les gestes possibles. */
function MakingPanel({
  making,
  productionId,
  clips,
  scenes,
  pending,
  onAction,
}: {
  making: LibraryMaking;
  productionId: string | null;
  clips: LibraryClip[] | undefined;
  scenes: number | null;
  pending: boolean;
  onAction: (fn: () => Promise<Notice>) => void;
}) {
  const waitingForLuca = making.status === "storyboard_review";
  return (
    <section className="flex flex-col gap-3 rounded-lg border p-3">
      {/* Étape et fin estimée : dans l'en-tête de la fiche */}
      <div className="flex items-center gap-2">
        <Progress value={making.progress_pct} className="h-1.5 flex-1" aria-label="Avancement" />
        <span className="text-muted-foreground text-xs tabular-nums">{making.progress_pct} %</span>
      </div>
      <p className="text-sm">
        {waitingForLuca
          ? "Pas encore de vidéo : le storyboard attend ton ✓ dans Création, qui lance les clips, la voix et le montage d’une traite."
          : making.status === "cancelled"
            ? "Fabrication arrêtée avant le montage : reprends-la ou supprime-la."
            : making.status === "failed"
              ? "Fabrication bloquée avant le montage : relance l’étape en échec depuis le panneau Tâches, ou supprime-la."
              : "Pas encore de vidéo : elle apparaîtra ici, prête à regarder, dès la fin du montage. En attendant, voici ce qui est déjà fait."}
      </p>

      {clips && clips.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <span className="text-muted-foreground text-xs font-medium">
            Clips déjà faits : {clips.length}
            {scenes ? ` sur ${scenes}` : ""}
          </span>
          <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
            {clips.map((clip) => (
              <figure key={clip.asset_id} className="flex shrink-0 flex-col gap-1">
                <video src={`/api/media/${clip.asset_id}#t=0.5`} controls preload="metadata" playsInline className="h-48 w-auto rounded-md bg-black" />
                {clip.scene_index !== null ? <figcaption className="text-muted-foreground text-[11px]">Scène {clip.scene_index + 1}</figcaption> : null}
              </figure>
            ))}
          </div>
        </div>
      ) : clips ? (
        <p className="text-muted-foreground text-xs">Aucun clip encore : le storyboard (plus bas) montre les images de départ.</p>
      ) : null}

      {productionId ? (
        <div className="flex flex-wrap gap-2">
          {waitingForLuca ? (
            <Button size="sm" asChild>
              <Link href="/create#storyboards">
                Voir le storyboard dans Création
                <ArrowRight />
              </Link>
            </Button>
          ) : null}
          {STOPPABLE.has(making.status) ? (
            <ConfirmButton size="sm" variant="outline" disabled={pending} confirmLabel="Confirmer l’arrêt" onConfirm={() => onAction(() => stopProduction(productionId))}>
              <Square />
              Arrêter la fabrication
            </ConfirmButton>
          ) : null}
          {making.status === "cancelled" ? (
            <Button size="sm" variant="outline" disabled={pending} onClick={() => onAction(() => resumeProduction(productionId))}>
              <Play />
              Reprendre
            </Button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

/** Fiche d'une vidéo de la bibliothèque : lecture, publication, stats, fabrication, suppression. */
export function LibrarySheet({ item, onClose }: { item: LibraryItem | null; onClose: () => void }) {
  const router = useRouter();
  const [loaded, setLoaded] = React.useState<{ id: string; data: LibraryDetail } | null>(null);
  const [notice, setNotice] = React.useState<Notice | null>(null);
  const [pending, startTransition] = React.useTransition();
  const [star, setStar] = React.useState<{ production: string; on: boolean } | null>(null); // étoile changée ici

  React.useEffect(() => {
    if (!item) return;
    let alive = true;
    fetchLibraryDetail(item.id, item.production_id, Boolean(item.making))
      .then((data) => {
        if (alive) setLoaded({ id: item.id, data });
      })
      .catch(() => {
        if (alive) setLoaded({ id: item.id, data: { detail: null, production: null } });
      });
    return () => {
      alive = false;
    };
  }, [item]);

  const data = loaded && item && loaded.id === item.id ? loaded.data : null;
  const production = data?.production ?? null;
  const script = production?.production.script ?? data?.detail?.script ?? null;
  const onYouTube = Boolean(item?.youtube_video_id);
  const productionId = production?.production.id ?? null;
  const favorite = star && star.production === productionId ? star.on : Boolean(data?.favorite);
  const making = item?.making ?? null;
  // Arrêter / reprendre : la liste (et donc cette fiche) se met à jour aussitôt
  const act = (fn: () => Promise<Notice>) =>
    startTransition(async () => {
      setNotice(await fn());
      router.refresh();
    });

  return (
    <Sheet
      open={item !== null}
      onOpenChange={(open) => {
        if (!open) {
          setNotice(null);
          onClose();
        }
      }}
    >
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-2xl">
        {item ? (
          <>
            <SheetHeader className="border-b pr-12">
              <SheetTitle className="leading-snug">{libraryTitle(item)}</SheetTitle>
              <SheetDescription>{[dateLine(item), making ? null : formatDuration(item.duration_s)].filter(Boolean).join(" · ")}</SheetDescription>
              <div className="flex flex-wrap gap-1.5">
                {making ? <ToneBadge tone={PRODUCTION_STATUS_TONES[making.status]}>{making.stage}</ToneBadge> : <VideoStatusBadge status={item.status} />}
                {item.origin === "imported" ? <ToneBadge tone="neutral">Importée de YouTube</ToneBadge> : <ToneBadge tone="info">Produite par l’appli</ToneBadge>}
                <ChannelBadge channel={{ slug: item.channel_slug, name: item.channel_name ?? item.channel_slug }} />
                {item.series_name ? <ToneBadge tone="neutral">{item.series_name}</ToneBadge> : null}
              </div>
              {item.youtube_video_id ? (
                <Button variant="outline" size="sm" className="w-fit" asChild>
                  <a href={`https://youtube.com/shorts/${item.youtube_video_id}`} target="_blank" rel="noreferrer noopener">
                    <ExternalLink />
                    Ouvrir sur YouTube
                  </a>
                </Button>
              ) : null}
            </SheetHeader>

            <ScrollArea className="min-h-0 flex-1">
              <div className="flex flex-col gap-6 p-4">
                {making ? (
                  <MakingPanel
                    making={making}
                    productionId={item.production_id}
                    clips={data?.clips}
                    scenes={production?.storyboard?.length ?? null}
                    pending={pending}
                    onAction={act}
                  />
                ) : (
                  <Player item={item} />
                )}

                {!making && canRetouch(item) ? (
                  <Button size="sm" variant="outline" className="w-fit" asChild>
                    <Link href={`/library/${item.id}/retouche`}>
                      <PenLine />
                      Retoucher : titre, sous-titres, musique, voix
                    </Link>
                  </Button>
                ) : null}

                {item.error && item.status === "failed" ? <p className="text-destructive text-sm">{item.error}</p> : null}

                {isDecidable(item.status) && !onYouTube ? (
                  <section className="flex flex-col gap-2 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
                    <h3 className="text-sm font-semibold">Publier cette vidéo ?</h3>
                    <VideoDecision videoId={item.id} />
                  </section>
                ) : null}

                {!making && item.origin !== "imported" && data?.tiktok ? (
                  <>
                    <Separator />
                    <TikTokPanel key={item.id} videoId={item.id} initial={data.tiktok} canPublish={Boolean(item.final_asset_id) && !item.files_deleted_at} />
                  </>
                ) : null}

                {onYouTube ? (
                  <>
                    <Separator />
                    <VideoStats video={item} detail={data?.detail ?? null} insight={data?.insight ?? null} loading={!data} />
                  </>
                ) : null}

                {item.origin !== "imported" ? (
                  <>
                    <Separator />
                    <section className="flex flex-col gap-3">
                      <h3 className="text-sm font-semibold">Fabrication</h3>
                      {production ? (
                        <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
                          {production.production.image_workflow ? <span>Images : {production.production.image_workflow}</span> : null}
                          {production.production.video_provider ? <span>Vidéo : {videoProviderLabel(production.production.video_provider)}</span> : null}
                          <span>{production.storyboard?.length ?? 0} scènes</span>
                        </div>
                      ) : null}
                      {production?.storyboard?.some((s) => s.candidates.length > 0) ? (
                        <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
                          {production.storyboard.map((scene, pos) => {
                            const pick = scene.candidates.find((c) => c.selected) ?? scene.candidates[0];
                            return pick ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img key={scene.index} src={`/api/media/${pick.asset_id}`} alt={`Scène ${pos + 1}`} className="h-28 w-[3.9rem] shrink-0 rounded-md object-cover" loading="lazy" />
                            ) : null;
                          })}
                        </div>
                      ) : null}
                      {script ? (
                        <ol className="flex flex-col gap-1.5 text-sm">
                          {script.scenes.map((scene, pos) => (
                            <li key={scene.index} className="flex gap-2">
                              <span className="text-muted-foreground w-5 shrink-0 tabular-nums">{pos + 1}.</span>
                              <span>{scene.narration?.[item.lang] || scene.on_screen_text?.[item.lang] || scene.visual_prompt}</span>
                            </li>
                          ))}
                        </ol>
                      ) : !data ? (
                        <p className="text-muted-foreground text-xs">Chargement…</p>
                      ) : null}
                      {production?.production.script ? (
                        <div className="flex flex-wrap items-center gap-2">
                          {!making || !STOPPABLE.has(making.status) ? (
                            <Button
                              size="sm"
                              variant="outline"
                              className="w-fit"
                              disabled={pending}
                              onClick={() => startTransition(async () => setNotice(await remakeProduction(production.production.id)))}
                            >
                              <Copy />
                              Refaire avec les réglages actuels
                            </Button>
                          ) : null}
                          <FavoriteStar
                            on={favorite}
                            withLabel
                            disabled={pending}
                            onToggle={() =>
                              startTransition(async () => {
                                const res = await toggleFavorite(production.production.id);
                                setStar({ production: production.production.id, on: res.favorite });
                                setNotice(res);
                              })
                            }
                          />
                        </div>
                      ) : null}
                    </section>

                    <Separator />
                    <section className="flex flex-wrap items-center gap-3">
                      <HardDrive className="text-muted-foreground size-4" />
                      <span className="text-sm">
                        {item.files_deleted_at ? "Fichiers effacés du PC" : `Sur le PC : ${formatBytes(item.size_bytes)}`}
                      </span>
                      {!item.files_deleted_at && item.status !== "uploading" ? (
                        <ConfirmButton
                          variant="outline"
                          size="sm"
                          className="ml-auto"
                          disabled={pending || Boolean(making?.running)}
                          confirmLabel={onYouTube ? "Confirmer : effacer les fichiers" : "Confirmer la suppression"}
                          onConfirm={() =>
                            startTransition(async () => {
                              const res = await deleteVideos([item.id]);
                              setNotice(res);
                              if (res.ok) onClose();
                            })
                          }
                        >
                          <Trash2 />
                          {onYouTube ? "Effacer du PC" : "Supprimer"}
                        </ConfirmButton>
                      ) : null}
                      <p className="text-muted-foreground w-full text-xs">
                        {onYouTube
                          ? "Efface la vidéo, les clips et les images du PC. La vidéo reste sur YouTube et ses stats restent ici."
                          : making?.running
                            ? "Un calcul tourne pour elle : arrête la fabrication d’abord, puis supprime-la."
                            : making
                              ? "Supprime sa fabrication (script, images, clips déjà faits) : la vidéo ne sera pas finie."
                              : "Supprime la vidéo, ses clips et ses images : elle ne sera pas publiée."}
                      </p>
                    </section>
                  </>
                ) : null}

                {notice ? (
                  <p className={cn("flex items-center gap-1.5 text-xs", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")} role="status">
                    {notice.ok ? <CircleCheck className="size-3.5" /> : <CircleX className="size-3.5" />}
                    {notice.message}
                  </p>
                ) : null}
              </div>
            </ScrollArea>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
