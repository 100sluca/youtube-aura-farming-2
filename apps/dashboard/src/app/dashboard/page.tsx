import type { Metadata } from "next";
import Link from "next/link";
import { Info } from "lucide-react";

import { AutoRefresh } from "@/components/auto-refresh";
import { NetworkSwitcher } from "@/components/networks/network-cards";
import { PageHeader } from "@/components/page-header";
import { AnalysisPanel } from "@/components/stats/analysis-panel";
import { InstagramAccounts } from "@/components/stats/instagram-accounts";
import { InstagramExplorer } from "@/components/stats/instagram-explorer";
import { InstagramKpis } from "@/components/stats/instagram-kpis";
import { isStatsPlatform } from "@/components/stats/platform-tabs";
import { StatsExplorer } from "@/components/stats/stats-explorer";
import { StatsKpis } from "@/components/stats/stats-kpis";
import { StatsToolbar } from "@/components/stats/stats-toolbar";
import { TikTokAccounts } from "@/components/stats/tiktok-accounts";
import { TikTokExplorer } from "@/components/stats/tiktok-explorer";
import { TikTokKpis } from "@/components/stats/tiktok-kpis";
import { getChannelContext } from "@/lib/channel-server";
import { formatDate } from "@/lib/format";
import { getInstagramStatsPage } from "@/lib/instagram-stats";
import type { NetworkAccount } from "@/lib/network-types";
import { getNetworkAccounts } from "@/lib/networks";
import { getStatsPage } from "@/lib/stats";
import { isStatsPeriod } from "@/lib/stats-types";
import { getTikTokStatsPage } from "@/lib/tiktok-stats";

export const metadata: Metadata = { title: "Dashboard" };

/** Dashboard des statistiques (docs/25-dashboard-statistiques.md) : toutes les vidéos publiées avec leurs chiffres,
 * triables, en graphiques, et l'agent analyste qui dit ce qui marche et pourquoi. Trois onglets : YouTube, TikTok
 * (?plateforme=tiktok, docs/39) et Instagram (?plateforme=instagram, docs/62), avec les mêmes chiffres pour chaque compte.
 * En haut, une rangée avec chaque compte de chaque réseau (docs/62) : un clic change d'onglet et de compte. */
export default async function DashboardPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const [{ periode, plateforme, compte, chaine }, { channels, selected }] = await Promise.all([searchParams, getChannelContext()]);
  const period = isStatsPeriod(periode) ? periode : "28";
  const platform = isStatsPlatform(plateforme) ? plateforme : "youtube";
  const account = typeof compte === "string" ? compte : undefined;
  const networks = await getNetworkAccounts(channels, selected);
  if (platform === "tiktok") return <TikTokTab period={period} channels={channels} selected={selected} account={account} networks={networks} />;
  if (platform === "instagram") return <InstagramTab period={period} channels={channels} selected={selected} account={account} networks={networks} />;

  // Chaîne choisie dans la rangée du haut (?chaine=), sinon celle de l'en-tête
  const ytSelected = (typeof chaine === "string" && channels.find((c) => c.slug === chaine)) || selected;
  const data = await getStatsPage(channels, ytSelected, period);
  const busy = data.sync.active || data.analysis.running;

  return (
    <div className="flex flex-col gap-6">
      <AutoRefresh seconds={busy ? 4 : 60} />
      <PageHeader
        description={`Les chiffres de chaque vidéo publiée ${ytSelected ? `sur « ${ytSelected.name} »` : "sur tes chaînes"}, pour voir ce qui marche : vues, rétention, accroche à 3 s, j’aime, commentaires, partages, abonnés. La période filtre les vidéos par date de mise en ligne.`}
        actions={
          <StatsToolbar
            channel={ytSelected && ytSelected !== selected ? ytSelected.slug : null}
            period={period}
            syncActive={data.sync.active}
            syncSince={data.sync.since}
            countersAt={data.counters_at}
            lastError={data.sync.last_error}
            connected={data.connected}
          />
        }
      />
      <NetworkSwitcher accounts={networks} platform="youtube" account={ytSelected && ytSelected !== selected ? ytSelected.slug : null} period={period} />

      {data.connected && !data.analytics_through ? (
        <div className="flex gap-3 rounded-xl border border-sky-500/40 bg-sky-500/5 p-4 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-sky-600 dark:text-sky-400" />
          <p>
            <span className="font-medium">YouTube Analytics n’a encore rien publié pour cette chaîne.</span>{" "}
            <span className="text-muted-foreground">
              Il donne rétention, accroche à 3 s, durée regardée, partages et abonnés par vidéo avec 2 à 3 jours de retard : ces colonnes se rempliront toutes
              seules. Vues, j’aime, commentaires et abonnés de la chaîne sont déjà à jour (relevés chaque heure).
            </span>
          </p>
        </div>
      ) : null}

      <StatsKpis data={data} />
      <StatsExplorer data={data} showChannel={!ytSelected && channels.length > 1} />
      <AnalysisPanel analysis={data.analysis} />
    </div>
  );
}

