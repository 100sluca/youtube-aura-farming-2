import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  Bell,
  CalendarClock,
  CircleCheck,
  CircleX,
  Clock,
  Eye,
  Factory,
  Film,
  Gauge,
  TriangleAlert,
  Users,
} from "lucide-react";

import { ChannelBadge } from "@/components/channel-badge";
import { FormatBadge } from "@/components/format-badge";
import { KpiCard, type KpiDelta } from "@/components/kpi-card";
import { DailyViewsChart } from "@/components/overview/daily-views-chart";
import { PageHeader } from "@/components/page-header";
import { SeverityBadge, ToneBadge, VideoStatusBadge, type Tone } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { parseChannel, withChannel } from "@/lib/channel";
import { getDailyViews, getOverviewKpis, getSchedule, listAlerts, listProductions } from "@/lib/data";
import {
  NOW,
  clampPct,
  formatCompact,
  formatDate,
  formatDateTime,
  formatHours,
  formatMinutes,
  formatNumber,
  formatPercent,
  formatRelative,
  formatSigned,
  formatSignedPercent,
  formatTime,
} from "@/lib/format";
import type { ChannelLang } from "@/lib/types";

export const metadata: Metadata = { title: "Vue d’ensemble" };

function trendOf(value: number | null | undefined): KpiDelta["trend"] {
  if (!value) return "flat";
  return value > 0 ? "up" : "down";
}

