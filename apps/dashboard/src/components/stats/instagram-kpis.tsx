import { Eye, Gauge, Heart, MessageCircle, Timer, Users } from "lucide-react";

import { KpiCard } from "@/components/kpi-card";
import { formatCompact, formatNumber, formatPercent, formatSigned } from "@/lib/format";
import type { InstagramStatsPage } from "@/lib/instagram-stats-types";

const LATER = "Instagram le donne après les premières vues";

/** Six chiffres de la période, comme les onglets YouTube et TikTok. « Encore là à 3 s » = 100 − la part des spectateurs
 * partis dans les 3 premières secondes (estimation de Meta) : l'équivalent de l'accroche à 3 s de YouTube. */
export function InstagramKpis({ data }: { data: InstagramStatsPage }) {
  const t = data.totals;
  const period = data.period === "all" ? "depuis le début" : `sur ${data.period} jours`;
  const shown = (data.account_id ? data.accounts.filter((a) => a.id === data.account_id) : data.accounts).filter((a) => a.connected);
  const followers = shown.some((a) => a.followers !== null) ? shown.reduce((s, a) => s + (a.followers ?? 0), 0) : null;
  const delta = shown.length && shown.every((a) => a.followers_delta_7d !== null) ? shown.reduce((s, a) => s + (a.followers_delta_7d ?? 0), 0) : null;
  return (
    <section aria-label="Indicateurs Instagram de la période" className="grid gap-4 *:min-w-0 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
      <KpiCard
        title="Vues"
        value={formatCompact(t.views)}
        icon={Eye}
        hint={`${formatNumber(t.videos)} Reel${t.videos > 1 ? "s" : ""} sorti${t.videos > 1 ? "s" : ""} ${period}${t.reach !== null ? ` · ${formatCompact(t.reach)} comptes touchés` : ""}`}
      />
      <KpiCard
        title="Abonnés"
        value={formatNumber(followers)}
        icon={Users}
        delta={delta !== null ? { text: `${formatSigned(delta)} sur 7 j`, trend: delta > 0 ? "up" : delta < 0 ? "down" : "flat" } : undefined}
        hint={shown.length > 1 ? "Total des comptes, relevé chaque heure" : "Total du compte, relevé chaque heure"}
      />
      <KpiCard
        title="Regardé en moyenne"
        value={formatPercent(t.watched_pct)}
        icon={Gauge}
        hint={t.avg_watch_s !== null ? `${formatNumber(t.avg_watch_s, 1)} s par vue, pondéré par les vues` : LATER}
      />
      <KpiCard
        title="Encore là à 3 s"
        value={formatPercent(t.hook_pct)}
        icon={Timer}
        hint={t.hook_pct !== null ? "Spectateurs qui n’ont pas zappé dans les 3 premières secondes (estimation de Meta)" : LATER}
      />
      <KpiCard title="J’aime" value={formatNumber(t.likes)} icon={Heart} hint={t.like_rate_pct !== null ? `${formatPercent(t.like_rate_pct, 2)} des vues` : undefined} />
      <KpiCard
        title="Commentaires · partages"
        value={`${formatNumber(t.comments)} · ${formatNumber(t.shares)}`}
        icon={MessageCircle}
        hint={t.saves !== null ? `${formatNumber(t.saves)} enregistrement${t.saves > 1 ? "s" : ""}` : t.watch_hours !== null ? `${formatNumber(t.watch_hours, 1)} h regardées` : undefined}
      />
    </section>
  );
}
