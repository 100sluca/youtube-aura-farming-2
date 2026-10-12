import Link from "next/link";
import { CalendarClock, ExternalLink, TriangleAlert } from "lucide-react";

import { InstagramMark } from "@/components/platform-marks";
import { dashboardHref } from "@/components/stats/platform-tabs";
import { ToneBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCompact, formatDateTime, formatNumber, formatRelative, formatSigned } from "@/lib/format";
import { PAF_ACCOUNT, instagramLabel, type InstagramStatsPage } from "@/lib/instagram-stats-types";
import type { StatsPeriod } from "@/lib/stats-types";
import { cn } from "@/lib/utils";

/** Onglet Instagram (docs/62) : les comptes du périmètre (un choix par compte), leur rôle (Shorts d'une chaîne ou « Paf,
 * j'achète »), ce qui cloche dans le branchement, et les Reels déjà programmés. */
export function InstagramAccounts({ data, period }: { data: InstagramStatsPage; period: StatsPeriod }) {
  const upcoming = data.upcoming.slice(0, 6);
  const choices = data.accounts;
  return (
    <section className="grid gap-4 *:min-w-0 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>{data.accounts.length > 1 ? "Comptes Instagram" : "Compte Instagram"}</CardTitle>
          <CardDescription>Reliés dans Réglages → Instagram et l’onglet Paf, j’achète · chiffres relevés chaque heure chez Zernio</CardDescription>
          {choices.length > 1 ? (
            <CardAction>
              <nav className="bg-muted inline-flex flex-wrap rounded-lg p-0.5 text-sm" aria-label="Compte">
                {[{ id: null as string | null, label: "Tous", off: false }, ...choices.map((a) => ({ id: a.connected ? a.id : PAF_ACCOUNT, label: instagramLabel(a), off: !a.connected }))].map((a) => {
                  const current = data.account_id === a.id;
                  return (
                    <Link
                      key={a.id ?? "all"}
                      href={dashboardHref("instagram", period, { compte: a.id })}
                      scroll={false}
                      aria-current={current ? "page" : undefined}
                      className={cn(
                        "flex h-8 items-center rounded-md px-3 font-medium whitespace-nowrap transition-colors",
                        current ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                        a.off && "italic",
                      )}
                    >
                      {a.label}
                    </Link>
                  );
                })}
              </nav>
            </CardAction>
          ) : null}
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col gap-3">
            {data.accounts.map((a) => (
              <li key={a.id} className={cn("flex flex-col gap-2 rounded-lg border p-3", data.account_id && data.account_id !== a.id && "opacity-60", !a.connected && "border-dashed")}>
                <div className="flex flex-wrap items-center gap-4">
                  {a.avatar_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={a.avatar_url} alt="" className="size-10 rounded-full" />
                  ) : (
                    <InstagramMark className="size-10 rounded-full [&>svg]:size-5" />
                  )}
                  <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="flex flex-wrap items-center gap-2 font-medium">
                      {a.connected ? `@${a.username}` : "Paf, j’achète"}
                      {a.channels.length ? (
                        <ToneBadge tone="info" className="px-1.5 py-0 text-[11px]" title="Les Shorts de ces chaînes partent aussi ici, à la même heure">
                          Shorts · {a.channels.join(", ")}
                        </ToneBadge>
                      ) : null}
                      {a.paf && a.connected ? (
                        <ToneBadge tone="warning" className="px-1.5 py-0 text-[11px]" title="La vidéo du vendredi, chaque semaine à 7 h (docs/50)">
                          Paf, j’achète
                        </ToneBadge>
                      ) : null}
                    </span>
                    <span className="text-muted-foreground text-xs" suppressHydrationWarning>
                      {a.connected ? (a.fetched_at ? `relevé ${formatRelative(a.fetched_at)}` : "jamais relevé") : "pas encore de compte à lui"}
                    </span>
                  </div>
                  {a.connected ? (
                    <dl className="flex gap-5 text-sm tabular-nums">
                      <div className="flex flex-col">
                        <dt className="text-muted-foreground text-xs">Abonnés</dt>
                        <dd className="font-medium">
                          {formatNumber(a.followers)}
                          {a.followers_delta_7d ? <span className="text-muted-foreground ml-1 text-xs font-normal">{formatSigned(a.followers_delta_7d)} / 7 j</span> : null}
                        </dd>
                      </div>
                      <div className="flex flex-col" title="Vues de tout le compte (Reels, publications, stories) sur 28 jours, d’après Instagram (jusqu’à 48 h de retard)">
                        <dt className="text-muted-foreground text-xs">Vues 28 j</dt>
                        <dd className="font-medium">{formatCompact(a.views_28d)}</dd>
                      </div>
                      <div className="flex flex-col" title="Comptes différents touchés sur 28 jours">
                        <dt className="text-muted-foreground text-xs">Portée 28 j</dt>
                        <dd className="font-medium">{formatCompact(a.reach_28d)}</dd>
                      </div>
                      <div className="flex flex-col">
                        <dt className="text-muted-foreground text-xs">Publications</dt>
                        <dd className="font-medium">{formatNumber(a.media_count)}</dd>
                      </div>
                    </dl>
                  ) : null}
                  {a.profile_url ? (
                    <Button variant="ghost" size="sm" asChild>
                      <a href={a.profile_url} target="_blank" rel="noreferrer noopener">
                        <ExternalLink />
                        Ouvrir
                      </a>
                    </Button>
                  ) : a.paf ? (
                    <Button variant="outline" size="sm" asChild>
                      <Link href="/paf-j-achete">Onglet Paf, j’achète</Link>
                    </Button>
                  ) : null}
                </div>
                {a.warning ? (
                  <p className="flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-400">
                    <TriangleAlert className="mt-px size-3.5 shrink-0" />
                    {a.warning}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Programmés sur Instagram</CardTitle>
          <CardDescription>
            {data.upcoming.length
              ? `${data.upcoming.length} Reel${data.upcoming.length > 1 ? "s" : ""} prévu${data.upcoming.length > 1 ? "s" : ""}, pas encore sorti${data.upcoming.length > 1 ? "s" : ""}`
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
              <li key={u.key} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                <div className="w-24 shrink-0 text-xs tabular-nums">{u.scheduled_for ? formatDateTime(u.scheduled_for) : "tout de suite"}</div>
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  {u.video_id ? (
                    <Link href={`/library?video=${u.video_id}`} className="truncate text-sm hover:underline" title={u.title}>
                      {u.title}
                    </Link>
                  ) : (
                    <Link href="/paf-j-achete" className="truncate text-sm hover:underline" title={u.title}>
                      {u.title}
                    </Link>
                  )}
                  <span className="text-muted-foreground text-[11px]">{u.username ? `@${u.username}` : ""}{u.paf ? " · vidéo du vendredi" : " · même heure que YouTube"}</span>
                </div>
              </li>
            ))}
            {upcoming.length === 0 ? (
              <li className="text-muted-foreground text-sm">Les Shorts programmés sur YouTube partent aussi ici, à la même heure, si la publication automatique est active (Réglages → Instagram).</li>
            ) : null}
          </ul>
        </CardContent>
      </Card>
    </section>
  );
}