/** Onglet TikTok (docs/39) : comptes reliés, chiffres de chaque vidéo sortie, publications programmées. */
async function TikTokTab({
  period,
  channels,
  selected,
  account,
  networks,
}: {
  period: Parameters<typeof getTikTokStatsPage>[2];
  channels: Parameters<typeof getTikTokStatsPage>[0];
  selected: Parameters<typeof getTikTokStatsPage>[1];
  account?: string;
  networks: NetworkAccount[];
}) {
  const data = await getTikTokStatsPage(channels, selected, period, account);
  const fetchedAt = data.accounts.map((a) => a.fetched_at).filter((t): t is string => Boolean(t)).sort().at(-1) ?? null;
  const business = data.accounts.some((a) => a.business);
  const viewsPending = data.videos.filter((v) => v.views_pending).length;
  const pending = viewsPending > 0 || (business && data.videos.some((v) => v.business_pending && v.age_h < 72));
  const noVideo = data.accounts.length > 0 && data.videos.length === 0;

  return (
    <div className="flex flex-col gap-6">
      <AutoRefresh seconds={data.sync.active ? 4 : 60} />
      <PageHeader
        description={`Les chiffres de chaque vidéo sortie sur TikTok ${selected ? `depuis « ${selected.name} »` : "sur tes comptes"}, comme pour YouTube : vues, part regardée, vue jusqu’au bout, j’aime, commentaires, partages, abonnés. La période filtre les vidéos par date de sortie.`}
        actions={
          <StatsToolbar
            platform="tiktok"
            account={data.account_id}
            period={period}
            syncActive={data.sync.active}
            syncSince={data.sync.since}
            countersAt={fetchedAt}
            lastError={data.sync.last_error}
            connected={data.configured && data.accounts.length > 0}
          />
        }
      />
      <NetworkSwitcher accounts={networks} platform="tiktok" account={data.account_id} period={period} />

      {!data.configured || data.accounts.length === 0 ? (
        <div className="flex gap-3 rounded-xl border border-sky-500/40 bg-sky-500/5 p-4 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-sky-600 dark:text-sky-400" />
          <p>
            <span className="font-medium">{!data.configured ? "TikTok n’est pas encore relié." : selected ? `Aucun compte TikTok relié à « ${selected.name} ».` : "Aucun compte TikTok relevé pour l’instant."}</span>{" "}
            <span className="text-muted-foreground">
              Dans{" "}
              <Link href="/settings#tiktok" className="underline underline-offset-2">
                Réglages → TikTok
              </Link>
              , colle la clé Zernio et relie un compte TikTok à la chaîne : ses chiffres arrivent ici dans l’heure.
            </span>
          </p>
        </div>
      ) : null}

      {data.accounts.length > 0 ? <TikTokAccounts data={data} period={period} /> : null}

      {noVideo ? (
        <div className="flex gap-3 rounded-xl border border-sky-500/40 bg-sky-500/5 p-4 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-sky-600 dark:text-sky-400" />
          <p>
            <span className="font-medium">Aucune vidéo sortie sur TikTok {period === "all" ? "pour l’instant" : "sur cette période"}.</span>{" "}
            <span className="text-muted-foreground">
              {data.upcoming[0]?.scheduled_for
                ? `La prochaine sort ${formatDate(data.upcoming[0].scheduled_for, "EEEE d MMMM 'à' HH:mm")} : ses chiffres arrivent dans l’heure qui suit.`
                : "Les chiffres arrivent dans l’heure qui suit la sortie d’une vidéo."}
            </span>
          </p>
        </div>
      ) : null}

      {pending ? (
        <div className="flex gap-3 rounded-xl border border-sky-500/40 bg-sky-500/5 p-4 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-sky-600 dark:text-sky-400" />
          <p>
            <span className="font-medium">Certains chiffres arrivent plus tard.</span>{" "}
            <span className="text-muted-foreground">
              {viewsPending
                ? `${viewsPending} vidéo${viewsPending > 1 ? "s" : ""} tout juste sortie${viewsPending > 1 ? "s" : ""} : j’aime, commentaires et partages sont lus en direct, les vues arrivent au prochain passage de Zernio (toutes les 90 min environ). `
                : "Vues, j’aime, commentaires et partages sont à jour (relevés chaque heure). "}
              {business
                ? "Part regardée, vue jusqu’au bout, abonnés gagnés et provenance des vues : TikTok les donne 24 à 48 h après la sortie, ces colonnes se rempliront toutes seules."
                : ""}
            </span>
          </p>
        </div>
      ) : null}

      {data.accounts.length > 0 ? (
        <>
          <TikTokKpis data={data} />
          <TikTokExplorer data={data} />
        </>
      ) : null}
    </div>
  );
}

