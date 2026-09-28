"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, CircleCheck, CircleX, Eye, Link2, Repeat, Search, Sparkles, Star, Trash2, TriangleAlert } from "lucide-react";

import { deleteFavorite, remakeFavorite } from "@/app/favorites/actions";
import { ConfirmButton } from "@/components/confirm-button";
import { ROLE_LABELS } from "@/components/production/storyboard-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { favoriteImageUrl, originalLabel, type Favorite, type FavoriteImage } from "@/lib/favorite-types";
import { formatDate, formatDateTime } from "@/lib/format";
import { videoProviderLabel } from "@/lib/labels";
import type { ChannelLang, ScriptScene } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Message après un geste ; `id` : le favori concerné (affiché sur sa carte), null : en haut de page. */
type Notice = { id: string | null; ok: boolean; message: string; remade?: boolean };

interface Shot {
  scene: ScriptScene;
  image: FavoriteImage | null;
  number: number | null; // les passages d'une visite n'ont ni image ni numéro
}

function shotsOf(favorite: Favorite): Shot[] {
  const byScene = new Map(favorite.images.map((i) => [i.scene_index, i]));
  const shots: Shot[] = [];
  for (const scene of favorite.script.scenes) {
    const number = scene.passage ? null : shots.filter((s) => s.number !== null).length + 1;
    shots.push({ scene, image: byScene.get(scene.index) ?? null, number });
  }
  return shots;
}

function langOf(favorite: Favorite): ChannelLang {
  return favorite.lang ?? (Object.keys(favorite.script.metadata ?? {})[0] as ChannelLang | undefined) ?? "fr";
}

function remadeLine(favorite: Favorite): string | null {
  if (!favorite.remade_count || !favorite.remade_at) return null;
  const last = formatDate(favorite.remade_at, "d MMM");
  return favorite.remade_count === 1 ? `refait le ${last}` : `refait ${favorite.remade_count} fois, la dernière le ${last}`;
}

