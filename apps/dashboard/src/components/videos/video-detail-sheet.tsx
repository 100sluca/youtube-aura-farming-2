"use client";

import { ExternalLink, ThumbsUp } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";

import { ChannelBadge } from "@/components/channel-badge";
import { FormatBadge } from "@/components/format-badge";
import { Poster } from "@/components/poster";
import { VideoStatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import type { VideoDetail } from "@/lib/data/contract";
import { formatDate, formatDateTime, formatDuration, formatNumber, formatPercent, formatRelative } from "@/lib/format";
import { categoryMeta } from "@/lib/labels";
import type { VideoOverview } from "@/lib/types";

const retentionConfig = {
  w: { label: "Audience", color: "var(--chart-1)" },
} satisfies ChartConfig;

const dailyConfig = {
  views: { label: "Vues", color: "var(--chart-2)" },
} satisfies ChartConfig;

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-muted/40 flex flex-col gap-1 rounded-lg border p-3">
      <span className="text-muted-foreground text-xs">{label}</span>
      <span className="text-lg font-semibold tabular-nums">{value}</span>
    </div>
  );
}

export function VideoDetailSheet({
  video,
  detail,
  loading,
  onClose,
}: {
  video: VideoOverview | null;
  detail: VideoDetail | null;
  loading: boolean;
  onClose: () => void;
}) {
  const retentionPoints = detail?.retention.map((p) => ({ t: Math.round(p.t * 100), w: Math.round(p.w * 1000) / 10 })) ?? [];

  return (
    <Sheet
      open={video !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-2xl">
        {video ? (
          <>
            <SheetHeader className="border-b pr-12">
              <div className="flex gap-4">
                <Poster category={video.category} size="md" />
                <div className="flex min-w-0 flex-col gap-2">
                  <SheetTitle className="leading-snug">{video.title ?? "Sans titre"}</SheetTitle>
                  <SheetDescription>
                    Publiée le {video.published_at ? formatDateTime(video.published_at) : "—"} · {formatDuration(video.duration_s)}
                  </SheetDescription>
                  <div className="flex flex-wrap gap-1.5">
                    <ChannelBadge lang={video.lang} />
                    <FormatBadge format={video.format} />
                    <Badge variant="outline">
                      <span aria-hidden>{categoryMeta(video.category).emoji}</span>
                      {categoryMeta(video.category).label}
                    </Badge>
                    <VideoStatusBadge status={video.status} />
                  </div>
                  {video.youtube_video_id ? (
                    <Button variant="outline" size="sm" className="w-fit" asChild>
                      <a href={`https://youtube.com/shorts/${video.youtube_video_id}`} target="_blank" rel="noreferrer noopener">
                        <ExternalLink />
                        Ouvrir sur YouTube
                      </a>
                    </Button>
                  ) : null}
                </div>
              </div>
            </SheetHeader>

            <ScrollArea className="min-h-0 flex-1">
              <div className="flex flex-col gap-6 p-4">
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <StatTile label="Vues" value={formatNumber(video.views)} />
                  <StatTile label="Likes" value={formatNumber(video.likes)} />
                  <StatTile label="Commentaires" value={formatNumber(video.comments)} />
                  <StatTile label="Rétention" value={formatPercent(video.average_view_pct, 1)} />
                </div>

                {loading || !detail ? (
                  <div className="flex flex-col gap-4" aria-busy>
                    <Skeleton className="h-[200px] w-full" />
                    <Skeleton className="h-[180px] w-full" />
                    <Skeleton className="h-24 w-full" />
                  </div>
                ) : (
                  <>
                    <section className="flex flex-col gap-3">
                      <div>
                        <h3 className="text-sm font-semibold">Courbe de rétention</h3>
                        <p className="text-muted-foreground text-xs">Part de l’audience encore présente selon l’avancement de la vidéo.</p>
                      </div>
                      <ChartContainer config={retentionConfig} className="aspect-auto h-[200px] w-full">
                        <LineChart data={retentionPoints} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                          <CartesianGrid vertical={false} />
                          <XAxis
                            dataKey="t"
                            type="number"
                            domain={[0, 100]}
                            ticks={[0, 25, 50, 75, 100]}
                            tickFormatter={(value) => `${value} %`}
                            tickLine={false}
                            axisLine={false}
                            tickMargin={8}
                          />
                          <YAxis domain={[0, 100]} width={44} tickFormatter={(value) => `${value} %`} tickLine={false} axisLine={false} />
                          <ChartTooltip
                            content={
                              <ChartTooltipContent
                                labelFormatter={(label) => `À ${String(label)} % de la vidéo`}
                                formatter={(value) => (
                                  <span className="flex w-full items-center justify-between gap-4">
                                    <span className="text-muted-foreground">Audience</span>
                                    <span className="font-mono font-medium tabular-nums">{formatPercent(Number(value), 1)}</span>
                                  </span>
                                )}
                              />
                            }
                          />
                          <Line dataKey="w" type="monotone" stroke="var(--color-w)" strokeWidth={2} dot={false} isAnimationActive={false} />
                        </LineChart>
                      </ChartContainer>
                    </section>

                    <section className="flex flex-col gap-3">
                      <h3 className="text-sm font-semibold">Vues par jour (14 j)</h3>
                      <ChartContainer config={dailyConfig} className="aspect-auto h-[180px] w-full">
                        <BarChart data={detail.daily} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                          <CartesianGrid vertical={false} />
                          <XAxis
                            dataKey="day"
                            tickLine={false}
                            axisLine={false}
                            tickMargin={8}
                            minTickGap={16}
                            tickFormatter={(value) => formatDate(`${String(value)}T12:00:00Z`, "d/M")}
                          />
                          <YAxis width={44} tickLine={false} axisLine={false} tickFormatter={(value) => formatNumber(Number(value))} />
                          <ChartTooltip
                            content={
                              <ChartTooltipContent
                                labelFormatter={(label) => formatDate(`${String(label)}T12:00:00Z`, "EEEE d MMMM")}
                                formatter={(value) => (
                                  <span className="flex w-full items-center justify-between gap-4">
                                    <span className="text-muted-foreground">Vues</span>
                                    <span className="font-mono font-medium tabular-nums">{formatNumber(Number(value))}</span>
                                  </span>
                                )}
                              />
                            }
                          />
                          <Bar dataKey="views" fill="var(--color-views)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                        </BarChart>
                      </ChartContainer>
                    </section>

                    <Separator />

                    <section className="flex flex-col gap-3">
                      <h3 className="text-sm font-semibold">Commentaires récents</h3>
                      <ul className="flex flex-col gap-3">
                        {detail.comments.map((comment) => (
                          <li key={comment.id} className="flex flex-col gap-1 text-sm">
                            <div className="flex items-center gap-2">
                              <span className="font-medium">{comment.author}</span>
                              <span className="text-muted-foreground text-xs">{formatRelative(comment.published_at)}</span>
                              <span className="text-muted-foreground ml-auto inline-flex items-center gap-1 text-xs tabular-nums">
                                <ThumbsUp className="size-3" />
                                {formatNumber(comment.like_count)}
                              </span>
                            </div>
                            <p className="text-muted-foreground">{comment.text}</p>
                          </li>
                        ))}
                        {detail.comments.length === 0 ? <li className="text-muted-foreground text-sm">Aucun commentaire.</li> : null}
                      </ul>
                    </section>

                    <Separator />

                    <section className="flex flex-col gap-3">
                      <div>
                        <h3 className="text-sm font-semibold">Script ({detail.script?.scenes.length ?? 0} scènes)</h3>
                        <p className="text-muted-foreground text-xs">
                          {video.format === "A_voiceover" ? "Narration voix off" : "Texte à l’écran (format visuel)"} · {video.lang.toUpperCase()}
                        </p>
                      </div>
                      {detail.script ? (
                        <ol className="flex flex-col gap-2">
                          {detail.script.scenes.map((scene) => {
                            const text = scene.narration[video.lang] || scene.on_screen_text?.[video.lang] || "—";
                            return (
                              <li key={scene.index} className="flex gap-3 rounded-lg border p-3 text-sm">
                                <span className="bg-muted text-muted-foreground flex size-7 shrink-0 items-center justify-center rounded-md text-xs font-semibold tabular-nums">
                                  {scene.index + 1}
                                </span>
                                <div className="flex min-w-0 flex-col gap-1">
                                  <p>{text}</p>
                                  <p className="text-muted-foreground text-xs">
                                    {formatDuration(scene.duration_s)}
                                    {scene.sfx ? ` · SFX : ${scene.sfx}` : ""}
                                  </p>
                                </div>
                              </li>
                            );
                          })}
                        </ol>
                      ) : (
                        <p className="text-muted-foreground text-sm">Script indisponible.</p>
                      )}
                    </section>
                  </>
                )}
              </div>
            </ScrollArea>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
