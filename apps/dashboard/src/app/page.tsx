import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  CalendarClock,
  CircleCheck,
  CircleX,
  Clapperboard,
  Clock,
  Eye,
  Factory,
  Film,
  Gauge,
  ListChecks,
  TriangleAlert,
  Users,
} from "lucide-react";

import { TikTokLine } from "@/components/calendar/slot-cell";
import { ChannelBadge } from "@/components/channel-badge";
import { ExperimentsSection } from "@/components/experiments/experiments-section";
import { FormatBadge } from "@/components/format-badge";
import { KpiCard, type KpiDelta } from "@/components/kpi-card";
import { DailyViewsChart } from "@/components/overview/daily-views-chart";
import { PageHeader } from "@/components/page-header";
import { YouTubeMark } from "@/components/platform-marks";
import { ToneBadge, VideoStatusBadge, type Tone } from "@/components/status-badge";
import { OpenTasksButton } from "@/components/tasks/task-manager";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { getChannelContext } from "@/lib/channel-server";
import { getDailyViews, getExperimentSummary, getOverviewKpis, getSchedule, listProductions } from "@/lib/data";
import {
  now,
  clampPct,
  formatCompact,
  formatDate,
  formatDateTime,
  formatHours,
  formatNumber,
  formatPercent,
  formatRelative,
  formatSigned,
  formatSignedPercent,
  formatTime,
  parisAddDays,
} from "@/lib/format";
import { getTikTokCalendar } from "@/lib/tiktok";

export const metadata: Metadata = { title: "Vue d’ensemble" };

function trendOf(value: number | null | undefined): KpiDelta["trend"] {
  if (!value) return "flat";
  return value > 0 ? "up" : "down";
}