export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const channel = parseChannel((await searchParams).channel);
  const [kpis, daily, schedule, productions, alerts] = await Promise.all([
    getOverviewKpis(channel),
    getDailyViews(28),
    getSchedule(NOW.toISOString(), 3),
    listProductions(),
    listAlerts(),
  ]);

  const upcoming = schedule
    .filter((s) => new Date(s.at).getTime() > NOW.getTime() && (!channel || s.channel_slug === channel))
    .sort((a, b) => a.at.localeCompare(b.at))
    .slice(0, 6);

  const inProduction = productions
    .filter((p) => ["scripting", "generating", "assembling"].includes(p.production.status))
    .sort((a, b) => b.production.updated_at.localeCompare(a.production.updated_at))
    .slice(0, 5);

  const openAlerts = alerts.filter((a) => !a.acknowledged_at).slice(0, 5);
  const publishTarget = 3 * 7 * (channel ? 1 : 2);
  const subsPct = clampPct((kpis.subscribers / kpis.ypp.subs_target) * 100);
  const viewsPct = clampPct((kpis.ypp.views_90d / kpis.ypp.views_90d_target) * 100);

  const chips: { label: string; value: number; tone: Tone; icon: typeof Factory }[] = [
    { label: "En génération", value: kpis.pipeline.generating, tone: "running", icon: Factory },
    { label: "Prêtes", value: kpis.pipeline.ready, tone: "success", icon: CircleCheck },
    { label: "Programmées", value: kpis.pipeline.scheduled, tone: "info", icon: CalendarClock },
    { label: "En échec", value: kpis.pipeline.failed, tone: "danger", icon: CircleX },
  ];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        description={
          channel
            ? `Santé de la chaîne ${channel.toUpperCase()} : audience, pipeline de production et prochains créneaux.`
            : "Santé des deux chaînes : audience, pipeline de production et prochains créneaux."
        }
        actions={<span className="text-muted-foreground text-xs">Mis à jour le {formatDateTime(NOW)}</span>}
      />

      <section aria-label="Indicateurs clés" className="grid gap-4 *:min-w-0 sm:grid-cols-2 xl:grid-cols-5">
        <KpiCard
          title="Abonnés"
          value={formatNumber(kpis.subscribers)}
          icon={Users}
          delta={{ text: `${formatSigned(kpis.subscribers_delta_7d)} sur 7 j`, trend: trendOf(kpis.subscribers_delta_7d) }}
          hint={channel ? "Total de la chaîne" : "Cumul des deux chaînes"}
        />
        <KpiCard
          title="Vues 7 j"
          value={formatCompact(kpis.views_7d)}
          icon={Eye}
          delta={{
            text: `${formatSignedPercent(kpis.views_7d_delta_pct, 1)} vs 7 j précédents`,
            trend: trendOf(kpis.views_7d_delta_pct),
          }}
        />
        <KpiCard
          title="Rétention moyenne 28 j"
          value={formatPercent(kpis.average_view_pct_28d, 1)}
          icon={Gauge}
          hint="Pourcentage moyen visionné, pondéré par les vues"
        />
        <KpiCard
          title="Heures de visionnage 28 j"
          value={formatHours(kpis.watch_hours_28d)}
          icon={Clock}
          hint="Estimation YouTube Analytics"
        />
        <KpiCard
          title="Shorts publiés 7 j"
          value={formatNumber(kpis.published_7d)}
          icon={Film}
          delta={{
            text: `objectif ${publishTarget} (3 / jour / chaîne)`,
            trend: kpis.published_7d >= publishTarget ? "up" : "flat",
          }}
        />
      </section>

      <section aria-label="Pipeline" className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground mr-1 text-sm">Pipeline :</span>
        {chips.map((chip) => {
          const Icon = chip.icon;
          return (
            <ToneBadge key={chip.label} tone={chip.tone} asChild className="px-3 py-1 text-sm">
              <Link href={withChannel("/production", channel)}>
                <Icon className="size-3.5" />
                {chip.label}
                <span className="font-semibold tabular-nums">{chip.value}</span>
              </Link>
            </ToneBadge>
          );
        })}
      </section>

      <section className="grid gap-4 *:min-w-0 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Vues par jour, 28 j</CardTitle>
            <CardDescription>Chaîne FR vs Channel EN (empilé)</CardDescription>
          </CardHeader>
          <CardContent>
            <DailyViewsChart data={daily} channel={channel} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Seuils YPP</CardTitle>
            <CardDescription>Programme Partenaire YouTube (Shorts)</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <div className="flex flex-col gap-2">
              <div className="flex items-baseline justify-between text-sm">
                <span className="font-medium">Abonnés</span>
                <span className="text-muted-foreground tabular-nums">
                  {formatNumber(kpis.subscribers)} / {formatNumber(kpis.ypp.subs_target)}
                </span>
              </div>
              <Progress value={subsPct} aria-label="Progression abonnés" />
              <p className="text-muted-foreground text-xs">
                {formatPercent(subsPct)} du seuil
                {channel ? "" : " · seuil évalué par chaîne"}
              </p>
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-baseline justify-between text-sm">
                <span className="font-medium">Vues sur 90 j</span>
                <span className="text-muted-foreground tabular-nums">
                  {formatCompact(kpis.ypp.views_90d)} / {formatCompact(kpis.ypp.views_90d_target)}
                </span>
              </div>
              <Progress value={viewsPct} aria-label="Progression vues 90 jours" />
              <p className="text-muted-foreground text-xs">{formatPercent(viewsPct, 1)} du seuil (10 M de vues Shorts)</p>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 *:min-w-0 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Prochaines publications</CardTitle>
            <CardDescription>6 prochains créneaux</CardDescription>
            <CardAction>
              <Button variant="ghost" size="sm" asChild>
                <Link href={withChannel("/calendar", channel)}>
                  Calendrier <ArrowRight />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {upcoming.map((slot) => (
                <li key={`${slot.channel_slug}-${slot.at}`} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                  <div className="w-20 shrink-0 text-sm">
                    <div className="font-medium capitalize">{formatDate(slot.at, "EEE d MMM")}</div>
                    <div className="text-muted-foreground text-xs tabular-nums">{formatTime(slot.at)}</div>
                  </div>
                  <ChannelBadge lang={slot.channel_slug as ChannelLang} />
                  {slot.video ? (
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <p className="truncate text-sm" title={slot.video.title ?? undefined}>
                        {slot.video.title ?? "Sans titre"}
                      </p>
                      <VideoStatusBadge status={slot.video.status} className="w-fit" />
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5 text-sm text-amber-700 dark:text-amber-400">
                      <TriangleAlert className="size-4" />
                      Créneau vide
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>En production</CardTitle>
            <CardDescription>{inProduction.length} production(s) actives</CardDescription>
            <CardAction>
              <Button variant="ghost" size="sm" asChild>
                <Link href={withChannel("/production", channel)}>
                  Kanban <ArrowRight />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-4">
              {inProduction.map((card) => (
                <li key={card.production.id} className="flex flex-col gap-2">
                  <div className="flex items-start justify-between gap-2">
                    <p className="line-clamp-2 text-sm font-medium">{card.concept?.title ?? "Production"}</p>
                    <FormatBadge format={card.production.format} />
                  </div>
                  <Progress value={card.progress_pct} aria-label={`Progression ${card.progress_pct} %`} />
                  <div className="text-muted-foreground flex items-center justify-between text-xs">
                    <span>{card.current_step}</span>
                    <span className="tabular-nums">
                      {formatPercent(card.progress_pct)}
                      {card.eta_minutes != null ? ` · ETA ${formatMinutes(card.eta_minutes)}` : ""}
                    </span>
                  </div>
                </li>
              ))}
              {inProduction.length === 0 ? (
                <li className="text-muted-foreground text-sm">Aucune production en cours.</li>
              ) : null}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Alertes ouvertes</CardTitle>
            <CardDescription>{alerts.filter((a) => !a.acknowledged_at).length} à traiter</CardDescription>
            <CardAction>
              <Button variant="ghost" size="sm" asChild>
                <Link href="/alerts">
                  <Bell /> Toutes
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {openAlerts.map((alert) => (
                <li key={alert.id} className="flex flex-col gap-1 py-2.5 first:pt-0 last:pb-0">
                  <div className="flex items-center gap-2">
                    <SeverityBadge severity={alert.severity} />
                    <span className="text-muted-foreground ml-auto text-xs">{formatRelative(alert.created_at)}</span>
                  </div>
                  <p className="text-sm leading-snug">{alert.title}</p>
                </li>
              ))}
              {openAlerts.length === 0 ? <li className="text-muted-foreground text-sm">Rien à signaler.</li> : null}
            </ul>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
