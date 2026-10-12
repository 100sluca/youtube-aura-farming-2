import Link from "next/link";
import { TrendingDown, TrendingUp, TriangleAlert } from "lucide-react";

import { InstagramMark, TikTokMark, YouTubeMark } from "@/components/platform-marks";
import { dashboardHref } from "@/components/stats/platform-tabs";
import { formatCompact, formatNumber, formatSigned, formatSignedPercent } from "@/lib/format";
import type { NetworkAccount, NetworkPlatform } from "@/lib/network-types";
import type { StatsPeriod } from "@/lib/stats-types";
import { cn } from "@/lib/utils";

const MARKS: Record<NetworkPlatform, (p: { className?: string }) => React.ReactNode> = { youtube: YouTubeMark, tiktok: TikTokMark, instagram: InstagramMark };

/** Barres des mini-courbes, une teinte par réseau (classes écrites en entier pour Tailwind). */
const BAR: Record<NetworkPlatform, string> = {
  youtube: "fill-[#e62117]",
  tiktok: "fill-foreground",
  instagram: "fill-[#e1306c]",
};

/** Lien du Dashboard sur ce compte (onglet du réseau, compte choisi). */
export function networkHref(a: NetworkAccount, period: StatsPeriod = "28"): string {
  if (!a.account) return dashboardHref(a.platform, period);
  return dashboardHref(a.platform, period, a.platform === "youtube" ? { chaine: a.account } : { compte: a.account });
}

function delta(a: NetworkAccount): { text: string; up: boolean | null } | null {
  if (a.views_7d === null || a.views_prev_7d === null) return null;
  if (a.views_prev_7d === 0) return a.views_7d > 0 ? { text: "nouveau", up: true } : null;
  const pct = ((a.views_7d - a.views_prev_7d) / a.views_prev_7d) * 100;
  return { text: `${formatSignedPercent(pct, Math.abs(pct) < 10 ? 1 : 0)} vs 7 j d’avant`, up: pct > 0 ? true : pct < 0 ? false : null };
}

/** Vues par jour sur 28 jours, en petites barres ; un jour inconnu n'a qu'un trait de base. */
function Sparkline({ account }: { account: NetworkAccount }) {
  const max = Math.max(1, ...account.daily.map((d) => d.views ?? 0));
  const n = account.daily.length || 1;
  return (
    <svg viewBox={`0 0 ${n * 4} 32`} preserveAspectRatio="none" className="h-8 w-full" role="img" aria-label={`Vues par jour sur ${n} jours`}>
      {account.daily.map((d, i) =>
        d.views === null ? (
          <rect key={d.day} x={i * 4} y={31} width={3} height={1} className="fill-muted-foreground/30" />
        ) : (
          <rect key={d.day} x={i * 4} y={32 - Math.max(1, (d.views / max) * 30)} width={3} height={Math.max(1, (d.views / max) * 30)} rx={0.6} className={BAR[account.platform]}>
            <title>{`${d.day} : ${formatNumber(d.views)} vues`}</title>
          </rect>
        ),
      )}
    </svg>
  );
}

/** Vue d'ensemble (docs/62) : une carte par compte, réseau par réseau. Un clic ouvre l'onglet du réseau sur ce compte. */
export function NetworkCards({ accounts }: { accounts: NetworkAccount[] }) {
  return (
    <div className="grid gap-4 *:min-w-0 sm:grid-cols-2 xl:grid-cols-4">
      {accounts.map((a) => {
        const Mark = MARKS[a.platform];
        const d = delta(a);
        return (
          <Link
            key={a.key}
            href={networkHref(a)}
            className={cn(
              "bg-card hover:border-foreground/30 flex flex-col gap-3 rounded-xl border p-4 shadow-xs transition-colors",
              !a.connected && "border-dashed shadow-none",
            )}
          >
            <div className="flex items-center gap-2">
              <Mark className="size-5 [&>svg]:size-3" />
              <span className="min-w-0 flex-1 truncate font-medium">{a.name}</span>
              <span className="text-muted-foreground shrink-0 text-xs">{a.role}</span>
            </div>
            {a.connected ? (
              <>
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span className="text-2xl font-semibold tabular-nums">{a.views_7d === null ? "—" : formatCompact(a.views_7d)}</span>
                  <span className="text-muted-foreground text-sm">vues sur 7 j</span>
                  {d ? (
                    <span
                      className={cn(
                        "flex items-center gap-0.5 text-xs font-medium",
                        d.up === true && "text-emerald-600 dark:text-emerald-400",
                        d.up === false && "text-red-600 dark:text-red-400",
                        d.up === null && "text-muted-foreground",
                      )}
                    >
                      {d.up === true ? <TrendingUp className="size-3.5" /> : d.up === false ? <TrendingDown className="size-3.5" /> : null}
                      {d.text}
                    </span>
                  ) : null}
                </div>
                <Sparkline account={a} />
                <p className="text-muted-foreground text-xs tabular-nums">
                  {a.followers === null ? "abonnés inconnus" : `${formatNumber(a.followers)} abonné${(a.followers ?? 0) > 1 ? "s" : ""}`}
                  {a.followers_delta_7d ? ` (${formatSigned(a.followers_delta_7d)} / 7 j)` : ""}
                  {" · "}
                  {a.posts_7d} vidéo{a.posts_7d > 1 ? "s" : ""} sortie{a.posts_7d > 1 ? "s" : ""} en 7 j
                  {a.views_28d !== null ? ` · ${formatCompact(a.views_28d)} vues sur 28 j` : ""}
                </p>
              </>
            ) : null}
            {a.warning ? (
              <p className="flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-400">
                <TriangleAlert className="mt-px size-3.5 shrink-0" />
                {a.warning}
              </p>
            ) : null}
          </Link>
        );
      })}
    </div>
  );
}

/** Haut du Dashboard (docs/62) : tous les comptes en une rangée, avec leurs vues sur 7 jours ; un clic change d'onglet et
 * de compte d'un coup. Le compte affiché est en relief (tous ceux du réseau quand l'onglet montre « Tous »). */
export function NetworkSwitcher({
  accounts,
  platform,
  account,
  period,
}: {
  accounts: NetworkAccount[];
  platform: NetworkPlatform;
  /** Compte affiché (?compte= ou ?chaine=), null : tous les comptes du réseau. */
  account: string | null;
  period: StatsPeriod;
}) {
  return (
    <nav aria-label="Réseau et compte" className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
      {accounts.map((a) => {
        const Mark = MARKS[a.platform];
        const active = a.platform === platform && (account === null || account === a.account);
        return (
          <Link
            key={a.key}
            href={networkHref(a, period)}
            scroll={false}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex min-w-40 shrink-0 items-center gap-2.5 rounded-lg border px-3 py-2 text-sm transition-colors",
              active ? "border-foreground/40 bg-background shadow-sm" : "bg-muted/40 text-muted-foreground hover:text-foreground border-transparent",
              !a.connected && "border-dashed",
            )}
            title={a.warning ?? undefined}
          >
            <Mark className="size-5 [&>svg]:size-3" />
            <span className="flex min-w-0 flex-col leading-tight">
              <span className={cn("truncate font-medium", active && "text-foreground")}>{a.name}</span>
              <span className="text-xs tabular-nums">
                {!a.connected ? (
                  <span className="text-amber-700 dark:text-amber-400">pas encore relié</span>
                ) : (
                  <>
                    {a.views_7d === null ? "—" : formatCompact(a.views_7d)} vues / 7 j{a.warning ? <TriangleAlert className="ml-1 inline size-3 text-amber-600" /> : null}
                  </>
                )}
              </span>
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