function NoticeLine({ notice, className }: { notice: Notice; className?: string }) {
  return (
    <p className={cn("flex flex-wrap items-center gap-1.5 text-sm", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive", className)} role="status">
      {notice.ok ? <CircleCheck className="size-4 shrink-0" /> : <CircleX className="size-4 shrink-0" />}
      {notice.message}
      {notice.ok && notice.remade ? (
        <Link href="/create" className="font-medium underline underline-offset-4">
          Suivre dans Création
        </Link>
      ) : null}
    </p>
  );
}

/** Refaire (avec ces images : le storyboard revient tel quel ; nouvelles images : réglages actuels) ou retirer. */
function FavoriteActions({
  favorite,
  pending,
  onOpen,
  onRemake,
  onDelete,
}: {
  favorite: Favorite;
  pending: boolean;
  onOpen?: () => void;
  onRemake: (keepImages: boolean) => void;
  onDelete: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {onOpen ? (
        <Button variant="outline" size="sm" onClick={onOpen}>
          <Eye />
          Revoir
        </Button>
      ) : null}
      <ConfirmButton variant="ghost" size="sm" disabled={pending} onConfirm={onDelete} confirmLabel="Confirmer : retirer et effacer ses images">
        <Trash2 />
        Retirer
      </ConfirmButton>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={pending}
          onClick={() => onRemake(false)}
          title="Même idée et même script ; les images sont refaites avec les modèles des réglages actuels"
        >
          <Sparkles />
          Nouvelles images
        </Button>
        {favorite.images.length > 0 ? (
          <Button
            size="sm"
            disabled={pending}
            onClick={() => onRemake(true)}
            title="Le storyboard revient dans Création avec ces images, prêt à valider ; les clips suivront le modèle vidéo des réglages actuels"
            className="bg-emerald-600 text-white hover:bg-emerald-700 dark:bg-emerald-600 dark:hover:bg-emerald-500"
          >
            <Repeat />
            Refaire avec ces images
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function SceneStrip({ favorite, onOpen }: { favorite: Favorite; onOpen: () => void }) {
  return (
    <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
      {shotsOf(favorite).map(({ scene, image, number }) =>
        number === null ? (
          <span key={scene.index} className="text-muted-foreground flex w-5 shrink-0 items-center justify-center" title="Passage vers la pièce suivante">
            <ArrowRight className="size-4" />
          </span>
        ) : (
          <button
            key={scene.index}
            type="button"
            onClick={onOpen}
            className="group relative h-40 w-[5.625rem] shrink-0 overflow-hidden rounded-md border"
            aria-label={`Scène ${number}`}
          >
            {image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={favoriteImageUrl(favorite.id, image.file)} alt="" className="size-full object-cover transition-transform group-hover:scale-105" loading="lazy" />
            ) : (
              <span className="bg-muted text-muted-foreground flex size-full flex-col items-center justify-center gap-1 p-1 text-center text-[10px]">
                <Link2 className="size-4" />
                {scene.continues_previous ? "suite du clip précédent" : "pas d’image"}
              </span>
            )}
            <span className="absolute bottom-1 left-1 rounded bg-black/60 px-1 text-[10px] font-medium text-white tabular-nums">{number}</span>
          </button>
        ),
      )}
    </div>
  );
}

function FavoriteCard({
  favorite,
  showChannel,
  pending,
  notice,
  onOpen,
  onRemake,
  onDelete,
}: {
  favorite: Favorite;
  showChannel: boolean;
  pending: boolean;
  notice: Notice | null;
  onOpen: () => void;
  onRemake: (keepImages: boolean) => void;
  onDelete: () => void;
}) {
  const shots = shotsOf(favorite);
  const passages = shots.filter((s) => s.number === null).length;
  const waiting = favorite.original_status === "storyboard_review";
  return (
    <li className="bg-card flex min-w-0 flex-col gap-3 rounded-xl border p-4 shadow-xs">
      <div className="flex items-start gap-2">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h3 className="leading-snug font-semibold">{favorite.title}</h3>
          <p className="text-muted-foreground text-xs">
            {[
              showChannel ? favorite.channel_name : null,
              favorite.series_name,
              `${shots.length - passages} scènes${passages ? ` · ${passages} passages` : ""}`,
              `gardé le ${formatDate(favorite.created_at, "d MMM")}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <Star className="mt-0.5 size-4 shrink-0 fill-amber-400 text-amber-500" aria-label="favori" />
      </div>
      {favorite.hook ? <p className="text-muted-foreground line-clamp-2 text-sm">{favorite.hook}</p> : null}
      <SceneStrip favorite={favorite} onOpen={onOpen} />
      <p className="text-muted-foreground flex flex-wrap items-center gap-x-1.5 text-xs">
        {[originalLabel(favorite.original_status), remadeLine(favorite)].filter(Boolean).join(" · ")}
        {waiting ? (
          <Link href="/create#storyboards" className="text-foreground font-medium underline underline-offset-4">
            l’ouvrir
          </Link>
        ) : null}
      </p>
      <FavoriteActions favorite={favorite} pending={pending} onOpen={onOpen} onRemake={onRemake} onDelete={onDelete} />
      {notice ? <NoticeLine notice={notice} className="text-xs" /> : null}
    </li>
  );
}

/** Le favori en grand : chaque scène avec son image, son texte et sa description, puis les mêmes gestes. */
function FavoriteSheet({
  favorite,
  pending,
  notice,
  onClose,
  onRemake,
  onDelete,
}: {
  favorite: Favorite | null;
  pending: boolean;
  notice: Notice | null;
  onClose: () => void;
  onRemake: (keepImages: boolean) => void;
  onDelete: () => void;
}) {
  const lang = favorite ? langOf(favorite) : "fr";
  return (
    <Sheet
      open={favorite !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-3xl">
        {favorite ? (
          <>
            <SheetHeader className="border-b pr-12">
              <SheetTitle className="leading-snug">{favorite.title}</SheetTitle>
              <SheetDescription>
                {[favorite.channel_name, favorite.series_name, `gardé le ${formatDateTime(favorite.created_at)}`].filter(Boolean).join(" · ")}
              </SheetDescription>
            </SheetHeader>
            <ScrollArea className="min-h-0 flex-1">
              <div className="flex flex-col gap-4 p-4">
                {favorite.hook ? <p className="text-sm font-medium">{favorite.hook}</p> : null}
                {favorite.premise ? <p className="text-muted-foreground text-sm">{favorite.premise}</p> : null}
                <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
                  {favorite.image_workflow ? <span>Images : {favorite.image_workflow}</span> : null}
                  {favorite.video_provider ? <span>Vidéo de l’original : {videoProviderLabel(favorite.video_provider)}</span> : null}
                  <span>{originalLabel(favorite.original_status)}</span>
                  {remadeLine(favorite) ? <span>{remadeLine(favorite)}</span> : null}
                </div>
                <ol className="flex flex-col gap-3">
                  {shotsOf(favorite).map(({ scene, image, number }) =>
                    number === null ? (
                      <li key={scene.index} className="text-muted-foreground flex items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-xs">
                        <ArrowRight className="size-3.5 shrink-0" />
                        Passage vers la pièce suivante : le clip relie deux images.
                      </li>
                    ) : (
                      <li key={scene.index} className="flex gap-3 rounded-lg border p-3">
                        {image ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={favoriteImageUrl(favorite.id, image.file)} alt={`Scène ${number}`} className="h-48 w-27 shrink-0 rounded-md object-cover" loading="lazy" />
                        ) : (
                          <span className="bg-muted text-muted-foreground flex h-48 w-27 shrink-0 flex-col items-center justify-center gap-1 rounded-md p-2 text-center text-[11px]">
                            <Link2 className="size-4" />
                            {scene.continues_previous ? "suite du clip précédent" : "pas d’image gardée"}
                          </span>
                        )}
                        <div className="flex min-w-0 flex-col gap-1.5">
                          <div className="flex flex-wrap items-center gap-2 text-xs">
                            <span className="font-medium">Scène {number}</span>
                            {scene.role ? <Badge variant="outline">{ROLE_LABELS[scene.role] ?? scene.role}</Badge> : null}
                          </div>
                          {scene.narration?.[lang] || scene.on_screen_text?.[lang] ? (
                            <p className="text-sm">{scene.narration?.[lang] || scene.on_screen_text?.[lang]}</p>
                          ) : null}
                          <p className="text-muted-foreground line-clamp-5 text-xs">{scene.visual_prompt}</p>
                          {image?.qc && !image.qc.ok ? (
                            <p className="flex gap-1 text-xs text-amber-700 dark:text-amber-400">
                              <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                              Contrôle automatique : {image.qc.problems.join(" ; ")}
                            </p>
                          ) : null}
                        </div>
                      </li>
                    ),
                  )}
                </ol>
              </div>
            </ScrollArea>
            <div className="flex flex-col gap-2 border-t p-4">
              <FavoriteActions favorite={favorite} pending={pending} onRemake={onRemake} onDelete={onDelete} />
              {notice ? <NoticeLine notice={notice} className="text-xs" /> : null}
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

/** Page Favoris : les storyboards gardés avec l'étoile, à revoir et à refaire (docs/19). */
export function FavoritesView({ favorites, showChannel }: { favorites: Favorite[]; showChannel: boolean }) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [openId, setOpenId] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<Notice | null>(null);
  const [query, setQuery] = React.useState("");

  const q = query.trim().toLowerCase();
  const visible = favorites.filter((f) => !q || `${f.title} ${f.hook ?? ""} ${f.series_name ?? ""}`.toLowerCase().includes(q));
  const open = favorites.find((f) => f.id === openId) ?? null;

  const remake = (id: string, keepImages: boolean) =>
    startTransition(async () => {
      const res = await remakeFavorite(id, keepImages);
      setNotice({ id, ...res, remade: res.ok });
      router.refresh();
    });
  const remove = (id: string) =>
    startTransition(async () => {
      const res = await deleteFavorite(id);
      setNotice({ id: res.ok ? null : id, ...res });
      if (res.ok) setOpenId(null);
      router.refresh();
    });
  const noticeFor = (id: string) => (notice?.id === id ? notice : null);

  if (favorites.length === 0) {
    return (
      <div className="text-muted-foreground flex flex-col items-center gap-2 rounded-xl border border-dashed p-10 text-center text-sm">
        <Star className="size-6" />
        <p>Aucun favori pour l’instant.</p>
        <p className="max-w-md">
          Dans Création, l’étoile d’un storyboard le garde ici avec son idée, son script et ses images, même si tu l’abandonnes ensuite. La fiche d’une vidéo de
          la Bibliothèque a la même étoile.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-muted-foreground text-sm">
          {visible.length} favori{visible.length > 1 ? "s" : ""}
        </span>
        {favorites.length > 6 ? (
          <div className="relative w-full sm:ml-auto sm:w-64">
            <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Chercher un titre, un thème…" className="pl-8" aria-label="Chercher" />
          </div>
        ) : null}
      </div>
      {notice && notice.id === null ? <NoticeLine notice={notice} /> : null}
      <ul className="grid gap-4 xl:grid-cols-2">
        {visible.map((f) => (
          <FavoriteCard
            key={f.id}
            favorite={f}
            showChannel={showChannel}
            pending={pending}
            notice={noticeFor(f.id)}
            onOpen={() => setOpenId(f.id)}
            onRemake={(keep) => remake(f.id, keep)}
            onDelete={() => remove(f.id)}
          />
        ))}
      </ul>
      <FavoriteSheet
        favorite={open}
        pending={pending}
        notice={open ? noticeFor(open.id) : null}
        onClose={() => setOpenId(null)}
        onRemake={(keep) => open && remake(open.id, keep)}
        onDelete={() => open && remove(open.id)}
      />
    </div>
  );
}
