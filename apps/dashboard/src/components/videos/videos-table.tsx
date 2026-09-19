"use client";

import * as React from "react";
import {
  columnFilteringFeature,
  createColumnHelper,
  createFilteredRowModel,
  createSortedRowModel,
  filterFn_equalsString,
  filterFn_includesString,
  flexRender,
  globalFilteringFeature,
  rowSortingFeature,
  sortFn_basic,
  sortFn_text,
  tableFeatures,
  useTable,
  type ColumnFiltersState,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown, Search } from "lucide-react";

import { fetchVideoDetail } from "@/app/videos/actions";
import { ChannelBadge } from "@/components/channel-badge";
import { FormatBadge } from "@/components/format-badge";
import { Poster } from "@/components/poster";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { VideoDetailSheet } from "@/components/videos/video-detail-sheet";
import type { VideoDetail } from "@/lib/data/contract";
import { formatDateTime, formatDuration, formatNumber, formatPercent, formatSigned } from "@/lib/format";
import { categoryLabel, categoryMeta } from "@/lib/labels";
import type { ChannelLang, VideoOverview } from "@/lib/types";
import { cn } from "@/lib/utils";

const features = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  rowSortingFeature,
  filteredRowModel: createFilteredRowModel(),
  sortedRowModel: createSortedRowModel(),
  filterFns: { includesString: filterFn_includesString, equalsString: filterFn_equalsString },
  sortFns: { basic: sortFn_basic, text: sortFn_text },
});

const helper = createColumnHelper<typeof features, VideoOverview>();

const NUMERIC_COLUMNS = new Set(["views", "likes", "comments", "average_view_pct", "subscribers_gained"]);

const columns = helper.columns([
  helper.display({
    id: "poster",
    header: () => <span className="sr-only">Vignette</span>,
    cell: ({ row }) => <Poster category={row.original.category} />,
  }),
  helper.accessor("title", {
    header: "Titre",
    filterFn: "includesString",
    sortFn: "text",
    cell: ({ row }) => (
      <div className="flex max-w-[26rem] min-w-[14rem] flex-col gap-0.5 whitespace-normal">
        <span className="line-clamp-2 font-medium">{row.original.title ?? "Sans titre"}</span>
        <span className="text-muted-foreground text-xs tabular-nums">{formatDuration(row.original.duration_s)}</span>
      </div>
    ),
  }),
  helper.accessor("channel_slug", {
    header: "Chaîne",
    filterFn: "equalsString",
    sortFn: "text",
    cell: ({ getValue }) => <ChannelBadge lang={getValue() as ChannelLang} />,
  }),
  helper.accessor("format", {
    header: "Format",
    filterFn: "equalsString",
    sortFn: "text",
    cell: ({ getValue }) => <FormatBadge format={getValue()} />,
  }),
  helper.accessor((row) => categoryLabel(row.category), {
    id: "category",
    header: "Catégorie",
    filterFn: "includesString",
    sortFn: "text",
    cell: ({ row, getValue }) => (
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden>{categoryMeta(row.original.category).emoji}</span>
        {getValue()}
      </span>
    ),
  }),
  helper.accessor("published_at", {
    header: "Publiée le",
    sortFn: "basic",
    cell: ({ getValue }) => {
      const value = getValue();
      return <span className="tabular-nums">{value ? formatDateTime(value) : "—"}</span>;
    },
  }),
  helper.accessor("views", {
    header: "Vues",
    sortFn: "basic",
    cell: ({ getValue }) => <span className="tabular-nums">{formatNumber(getValue())}</span>,
  }),
  helper.accessor("likes", {
    header: "Likes",
    sortFn: "basic",
    cell: ({ getValue }) => <span className="tabular-nums">{formatNumber(getValue())}</span>,
  }),
  helper.accessor("comments", {
    header: "Commentaires",
    sortFn: "basic",
    cell: ({ getValue }) => <span className="tabular-nums">{formatNumber(getValue())}</span>,
  }),
  helper.accessor("average_view_pct", {
    header: "Rétention",
    sortFn: "basic",
    cell: ({ getValue }) => <span className="tabular-nums">{formatPercent(getValue(), 1)}</span>,
  }),
  helper.accessor("subscribers_gained", {
    header: "Abonnés",
    sortFn: "basic",
    cell: ({ getValue }) => <span className="tabular-nums">{formatSigned(getValue())}</span>,
  }),
]);

