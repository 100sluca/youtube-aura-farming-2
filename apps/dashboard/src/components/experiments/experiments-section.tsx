import { Clapperboard, Mic, Trophy } from "lucide-react";

import { FormatComparisonChart } from "@/components/experiments/format-comparison-chart";
import { Badge } from "@/components/ui/badge";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ExperimentSummary, FormatSummary } from "@/lib/data";
import { formatCompact, formatNumber, formatPercent } from "@/lib/format";
import { FORMAT_LABELS, categoryMeta } from "@/lib/labels";
import type { VideoFormat } from "@/lib/types";
import { cn } from "@/lib/utils";

type MetricKey = "avg_view_pct" | "views_per_video" | "subs_per_1k_views";

const METRICS: { key: MetricKey; label: string; format: (value: number) => string }[] = [
  { key: "avg_view_pct", label: "Rétention moyenne", format: (v) => formatPercent(v, 1) },
  { key: "views_per_video", label: "Vues / vidéo", format: (v) => formatCompact(v) },
  { key: "subs_per_1k_views", label: "Abonnés / 1 000 vues", format: (v) => formatNumber(v, 2) },
];

function FormatCard({ summary, other }: { summary: FormatSummary; other: FormatSummary | undefined }) {
  const Icon = summary.format === "A_voiceover" ? Mic : Clapperboard;
  const wins = METRICS.filter((m) => other && summary[m.key] > other[m.key]).length;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon className="size-4" />
          {FORMAT_LABELS[summary.format].long}
        </CardTitle>
        <CardDescription>{FORMAT_LABELS[summary.format].description}</CardDescription>
        <CardAction>
          <Badge variant={wins >= 2 ? "default" : "secondary"} className="gap-1">
            {wins >= 2 ? <Trophy className="size-3" /> : null}
            {wins}/{METRICS.length} métriques
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="bg-muted/40 flex flex-col gap-1 rounded-lg border p-3">
          <span className="text-muted-foreground text-xs">Vidéos</span>
          <span className="text-lg font-semibold tabular-nums">{formatNumber(summary.videos)}</span>
        </div>
        {METRICS.map((metric) => {
          const best = other ? summary[metric.key] > other[metric.key] : false;
          return (
            <div key={metric.key} className={cn("bg-muted/40 flex flex-col gap-1 rounded-lg border p-3", best && "border-emerald-500/40")}>
              <span className="text-muted-foreground text-xs">{metric.label}</span>
              <span className={cn("text-lg font-semibold tabular-nums", best && "text-emerald-600 dark:text-emerald-400")}>
                {metric.format(summary[metric.key])}
              </span>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

/** « Ce qui marche le mieux » (ancienne page Expériences) : formats A/B et catégories, sur les Shorts publiées par l'appli. */
export function ExperimentsSection({ summary }: { summary: ExperimentSummary }) {
  const byFormat = new Map<VideoFormat, FormatSummary>(summary.byFormat.map((f) => [f.format, f]));
  const a = byFormat.get("A_voiceover");
  const b = byFormat.get("B_visual");
  if (!a && !b && summary.byCategory.length === 0) {
    return (
      <p className="text-muted-foreground rounded-xl border border-dashed p-6 text-center text-sm">
        Les comparaisons (voix off contre visuel, catégories qui retiennent le mieux) s’afficheront dès les premières Shorts publiées par l’appli.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 lg:grid-cols-2">
        {a ? <FormatCard summary={a} other={b} /> : null}
        {b ? <FormatCard summary={b} other={a} /> : null}
      </div>
      {a && b ? (
        <Card>
          <CardHeader>
            <CardTitle>Format A contre format B</CardTitle>
            <CardDescription>Indice relatif par métrique (100 = meilleur des deux formats). Survole pour les valeurs réelles.</CardDescription>
          </CardHeader>
          <CardContent>
            <FormatComparisonChart byFormat={summary.byFormat} />
          </CardContent>
        </Card>
      ) : null}
      {summary.byCategory.length > 0 ? (
        <Card className="gap-0 overflow-hidden py-0">
          <CardHeader className="border-b py-5">
            <CardTitle>Par catégorie</CardTitle>
            <CardDescription>Classement des sujets par rétention moyenne.</CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-6">Catégorie</TableHead>
                  <TableHead className="text-right">Vidéos</TableHead>
                  <TableHead className="text-right">Rétention moyenne</TableHead>
                  <TableHead className="pr-6 text-right">Vues / vidéo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {summary.byCategory.map((row, index) => {
                  const meta = categoryMeta(row.category);
                  return (
                    <TableRow key={row.category}>
                      <TableCell className="pl-6">
                        <span className="inline-flex items-center gap-2">
                          <span className="text-muted-foreground w-4 text-xs tabular-nums">{index + 1}</span>
                          <span aria-hidden>{meta.emoji}</span>
                          <span className="font-medium">{meta.label === "Autre" ? row.category : meta.label}</span>
                        </span>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{formatNumber(row.videos)}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatPercent(row.avg_view_pct, 1)}</TableCell>
                      <TableCell className="pr-6 text-right tabular-nums">{formatNumber(row.views_per_video)}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
