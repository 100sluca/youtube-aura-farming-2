import type { Metadata } from "next";
import Link from "next/link";
import { ChevronLeft, ChevronRight, TriangleAlert } from "lucide-react";

import { SlotCell, TikTokLine } from "@/components/calendar/slot-cell";
import { ChannelBadge } from "@/components/channel-badge";
import { PageHeader } from "@/components/page-header";
import { TikTokMark, YouTubeMark } from "@/components/platform-marks";
import { ToneBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { getChannelContext } from "@/lib/channel-server";
import { getSchedule } from "@/lib/data";
import { now, formatDate, parisAddDays, parisDateTime, parisDayKey, parisSlot, parisStartOfWeek } from "@/lib/format";
import { getTikTokCalendar } from "@/lib/tiktok";
import type { TikTokCalendarItem } from "@/lib/tiktok-types";
import type { ScheduleSlot } from "@/lib/types";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Calendrier" };

const WEEK_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

function resolveWeekAnchor(value: string | string[] | undefined): Date {
  const raw = Array.isArray(value) ? value[0] : value;
  const match = raw ? WEEK_RE.exec(raw) : null;
  if (!match) return now();
  const candidate = parisDateTime(Number(match[1]), Number(match[2]), Number(match[3]), 12);
  return Number.isNaN(candidate.getTime()) ? now() : candidate;
}

const LEGEND: { label: string; tone: React.ComponentProps<typeof ToneBadge>["tone"]; hint: string }[] = [
  { label: "Publiée", tone: "success", hint: "en ligne" },
  { label: "Programmée", tone: "info", hint: "envoyée avec sa date de publication" },
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
  const { channels, selected } = await getChannelContext();
  const channel = selected?.slug;
  const weekStart = parisStartOfWeek(resolveWeekAnchor(sp.week));
  const [schedule, tiktok] = await Promise.all([
    getSchedule(weekStart.toISOString(), 7),
    getTikTokCalendar(weekStart.toISOString(), parisAddDays(weekStart, 7).toISOString()),
  ]);

  const days = Array.from({ length: 7 }, (_, i) => parisAddDays(weekStart, i));
  const todayKey = parisDayKey(now());
  const prevWeek = parisDayKey(parisAddDays(weekStart, -7));
  const nextWeek = parisDayKey(parisAddDays(weekStart, 7));
  const visibleChannels = selected ? [selected] : channels.filter((c) => c.is_active);
  const bySlot = new Map<string, ScheduleSlot>(schedule.map((s) => [`${s.channel_slug}|${s.at}`, s]));

  // TikTok (docs/39) : chaque publication va dans le créneau de sa chaîne (±10 min), sinon dans la ligne « autres heures »
  const tiktokBySlot = new Map<string, TikTokCalendarItem[]>();
  const tiktokOther = new Map<string, TikTokCalendarItem[]>();
  for (const t of tiktok) {
    const ch = channels.find((c) => c.id === t.channel_id);
    if (!ch) continue;
    const ms = new Date(t.at).getTime();
    const slot = ch.publish_slots.map((s) => parisSlot(t.at, s)).find((s) => Math.abs(s.getTime() - ms) < 10 * 60_000);
    const key = slot ? `${ch.slug}|${slot.toISOString()}` : `${ch.slug}|${parisDayKey(t.at)}`;
    const target = slot ? tiktokBySlot : tiktokOther;
    target.set(key, [...(target.get(key) ?? []), t]);
  }
  const emptySoon = schedule.filter((s) => {
    const at = new Date(s.at).getTime();
    return !s.video && at > now().getTime() && at - now().getTime() < 48 * 3_600_000 && (!channel || s.channel_slug === channel);
  }).length;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        description={`Semaine du ${formatDate(weekStart, "d MMMM")} au ${formatDate(days[6], "d MMMM yyyy")} · 3 créneaux par jour et par chaîne (heure de Paris), sur YouTube et TikTok.`}
        actions={
          <>
            <Button variant="outline" size="sm" asChild>
              <Link href={`/calendar?week=${prevWeek}`} aria-label="Semaine précédente">
                <ChevronLeft />
                Semaine précédente
              </Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link href="/calendar">Aujourd’hui</Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link href={`/calendar?week=${nextWeek}`} aria-label="Semaine suivante">
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
              {visibleChannels.flatMap((ch) => {
                const rows = ch.publish_slots.map((slot, slotIndex) => (
                  <tr key={`${ch.slug}-${slot}`} className={cn("border-b last:border-b-0", slotIndex === 0 && "border-t-2")}>
                    <th scope="row" className="bg-card sticky left-0 z-10 p-3 text-left font-normal">
                      <div className="flex items-center gap-2">
                        <ChannelBadge channel={ch} className="max-w-28" />
                        <span className="tabular-nums">{slot}</span>
                      </div>
                    </th>
                    {days.map((d) => {
                      const at = parisSlot(d, slot).toISOString();
                      const isToday = parisDayKey(d) === todayKey;
                      return (
                        <td key={at} className={cn("h-20 w-[12.5%] border-l p-2 align-top", isToday && "bg-accent/30")}>
                          <SlotCell slot={bySlot.get(`${ch.slug}|${at}`)} tiktok={tiktokBySlot.get(`${ch.slug}|${at}`)} />
                        </td>
                      );
                    })}
                  </tr>
                ));
                // Publications TikTok hors des créneaux (« Publier sur TikTok » d'une vidéo déjà sortie, créneau déplacé)
                const others = days.map((d) => tiktokOther.get(`${ch.slug}|${parisDayKey(d)}`) ?? []);
                if (others.some((o) => o.length > 0)) {
                  rows.push(
                    <tr key={`${ch.slug}-tiktok`} className="border-b last:border-b-0">
                      <th scope="row" className="bg-card sticky left-0 z-10 p-3 text-left font-normal">
                        <div className="flex items-center gap-2">
                          <ChannelBadge channel={ch} className="max-w-28" />
                          <TikTokMark />
                          <span className="text-muted-foreground text-xs">autres heures</span>
                        </div>
                      </th>
                      {days.map((d, i) => (
                        <td key={d.toISOString()} className={cn("w-[12.5%] border-l p-2 align-top", parisDayKey(d) === todayKey && "bg-accent/30")}>
                          <div className="flex flex-col gap-2">
                            {others[i].map((t) => (
                              <TikTokLine key={t.video_id} item={t} showTitle showTime />
                            ))}
                          </div>
                        </td>
                      ))}
                    </tr>,
                  );
                }
                return rows;
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
        <span className="text-muted-foreground">Légende :</span>
        <span className="inline-flex items-center gap-1.5">
          <YouTubeMark className="size-3.5" />
          <span className="text-muted-foreground">YouTube</span>
          <TikTokMark className="ml-1 size-3.5" />
          <span className="text-muted-foreground">TikTok (même heure, sauf « autres heures »)</span>
        </span>
        {LEGEND.map((item) => (
          <span key={item.label} className="inline-flex items-center gap-1.5">
            <ToneBadge tone={item.tone}>{item.label}</ToneBadge>
            <span className="text-muted-foreground">{item.hint}</span>
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <ToneBadge tone="info">Rattrapage</ToneBadge>
          <span className="text-muted-foreground">ancienne vidéo envoyée sur TikTok dans un créneau vide</span>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <ToneBadge tone="neutral" className="border-dashed opacity-70">
            Rattrapage prévu
          </ToneBadge>
          <span className="text-muted-foreground">y partira si aucune nouvelle vidéo ne prend le créneau</span>
        </span>
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
