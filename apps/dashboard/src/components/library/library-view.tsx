"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { CheckSquare, CircleCheck, CircleX, Eye, Film, HardDrive, MonitorPlay, Search, Square, Trash2, X } from "lucide-react";

import { deleteVideos } from "@/app/library/actions";
import { ConfirmButton } from "@/components/confirm-button";
import { LibrarySheet, dateLine, libraryTitle } from "@/components/library/library-sheet";
import { Poster } from "@/components/poster";
import { PRODUCTION_STATUS_TONES, ToneBadge, VideoStatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatBytes, formatCompact, formatDuration } from "@/lib/format";
import { LIBRARY_GROUPS, libraryGroup, type LibraryGroup, type LibraryItem } from "@/lib/library-types";
import { cn } from "@/lib/utils";

type Origin = "all" | "app" | "imported";

function thumbnail(v: LibraryItem): string | null {
  if (v.poster_asset_id && !v.files_deleted_at) return `/api/media/${v.poster_asset_id}`;
  if (v.thumbnail_url) return v.thumbnail_url;
  if (v.youtube_video_id) return `https://i.ytimg.com/vi/${v.youtube_video_id}/hqdefault.jpg`;
  // Pas encore montée : une image de son storyboard
  if (v.making?.cover_asset_id) return `/api/media/${v.making.cover_asset_id}`;
  return null;
}

/** Une vignette 9:16 : image, statut, origine, durée et vues ; en mode sélection, une case à cocher. */
function LibraryCard({
  item,
  showChannel,
  selecting,
  selected,
  onOpen,
  onToggle,
}: {
  item: LibraryItem;
  showChannel: boolean;
  selecting: boolean;
  selected: boolean;
  onOpen: () => void;
  onToggle: () => void;
}) {
  const src = thumbnail(item);
  const making = item.making ?? null;
  // En plein calcul : il faut l'arrêter depuis sa fiche avant de la supprimer
  const selectable = item.origin !== "imported" && !item.files_deleted_at && item.status !== "uploading" && !making?.running;
  return (
    <li className="flex min-w-0 flex-col gap-2">
      <button
        type="button"
        onClick={selecting ? (selectable ? onToggle : undefined) : onOpen}
        className={cn(
          "group bg-muted relative aspect-[9/16] w-full overflow-hidden rounded-xl border text-left outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
          selecting && !selectable && "opacity-50",
          selected && "ring-primary ring-2",
        )}
        aria-label={libraryTitle(item)}
      >
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt="" loading="lazy" className="size-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" />
        ) : (
          <Poster category={item.category} className="size-full rounded-none text-4xl" />
        )}
        <span className="absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-black/70 to-transparent" aria-hidden />
        <span className="absolute top-2 left-2 flex flex-wrap gap-1">
          {selecting && selectable ? (
            selected ? (
              <CheckSquare className="bg-primary text-primary-foreground size-6 rounded p-0.5" />
            ) : (
              <Square className="size-6 rounded bg-black/40 p-0.5 text-white" />
            )
          ) : making ? (
            <ToneBadge tone={PRODUCTION_STATUS_TONES[making.status]} className="bg-background/85 max-w-full truncate backdrop-blur">
              {making.stage}
            </ToneBadge>
          ) : (
            <VideoStatusBadge status={item.status} className="bg-background/85 backdrop-blur" />
          )}
        </span>
        {item.origin === "imported" ? (
          <span className="absolute top-2 right-2 flex items-center gap-1 rounded-md bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white" title="Importée de YouTube : pas produite par l’appli">
            <MonitorPlay className="size-3" />
            Importée
          </span>
        ) : null}
        <span className="absolute right-2 bottom-2 left-2 flex items-center gap-2 text-[11px] font-medium text-white tabular-nums">
          {item.youtube_video_id && item.status === "published" ? (
            <span className="flex items-center gap-1">
              <Eye className="size-3" />
              {formatCompact(item.views)}
            </span>
          ) : null}
          {making ? (
            <>
              <span className="h-1 flex-1 overflow-hidden rounded-full bg-white/30" aria-hidden>
                <span className="block h-full rounded-full bg-white" style={{ width: `${making.progress_pct}%` }} />
              </span>
              <span className="rounded bg-black/50 px-1">{making.progress_pct} %</span>
            </>
          ) : (
            <span className="ml-auto rounded bg-black/50 px-1">{formatDuration(item.duration_s)}</span>
          )}
        </span>
      </button>
      <div className="flex min-w-0 flex-col gap-0.5 px-0.5">
        <p className="line-clamp-2 text-sm leading-snug font-medium">{libraryTitle(item)}</p>
        <p className="text-muted-foreground truncate text-xs">
          {[showChannel ? item.channel_name : null, dateLine(item)].filter(Boolean).join(" · ")}
        </p>
        {item.origin !== "imported" ? (
          <p className="text-muted-foreground text-[11px] tabular-nums">
            {item.files_deleted_at ? "fichiers effacés du PC" : `${formatBytes(item.size_bytes)} sur le PC`}
          </p>
        ) : null}
      </div>
    </li>
  );
}

