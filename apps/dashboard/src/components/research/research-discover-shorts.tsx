"use client";

import * as React from "react";
import { Loader2, Plus, Radar, X } from "lucide-react";

import { discoverShortsNow, setNicheStatus } from "@/app/research/actions";
import { ScoreBar, ScoreParts } from "@/components/research/research-niches";
import { EffortBadge, NoticeLine, VideoCard } from "@/components/research/research-videos";
import { Button } from "@/components/ui/button";
import { formatCompact, formatPercent, formatRelative } from "@/lib/format";
import type { ResearchJob, ResearchNiche, ResearchVideo } from "@/lib/research-types";

type Notice = { ok: boolean; message: string } | null;

/** Ce que l'effort moyen d'une niche veut dire pour nous. */
function reach(effort: number | null | undefined): string {
  if (effort == null) return "faisabilité pas encore jugée";
  if (effort <= 1.5) return "nos recettes la font déjà";
  if (effort <= 2.5) return "faisable avec un réglage";
  if (effort <= 3.5) return "il faut une nouvelle recette";
  if (effort <= 4.5) return "difficile pour l’IA aujourd’hui";
  return "hors de portée : tournage, visage ou jeu vidéo";
}

/** Recherche → Découverte → Shorts (docs/64 §2) : les niches Shorts hors des nôtres, mesurées comme les nôtres. */
export function DiscoverShortsPanel({
  niches,
  videos,
  jobs,
  onOpen,
}: {
  niches: ResearchNiche[];
  videos: Map<string, ResearchVideo>;
  jobs: ResearchJob[];
  onOpen: (v: ResearchVideo) => void;
}) {
  const [notice, setNotice] = React.useState<Notice>(null);
  const [pending, start] = React.useTransition();
  const [only, setOnly] = React.useState<"all" | "doable">("all");
  const run = (fn: () => Promise<{ ok: boolean; message: string }>) => start(async () => setNotice(await fn()));
  const running = jobs.find((j) => j.action === "discover_shorts");
  const jobOf = new Map(jobs.filter((j) => j.video_id).map((j) => [j.video_id as string, j]));
  const found = niches.filter((n) => n.origin === "discover" && n.status === "proposed");
  const measured = found
    .filter((n) => n.summary)
    .filter((n) => only === "all" || (n.summary?.effort ?? 3) <= 3.5)
    .sort((a, b) => (b.summary?.score_parts.score ?? 0) - (a.summary?.score_parts.score ?? 0));
  const followed = niches.filter((n) => n.origin === "discover" && (n.status === "active" || n.status === "paused")).length;
  const last = found.map((n) => n.last_scan_at ?? n.summary?.updated_at).filter(Boolean).sort().at(-1);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => run(() => discoverShortsNow(40))} disabled={pending || Boolean(running)}>
          {running ? <Loader2 className="animate-spin" /> : <Radar />}
          {running ? "Découverte en cours…" : "Découvrir maintenant"}
        </Button>
        <span className="text-muted-foreground text-sm" suppressHydrationWarning>
          {found.filter((n) => n.summary).length} niches mesurées
          {followed ? ` · ${followed} déjà suivies` : ""}
          {last ? ` · dernière mesure ${formatRelative(last)}` : ""} · chaque jour à 9 h 45, une recherche par sujet et par mois
        </span>
        {running ? (
          <span className="text-xs text-violet-600 dark:text-violet-400">
            {running.status === "queued" ? "En file" : `${running.label ?? "En cours"}${running.progress != null ? ` (${running.progress} %)` : ""}`}
          </span>
        ) : null}
        <NoticeLine result={notice} />
      </div>
      <p className="text-muted-foreground text-sm">
        L’appli balaie de grands sujets de YouTube qui ne sont pas dans nos niches (Minecraft, jeux vidéo, montres, voitures, cuisine, sport,
        animaux, bricolage, argent…) et mesure chacun exactement comme nos niches : les 50 Shorts les plus vus du dernier mois jugé, leurs
        vues médianes, leurs tubes, la porte ouverte, et l’effort pour les refaire chez nous. <b>Suivre</b> fait entrer la niche dans la veille
        de chaque jour (sa courbe sur 12 mois se remplit en quelques jours) ; ses vidéos se refont depuis les miniatures.
      </p>
      <div className="bg-muted inline-flex w-fit rounded-lg p-0.5 text-sm">
        {(
          [
            ["all", "Toutes"],
            ["doable", "Faisables chez nous (effort 1 à 3)"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setOnly(id)}
            className={`rounded-md px-3 py-1 ${only === id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {measured.length ? (
        <div className="grid gap-3 xl:grid-cols-2">
          {measured.map((n) => {
            const s = n.summary!;
            const tops = n.top.map((id) => videos.get(id)).filter((v): v is ResearchVideo => Boolean(v)).slice(0, 4);
            return (
              <div key={n.id} className="flex flex-col gap-3 rounded-lg border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{n.label}</span>
                  <ScoreBar score={s.score_parts.score} />
                  <EffortBadge effort={s.effort != null ? Math.round(s.effort) : null} />
                  <span className="text-muted-foreground text-xs">{reach(s.effort)}</span>
                </div>
                <p className="text-sm">
                  <b>{formatCompact(s.median_views_month)}</b> vues médianes · <b>{s.hits_month ?? 0}</b> tubes sur {s.sample_month ?? 50} ·
                  porte ouverte <b>{s.open_share_month != null ? formatPercent(s.open_share_month * 100) : "—"}</b>
                  {s.formats.length ? <span className="text-muted-foreground"> · {s.formats.join(", ")}</span> : null}
                </p>
                <ScoreParts parts={s.score_parts} />
                {tops.length ? (
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    {tops.map((v) => (
                      <VideoCard key={v.id} video={v} compact job={jobOf.get(v.id)} onOpen={onOpen} onNotice={setNotice} />
                    ))}
                  </div>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" disabled={pending} onClick={() => run(() => setNicheStatus(n.id, "active"))}>
                    <Plus /> Suivre chaque jour
                  </Button>
                  <Button size="sm" variant="ghost" disabled={pending} onClick={() => run(() => setNicheStatus(n.id, "archived"))}>
                    <X /> Écarter
                  </Button>
                  <span className="text-muted-foreground self-center text-xs">recherche « {n.queries[0]?.q} »</span>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-sm">
          {found.length || running
            ? "Les niches arrivent au fil des mesures."
            : "Rien encore : « Découvrir maintenant » balaie une quarantaine de sujets d’un coup (le reste les jours suivants)."}
        </p>
      )}
    </div>
  );
}
