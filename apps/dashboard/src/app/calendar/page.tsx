import type { Metadata } from "next";
import Link from "next/link";
import { ChevronLeft, ChevronRight, TriangleAlert } from "lucide-react";

import { SlotCell } from "@/components/calendar/slot-cell";
import { ChannelBadge } from "@/components/channel-badge";
import { PageHeader } from "@/components/page-header";
import { ToneBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { parseChannel, withChannel } from "@/lib/channel";
import { getChannels, getSchedule } from "@/lib/data";
import { NOW, formatDate, parisAddDays, parisDateTime, parisDayKey, parisSlot, parisStartOfWeek } from "@/lib/format";
import type { ChannelLang, ScheduleSlot } from "@/lib/types";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Calendrier" };

const WEEK_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

function resolveWeekAnchor(value: string | string[] | undefined): Date {
  const raw = Array.isArray(value) ? value[0] : value;
  const match = raw ? WEEK_RE.exec(raw) : null;
  if (!match) return NOW;
  const candidate = parisDateTime(Number(match[1]), Number(match[2]), Number(match[3]), 12);
  return Number.isNaN(candidate.getTime()) ? NOW : candidate;
}

const LEGEND: { label: string; tone: React.ComponentProps<typeof ToneBadge>["tone"]; hint: string }[] = [
  { label: "Publiée", tone: "success", hint: "en ligne sur YouTube" },
  { label: "Programmée", tone: "info", hint: "envoyée à YouTube avec date de publication" },
  { label: "Prête", tone: "success", hint: "rendu validé, envoi en attente" },
  { label: "Planifiée", tone: "neutral", hint: "créneau assigné, production en cours" },
  { label: "Échec", tone: "danger", hint: "intervention nécessaire" },
];

export default async function CalendarPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const channel = parseChannel(sp.channel);
  const weekStart = parisStartOfWeek(resolveWeekAnchor(sp.week));
  const [schedule, channels] = await Promise.all([getSchedule(weekStart.toISOString(), 7), getChannels()]);

  const days = Array.from({ length: 7 }, (_, i) => parisAddDays(weekStart, i));
  const todayKey = parisDayKey(NOW);
  const prevWeek = parisDayKey(parisAddDays(weekStart, -7));
  const nextWeek = parisDayKey(parisAddDays(weekStart, 7));
  const visibleChannels = channel ? channels.filter((c) => c.slug === channel) : channels;
  const bySlot = new Map<string, ScheduleSlot>(schedule.map((s) => [`${s.channel_slug}|${s.at}`, s]));
  const emptySoon = schedule.filter((s) => {
    const at = new Date(s.at).getTime();
    return !s.video && at > NOW.getTime() && at - NOW.getTime() < 48 * 3_600_000 && (!channel || s.channel_slug === channel);
  }).length;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        description={`Semaine du ${formatDate(weekStart, "d MMMM")} au ${formatDate(days[6], "d MMMM yyyy")} · 3 créneaux par jour et par chaîne (heure de Paris).`}
        actions={
          <>
            <Button variant="outline" size="sm" asChild>
              <Link href={withChannel(`/calendar?week=${prevWeek}`, channel)} aria-label="Semaine précédente">
                <ChevronLeft />
                Semaine précédente
              </Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link href={withChannel("/calendar", channel)}>Aujourd’hui</Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link href={withChannel(`/calendar?week=${nextWeek}`, channel)} aria-label="Semaine suivante">
                Semaine suivante
                <ChevronRight />
              </Link>
            </Button>
          </>
        }
      />

      {emptySoon > 0 ? (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-300">
          <TriangleAlert className="size-4 shrink-0" />
          {emptySoon} créneau{emptySoon > 1 ? "x" : ""} vide{emptySoon > 1 ? "s" : ""} dans les 48 prochaines heures.
        </div>
      ) : null}

      <Card className="gap-0 overflow-hidden py-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] border-collapse text-sm">
            <thead>
              <tr className="bg-muted/40">
                <th scope="col" className="bg-card sticky left-0 z-10 w-44 border-b p-3 text-left text-xs font-medium">
                  Chaîne · créneau
                </th>
                {days.map((d) => {
                  const isToday = parisDayKey(d) === todayKey;
                  return (
                    <th
                      key={d.toISOString()}
                      scope="col"
                      className={cn("border-b border-l p-3 text-left font-medium", isToday && "bg-accent/60")}
                    >
                      <div className="capitalize">{formatDate(d, "EEEE")}</div>
                      <div className="text-muted-foreground text-xs font-normal">
                        {formatDate(d, "d MMM")}
                        {isToday ? " · aujourd’hui" : ""}
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {visibleChannels.flatMap((ch) =>
                ch.publish_slots.map((slot, slotIndex) => (
                  <tr key={`${ch.slug}-${slot}`} className={cn("border-b last:border-b-0", slotIndex === 0 && "border-t-2")}>
                    <th scope="row" className="bg-card sticky left-0 z-10 p-3 text-left font-normal">
                      <div className="flex items-center gap-2">
                        <ChannelBadge lang={ch.lang as ChannelLang} />
                        <span className="tabular-nums">{slot}</span>
                      </div>
                    </th>
                    {days.map((d) => {
                      const at = parisSlot(d, slot).toISOString();
                      const isToday = parisDayKey(d) === todayKey;
                      return (
                        <td key={at} className={cn("h-20 w-[12.5%] border-l p-2 align-top", isToday && "bg-accent/30")}>
                          <SlotCell slot={bySlot.get(`${ch.slug}|${at}`)} />
                        </td>
                      );
                    })}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
        <span className="text-muted-foreground">Légende :</span>
        {LEGEND.map((item) => (
          <span key={item.label} className="inline-flex items-center gap-1.5">
            <ToneBadge tone={item.tone}>{item.label}</ToneBadge>
            <span className="text-muted-foreground">{item.hint}</span>
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-flex items-center gap-1 rounded-md border border-amber-500/50 bg-amber-500/10 px-2 py-0.5 text-amber-700 dark:text-amber-400">
            <TriangleAlert className="size-3" />
            Vide · sous 48 h
          </span>
          <span className="text-muted-foreground">créneau à combler en urgence</span>
        </span>
      </div>
    </div>
  );
}
