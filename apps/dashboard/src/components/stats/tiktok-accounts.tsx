import Link from "next/link";
import { CalendarClock, ExternalLink, History, Music2 } from "lucide-react";

import { dashboardHref } from "@/components/stats/platform-tabs";
import { ToneBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCompact, formatDateTime, formatNumber, formatRelative } from "@/lib/format";
import type { StatsPeriod } from "@/lib/stats-types";
import type { TikTokStatsPage } from "@/lib/tiktok-stats-types";
import { cn } from "@/lib/utils";

const SOURCE_LABELS = { auto: "même heure que YouTube", rattrapage: "rattrapage", "bibliothèque": "Bibliothèque", cli: "terminal", manuel: "à la main" } as const;

/** Onglet TikTok (docs/39) : les comptes du périmètre (un choix par compte s'il y en a plusieurs) et les publications déjà
 * programmées, pas encore sorties. */
export function TikTokAccounts({ data, period }: { data: TikTokStatsPage; period: StatsPeriod }) {
  const upcoming = data.upcoming.slice(0, 6);
  return (
    <section className="grid gap-4 *:min-w-0 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>{data.accounts.length > 1 ? "Comptes TikTok" : "Compte TikTok"}</CardTitle>
          <CardDescription>Relié{data.accounts.length > 1 ? "s" : ""} dans Réglages → TikTok · chiffres relevés chaque heure chez Zernio</CardDescription>
          {data.accounts.length > 1 ? (
            <CardAction>
              <nav className="bg-muted inline-flex flex-wrap rounded-lg p-0.5 text-sm" aria-label="Compte">
                {[{ id: null as string | null, label: "Tous" }, ...data.accounts.map((a) => ({ id: a.id as string | null, label: `@${a.username}` }))].map((a) => (
                  <Link
                    key={a.id ?? "all"}
                    href={dashboardHref("tiktok", period, { compte: a.id })}
                    scroll={false}
                    aria-current={data.account_id === a.id ? "page" : undefined}
                    className={cn(
                      "flex h-8 items-center rounded-md px-3 font-medium whitespace-nowrap transition-colors",
                      data.account_id === a.id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {a.label}
                  </Link>
                ))}
              </nav>
            </CardAction>
          ) : null}
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col gap-3">
            {data.accounts.map((a) => (
              <li key={a.id} className={cn("flex flex-wrap items-center gap-4 rounded-lg border p-3", data.account_id && data.account_id !== a.id && "opacity-60")}>
                {a.avatar_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={a.avatar_url} alt="" className="size-10 rounded-full" />
                ) : (
                  <span className="bg-muted flex size-10 items-center justify-center rounded-full">
                    <Music2 className="size-5" />
                  </span>
                )}
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="flex flex-wrap items-center gap-2 font-medium">
                    @{a.username}
                    {a.business ? (
                      <ToneBadge tone="info" className="px-1.5 py-0 text-[11px]" title="Relié par l’appli TikTok for Business : temps regardé, part vue jusqu’au bout et provenance des vues">
                        Business
                      </ToneBadge>
                    ) : null}
                  </span>
                  <span className="text-muted-foreground text-xs" suppressHydrationWarning>
                    {a.channels.length ? `Chaîne${a.channels.length > 1 ? "s" : ""} ${a.channels.join(", ")}` : "Relié à aucune chaîne"}
                    {" · "}
                    {a.fetched_at ? `relevé ${formatRelative(a.fetched_at)}` : "jamais relevé"}
                  </span>
                </div>
                <dl className="flex gap-5 text-sm tabular-nums">
                  <div className="flex flex-col">
                    <dt className="text-muted-foreground text-xs">Abonnés</dt>
                    <dd className="font-medium">{formatNumber(a.followers)}</dd>
                  </div>
                  <div className="flex flex-col">
                    <dt className="text-muted-foreground text-xs">J’aime reçus</dt>
                    <dd className="font-medium">{formatCompact(a.likes)}</dd>
                  </div>
                  <div className="flex flex-col">
                    <dt className="text-muted-foreground text-xs">Vidéos</dt>
                    <dd className="font-medium">{formatNumber(a.videos)}</dd>
                  </div>
                </dl>
                {a.profile_url ? (
                  <Button variant="ghost" size="sm" asChild>
                    <a href={a.profile_url} target="_blank" rel="noreferrer noopener">
                      <ExternalLink />
                      Ouvrir
                    </a>
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Programmées sur TikTok</CardTitle>
          <CardDescription>
            {data.upcoming.length
              ? `${data.upcoming.length} publication${data.upcoming.length > 1 ? "s" : ""} prévue${data.upcoming.length > 1 ? "s" : ""}, pas encore sortie${data.upcoming.length > 1 ? "s" : ""}`
              : "Rien de prévu pour l’instant"}
          </CardDescription>
          <CardAction>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/calendar">
                <CalendarClock />
                Calendrier
              </Link>
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          <ul className="divide-y">
            {upcoming.map((u) => (
              <li key={u.video_id} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                <div className="w-24 shrink-0 text-xs tabular-nums">{u.scheduled_for ? formatDateTime(u.scheduled_for) : "tout de suite"}</div>
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <Link href={`/library?video=${u.video_id}`} className="truncate text-sm hover:underline" title={u.title ?? undefined}>
                    {u.title ?? "Sans titre"}
                  </Link>
                  <span className="text-muted-foreground flex items-center gap-1 text-[11px]">
                    {u.source === "rattrapage" ? <History className="size-3" /> : null}
                    {SOURCE_LABELS[u.source]}
                  </span>
                </div>
              </li>
            ))}
            {upcoming.length === 0 ? (
              <li className="text-muted-foreground text-sm">Les Shorts programmés sur YouTube partent aussi ici, à la même heure, si la publication automatique est active.</li>
            ) : null}
          </ul>
        </CardContent>
      </Card>
    </section>
  );
}