export default async function OverviewPage() {
  const { channels, selected } = await getChannelContext();
  const [kpis, daily, schedule, productions, experiments, tiktok] = await Promise.all([
    getOverviewKpis(selected?.slug),
    getDailyViews(28),
    getSchedule(now().toISOString(), 3),
    listProductions(),
    getExperimentSummary(),
    getTikTokCalendar(now().toISOString(), parisAddDays(now(), 4).toISOString()),
  ]);
  // TikTok (docs/39) : publications du même créneau (±10 min) de la même chaîne
  const tiktokAt = (slug: string, at: string) => {
    const ch = channels.find((c) => c.slug === slug);
    const ms = new Date(at).getTime();
    return tiktok.filter((t) => t.channel_id === ch?.id && Math.abs(new Date(t.at).getTime() - ms) < 10 * 60_000);
  };
  const shown = selected ? [selected] : channels.filter((c) => c.is_active);
  const bySlug = new Map(channels.map((c) => [c.slug, c]));
  const mine = productions.filter((p) => !selected || p.production.channel_id === selected.id);

  const upcoming = schedule
    .filter((s) => new Date(s.at).getTime() > now().getTime() && (!selected || s.channel_slug === selected.slug))
    .sort((a, b) => a.at.localeCompare(b.at))
    .slice(0, 6);

  const inProduction = mine
    .filter((p) => ["draft", "scripting", "generating", "assembling"].includes(p.production.status))
    .sort((a, b) => b.production.updated_at.localeCompare(a.production.updated_at))
    .slice(0, 5);
  const storyboards = mine.filter((p) => p.production.status === "storyboard_review");
  const toValidate = mine.flatMap((p) => p.videos.filter((v) => v.status === "review").map((v) => ({ video: v, card: p })));

  const publishTarget = 3 * 7 * Math.max(1, shown.length);
  const subsPct = clampPct((kpis.subscribers / kpis.ypp.subs_target) * 100);
  const viewsPct = clampPct((kpis.ypp.views_90d / kpis.ypp.views_90d_target) * 100);

  const chips: { label: string; value: number; tone: Tone; icon: typeof Factory; href: string | null }[] = [
    { label: "En fabrication", value: kpis.pipeline.generating, tone: "running", icon: Factory, href: null },
    { label: "Vidéos à valider", value: kpis.pipeline.ready, tone: "success", icon: CircleCheck, href: "/library?statut=a_valider" },
    { label: "Programmées", value: kpis.pipeline.scheduled, tone: "info", icon: CalendarClock, href: "/library?statut=programmees" },
    { label: "En échec", value: kpis.pipeline.failed, tone: "danger", icon: CircleX, href: null },
  ];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        description={
          selected
            ? `Santé de « ${selected.name} » : audience, fabrication et prochains créneaux.`
            : "Santé de tes chaînes : audience, fabrication et prochains créneaux. Choisis une chaîne en haut pour la voir seule."
        }
        actions={
          <span className="text-muted-foreground text-xs" suppressHydrationWarning>
            {kpis.counters_at ? `Stats YouTube relevées ${formatRelative(kpis.counters_at)} (chaque heure)` : `Mis à jour le ${formatDateTime(now())}`}
            {" · "}
            <Link href="/dashboard" className="hover:text-foreground underline underline-offset-2">
              Toutes les stats
            </Link>
            {" · "}
            <Link href="/dashboard?plateforme=tiktok" className="hover:text-foreground underline underline-offset-2">
              TikTok
            </Link>
          </span>
        }
      />

      <section aria-label="Indicateurs clés" className="grid gap-4 *:min-w-0 sm:grid-cols-2 xl:grid-cols-5">
        <KpiCard
          title="Abonnés"
          value={formatNumber(kpis.subscribers)}
          icon={Users}
          delta={
            kpis.subscribers_delta_known === false
              ? undefined
              : { text: `${formatSigned(kpis.subscribers_delta_7d)} sur 7 j`, trend: trendOf(kpis.subscribers_delta_7d) }
          }
          hint={selected ? "Total de la chaîne, relevé chaque heure" : "Cumul des chaînes, relevé chaque heure"}
        />
        <KpiCard
          title="Vues 7 j"
          value={formatCompact(kpis.views_7d)}
          icon={Eye}
          delta={
            kpis.views_7d_delta_pct === null
              ? undefined
              : { text: `${formatSignedPercent(kpis.views_7d_delta_pct, 1)} vs 7 j précédents`, trend: trendOf(kpis.views_7d_delta_pct) }
          }
          hint={kpis.views_7d_estimated ? "Derniers jours d’après les compteurs (Analytics : 2 à 3 j de retard)" : undefined}
        />
        <KpiCard
          title="Rétention moyenne 28 j"
          value={formatPercent(kpis.average_view_pct_28d, 1)}
          icon={Gauge}
          hint="Pourcentage moyen visionné, pondéré par les vues"
        />
        <KpiCard
          title="Heures de visionnage 28 j"
          value={kpis.analytics_through === null ? "—" : formatHours(kpis.watch_hours_28d)}
          icon={Clock}
          hint={kpis.analytics_through === null ? "YouTube Analytics : rien de publié encore (2 à 3 j de retard)" : "Estimation YouTube Analytics"}
        />
        <KpiCard
          title="Shorts publiés 7 j"
          value={formatNumber(kpis.published_7d)}
          icon={Film}
          delta={{
            text: `objectif ${publishTarget} (3 par jour et par chaîne)`,
            trend: kpis.published_7d >= publishTarget ? "up" : "flat",
          }}
        />
      </section>

      <section aria-label="Fabrication" className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground mr-1 text-sm">Fabrication :</span>
        {chips.map((chip) => {
          const Icon = chip.icon;
          const inner = (
            <>
              <Icon className="size-3.5" />
              {chip.label}
              <span className="font-semibold tabular-nums">{chip.value}</span>
            </>
          );
          return chip.href ? (
            <ToneBadge key={chip.label} tone={chip.tone} asChild className="px-3 py-1 text-sm">
              <Link href={chip.href}>{inner}</Link>
            </ToneBadge>
          ) : (
            <ToneBadge key={chip.label} tone={chip.tone} className="px-3 py-1 text-sm">
              {inner}
            </ToneBadge>
          );
        })}
        <OpenTasksButton variant="ghost" size="sm">
          <ListChecks />
          Ouvrir les tâches
        </OpenTasksButton>
      </section>

      <section className="grid gap-4 *:min-w-0 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Vues par jour, 28 j</CardTitle>
            <CardDescription>{shown.length > 1 ? "Une couleur par chaîne (empilé)" : (shown[0]?.name ?? "")}</CardDescription>
            <CardAction>
              <Button variant="ghost" size="sm" asChild>
                <Link href="/dashboard">
                  Dashboard <ArrowRight />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <DailyViewsChart data={daily} channels={shown.map((c) => ({ slug: c.slug, name: c.name }))} />
            {daily.some((d) => d.estimated) || (kpis.unattributed_views ?? 0) > 0 ? (
              <p className="text-muted-foreground text-xs">
                Barres claires : estimées d’après les compteurs relevés chaque heure, en attendant YouTube Analytics (2 à 3 jours de retard).
                {(kpis.unattributed_views ?? 0) > 0
                  ? ` ${formatNumber(kpis.unattributed_views)} vue${(kpis.unattributed_views ?? 0) > 1 ? "s" : ""} pas encore rangée${(kpis.unattributed_views ?? 0) > 1 ? "s" : ""} dans un jour (comptée${(kpis.unattributed_views ?? 0) > 1 ? "s" : ""} dans « Vues 7 j »).`
                  : ""}
              </p>
            ) : null}
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
                {selected ? "" : " · seuil évalué par chaîne"}
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
            <CardTitle>À valider</CardTitle>
            <CardDescription>
              {storyboards.length + toValidate.length > 0 ? "Ce qui attend ton avis" : "Rien n’attend ton avis"}
            </CardDescription>
            <CardAction>
              <Button variant="ghost" size="sm" asChild>
                <Link href="/create">
                  Création <ArrowRight />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {storyboards.slice(0, 4).map((card) => (
                <li key={card.production.id} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                  <Clapperboard className="size-4 shrink-0 text-amber-600" />
                  <Link href="/create#storyboards" className="min-w-0 flex-1 truncate text-sm hover:underline">
                    {card.concept?.title ?? "Storyboard"}
                  </Link>
                  <span className="text-muted-foreground shrink-0 text-xs">storyboard</span>
                </li>
              ))}
              {toValidate.slice(0, 4).map(({ video }) => (
                <li key={video.id} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                  <Film className="size-4 shrink-0 text-sky-600" />
                  <Link href="/library?statut=a_valider" className="min-w-0 flex-1 truncate text-sm hover:underline">
                    {video.title ?? "Vidéo"}
                  </Link>
                  <span className="text-muted-foreground shrink-0 text-xs">vidéo finie</span>
                </li>
              ))}
              {storyboards.length + toValidate.length === 0 ? (
                <li className="text-muted-foreground text-sm">Lance des idées depuis Création : les storyboards et les vidéos finies arriveront ici.</li>
              ) : null}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>En fabrication</CardTitle>
            <CardDescription>
              {inProduction.length} vidéo{inProduction.length > 1 ? "s" : ""} en cours
            </CardDescription>
            <CardAction>
              <OpenTasksButton variant="ghost" size="sm">
                Tâches <ArrowRight />
              </OpenTasksButton>
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
                    <span className="truncate">{card.current_step ?? "en file"}</span>
                    <span className="tabular-nums">{formatPercent(card.progress_pct)}</span>
                  </div>
                </li>
              ))}
              {inProduction.length === 0 ? <li className="text-muted-foreground text-sm">Rien ne se fabrique en ce moment.</li> : null}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Prochaines publications</CardTitle>
            <CardDescription>6 prochains créneaux</CardDescription>
            <CardAction>
              <Button variant="ghost" size="sm" asChild>
                <Link href="/calendar">
                  Calendrier <ArrowRight />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {upcoming.map((slot) => {
                const ch = bySlug.get(slot.channel_slug);
                const onTikTok = tiktokAt(slot.channel_slug, slot.at);
                return (
                  <li key={`${slot.channel_slug}-${slot.at}`} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                    <div className="w-20 shrink-0 text-sm">
                      <div className="font-medium capitalize">{formatDate(slot.at, "EEE d MMM")}</div>
                      <div className="text-muted-foreground text-xs tabular-nums">{formatTime(slot.at)}</div>
                    </div>
                    {!selected && ch ? <ChannelBadge channel={ch} className="max-w-24" /> : null}
                    {slot.video ? (
                      <div className="flex min-w-0 flex-1 flex-col gap-1">
                        <p className="truncate text-sm" title={slot.video.title ?? undefined}>
                          {slot.video.title ?? "Sans titre"}
                        </p>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="flex items-center gap-1">
                            <YouTubeMark className="size-3.5" />
                            <VideoStatusBadge status={slot.video.status} className="w-fit" />
                          </span>
                          {onTikTok.map((t) => (
                            <TikTokLine key={t.video_id} item={t} showTitle={t.video_id !== slot.video?.id} />
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="flex min-w-0 flex-1 flex-col gap-1">
                        <div className="flex items-center gap-1.5 text-sm text-amber-700 dark:text-amber-400">
                          <TriangleAlert className="size-4" />
                          Créneau vide
                        </div>
                        {onTikTok.map((t) => (
                          <TikTokLine key={t.video_id} item={t} showTitle />
                        ))}
                      </div>
                    )}
                  </li>
                );
              })}
              {upcoming.length === 0 ? <li className="text-muted-foreground text-sm">Aucun créneau à venir.</li> : null}
            </ul>
          </CardContent>
        </Card>
      </section>

      <section id="ce-qui-marche" className="flex scroll-mt-20 flex-col gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Ce qui marche le mieux</h2>
          <p className="text-muted-foreground text-sm">Formats et sujets comparés sur les Shorts publiées par l’appli (l’historique importé n’est pas compté).</p>
        </div>
        <ExperimentsSection summary={experiments} />
      </section>
    </div>
  );
}
