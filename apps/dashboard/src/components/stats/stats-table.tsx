"use client";

import * as React from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, Info, Music, Search } from "lucide-react";

import { FORMAT_DOT, FORMAT_HINTS, FORMAT_LABELS, FORMAT_ORDER, formatKey, type FormatKey } from "@/components/stats/formats";
import { ToneBadge, type Tone } from "@/components/status-badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatDate, formatDuration, formatNumber, formatPercent, formatRelative, formatSigned } from "@/lib/format";
import { VERDICT_LABELS, type StatsVideo, type Verdict } from "@/lib/stats-types";
import { cn } from "@/lib/utils";

type SortKey =
  | "published"
  | "duration"
  | "views"
  | "views_24h"
  | "score"
  | "retention"
  | "hook"
  | "avg_duration"
  | "likes"
  | "comments"
  | "shares"
  | "subs"
  | "engaged";
type Dir = "asc" | "desc";
type VerdictFilter = "all" | "top" | "flop";

export const VERDICT_TONES: Record<Verdict, Tone> = { top: "success", moyen: "neutral", flop: "danger", "trop récente": "info" };

const LATER = " YouTube Analytics la publie 2 à 3 jours après la mise en ligne.";

interface Column {
  key: SortKey;
  label: string;
  hint: string;
  value: (v: StatsVideo) => number | null | undefined;
  cell: (v: StatsVideo, maxViews: number) => React.ReactNode;
}

function thumbnail(v: StatsVideo): string | null {
  if (v.poster_asset_id && !v.files_deleted_at) return `/api/media/${v.poster_asset_id}`;
  if (v.thumbnail_url) return v.thumbnail_url;
  if (v.youtube_video_id) return `https://i.ytimg.com/vi/${v.youtube_video_id}/hqdefault.jpg`;
  return null;
}

/** Couleur de la note : celle du verdict (un ×1,4 deuxième sur quatre reste « moyen »). */
function scoreClass(verdict: Verdict): string {
  if (verdict === "top") return "text-emerald-600 dark:text-emerald-400";
  if (verdict === "flop") return "text-red-600 dark:text-red-400";
  return verdict === "trop récente" ? "text-muted-foreground" : "";
}

const muted = <span className="text-muted-foreground">—</span>;
const num = (n: number | null | undefined, digits = 0) => (n === null || n === undefined ? muted : formatNumber(n, digits));
const pct = (n: number | null | undefined, digits = 0) => (n === null || n === undefined ? muted : formatPercent(n, digits));

