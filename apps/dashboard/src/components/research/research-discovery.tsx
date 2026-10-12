"use client";

import * as React from "react";
import { ExternalLink, Loader2, MonitorPlay, Radar, X } from "lucide-react";

import { discoverNow, dismissChannel, longIdeasFromNiche } from "@/app/research/discovery-actions";
import { ToneBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCompact, formatRelative } from "@/lib/format";
import type { DiscoveredNiche, DiscoveryData } from "@/lib/research-discovery";

type Notice = { ok: boolean; message: string } | null;

const CATEGORY_LABELS: Record<string, string> = {
  histoire: "Histoire",
  mystere_crime: "Mystères, enquêtes",
  horreur_histoires: "Horreur, histoires",
  science_education: "Science, éducation",
  espace_sommeil: "Espace, pour dormir",
  geopolitique_guerre: "Géopolitique, guerre",
  argent_business: "Argent, business",
  tech_ia: "Tech, IA",
  psychologie_sante: "Psychologie, santé",
  survie_nature: "Survie, nature",
  lieux_voyage: "Lieux, voyages",
  culture_cinema: "Culture, cinéma",
  divertissement: "Divertissement",
};

const money = (n: number | null | undefined) => (n == null ? "?" : `${formatCompact(Math.round(n))} $`);

/** Recherche → Découverte (docs/63 §9) : les niches qui rapportent, découvertes au-delà des nôtres. */
export function DiscoveryPanel({ data }: { data: DiscoveryData }) {
  const [notice, setNotice] = React.useState<Notice>(null);
  const [pending, start] = React.useTransition();
  const [lang, setLang] = React.useState<"all" | "fr" | "en">("all");
  const run = (fn: () => Promise<{ ok: boolean; message: string }>) => start(async () => setNotice(await fn()));
  // filtre de langue : chaque niche ne garde que ses chaînes de cette langue, et son total se recalcule
  const niches = React.useMemo(() => {
    if (lang === "all") return data.niches;
    return data.niches
      .map((n) => {
        const channels = n.channels.filter((c) => (c.lang ?? "").startsWith(lang));
        return { ...n, channels, revenue: channels.reduce((t, c) => t + (c.revenue ?? 0), 0), langs: [lang] };
      })
      .filter((n) => n.channels.length)
      .sort((a, b) => b.revenue - a.revenue);
  }, [data.niches, lang]);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => run(discoverNow)} disabled={pending || Boolean(data.running)}>
          {data.running ? <Loader2 className="animate-spin" /> : <Radar />}
          {data.running ? "Découverte en cours…" : "Découvrir maintenant"}
        </Button>
        <span className="text-muted-foreground text-sm">
          {data.total} chaînes qui percent · {data.seedsDone} sujets de départ explorés
          {data.lastRun ? ` · dernier passage ${formatRelative(data.lastRun)}` : ""} · chaque jour à 9 h 30
        </span>
        {data.running ? (
          <span className="text-xs text-violet-600 dark:text-violet-400">
            {data.running.status === "queued" ? "En file" : `${data.running.label ?? "En cours"}${data.running.progress != null ? ` (${data.running.progress} %)` : ""}`}
          </span>
        ) : null}
        {notice ? <span className={`text-xs ${notice.ok ? "text-emerald-600" : "text-destructive"}`}>{notice.message}</span> : null}
      </div>
      <p className="text-muted-foreground text-sm">
        Des chaînes récentes (moins de 18 mois) ou petites (moins de 150 000 abonnés) dont une vidéo des 45 derniers jours dépasse 50 000 vues,
        trouvées en balayant de larges sujets en français et en anglais, surtout en vidéo longue. Le revenu est une estimation : vues par mois ×
        RPM de la niche et de la langue (docs/61), à lire comme un ordre de grandeur.
      </p>
      <div className="bg-muted inline-flex w-fit rounded-lg p-0.5 text-sm">
        {(
          [
            ["all", "Toutes les langues"],
            ["fr", "Français"],
            ["en", "Anglais"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setLang(id)}
            className={`rounded-md px-3 py-1 ${lang === id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {niches.length ? (
        niches.map((n) => <NicheCard key={n.niche} niche={n} busy={pending} run={run} />)
      ) : (
        <Card>
          <CardContent className="text-muted-foreground pt-6 text-sm">Rien encore : « Découvrir maintenant » lance un premier balayage.</CardContent>
        </Card>
      )}
    </div>
  );
}

function NicheCard({ niche, busy, run }: { niche: DiscoveredNiche; busy: boolean; run: (fn: () => Promise<{ ok: boolean; message: string }>) => void }) {
  const examples = niche.channels.flatMap((c) => c.top.slice(0, 2).map((v) => v.title)).slice(0, 6);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          {niche.niche}
          <ToneBadge tone="success">≈ {money(niche.revenue)} / mois à elles toutes</ToneBadge>
          {niche.category ? <ToneBadge tone="neutral">{CATEGORY_LABELS[niche.category] ?? niche.category}</ToneBadge> : null}
          {niche.effort != null ? <ToneBadge tone={niche.effort <= 2 ? "success" : niche.effort <= 3 ? "warning" : "danger"}>effort {niche.effort}/5</ToneBadge> : null}
        </CardTitle>
        <CardDescription>
          {niche.channels.length} chaîne{niche.channels.length > 1 ? "s" : ""} · langues : {niche.langs.join(", ")}
          {niche.youngest != null ? ` · la plus jeune a ${niche.youngest.toFixed(1)} mois` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {niche.channels.slice(0, 6).map((c) => (
          <div key={c.id} className="flex flex-col gap-1 rounded-lg border p-2 text-sm md:flex-row md:items-center md:gap-3">
            <a href={`https://www.youtube.com/channel/${c.id}`} target="_blank" rel="noreferrer" className="flex items-center gap-1 font-medium hover:underline md:w-56 md:shrink-0">
              {c.title} <ExternalLink className="size-3" />
            </a>
            <span className="text-muted-foreground text-xs md:w-72 md:shrink-0">
              {c.lang ?? "?"} · {c.months != null ? `${c.months.toFixed(1)} mois` : "?"} · {c.subs != null ? formatCompact(c.subs) : "?"} abonnés ·{" "}
              {formatCompact(c.monthlyViews ?? 0)} vues/mois · RPM {c.rpm ?? "?"} $ · <strong>≈ {money(c.revenue)}/mois</strong>
            </span>
            <span className="line-clamp-2 flex-1 text-xs">
              {c.top[0] ? `« ${c.top[0].title} » (${formatCompact(c.top[0].views)} vues, ${Math.round(c.top[0].duration_s / 60)} min)` : ""}
              {c.why ? <span className="text-muted-foreground"> — {c.why}</span> : null}
            </span>
            <div className="flex shrink-0 items-center gap-1">
              {c.aiMade ? <ToneBadge tone="info">IA</ToneBadge> : null}
              {c.faceless === false ? <ToneBadge tone="warning">visage</ToneBadge> : null}
              <Button size="icon-sm" variant="ghost" title="Écarter cette chaîne" onClick={() => run(() => dismissChannel(c.id))} disabled={busy}>
                <X />
              </Button>
            </div>
          </div>
        ))}
        <div>
          <Button size="sm" variant="outline" onClick={() => run(() => longIdeasFromNiche(niche.niche, examples))} disabled={busy}>
            <MonitorPlay /> Sujets de vidéos longues dans cette niche
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