/** Onglet Instagram (docs/62) : le compte des Shorts et celui de « Paf, j'achète », chiffres de chaque Reel, Reels
 * programmés. */
async function InstagramTab({
  period,
  channels,
  selected,
  account,
  networks,
}: {
  period: Parameters<typeof getInstagramStatsPage>[2];
  channels: Parameters<typeof getInstagramStatsPage>[0];
  selected: Parameters<typeof getInstagramStatsPage>[1];
  account?: string;
  networks: NetworkAccount[];
}) {
  const data = await getInstagramStatsPage(channels, selected, period, account);
  const connected = data.accounts.filter((a) => a.connected);
  const fetchedAt = connected.map((a) => a.fetched_at).filter((t): t is string => Boolean(t)).sort().at(-1) ?? null;
  const viewsPending = data.videos.filter((v) => v.views_pending).length;
  const current = data.accounts.find((a) => a.id === data.account_id);
  const noVideo = (current ? current.connected : connected.length > 0) && data.videos.length === 0;

  return (
    <div className="flex flex-col gap-6">
      <AutoRefresh seconds={data.sync.active ? 4 : 60} />
      <PageHeader
        description="Les chiffres de chaque Reel sorti sur Instagram, comme pour YouTube et TikTok : vues, accroche à 3 s, part regardée, portée, j’aime, commentaires, partages, enregistrements. Deux comptes : celui où partent les Shorts, et celui de « Paf, j’achète ». La période filtre les Reels par date de sortie."
        actions={
          <StatsToolbar
            platform="instagram"
            account={account ?? null}
            period={period}
            syncActive={data.sync.active}
            syncSince={data.sync.since}
            countersAt={fetchedAt}
            lastError={data.sync.last_error}
            connected={data.configured && connected.length > 0}
          />
        }
      />
      <NetworkSwitcher accounts={networks} platform="instagram" account={account ?? null} period={period} />

      {!data.configured || connected.length === 0 ? (
        <div className="flex gap-3 rounded-xl border border-sky-500/40 bg-sky-500/5 p-4 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-sky-600 dark:text-sky-400" />
          <p>
            <span className="font-medium">{!data.configured ? "Instagram n’est pas encore relié." : "Aucun compte Instagram relevé pour l’instant."}</span>{" "}
            <span className="text-muted-foreground">
              La clé Zernio de{" "}
              <Link href="/settings#tiktok" className="underline underline-offset-2">
                Réglages → TikTok
              </Link>{" "}
              lit le compte des Shorts, celle de l’onglet{" "}
              <Link href="/paf-j-achete" className="underline underline-offset-2">
                Paf, j’achète
              </Link>{" "}
              le compte du vendredi : leurs chiffres arrivent ici dans l’heure (ou tout de suite avec « Actualiser »).
            </span>
          </p>
        </div>
      ) : null}

      {data.accounts.length > 0 ? <InstagramAccounts data={data} period={period} /> : null}

      {noVideo ? (
        <div className="flex gap-3 rounded-xl border border-sky-500/40 bg-sky-500/5 p-4 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-sky-600 dark:text-sky-400" />
          <p>
            <span className="font-medium">Aucun Reel sorti {period === "all" ? "pour l’instant" : "sur cette période"}.</span>{" "}
            <span className="text-muted-foreground">
              {data.upcoming[0]?.scheduled_for
                ? `Le prochain sort ${formatDate(data.upcoming[0].scheduled_for, "EEEE d MMMM 'à' HH:mm")} : ses chiffres arrivent dans l’heure qui suit.`
                : "Les chiffres arrivent dans l’heure qui suit la sortie d’un Reel."}
            </span>
          </p>
        </div>
      ) : null}

      {viewsPending > 0 ? (
        <div className="flex gap-3 rounded-xl border border-sky-500/40 bg-sky-500/5 p-4 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-sky-600 dark:text-sky-400" />
          <p>
            <span className="font-medium">
              {viewsPending} Reel{viewsPending > 1 ? "s" : ""} tout juste sorti{viewsPending > 1 ? "s" : ""}.
            </span>{" "}
            <span className="text-muted-foreground">J’aime et commentaires sont lus en direct, les vues arrivent au relevé suivant.</span>
          </p>
        </div>
      ) : null}

      {connected.length > 0 && !(current && !current.connected) ? (
        <>
          <InstagramKpis data={data} />
          <InstagramExplorer data={data} />
        </>
      ) : null}
    </div>
  );
}
