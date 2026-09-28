import { Eye, Gauge, Heart, MessageCircle, Timer, Users } from "lucide-react";

import { KpiCard } from "@/components/kpi-card";
import { formatCompact, formatNumber, formatPercent, formatSigned } from "@/lib/format";
import type { StatsPage } from "@/lib/stats-types";

const LATER = "YouTube Analytics : 2 à 3 jours après la mise en ligne";

/** Six chiffres de la période : ce que les vidéos affichées ont fait, et la chaîne aujourd'hui. */
export function StatsKpis({ data }: { data: StatsPage }) {
  const t = data.totals;
  const period = data.period === "all" ? "depuis le début" : `sur ${data.period} jours`;
  return (
    <section aria-label="Indicateurs de la période" className="grid gap-4 *:min-w-0 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
      <KpiCard
        title="Vues"
        value={formatCompact(t.views)}
        icon={Eye}
        hint={`${formatNumber(t.videos)} vidéo${t.videos > 1 ? "s" : ""} publiée${t.videos > 1 ? "s" : ""} ${period}`}
      />
      <KpiCard
        title="Abonnés"
        value={formatNumber(data.subscribers)}
        icon={Users}
        delta={
          data.subscribers_delta_7d !== null
            ? { text: `${formatSigned(data.subscribers_delta_7d)} sur 7 j`, trend: data.subscribers_delta_7d > 0 ? "up" : data.subscribers_delta_7d < 0 ? "down" : "flat" }
            : undefined
        }
        hint={t.subscribers_gained !== null ? `${formatSigned(t.subscribers_gained)} grâce à ces vidéos` : "Total de la chaîne, relevé chaque heure"}
      />
      <KpiCard
        title="Rétention moyenne"
        value={formatPercent(t.average_view_pct, 1)}
        icon={Gauge}
        hint={t.average_view_pct !== null ? "Part de la vidéo regardée, pondérée par les vues" : LATER}
      />
      <KpiCard
        title="Encore là à 3 s"
        value={formatPercent(t.hook_retention_pct, 1)}
        icon={Timer}
        hint={t.hook_retention_pct !== null ? "L’accroche retient-elle ? (courbe de rétention)" : LATER}
      />
      <KpiCard
        title="J’aime"
        value={formatNumber(t.likes)}
        icon={Heart}
        hint={t.like_rate_pct !== null ? `${formatPercent(t.like_rate_pct, 2)} des vues` : undefined}
      />
      <KpiCard
        title="Commentaires · partages"
        value={`${formatNumber(t.comments)} · ${t.shares !== null ? formatNumber(t.shares) : "—"}`}
        icon={MessageCircle}
        hint={t.watch_hours !== null ? `${formatNumber(t.watch_hours, 1)} h regardées` : t.shares === null ? "Partages : dans 2 à 3 jours (YouTube Analytics)" : undefined}
      />
    </section>
  );
}