/** Bibliothèque : tout ce qui a été produit (et l'historique importé), filtrable, avec lecture et suppression. */
export function LibraryView({
  items,
  totalBytes,
  initialGroup,
  initialOpenId = null,
  showChannel,
}: {
  items: LibraryItem[];
  totalBytes: number;
  initialGroup: LibraryGroup | null;
  /** Fiche ouverte d'emblée (?video=<id>). */
  initialOpenId?: string | null;
  showChannel: boolean;
}) {
  const router = useRouter();
  const [group, setGroup] = React.useState<LibraryGroup | "all">(initialGroup ?? "all");
  const [origin, setOrigin] = React.useState<Origin>("all");
  const [query, setQuery] = React.useState("");
  const [openId, setOpenId] = React.useState<string | null>(initialOpenId);
  const [selecting, setSelecting] = React.useState(false);
  const [selected, setSelected] = React.useState<Set<string>>(() => new Set());
  const [notice, setNotice] = React.useState<{ ok: boolean; message: string } | null>(null);
  const [pending, startTransition] = React.useTransition();

  const byOrigin = items.filter((v) => origin === "all" || (origin === "imported" ? v.origin === "imported" : v.origin !== "imported"));
  const counts = new Map<LibraryGroup, number>();
  for (const v of byOrigin) counts.set(libraryGroup(v), (counts.get(libraryGroup(v)) ?? 0) + 1);
  const q = query.trim().toLowerCase();
  const visible = byOrigin.filter(
    (v) =>
      (group === "all" || libraryGroup(v) === group) &&
      (!q || `${v.title ?? ""} ${v.making?.concept_title ?? ""} ${v.series_name ?? ""} ${v.hook ?? ""}`.toLowerCase().includes(q)),
  );
  const openItem = items.find((v) => v.id === openId) ?? null;
  const importedCount = items.filter((v) => v.origin === "imported").length;
  const selectedBytes = items.filter((v) => selected.has(v.id)).reduce((s, v) => s + v.size_bytes, 0);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="bg-muted inline-flex flex-wrap rounded-lg p-0.5 text-sm" role="tablist" aria-label="Statut">
          {[{ id: "all" as const, label: "Toutes", n: byOrigin.length }, ...LIBRARY_GROUPS.map((g) => ({ ...g, n: counts.get(g.id) ?? 0 }))]
            .filter((g) => g.id === "all" || g.n > 0 || g.id === group)
            .map((g) => (
              <button
                key={g.id}
                type="button"
                role="tab"
                aria-selected={group === g.id}
                onClick={() => setGroup(g.id)}
                className={cn(
                  "h-8 rounded-md px-3 font-medium transition-colors",
                  group === g.id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {g.label} <span className="tabular-nums opacity-70">{g.n}</span>
              </button>
            ))}
        </div>
        {importedCount > 0 ? (
          <div className="bg-muted inline-flex rounded-lg p-0.5 text-sm" role="tablist" aria-label="Origine">
            {(
              [
                ["all", "Toutes"],
                ["app", "Produites ici"],
                ["imported", "Importées"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={origin === id}
                onClick={() => setOrigin(id)}
                className={cn(
                  "h-8 rounded-md px-3 font-medium transition-colors",
                  origin === id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        ) : null}
        <div className="relative w-full sm:ml-auto sm:w-64">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Chercher un titre, un thème…" className="pl-8" aria-label="Chercher" />
        </div>
      </div>

      <div className="text-muted-foreground flex flex-wrap items-center gap-3 text-sm">
        <span className="flex items-center gap-1.5">
          <HardDrive className="size-4" />
          {formatBytes(totalBytes)} sur le PC
        </span>
        <span>·</span>
        <span>
          {visible.length} vidéo{visible.length > 1 ? "s" : ""}
        </span>
        <Button
          variant={selecting ? "secondary" : "outline"}
          size="sm"
          className="ml-auto"
          onClick={() => {
            setSelecting((v) => !v);
            setSelected(new Set());
          }}
        >
          {selecting ? <X /> : <CheckSquare />}
          {selecting ? "Terminer la sélection" : "Sélectionner pour supprimer"}
        </Button>
      </div>

      {notice ? (
        <p className={cn("flex items-center gap-1.5 text-sm", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")} role="status">
          {notice.ok ? <CircleCheck className="size-4" /> : <CircleX className="size-4" />}
          {notice.message}
        </p>
      ) : null}

      {visible.length > 0 ? (
        <ul className="grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
          {visible.map((item) => (
            <LibraryCard
              key={item.id}
              item={item}
              showChannel={showChannel}
              selecting={selecting}
              selected={selected.has(item.id)}
              onOpen={() => setOpenId(item.id)}
              onToggle={() => toggle(item.id)}
            />
          ))}
        </ul>
      ) : (
        <div className="text-muted-foreground flex flex-col items-center gap-2 rounded-xl border border-dashed p-10 text-center text-sm">
          <Film className="size-6" />
          <p>{items.length === 0 ? "Aucune vidéo pour l’instant : elles arrivent ici dès que leur script est écrit." : "Aucune vidéo ne correspond à ces filtres."}</p>
        </div>
      )}

      {selecting && selected.size > 0 ? (
        <div className="bg-background/95 sticky bottom-4 z-20 mx-auto flex w-full max-w-xl items-center gap-3 rounded-xl border p-3 shadow-lg backdrop-blur">
          <span className="text-sm">
            {selected.size} sélectionnée{selected.size > 1 ? "s" : ""} · {formatBytes(selectedBytes)}
          </span>
          <ConfirmButton
            size="sm"
            variant="outline"
            className="ml-auto"
            disabled={pending}
            confirmLabel="Confirmer la suppression"
            onConfirm={() =>
              startTransition(async () => {
                const res = await deleteVideos([...selected]);
                setNotice(res);
                setSelected(new Set());
                setSelecting(false);
                router.refresh();
              })
            }
          >
            <Trash2 />
            Supprimer
          </ConfirmButton>
        </div>
      ) : null}

      <LibrarySheet
        item={openItem}
        onClose={() => {
          setOpenId(null);
          const url = new URL(window.location.href);
          if (url.searchParams.has("video")) {
            url.searchParams.delete("video");
            window.history.replaceState(null, "", url);
          }
          router.refresh();
        }}
      />
    </div>
  );
}
