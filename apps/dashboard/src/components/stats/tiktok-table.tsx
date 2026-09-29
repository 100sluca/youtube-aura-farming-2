"use client";

import * as React from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ExternalLink, Search } from "lucide-react";

import { FORMAT_DOT, FORMAT_HINTS, FORMAT_LABELS, FORMAT_ORDER, formatKey, type FormatKey } from "@/components/stats/formats";
import { HeaderHint, VERDICT_TONES } from "@/components/stats/stats-table";
import { ToneBadge } from "@/components/status-badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatDuration, formatNumber, formatPercent, formatRelative, formatSigned } from "@/lib/format";
import { VERDICT_LABELS } from "@/lib/stats-types";
import type { TikTokStatsVideo } from "@/lib/tiktok-stats-types";
import { cn } from "@/lib/utils";

type SortKey =
  | "published"
  | "duration"
  | "views"
  | "score"
  | "views_24h"
  | "watched"
  | "completion"
  | "avg_watch"
  | "likes"
  | "comments"
  | "shares"
  | "saves"
  | "follows"
  | "for_you"
  | "youtube";
type Dir = "asc" | "desc";
type VerdictFilter = "all" | "top" | "flop";

const LATER = " TikTok le donne 24 à 48 h après la sortie, pour les vidéos vues dans les 7 derniers jours.";

interface Column {
  key: SortKey;
  label: string;
  hint: string;
  value: (v: TikTokStatsVideo) => number | null | undefined;
  cell: (v: TikTokStatsVideo, maxViews: number) => React.ReactNode;
}

const muted = <span className="text-muted-foreground">—</span>;
const num = (n: number | null | undefined, digits = 0) => (n === null || n === undefined ? muted : formatNumber(n, digits));
const pct = (n: number | null | undefined, digits = 0) => (n === null || n === undefined ? muted : formatPercent(n, digits));

function scoreClass(v: TikTokStatsVideo): string {
  if (v.verdict === "top") return "text-emerald-600 dark:text-emerald-400";
  if (v.verdict === "flop") return "text-red-600 dark:text-red-400";
  return v.verdict === "trop récente" ? "text-muted-foreground" : "";
}