function SortIcon({ direction }: { direction: false | "asc" | "desc" }) {
  if (direction === "asc") return <ArrowUp className="size-3.5" />;
  if (direction === "desc") return <ArrowDown className="size-3.5" />;
  return <ArrowUpDown className="size-3.5 opacity-50" />;
}

export function VideosTable({ videos, initialChannel }: { videos: VideoOverview[]; initialChannel?: ChannelLang }) {
  const [sorting, setSorting] = React.useState<SortingState>([{ id: "published_at", desc: true }]);
  const [globalFilter, setGlobalFilter] = React.useState("");
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>(
    initialChannel ? [{ id: "channel_slug", value: initialChannel }] : []
  );
  const [selected, setSelected] = React.useState<VideoOverview | null>(null);
  const [detail, setDetail] = React.useState<VideoDetail | null>(null);
  const [loading, startTransition] = React.useTransition();
  const latestId = React.useRef<string | null>(null);

  const table = useTable({
    features,
    columns,
    data: videos,
    getRowId: (row) => row.id,
    state: { sorting, columnFilters, globalFilter },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    globalFilterFn: "includesString",
    getColumnCanGlobalFilter: (column) => column.id === "title" || column.id === "category",
  });

  const rows = table.getRowModel().rows;
  const channelFilter = (columnFilters.find((f) => f.id === "channel_slug")?.value as string | undefined) ?? "all";
  const formatFilter = (columnFilters.find((f) => f.id === "format")?.value as string | undefined) ?? "all";

  function setColumnFilter(id: string, value: string) {
    setColumnFilters((prev) => {
      const rest = prev.filter((f) => f.id !== id);
      return value === "all" ? rest : [...rest, { id, value }];
    });
  }

  function select(video: VideoOverview) {
    latestId.current = video.id;
    setSelected(video);
    setDetail(null);
    startTransition(async () => {
      const result = await fetchVideoDetail(video.id);
      if (latestId.current === video.id) setDetail(result);
    });
  }

  function close() {
    latestId.current = null;
    setSelected(null);
    setDetail(null);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-center">
        <div className="relative md:w-80">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input
            value={globalFilter}
            onChange={(event) => setGlobalFilter(event.target.value)}
            placeholder="Rechercher un titre, une catégorie…"
            aria-label="Recherche"
            className="pl-8"
          />
        </div>
        <Select value={channelFilter} onValueChange={(value) => setColumnFilter("channel_slug", value)}>
          <SelectTrigger className="w-full md:w-44" aria-label="Filtrer par chaîne">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Toutes les chaînes</SelectItem>
            <SelectItem value="fr">Chaîne FR</SelectItem>
            <SelectItem value="en">Channel EN</SelectItem>
          </SelectContent>
        </Select>
        <Select value={formatFilter} onValueChange={(value) => setColumnFilter("format", value)}>
          <SelectTrigger className="w-full md:w-44" aria-label="Filtrer par format">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tous les formats</SelectItem>
            <SelectItem value="A_voiceover">A · voix off</SelectItem>
            <SelectItem value="B_visual">B · visuel</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-muted-foreground text-sm tabular-nums md:ml-auto">
          {rows.length} vidéo{rows.length > 1 ? "s" : ""} sur {videos.length}
        </p>
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id} className="hover:bg-transparent">
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id} className={cn(NUMERIC_COLUMNS.has(header.column.id) && "text-right")}>
                    {header.isPlaceholder ? null : header.column.getCanSort() ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        className={cn("-mx-2 h-8 gap-1 px-2", NUMERIC_COLUMNS.has(header.column.id) && "-mr-2 ml-auto")}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        <SortIcon direction={header.column.getIsSorted()} />
                      </Button>
                    ) : (
                      flexRender(header.column.columnDef.header, header.getContext())
                    )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow
                key={row.id}
                tabIndex={0}
                aria-label={`Détail : ${row.original.title ?? "vidéo"}`}
                className="cursor-pointer outline-none focus-visible:bg-muted/60"
                data-state={selected?.id === row.original.id ? "selected" : undefined}
                onClick={() => select(row.original)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    select(row.original);
                  }
                }}
              >
                {row.getAllCells().map((cell) => (
                  <TableCell key={cell.id} className={cn(NUMERIC_COLUMNS.has(cell.column.id) && "text-right")}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="text-muted-foreground h-24 text-center">
                  Aucune vidéo ne correspond aux filtres.
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>

      <VideoDetailSheet video={selected} detail={detail} loading={loading} onClose={close} />
    </div>
  );
}
