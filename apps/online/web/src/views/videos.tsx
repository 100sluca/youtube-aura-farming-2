/** Onglet Vidéos : les 40 dernières vidéos sorties, une ligne par vidéo avec ses chiffres sur chaque réseau. */
import { useState } from "react";
import { ExternalLink } from "lucide-react";

import { Empty, PlatformIcon, StatCard } from "@/components/shared";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { compact, dayLabel, duration, fmt, isNum, pct, safeUrl, sum, time } from "@/lib/format";
import { PLATFORM_LABEL, PLATFORMS, type Platform, type PlatformStats, type Snapshot, type Video } from "@/lib/snapshot";

const RECIPE: Record<string, string> = { timelapse: "Chantier", tour: "Visite", story: "Récit", drama: "Drame", quote: "Citation" };
const VERDICT: Record<string, string> = { top: "Top", flop: "Flop" };

type Filter = "all" | Platform;
type Sort = "recent" | "views" | "retention";

export function VideosView({ s }: { s: Snapshot }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("recent");
  const totals = (p: Platform) => s[p]?.totals ?? null;
  const total = (v: Video) => sum(PLATFORMS.map((p) => v[p]?.views));

  let list = [...(s.videos ?? [])];
  if (filter !== "all") list = list.filter((v) => v[filter]);
  if (sort === "views") list.sort((a, b) => total(b) - total(a));
  if (sort === "retention") list.sort((a, b) => (watched(b) ?? -1) - (watched(a) ?? -1));

  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {PLATFORMS.map((p) => (
          <StatCard
            key={p}
            label={PLATFORM_LABEL[p]}
            value={compact(totals(p)?.views)}
            unit="vues"
            hint={`${fmt(totals(p)?.videos)} vidéos · ${pct(p === "youtube" ? totals(p)?.average_view_pct : totals(p)?.watched_pct)} vu en moyenne`}
          />
        ))}
        <StatCard label="J’aime" value={compact(sum(PLATFORMS.map((p) => totals(p)?.likes)))} hint={`${fmt(sum(PLATFORMS.map((p) => totals(p)?.comments)))} commentaires`} />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
          <TabsList>
            <TabsTrigger value="all">Toutes</TabsTrigger>
            {PLATFORMS.map((p) => (
              <TabsTrigger key={p} value={p} aria-label={PLATFORM_LABEL[p]}>
                <PlatformIcon platform={p} />
                <span className="hidden sm:inline">{PLATFORM_LABEL[p]}</span>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <Select value={sort} onValueChange={(v) => setSort(v as Sort)}>
          <SelectTrigger size="sm" className="w-40" aria-label="Trier">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="recent">Plus récentes</SelectItem>
            <SelectItem value="views">Plus vues</SelectItem>
            <SelectItem value="retention">Meilleure rétention</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card className="py-0">
        <CardContent className="px-4">
          {list.length ? (
            <Accordion type="single" collapsible>
              {list.map((v) => (
                <VideoRow key={v.key} v={v} />
              ))}
            </Accordion>
          ) : (
            <Empty>Aucune vidéo.</Empty>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** Part vue : YouTube d'abord, sinon TikTok, sinon Instagram. */
const watched = (v: Video): number | null => PLATFORMS.map((p) => v[p]?.watched_pct).find(isNum) ?? null;

function VideoRow({ v }: { v: Video }) {
  const thumb = safeUrl(v.thumbnail);
  const verdict = PLATFORMS.map((p) => v[p]?.verdict).find((x) => x && VERDICT[x]);
  const on = PLATFORMS.filter((p) => v[p]);
  return (
    <AccordionItem value={v.key}>
      <AccordionTrigger className="items-center gap-3 py-3 hover:no-underline">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          {thumb ? (
            <img src={thumb} alt="" loading="lazy" referrerPolicy="no-referrer" className="bg-muted h-16 w-11 shrink-0 rounded-md object-cover" />
          ) : (
            <div className="bg-muted h-16 w-11 shrink-0 rounded-md" />
          )}
          <div className="grid min-w-0 gap-1">
            <span className="line-clamp-2 text-sm leading-snug font-medium">{v.title}</span>
            <span className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-normal">
              <span>
                {dayLabel(v.published_at)} · {time(v.published_at)}
              </span>
              {on.map((p) => (
                <span key={p} className="text-foreground inline-flex items-center gap-1 tabular-nums">
                  <PlatformIcon platform={p} className="size-3.5" />
                  {v[p]!.pending ? "…" : compact(v[p]!.views)}
                </span>
              ))}
              {verdict ? (
                <Badge variant="outline" className={verdict === "top" ? "text-success" : "text-destructive"}>
                  {VERDICT[verdict]}
                </Badge>
              ) : null}
            </span>
          </div>
        </div>
      </AccordionTrigger>
      <AccordionContent className="grid gap-3">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead />
              {on.map((p) => (
                <TableHead key={p} className="text-right">
                  {PLATFORM_LABEL[p]}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {/* une ligne vide sur tous les réseaux n'apprend rien : masquée */}
            {ROWS.filter(([, get]) => on.some((p) => get(v[p]!) !== "—")).map(([label, get]) => (
              <TableRow key={label}>
                <TableCell className="text-muted-foreground">{label}</TableCell>
                {on.map((p) => (
                  <TableCell key={p} className="text-right tabular-nums">
                    {get(v[p]!)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {v.insight ? <p className="text-muted-foreground border-l-2 pl-3 text-sm">{v.insight}</p> : null}
        <p className="text-muted-foreground text-xs">
          {[v.recipe ? (RECIPE[v.recipe] ?? v.recipe) : null, v.series, isNum(v.duration_s) ? duration(v.duration_s) : null].filter(Boolean).join(" · ")}
        </p>
        <div className="flex flex-wrap gap-2">
          {on
            .filter((p) => safeUrl(v[p]!.url))
            .map((p) => (
              <Button key={p} variant="outline" size="sm" asChild>
                <a href={safeUrl(v[p]!.url)} target="_blank" rel="noopener noreferrer">
                  <PlatformIcon platform={p} />
                  {PLATFORM_LABEL[p]}
                  <ExternalLink className="text-muted-foreground" />
                </a>
              </Button>
            ))}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}

const ROWS: [string, (x: PlatformStats) => string][] = [
  ["Vues", (x) => (x.pending ? "en attente" : fmt(x.views))],
  ["En 24 h", (x) => fmt(x.views_24h)],
  ["En 7 jours", (x) => fmt(x.views_7d)],
  ["J’aime", (x) => fmt(x.likes)],
  ["Commentaires", (x) => fmt(x.comments)],
  ["Partages", (x) => fmt(x.shares)],
  ["Part vue", (x) => pct(x.watched_pct)],
  ["Encore là à 3 s", (x) => pct(x.hook_pct)],
  ["Jusqu’au bout", (x) => pct(x.end_pct)],
  ["Durée moyenne", (x) => duration(x.avg_watch_s)],
  ["Abonnés gagnés", (x) => fmt(x.subscribers_gained)],
  ["Note", (x) => (isNum(x.score) ? `×${x.score.toFixed(2).replace(".", ",")}` : "—")],
];