function columns(median: number | null): Column[] {
  return [
    {
      key: "published",
      label: "Sortie",
      hint: "Date de sortie sur TikTok (heure de Paris).",
      value: (v) => new Date(v.published_at).getTime(),
      cell: (v) => (
        <div className="flex flex-col">
          <span className="capitalize">{formatDate(v.published_at, "EEE d MMM")}</span>
          <span className="text-muted-foreground text-xs" suppressHydrationWarning>
            {formatRelative(v.published_at)}
          </span>
        </div>
      ),
    },
    { key: "duration", label: "Durée", hint: "Durée de la vidéo (vidéos de l’appli).", value: (v) => v.duration_s, cell: (v) => (v.duration_s ? formatDuration(v.duration_s) : muted) },
    {
      key: "views",
      label: "Vues",
      hint: "Compteur de TikTok, relevé chaque heure. « — » : vidéo tout juste sortie, Zernio relève ses vues toutes les 90 min environ.",
      value: (v) => (v.views_pending ? null : v.views),
      cell: (v, maxViews) =>
        v.views_pending ? (
          <span className="text-muted-foreground" title="Tout juste sortie : Zernio relève ses vues toutes les 90 min environ">
            —
          </span>
        ) : (
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
      hint: `Vues de la vidéo (à 7 jours si elle est plus ancienne) ÷ médiane du compte${median !== null ? ` (${formatNumber(median)} vues)` : ""}. Mêmes règles que sur YouTube : top à ×1,25 et plus, flop à ×0,8 et moins (vidéos de plus de 24 h).`,
      value: (v) => v.score,
      cell: (v) => (v.score === null ? muted : <span className={cn("font-medium", scoreClass(v))}>×{formatNumber(v.score, v.score >= 10 ? 0 : 2)}</span>),
    },
    { key: "views_24h", label: "Vues 24 h", hint: "Vues 24 h après la sortie, d’après les relevés horaires.", value: (v) => v.views_24h, cell: (v) => num(v.views_24h) },
    {
      key: "watched",
      label: "Regardée",
      hint: `Durée moyenne regardée ÷ durée de la vidéo : l’équivalent de la rétention de YouTube. Au-delà de 100 % : revue en boucle.${LATER}`,
      value: (v) => v.watched_pct,
      cell: (v) => pct(v.watched_pct),
    },
    {
      key: "completion",
      label: "Jusqu’au bout",
      hint: `Part des spectateurs allés jusqu’à la fin : le chiffre que TikTok regarde le plus pour pousser une vidéo.${LATER}`,
      value: (v) => v.completion_pct,
      cell: (v) => pct(v.completion_pct),
    },
    {
      key: "avg_watch",
      label: "Durée vue",
      hint: `Durée moyenne regardée par vue.${LATER}`,
      value: (v) => v.avg_watch_s,
      cell: (v) => (v.avg_watch_s === null ? muted : `${formatNumber(v.avg_watch_s, 1)} s`),
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
    { key: "shares", label: "Partages", hint: "Partages.", value: (v) => v.shares, cell: (v) => formatNumber(v.shares) },
    { key: "saves", label: "Enreg.", hint: `Ajouts aux favoris.${LATER}`, value: (v) => v.saves, cell: (v) => num(v.saves) },
    { key: "follows", label: "Abonnés", hint: `Abonnés gagnés grâce à la vidéo.${LATER}`, value: (v) => v.follows, cell: (v) => (v.follows === null ? muted : formatSigned(v.follows)) },
    {
      key: "for_you",
      label: "Pour toi",
      hint: `Part des vues venues du fil « Pour toi » : TikTok la montre à des inconnus. Le reste vient des abonnés, de la recherche, du profil…${LATER}`,
      value: (v) => v.for_you_pct,
      cell: (v) => pct(v.for_you_pct),
    },
    {
      key: "youtube",
      label: "YouTube",
      hint: "Vues de la même vidéo sur YouTube, pour comparer.",
      value: (v) => v.youtube_views,
      cell: (v) => num(v.youtube_views),
    },
  ];
}

function segmented(value: string, current: string, set: () => void, label: React.ReactNode) {
  return (
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
}

/** Toutes les vidéos TikTok de la période, triables par n'importe quelle colonne ; un clic ouvre la fiche (vidéo de l'appli)
 * ou la vidéo sur TikTok (publiée à la main). */
export function TikTokTable({ videos, median, showAccount, onOpen }: { videos: TikTokStatsVideo[]; median: number | null; showAccount: boolean; onOpen: (v: TikTokStatsVideo) => void }) {
  const [sort, setSort] = React.useState<{ key: SortKey; dir: Dir }>({ key: "published", dir: "desc" });
  const [format, setFormat] = React.useState<FormatKey | "all">("all");
  const [verdict, setVerdict] = React.useState<VerdictFilter>("all");
  const [query, setQuery] = React.useState("");
  const cols = columns(median);
  const present = FORMAT_ORDER.filter((f) => videos.some((v) => formatKey(v) === f));

  const q = query.trim().toLowerCase();
  const visible = videos.filter(
    (v) => (format === "all" || formatKey(v) === format) && (verdict === "all" || v.verdict === verdict) && (!q || `${v.title} ${v.series_name ?? ""}`.toLowerCase().includes(q)),
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

  const sum = (f: (v: TikTokStatsVideo) => number | null | undefined) => sorted.reduce((s, v) => s + (f(v) ?? 0), 0);
  const some = (f: (v: TikTokStatsVideo) => number | null | undefined) => sorted.some((v) => f(v) !== null && f(v) !== undefined);
  const weighted = (f: (v: TikTokStatsVideo) => number | null | undefined) => {
    const list = sorted.filter((v) => f(v) !== null && f(v) !== undefined);
    const w = list.reduce((s, v) => s + v.views, 0);
    return w > 0 ? list.reduce((s, v) => s + (f(v) ?? 0) * v.views, 0) / w : null;
  };

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
                  {f === "imported" ? "Faite dans TikTok" : FORMAT_LABELS[f]}
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
              const f = formatKey(v);
              return (
                <TableRow key={v.id} className="group cursor-pointer" onClick={() => onOpen(v)}>
                  <TableCell className="bg-card group-hover:bg-muted sticky left-0 z-10 min-w-64 whitespace-normal">
                    <div className="flex items-center gap-3">
                      {v.thumbnail ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={v.thumbnail} alt="" loading="lazy" className="bg-muted aspect-[9/16] w-9 shrink-0 rounded-md object-cover" />
                      ) : (
                        <span className="bg-muted aspect-[9/16] w-9 shrink-0 rounded-md" />
                      )}
                      <div className="flex min-w-0 flex-col gap-1">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpen(v);
                          }}
                          className="line-clamp-2 max-w-72 text-left leading-snug font-medium hover:underline"
                        >
                          {v.title}
                        </button>
                        <div className="flex flex-wrap items-center gap-1.5 text-xs">
                          <span className="text-muted-foreground flex items-center gap-1" title={v.item ? FORMAT_HINTS[f] : "Publiée à la main dans TikTok"}>
                            <span className={cn("size-2 rounded-full", FORMAT_DOT[f])} />
                            {v.item ? FORMAT_LABELS[f] : "Faite dans TikTok"}
                          </span>
                          {v.verdict !== "moyen" ? (
                            <ToneBadge tone={VERDICT_TONES[v.verdict]} className="px-1.5 py-0 text-[11px]">
                              {VERDICT_LABELS[v.verdict]}
                            </ToneBadge>
                          ) : null}
                          {showAccount ? <span className="text-muted-foreground">@{v.username}</span> : null}
                          {v.url ? (
                            <a
                              href={v.url}
                              target="_blank"
                              rel="noreferrer noopener"
                              onClick={(e) => e.stopPropagation()}
                              className="text-muted-foreground hover:text-foreground inline-flex items-center gap-0.5"
                              aria-label="Ouvrir sur TikTok"
                            >
                              <ExternalLink className="size-3" />
                            </a>
                          ) : null}
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
                  {videos.length === 0 ? "Aucune vidéo sortie sur TikTok sur cette période." : "Aucune vidéo ne correspond à ces filtres."}
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
          {sorted.length > 1 ? (
            <TableFooter>
              <TableRow className="hover:bg-transparent">
                <TableCell className="bg-muted sticky left-0 z-10 font-medium">{sorted.length} vidéos · total et moyennes</TableCell>
                {cols.map((c) => {
                  let content: React.ReactNode = "";
                  if (c.key === "views") content = formatNumber(sum((v) => v.views));
                  else if (c.key === "watched") content = pct(weighted((v) => v.watched_pct));
                  else if (c.key === "completion") content = pct(weighted((v) => v.completion_pct));
                  else if (c.key === "avg_watch") {
                    const d = weighted((v) => v.avg_watch_s);
                    content = d === null ? muted : `${formatNumber(d, 1)} s`;
                  } else if (c.key === "likes") content = formatNumber(sum((v) => v.likes));
                  else if (c.key === "comments") content = formatNumber(sum((v) => v.comments));
                  else if (c.key === "shares") content = formatNumber(sum((v) => v.shares));
                  else if (c.key === "saves") content = some((v) => v.saves) ? formatNumber(sum((v) => v.saves)) : muted;
                  else if (c.key === "follows") content = some((v) => v.follows) ? formatSigned(sum((v) => v.follows)) : muted;
                  else if (c.key === "for_you") content = pct(weighted((v) => v.for_you_pct));
                  else if (c.key === "youtube") content = some((v) => v.youtube_views) ? formatNumber(sum((v) => v.youtube_views)) : muted;
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
