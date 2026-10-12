/** Onglet Direct : l'essentiel d'un coup d'œil. */
import { Bar, BarChart, CartesianGrid, XAxis } from "recharts";

import { Empty, PlatformDot, Sparkline, StatCard, TrendBadge } from "@/components/shared";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Progress } from "@/components/ui/progress";
import { compact, dayLabel, eta, fmt, isNum, safeUrl, shortDay, signed, sum, time } from "@/lib/format";
import { PLATFORM_LABEL, PLATFORMS, type NetworkAccount, type Platform, type Snapshot } from "@/lib/snapshot";

const chartConfig = {
  youtube: { label: "YouTube", color: "var(--youtube)" },
  tiktok: { label: "TikTok", color: "var(--tiktok)" },
  instagram: { label: "Instagram", color: "var(--instagram)" },
} satisfies ChartConfig;

/** Vues par jour sur 28 jours, réseau par réseau (comptes additionnés ; null : jour pas encore connu). */
function dailyByPlatform(s: Snapshot) {
  const days = new Map<string, Record<Platform, number | null> & { day: string }>();
  for (const a of s.networks ?? []) {
    if (!a.connected) continue;
    for (const d of a.daily ?? []) {
      const row = days.get(d.day) ?? { day: d.day, youtube: null, tiktok: null, instagram: null };
      if (isNum(d.views)) row[a.platform] = (row[a.platform] ?? 0) + d.views;
      days.set(d.day, row);
    }
  }
  const rows = [...days.values()].sort((a, b) => a.day.localeCompare(b.day)).slice(-28);
  // Les jours d'avant la première vue (chaîne pas encore lancée) ne disent rien : on les retire
  const first = rows.findIndex((r) => PLATFORMS.some((p) => (r[p] ?? 0) > 0));
  return first > 0 ? rows.slice(first) : rows;
}