function columns(median: number | null): Column[] {
  return [
    {
      key: "published",
      label: "Publiée",
      hint: "Date de mise en ligne (heure de Paris).",
      value: (v) => (v.published_at ? new Date(v.published_at).getTime() : null),
      cell: (v) =>
        v.published_at ? (
          <div className="flex flex-col">
            <span className="capitalize">{formatDate(v.published_at, "EEE d MMM")}</span>
            <span className="text-muted-foreground text-xs" suppressHydrationWarning>
              {formatRelative(v.published_at)}
            </span>
          </div>
        ) : (
          muted
        ),
    },
    { key: "duration", label: "Durée", hint: "Durée de la vidéo.", value: (v) => v.duration_s, cell: (v) => formatDuration(v.duration_s) },
    {
      key: "views",
      label: "Vues",
      hint: "Compteur public de YouTube, relevé chaque heure.",
      value: (v) => v.views,
      cell: (v, maxViews) => (
        <div className="flex min-w-24 flex-col gap-1">
          <span className="font-medium">{formatNumber(v.views)}</span>
          <span className="bg-muted h-1 w-full overflow-hidden rounded-full" aria-hidden>
            <span className="block h-full rounded-full bg-[#2a78d6] dark:bg-[#3987e5]" style={{ width: `${maxViews ? Math.max(2, (v.views / maxViews) * 100) : 0}%` }} />
          </span>
        </div>
      ),
    },
    {
      key: "score",
      label: "Note",
      hint: `Vues de la vidéo (à 7 jours si elle est plus ancienne) ÷ médiane de la chaîne${median !== null ? ` (${formatNumber(median)} vues)` : ""}. ×2 : deux fois plus que la vidéo « du milieu ». Top à ×1,25 et plus, flop à ×0,8 et moins (vidéos de plus de 24 h).`,
      value: (v) => v.score,
      cell: (v) => (v.score === null ? muted : <span className={cn("font-medium", scoreClass(v.verdict))}>×{formatNumber(v.score, v.score >= 10 ? 0 : 2)}</span>),
    },
    {
      key: "views_24h",
      label: "Vues 24 h",
      hint: "Vues 24 h après la mise en ligne, d’après les relevés horaires (vidéos publiées depuis le 28 septembre 2026).",
      value: (v) => v.views_24h,
      cell: (v) => num(v.views_24h),
    },
    {
      key: "retention",
      label: "Rétention",
      hint: `Part moyenne de la vidéo regardée. Au-delà de 100 % : des gens la revoient en boucle.${LATER}`,
      value: (v) => v.average_view_pct,
      cell: (v) => pct(v.average_view_pct, 1),
    },
    {
      key: "hook",
      label: "À 3 s",
      hint: `Part des spectateurs encore là à 3 secondes : l’accroche a-t-elle retenu ? (courbe de rétention)${LATER}`,
      value: (v) => v.hook_retention_pct,
      cell: (v) => pct(v.hook_retention_pct),
    },
    {
      key: "avg_duration",
      label: "Durée vue",
      hint: `Durée moyenne regardée par vue.${LATER}`,
      value: (v) => v.average_view_duration_s,
      cell: (v) => (v.average_view_duration_s === null || v.average_view_duration_s === undefined ? muted : `${formatNumber(v.average_view_duration_s, 1)} s`),
    },
    {
      key: "likes",
      label: "J’aime",
      hint: "J’aime, et leur part dans les vues.",
      value: (v) => v.likes,
      cell: (v) => (
        <div className="flex flex-col">
          <span>{formatNumber(v.likes)}</span>
          <span className="text-muted-foreground text-xs">{v.like_rate_pct === null ? "—" : formatPercent(v.like_rate_pct, 1)}</span>
        </div>
      ),
    },
    { key: "comments", label: "Comm.", hint: "Commentaires.", value: (v) => v.comments, cell: (v) => formatNumber(v.comments) },
    { key: "shares", label: "Partages", hint: `Partages.${LATER}`, value: (v) => v.shares, cell: (v) => num(v.shares) },
    {
      key: "subs",
      label: "Abonnés",
      hint: `Abonnés gagnés grâce à la vidéo (moins ceux perdus).${LATER}`,
      value: (v) => (v.subscribers_gained === null ? null : (v.subscribers_gained ?? 0) - (v.subscribers_lost ?? 0)),
      cell: (v) => (v.subscribers_gained === null ? muted : formatSigned((v.subscribers_gained ?? 0) - (v.subscribers_lost ?? 0))),
    },
    {
      key: "engaged",
      label: "Engagées",
      hint: `Vues engagées ÷ vues : lectures poursuivies au-delà de la première image. Ce sont elles qui comptent pour les revenus des Shorts.${LATER}`,
      value: (v) => v.engaged_pct,
      cell: (v) => pct(v.engaged_pct),
    },
  ];
}

function HeaderHint({ label, hint }: { label: string; hint: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="text-muted-foreground/70 inline-flex cursor-help" aria-label={`À propos de ${label}`}>
          <Info className="size-3" />
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-72 text-xs leading-snug">{hint}</TooltipContent>
    </Tooltip>
  );
}

