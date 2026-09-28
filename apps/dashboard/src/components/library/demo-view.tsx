"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { CircleCheck, CircleX, ExternalLink, Film, FlaskConical, FolderOpen, HardDrive, MonitorPlay, Trash2 } from "lucide-react";

import { deleteDemo } from "@/app/library/actions";
import { ConfirmButton } from "@/components/confirm-button";
import { ToneBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { DEMO_KIND_LABELS, type DemoFolder } from "@/lib/demo-types";
import { formatBytes, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type Notice = { ok: boolean; message: string };

const plural = (n: number, word: string) => `${n} ${word}${n > 1 ? "s" : ""}`;

/** Vignette 9:16 d'un dossier : une image de sa première vidéo (aucune affiche n'existe hors de l'appli). */
function DemoCard({ demo, onOpen }: { demo: DemoFolder; onOpen: () => void }) {
  return (
    <li className="flex min-w-0 flex-col gap-2">
      <button
        type="button"
        onClick={onOpen}
        className="group relative aspect-[9/16] w-full overflow-hidden rounded-xl border bg-black text-left outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        aria-label={demo.title}
      >
        <video
          src={`${demo.videos[0].url}#t=1`}
          muted
          playsInline
          preload="metadata"
          className="size-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
        />
        <span className="absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-black/70 to-transparent" aria-hidden />
        <span className="absolute top-2 left-2">
          <ToneBadge tone={demo.kind === "demo" ? "info" : "neutral"} className="bg-background/85 backdrop-blur">
            {DEMO_KIND_LABELS[demo.kind]}
          </ToneBadge>
        </span>
        {demo.youtube_video_id ? (
          <span className="absolute top-2 right-2 flex items-center gap-1 rounded-md bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white" title="Mise en ligne à la main sur YouTube">
            <MonitorPlay className="size-3" />
            Sur YouTube
          </span>
        ) : null}
        <span className="absolute right-2 bottom-2 left-2 flex items-center gap-1 text-[11px] font-medium text-white tabular-nums">
          <Film className="size-3" />
          {plural(demo.videos.length, "vidéo")}
        </span>
      </button>
      <div className="flex min-w-0 flex-col gap-0.5 px-0.5">
        <p className="line-clamp-2 text-sm leading-snug font-medium">{demo.title}</p>
        <p className="text-muted-foreground truncate text-xs">Faite le {formatDateTime(demo.modified_at)}</p>
        <p className="text-muted-foreground text-[11px] tabular-nums">{formatBytes(demo.size_bytes)} sur le PC</p>
      </div>
    </li>
  );
}

/** Fiche d'un dossier : ses vidéos finies, ses clips à la demande, son emplacement et la suppression du dossier. */
function DemoSheet({ demo, onClose, onDone }: { demo: DemoFolder | null; onClose: () => void; onDone: (res: Notice) => void }) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [error, setError] = React.useState<string | null>(null);
  const [showClips, setShowClips] = React.useState(false);
  const mains = demo ? demo.videos.slice(0, demo.main_count) : [];
  const clips = demo ? demo.videos.slice(demo.main_count) : [];

  return (
    <Sheet
      open={demo !== null}
      onOpenChange={(open) => {
        if (!open) {
          setError(null);
          setShowClips(false);
          onClose();
        }
      }}
    >
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-2xl">
        {demo ? (
          <>
            <SheetHeader className="border-b pr-12">
              <SheetTitle className="leading-snug">{demo.title}</SheetTitle>
              <SheetDescription>{[`Faite le ${formatDateTime(demo.modified_at)}`, plural(demo.videos.length, "vidéo")].join(" · ")}</SheetDescription>
              <div className="flex flex-wrap gap-1.5">
                <ToneBadge tone={demo.kind === "demo" ? "info" : "neutral"}>{DEMO_KIND_LABELS[demo.kind]}</ToneBadge>
                <ToneBadge tone="neutral">Faite hors de l’appli</ToneBadge>
              </div>
              {demo.youtube_video_id ? (
                <Button variant="outline" size="sm" className="w-fit" asChild>
                  <a href={`https://youtube.com/shorts/${demo.youtube_video_id}`} target="_blank" rel="noreferrer noopener">
                    <ExternalLink />
                    Ouvrir sur YouTube
                  </a>
                </Button>
              ) : null}
            </SheetHeader>

            <ScrollArea className="min-h-0 flex-1">
              <div className="flex flex-col gap-6 p-4">
                {demo.description ? <p className="text-sm leading-relaxed">{demo.description}</p> : null}

                <div className="flex flex-col gap-5">
                  {mains.map((v) => (
                    <figure key={v.path} className="flex flex-col items-center gap-1.5">
                      <video src={v.url} controls preload="metadata" playsInline className="mx-auto max-h-[60vh] w-auto max-w-full rounded-lg bg-black" />
                      <figcaption className="text-muted-foreground text-xs">
                        {v.path} · {formatBytes(v.size_bytes)}
                      </figcaption>
                    </figure>
                  ))}
                </div>

                {clips.length > 0 ? (
                  <section className="flex flex-col gap-2">
                    <h3 className="text-sm font-semibold">Clips et essais intermédiaires ({clips.length})</h3>
                    {showClips ? (
                      <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                        {clips.map((v) => (
                          <li key={v.path} className="flex min-w-0 flex-col gap-1">
                            <video src={`${v.url}#t=0.5`} controls preload="metadata" playsInline className="aspect-[9/16] w-full rounded-md bg-black object-contain" />
                            <span className="text-muted-foreground truncate text-[11px]" title={v.path}>
                              {v.path}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <Button size="sm" variant="outline" className="w-fit" onClick={() => setShowClips(true)}>
                        <Film />
                        Afficher les {clips.length} clips
                      </Button>
                    )}
                  </section>
                ) : null}

                <Separator />
                <section className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-3">
                    <HardDrive className="text-muted-foreground size-4" />
                    <span className="text-sm">Sur le PC : {formatBytes(demo.size_bytes)}</span>
                    <ConfirmButton
                      variant="outline"
                      size="sm"
                      className="ml-auto"
                      disabled={pending}
                      confirmLabel="Confirmer la suppression"
                      onConfirm={() =>
                        startTransition(async () => {
                          const res = await deleteDemo(demo.id);
                          if (!res.ok) {
                            setError(res.message);
                            return;
                          }
                          onDone(res);
                          onClose();
                          router.refresh();
                        })
                      }
                    >
                      <Trash2 />
                      Supprimer le dossier
                    </ConfirmButton>
                  </div>
                  <p className="text-muted-foreground flex items-start gap-1.5 text-xs break-all">
                    <FolderOpen className="mt-px size-3.5 shrink-0" />
                    {demo.location}
                  </p>
                  <p className="text-muted-foreground text-xs">
                    Supprime tout le dossier : vidéos, clips, images et journaux. Ne touche ni à la base ni à YouTube
                    {demo.youtube_video_id ? " (la vidéo mise en ligne reste dans Vidéos → Importées, avec ses stats)" : ""}.
                  </p>
                  {error ? (
                    <p className="text-destructive flex items-center gap-1.5 text-xs" role="status">
                      <CircleX className="size-3.5" />
                      {error}
                    </p>
                  ) : null}
                </section>
              </div>
            </ScrollArea>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

/** Démos et essais faits hors de l'appli (docs/28) : lecture et suppression, rien d'autre (ils ne sont pas en base). */
export function DemoView({ demos }: { demos: DemoFolder[] }) {
  const [openId, setOpenId] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<Notice | null>(null);
  const total = demos.reduce((s, d) => s + d.size_bytes, 0);
  const open = demos.find((d) => d.id === openId) ?? null;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground max-w-3xl text-sm">
        Vidéos faites par des scripts, hors de l’appli : les démos des formats du 25/09 (avant que tout passe par l’appli) et les bancs d’essai
        qui comparent des modèles. Elles ne sont pas en base : ni publication ni stats ici, seulement la lecture et la suppression.
      </p>
      <div className="text-muted-foreground flex flex-wrap items-center gap-3 text-sm">
        <span className="flex items-center gap-1.5">
          <HardDrive className="size-4" />
          {formatBytes(total)} sur le PC
        </span>
        <span>·</span>
        <span>{plural(demos.length, "dossier")}</span>
      </div>

      {notice ? (
        <p className={cn("flex items-center gap-1.5 text-sm", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")} role="status">
          {notice.ok ? <CircleCheck className="size-4" /> : <CircleX className="size-4" />}
          {notice.message}
        </p>
      ) : null}

      {demos.length > 0 ? (
        <ul className="grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
          {demos.map((demo) => (
            <DemoCard key={demo.id} demo={demo} onOpen={() => setOpenId(demo.id)} />
          ))}
        </ul>
      ) : (
        <div className="text-muted-foreground flex flex-col items-center gap-2 rounded-xl border border-dashed p-10 text-center text-sm">
          <FlaskConical className="size-6" />
          <p>Aucune démo ni aucun essai sur le PC.</p>
        </div>
      )}

      <DemoSheet demo={open} onClose={() => setOpenId(null)} onDone={setNotice} />
    </div>
  );
}