export function DirectView({ s, goTo }: { s: Snapshot; goTo: (tab: string) => void }) {
  const nets = (s.networks ?? []).filter((a) => a.connected);
  const views7 = sum(nets.map((a) => a.views_7d));
  const prev7 = nets.every((a) => isNum(a.views_prev_7d)) ? sum(nets.map((a) => a.views_prev_7d)) : null;
  const followers = sum(nets.map((a) => a.followers));
  const followersDelta = nets.some((a) => isNum(a.followers_delta_7d)) ? sum(nets.map((a) => a.followers_delta_7d)) : null;
  const k = s.youtube?.kpis;
  const rows = dailyByPlatform(s);
  const unknownDays = rows.filter((r) => PLATFORMS.some((p) => r[p] === null && rows.some((o) => isNum(o[p])))).length;
  const items = s.production?.items ?? [];
  const live = items.filter((i) => ["running", "preparing", "queued"].includes(i.group));
  const waiting = items.filter((i) => i.group === "waiting").length;
  const gpu = s.machine?.gpu_job;

  return (
    <div className="grid grid-cols-1 gap-4">
      {s.machine ? (
        <p className="text-muted-foreground flex items-start gap-2 text-sm">
          <span className={`mt-[7px] size-1.5 shrink-0 rounded-full ${s.machine.worker === "ok" ? "bg-success" : "bg-destructive"}`} />
          <span>
          {s.machine.worker === "ok" ? "PC en marche" : "Worker arrêté"}
          {gpu ? ` · la carte graphique fait « ${gpu.label} »` : " · carte graphique au repos"}
          </span>
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Vues · 7 jours"
          value={compact(views7)}
          badge={<TrendBadge now={views7} before={prev7} />}
          hint="Tous réseaux, vs les 7 jours d’avant"
        />
        <StatCard label="Abonnés" value={fmt(followers)} hint={followersDelta !== null ? `${signed(followersDelta)} en 7 jours, tous comptes` : "Tous comptes"} />
        <StatCard label="Vidéos sorties" value={fmt(k?.published_7d)} hint="YouTube, 7 derniers jours" />
        <StatCard label="Rétention" value={isNum(k?.average_view_pct_28d) ? String(Math.round(k.average_view_pct_28d)) : "—"} unit="%" hint="Part vue en moyenne, YouTube 28 j" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Vues par jour</CardTitle>
          <CardDescription>Jusqu’à 28 jours, par réseau</CardDescription>
        </CardHeader>
        <CardContent className="px-2 sm:px-6">
          {rows.length ? (
            <ChartContainer config={chartConfig} className="aspect-auto h-[220px] w-full">
              <BarChart data={rows} margin={{ left: 4, right: 4 }}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="day" tickLine={false} axisLine={false} tickMargin={8} minTickGap={28} tickFormatter={shortDay} />
                <ChartTooltip cursor={false} content={<ChartTooltipContent labelFormatter={(v) => shortDay(String(v))} />} />
                <ChartLegend content={<ChartLegendContent />} />
                {PLATFORMS.map((p, i) => (
                  <Bar key={p} dataKey={p} stackId="v" fill={`var(--color-${p})`} radius={i === PLATFORMS.length - 1 ? [3, 3, 0, 0] : 0} />
                ))}
              </BarChart>
            </ChartContainer>
          ) : (
            <Empty>Pas encore de vues relevées.</Empty>
          )}
        </CardContent>
        {unknownDays ? (
          <CardFooter className="text-muted-foreground text-xs">
            Les derniers jours YouTube manquent encore : YouTube Analytics les publie avec 2 à 3 jours de retard.
          </CardFooter>
        ) : null}
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {(s.networks ?? []).map((a) => (
          <AccountCard key={a.key} a={a} />
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>En fabrication</CardTitle>
            <CardDescription>{live.length ? `${live.length} vidéo${live.length > 1 ? "s" : ""} en route` : "Rien ne tourne"}</CardDescription>
            <CardAction>
              <Button variant="outline" size="sm" onClick={() => goTo("fabrique")}>
                Détail
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4">
            {live.slice(0, 3).map((i) => {
              const stepOnly = i.group === "running" && !i.progress_pct && isNum(i.step_progress);
              const value = stepOnly ? (i.step_progress ?? 0) : i.progress_pct;
              return (
                <div key={i.id} className="grid gap-1.5">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="line-clamp-1 text-sm font-medium">{i.title}</span>
                    <span className="text-muted-foreground shrink-0 text-sm whitespace-nowrap tabular-nums">{Math.round(value)} %</span>
                  </div>
                  <Progress value={value} className={i.group === "running" ? "[&>[data-slot=progress-indicator]]:bg-signal" : undefined} />
                  <span className="text-muted-foreground text-xs">
                    {i.stage}
                    {eta(i.eta_at) ? ` · fin ${eta(i.eta_at)}` : ""}
                  </span>
                </div>
              );
            })}
            {!live.length ? <Empty>Aucune vidéo en cours.</Empty> : null}
            {waiting || s.production?.review_videos ? (
              <div className="flex flex-wrap gap-2">
                {waiting ? <Badge variant="secondary">{waiting} storyboard{waiting > 1 ? "s" : ""} à valider</Badge> : null}
                {s.production?.review_videos ? (
                  <Badge variant="secondary">
                    {s.production.review_videos} vidéo{s.production.review_videos > 1 ? "s" : ""} à valider
                  </Badge>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Prochaines sorties</CardTitle>
            <CardDescription>Programmées sur les 7 prochains jours</CardDescription>
          </CardHeader>
          <CardContent>
            {s.upcoming?.length ? (
              <ul className="divide-y">
                {s.upcoming.slice(0, 6).map((u, n) => (
                  <li key={`${u.at}-${n}`} className="flex items-start justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                    <div className="min-w-0">
                      <p className="line-clamp-1 text-sm font-medium">{u.title}</p>
                      <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
                        {u.platforms.map((p) => (
                          <PlatformDot key={p} platform={p as Platform} />
                        ))}
                        {u.platforms.map((p) => PLATFORM_LABEL[p as Platform] ?? p).join(", ")}
                      </p>
                    </div>
                    <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
                      {dayLabel(u.at)} · {time(u.at)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>Rien de programmé.</Empty>
            )}
          </CardContent>
        </Card>
      </div>

      {s.youtube?.analysis ? (
        <Card>
          <CardHeader>
            <CardTitle>L’avis de l’analyste</CardTitle>
            <CardDescription>Rapport du {dayLabel(s.youtube.analysis.created_at)}</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm">
            {s.youtube.analysis.summary ? <p>{s.youtube.analysis.summary}</p> : null}
            {s.youtube.analysis.findings?.length ? (
              <ul className="text-muted-foreground ml-4 list-disc space-y-1">
                {s.youtube.analysis.findings.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            ) : null}
          </CardContent>
          {s.youtube.analysis.proposed ? (
            <CardFooter className="text-muted-foreground text-xs">
              {s.youtube.analysis.proposed} leçon{s.youtube.analysis.proposed > 1 ? "s" : ""} à valider dans le Dashboard du PC
            </CardFooter>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}

function AccountCard({ a }: { a: NetworkAccount }) {
  const avatar = safeUrl(a.avatar_url);
  return (
    <Card className="gap-4 py-4">
      <CardHeader className="px-4">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar className="size-9">
            {avatar ? <AvatarImage src={avatar} alt="" referrerPolicy="no-referrer" /> : null}
            <AvatarFallback className="text-xs">{a.name.replace("@", "").slice(0, 2).toUpperCase()}</AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <CardTitle className="truncate text-sm">{a.name}</CardTitle>
            <CardDescription className="flex items-center gap-1.5 text-xs">
              <PlatformDot platform={a.platform} />
              {PLATFORM_LABEL[a.platform]} · {a.role}
            </CardDescription>
          </div>
        </div>
        {a.connected ? (
          <CardAction>
            <TrendBadge now={a.views_7d} before={a.views_prev_7d} />
          </CardAction>
        ) : null}
      </CardHeader>
      <CardContent className="px-4">
        {a.connected ? (
          <>
            <dl className="grid grid-cols-3 gap-2 text-sm">
              <div>
                <dt className="text-muted-foreground text-xs">Abonnés</dt>
                <dd className="font-semibold tabular-nums">
                  {compact(a.followers)}
                  {isNum(a.followers_delta_7d) && a.followers_delta_7d ? <span className="text-muted-foreground ml-1 text-xs font-normal">{signed(a.followers_delta_7d)}</span> : null}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Vues 7 j</dt>
                <dd className="font-semibold tabular-nums">{compact(a.views_7d)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Vidéos 7 j</dt>
                <dd className="font-semibold tabular-nums">{fmt(a.posts_7d)}</dd>
              </div>
            </dl>
            <Sparkline values={(a.daily ?? []).map((d) => d.views)} color={`var(--${a.platform})`} className="mt-3" />
          </>
        ) : (
          <p className="text-muted-foreground text-sm">{a.warning ?? "Compte pas encore relié."}</p>
        )}
      </CardContent>
    </Card>
  );
}