/** Toutes les vidéos publiées de la période, triables par n'importe quelle colonne ; un clic ouvre la fiche. */
export function StatsTable({ videos, median, showChannel, onOpen }: { videos: StatsVideo[]; median: number | null; showChannel: boolean; onOpen: (id: string) => void }) {
  const [sort, setSort] = React.useState<{ key: SortKey; dir: Dir }>({ key: "published", dir: "desc" });
  const [format, setFormat] = React.useState<FormatKey | "all">("all");
  const [verdict, setVerdict] = React.useState<VerdictFilter>("all");
  const [query, setQuery] = React.useState("");
  const cols = columns(median);
  const present = FORMAT_ORDER.filter((f) => videos.some((v) => formatKey(v) === f));

  const q = query.trim().toLowerCase();
  const visible = videos.filter(
    (v) =>
      (format === "all" || formatKey(v) === format) &&
      (verdict === "all" || v.verdict === verdict) &&
      (!q || `${v.title ?? ""} ${v.series_name ?? ""}`.toLowerCase().includes(q)),
  );
  const col = cols.find((c) => c.key === sort.key) ?? cols[0];
  const sorted = [...visible].sort((a, b) => {
    const x = col.value(a);
    const y = col.value(b);
    if (x === null || x === undefined) return y === null || y === undefined ? 0 : 1; // sans valeur : toujours à la fin
    if (y === null || y === undefined) return -1;
    return sort.dir === "asc" ? x - y : y - x;
  });
  const maxViews = Math.max(0, ...videos.map((v) => v.views));
  const toggle = (key: SortKey) => setSort((s) => (s.key === key ? { key, dir: s.dir === "desc" ? "asc" : "desc" } : { key, dir: "desc" }));

  // Totaux des lignes affichées (moyennes pondérées par les vues)
  const sum = (f: (v: StatsVideo) => number | null | undefined) => sorted.reduce((s, v) => s + (f(v) ?? 0), 0);
  const weighted = (f: (v: StatsVideo) => number | null | undefined) => {
    const list = sorted.filter((v) => f(v) !== null && f(v) !== undefined);
    const w = list.reduce((s, v) => s + v.views, 0);
    return w > 0 ? list.reduce((s, v) => s + (f(v) ?? 0) * v.views, 0) / w : null;
  };
  const totalViews = sum((v) => v.views);

  const segmented = (value: string, current: string, set: () => void, label: React.ReactNode) => (
    <button
      key={value}
      type="button"
      role="tab"
      aria-selected={current === value}
      onClick={set}
      className={cn(
        "flex h-8 items-center gap-1.5 rounded-md px-3 font-medium transition-colors",
        current === value ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {present.length > 1 ? (
          <div className="bg-muted inline-flex flex-wrap rounded-lg p-0.5 text-sm" role="tablist" aria-label="Format">
            {segmented("all", format, () => setFormat("all"), "Tous les formats")}
            {present.map((f) =>
              segmented(
                f,
                format,
                () => setFormat(f),
                <>
                  <span className={cn("size-2 rounded-full", FORMAT_DOT[f])} />
                  {FORMAT_LABELS[f]}
                </>,
              ),
            )}
          </div>
        ) : null}
        <div className="bg-muted inline-flex rounded-lg p-0.5 text-sm" role="tablist" aria-label="Verdict">
          {segmented("all", verdict, () => setVerdict("all"), "Toutes")}
          {segmented("top", verdict, () => setVerdict("top"), "Tops")}
          {segmented("flop", verdict, () => setVerdict("flop"), "Flops")}
        </div>
        <div className="relative w-full sm:ml-auto sm:w-64">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Chercher un titre, un thème…" className="pl-8" aria-label="Chercher une vidéo" />
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border">
        <Table className="text-sm">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="bg-card sticky left-0 z-10 min-w-64">Vidéo</TableHead>
              {cols.map((c) => (
                <TableHead key={c.key} className="text-right" aria-sort={sort.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
                  <span className="inline-flex items-center justify-end gap-1">
                    <HeaderHint label={c.label} hint={c.hint} />
                    <button type="button" onClick={() => toggle(c.key)} className="hover:text-foreground inline-flex items-center gap-1 font-medium">
                      {c.label}
                      {sort.key === c.key ? sort.dir === "asc" ? <ArrowUp className="size-3.5" /> : <ArrowDown className="size-3.5" /> : <ArrowUpDown className="size-3.5 opacity-40" />}
                    </button>
                  </span>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((v) => {
              const src = thumbnail(v);
              const f = formatKey(v);
              return (
                <TableRow key={v.id} className="group cursor-pointer" onClick={() => onOpen(v.id)}>
                  <TableCell className="bg-card group-hover:bg-muted sticky left-0 z-10 min-w-64 whitespace-normal">
                    <div className="flex items-center gap-3">
                      {src ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={src} alt="" loading="lazy" className="bg-muted aspect-[9/16] w-9 shrink-0 rounded-md object-cover" />
                      ) : (
                        <span className="bg-muted aspect-[9/16] w-9 shrink-0 rounded-md" />
                      )}
                      <div className="flex min-w-0 flex-col gap-1">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpen(v.id);
                          }}
                          className="line-clamp-2 max-w-72 text-left leading-snug font-medium hover:underline"
                        >
                          {v.title ?? "Sans titre"}
                        </button>
                        <div className="flex flex-wrap items-center gap-1.5 text-xs">
                          <span className="text-muted-foreground flex items-center gap-1" title={FORMAT_HINTS[f]}>
                            <span className={cn("size-2 rounded-full", FORMAT_DOT[f])} />
                            {FORMAT_LABELS[f]}
                          </span>
                          {v.verdict !== "moyen" ? (
                            <ToneBadge tone={VERDICT_TONES[v.verdict]} className="px-1.5 py-0 text-[11px]">
                              {VERDICT_LABELS[v.verdict]}
                            </ToneBadge>
                          ) : null}
                          {v.music_title || v.music_track ? (
                            <span className="text-muted-foreground flex items-center gap-1" title="Musique posée au montage">
                              <Music className="size-3" />
                              {v.music_title ?? v.music_track}
                            </span>
                          ) : null}
                          {showChannel && v.channel_name ? <span className="text-muted-foreground">{v.channel_name}</span> : null}
                        </div>
                      </div>
                    </div>
                  </TableCell>
                  {cols.map((c) => (
                    <TableCell key={c.key} className="text-right tabular-nums">
                      {c.cell(v, maxViews)}
                    </TableCell>
                  ))}
                </TableRow>
              );
            })}
            {sorted.length === 0 ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={cols.length + 1} className="text-muted-foreground py-10 text-center">
                  {videos.length === 0 ? "Aucune vidéo publiée sur cette période." : "Aucune vidéo ne correspond à ces filtres."}
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
          {sorted.length > 1 ? (
            <TableFooter>
              <TableRow className="hover:bg-transparent">
                <TableCell className="bg-muted sticky left-0 z-10 font-medium">
                  {sorted.length} vidéos · total et moyennes
                </TableCell>
                {cols.map((c) => {
                  let content: React.ReactNode = "";
                  if (c.key === "views") content = formatNumber(totalViews);
                  else if (c.key === "retention") content = pct(weighted((v) => v.average_view_pct), 1);
                  else if (c.key === "hook") content = pct(weighted((v) => v.hook_retention_pct));
                  else if (c.key === "avg_duration") {
                    const d = weighted((v) => v.average_view_duration_s);
                    content = d === null ? muted : `${formatNumber(d, 1)} s`;
                  } else if (c.key === "likes") content = formatNumber(sum((v) => v.likes));
                  else if (c.key === "comments") content = formatNumber(sum((v) => v.comments));
                  else if (c.key === "shares") content = sorted.some((v) => v.shares !== null) ? formatNumber(sum((v) => v.shares)) : muted;
                  else if (c.key === "subs")
                    content = sorted.some((v) => v.subscribers_gained !== null) ? formatSigned(sum((v) => c.value(v))) : muted;
                  return (
                    <TableCell key={c.key} className="text-right font-medium tabular-nums">
                      {content}
                    </TableCell>
                  );
                })}
              </TableRow>
            </TableFooter>
          ) : null}
        </Table>
      </div>
    </div>
  );
}
