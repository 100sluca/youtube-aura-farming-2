"use client";

import * as React from "react";
import { Compass, Gem, Lightbulb, Loader2, MessageCircleQuestion, Plus, Radar, RefreshCw, Search, Send, Sparkles, Target, TriangleAlert, X, Zap } from "lucide-react";

import {
  adaptVideo,
  addNiche,
  askStrategist,
  exploreTopic,
  reproduceVideo,
  requestBrief,
  saveResearchSettings,
  scanNow,
  setNicheStatus,
} from "@/app/research/actions";
import { DiscoverShortsPanel } from "@/components/research/research-discover-shorts";
import { DiscoveryPanel } from "@/components/research/research-discovery";
import { NichesPanel, PhaseBadge } from "@/components/research/research-niches";
import { AnalysisDialog, NoticeLine, VideoCard, VideosPanel } from "@/components/research/research-videos";
import { ToneBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { formatCompact, formatDateTime, formatRelative } from "@/lib/format";
import type { DiscoveryData } from "@/lib/research-discovery";
import { RECIPE_LABELS, SEARCH_CAP, VERDICT_TONES, type ResearchOverview, type ResearchVideo } from "@/lib/research-types";

type Notice = { ok: boolean; message: string } | null;

const ACTION_LABELS: Record<string, string> = {
  scan: "Relevé des niches",
  explore: "Exploration",
  watch: "Gemini regarde",
  adapt: "Version fidèle",
  reproduce: "Reproduction",
  brief: "Recommandations",
  discover: "Découverte (vidéos longues)",
  discover_shorts: "Découverte (Shorts)",
};

/** Page Recherche (docs/60, docs/64) : que faire, niches, vidéos à reproduire, découverte, test d'un sujet et réglages. */
export function ResearchView({ data, discovery }: { data: ResearchOverview; discovery: DiscoveryData }) {
  const [tab, setTab] = React.useState(data.report ? "reco" : data.niches.some((n) => n.summary) ? "niches" : "explore");
  const [opened, setOpened] = React.useState<ResearchVideo | null>(null);
  const [notice, setNotice] = React.useState<Notice>(null);
  const [pending, start] = React.useTransition();
  const run = (fn: () => Promise<{ ok: boolean; message: string }>) => start(async () => setNotice(await fn()));

  const byId = React.useMemo(() => {
    const m = new Map<string, ResearchVideo>();
    for (const v of [...data.nicheVideos, ...data.reproduced, ...data.videos]) m.set(v.id, v);
    return m;
  }, [data]);
  // la vidéo ouverte suit les rechargements de la page (analyse arrivée entre-temps)
  const openedLive = opened ? (byId.get(opened.id) ?? opened) : null;
  const scanning = data.jobs.find((j) => j.action === "scan" || j.action === "explore");
  const briefing = data.jobs.find((j) => j.action === "brief");
  const tracked = data.niches.filter((n) => n.status === "active").length;
  const openedJob = openedLive ? data.jobs.find((j) => j.video_id === openedLive.id) : undefined;
  const discovered = data.niches.filter((n) => n.origin === "discover" && n.status === "proposed" && n.summary).length;
  const searchesLeft = Math.max(0, SEARCH_CAP - data.searchesToday);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => run(scanNow)} disabled={pending || Boolean(scanning)}>
          {scanning ? <Loader2 className="animate-spin" /> : <Radar />}
          {scanning ? "Relevé en cours…" : "Relever maintenant"}
        </Button>
        <span className="text-muted-foreground text-sm">
          {tracked} niches suivies · {data.searchesToday} / {SEARCH_CAP} recherches YouTube aujourd’hui ({searchesLeft} restantes) · relevé
          automatique chaque jour à 10 h
        </span>
        {scanning ? (
          <span className="text-xs text-violet-600 dark:text-violet-400">
            {scanning.status === "queued"
              ? "En file : le worker le prend dès qu’il est libre"
              : `${scanning.label ?? "En cours"}${scanning.progress != null ? ` (${scanning.progress} %)` : ""}`}
          </span>
        ) : data.lastJob ? (
          <span className="text-muted-foreground text-xs" suppressHydrationWarning>
            Dernière tâche : {ACTION_LABELS[data.lastJob.action] ?? data.lastJob.action}
            {data.lastJob.finished_at ? `, ${formatRelative(data.lastJob.finished_at)}` : ""}
            {data.lastJob.status === "failed" ? ` (ratée : ${data.lastJob.error?.slice(0, 140)})` : ""}
          </span>
        ) : null}
        <NoticeLine result={notice} />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="reco">
            <Lightbulb /> Que faire
          </TabsTrigger>
          <TabsTrigger value="niches">
            <Compass /> Niches
          </TabsTrigger>
          <TabsTrigger value="videos">
            <Sparkles /> Vidéos à reproduire
            {data.videos.length ? <Badge variant="secondary">{data.videos.length}</Badge> : null}
          </TabsTrigger>
          <TabsTrigger value="discover">
            <Gem /> Découverte
            {discovered + discovery.niches.length ? <Badge variant="secondary">{discovered + discovery.niches.length}</Badge> : null}
          </TabsTrigger>
          <TabsTrigger value="explore">
            <Search /> Tester un sujet · Réglages
          </TabsTrigger>
        </TabsList>

        <TabsContent value="reco" className="mt-2">
          <ReportPanel data={data} byId={byId} briefing={Boolean(briefing)} onOpen={setOpened} onNotice={setNotice} />
        </TabsContent>
        <TabsContent value="niches" className="mt-2">
          <NichesPanel niches={data.niches} videos={byId} jobs={data.jobs} onOpen={setOpened} />
        </TabsContent>
        <TabsContent value="videos" className="mt-2">
          <VideosPanel videos={data.videos} reproduced={data.reproduced} niches={data.niches} jobs={data.jobs} onOpen={setOpened} />
        </TabsContent>
        <TabsContent value="discover" className="mt-2">
          <DiscoverTab data={data} discovery={discovery} byId={byId} onOpen={setOpened} />
        </TabsContent>
        <TabsContent value="explore" className="mt-2">
          <ExplorePanel data={data} />
        </TabsContent>
      </Tabs>

      <AnalysisDialog
        video={openedLive}
        open={Boolean(opened)}
        onOpenChange={(o) => !o && setOpened(null)}
        busy={pending}
        job={openedJob}
        onReproduce={(v, mode) => run(() => reproduceVideo(v.id, mode))}
        onAdapt={(v) => run(() => adaptVideo(v.id))}
      />
    </div>
  );
}

function ReportPanel({
  data,
  byId,
  briefing,
  onOpen,
  onNotice,
}: {
  data: ResearchOverview;
  byId: Map<string, ResearchVideo>;
  briefing: boolean;
  onOpen: (v: ResearchVideo) => void;
  onNotice: (n: Notice) => void;
}) {
  const [pending, start] = React.useTransition();
  const run = (fn: () => Promise<{ ok: boolean; message: string }>) => start(async () => onNotice(await fn()));
  const r = data.report?.report;
  const nicheBySlug = new Map(data.niches.map((n) => [n.slug, n]));
  const button = (
    <Button variant="outline" onClick={() => run(requestBrief)} disabled={pending || briefing}>
      {briefing ? <Loader2 className="animate-spin" /> : <RefreshCw />}
      {briefing ? "Le stratège lit la veille…" : "Nouvelles recommandations"}
    </Button>
  );
  // LA vidéo à faire : celle du stratège, sinon la première de ses vidéos à reproduire, sinon la mieux classée
  const nextId = r?.next_video?.video_id ?? r?.remakes.find((p) => p.video_id && byId.get(p.video_id)?.status !== "reproduced")?.video_id;
  const next = (nextId ? byId.get(nextId) : undefined) ?? data.videos.find((v) => v.status !== "reproduced");
  const nextWhy = r?.next_video?.video_id === next?.id ? r?.next_video : r?.remakes.find((p) => p.video_id === next?.id);
  if (!r) {
    return (
      <div className="flex flex-col gap-4">
        <NextVideo video={next} why={undefined} how={undefined} data={data} onOpen={onOpen} onNotice={onNotice} />
        <AskPanel data={data} byId={byId} onOpen={onOpen} onNotice={onNotice} />
        <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed p-6">
          <p className="text-sm">
            Pas encore de recommandations. Le stratège les écrit chaque lundi après le relevé ; tu peux les demander dès qu’un relevé a eu
            lieu.
          </p>
          {button}
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <NextVideo
        video={next}
        why={nextWhy?.why}
        how={r.next_video?.video_id === next?.id ? r.next_video?.how : (nextWhy as { angle?: string } | undefined)?.angle}
        data={data}
        onOpen={onOpen}
        onNotice={onNotice}
      />
      <AskPanel data={data} byId={byId} onOpen={onOpen} onNotice={onNotice} />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-lg font-semibold">{r.headline}</p>
          <p className="text-muted-foreground text-xs">
            {formatDateTime(data.report!.created_at)}
            {data.report!.model ? ` · ${data.report!.model}` : ""}
          </p>
        </div>
        {button}
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {r.niches.map((p) => {
          const n = nicheBySlug.get(p.niche);
          return (
            <Card key={p.niche} className="gap-3 py-4">
              <CardHeader className="px-4">
                <div className="flex flex-wrap items-center gap-2">
                  <ToneBadge tone={VERDICT_TONES[p.verdict] ?? "neutral"}>{p.verdict}</ToneBadge>
                  <CardTitle className="text-base">{n?.label ?? p.niche}</CardTitle>
                  {n?.summary ? <PhaseBadge phase={n.summary.phase} reason={n.summary.phase_reason} /> : null}
                  {n?.summary ? <span className="text-muted-foreground text-xs">note {n.summary.score_parts.score}/100</span> : null}
                </div>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 px-4 text-sm">
                <p>{p.why}</p>
                {p.how ? (
                  <p className="text-muted-foreground">
                    <b>Comment :</b> {p.how}
                  </p>
                ) : null}
                {p.first_videos?.length ? (
                  <ul className="list-disc pl-5 text-xs">
                    {p.first_videos.map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                ) : null}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {r.remakes.length ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Vidéos à reproduire maintenant</h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {r.remakes.map((p) => {
              const v = p.video_id ? byId.get(p.video_id) : undefined;
              if (!v) return null;
              const job = data.jobs.find((j) => j.video_id === v.id);
              return (
                <div key={p.ref} className="flex flex-col gap-1.5">
                  <VideoCard video={v} compact job={job} onOpen={onOpen} onNotice={onNotice} />
                  <p className="text-xs">{p.why}</p>
                  {p.angle ? <p className="text-muted-foreground text-xs italic">{p.angle}</p> : null}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {r.fast_formats.length ? (
        <div className="flex flex-col gap-2">
          <h3 className="flex items-center gap-1.5 text-sm font-semibold">
            <Zap className="size-4 text-amber-500" /> Formats rapides à fabriquer
          </h3>
          <div className="grid gap-2 md:grid-cols-2">
            {r.fast_formats.map((f, i) => (
              <div key={i} className="rounded-lg border p-3 text-sm">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{f.format}</span>
                  <Badge variant="outline">{RECIPE_LABELS[f.recipe] ?? f.recipe}</Badge>
                </div>
                <p className="text-muted-foreground mt-1">{f.why}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {r.new_niches.length ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Niches à ajouter à la veille</h3>
          <div className="grid gap-2 md:grid-cols-3">
            {r.new_niches.map((nn, i) => {
              const proposed = data.niches.find((n) => n.label === nn.label && n.status === "proposed");
              return (
                <div key={i} className="flex flex-col gap-1.5 rounded-lg border p-3 text-sm">
                  <span className="font-medium">{nn.label}</span>
                  <p className="text-muted-foreground text-xs">{nn.why || nn.description}</p>
                  <p className="text-xs">{nn.queries.map((q) => `« ${q} »`).join(", ")}</p>
                  {proposed ? (
                    <Button size="sm" variant="outline" className="w-fit" disabled={pending} onClick={() => run(() => setNicheStatus(proposed.id, "active"))}>
                      <Plus /> Suivre
                    </Button>
                  ) : (
                    <Button size="sm" variant="ghost" className="w-fit" disabled={pending} onClick={() => run(() => addNiche(nn.label, nn.queries))}>
                      <Plus /> Suivre
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {r.warnings.length ? (
        <div className="text-muted-foreground flex flex-col gap-1 text-xs">
          {r.warnings.map((w, i) => (
            <p key={i} className="flex gap-1.5">
              <TriangleAlert className="size-3.5 shrink-0" /> {w}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** LA vidéo à faire maintenant : en grand, avec pourquoi et un bouton pour la refaire fidèlement. */
function NextVideo({
  video,
  why,
  how,
  data,
  onOpen,
  onNotice,
}: {
  video: ResearchVideo | undefined;
  why: string | undefined;
  how: string | undefined;
  data: ResearchOverview;
  onOpen: (v: ResearchVideo) => void;
  onNotice: (n: Notice) => void;
}) {
  if (!video) return null;
  const niche = data.niches.find((n) => n.id === video.niche_id);
  const job = data.jobs.find((j) => j.video_id === video.id);
  return (
    <Card className="gap-3 border-violet-500/40 py-4">
      <CardHeader className="px-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <Target className="size-4 text-violet-500" /> La vidéo à faire maintenant
        </CardTitle>
        <CardDescription>
          Choisie par le stratège parmi les vidéos à reproduire : forte, récente, faisable, dans une niche qui tient. « Refaire » la réécrit en
          français (même sujet, même déroulé, nos mots) puis l’envoie en fabrication ; le storyboard reste à valider dans Création.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 px-4 sm:grid-cols-[170px_1fr]">
        <VideoCard video={video} compact job={job} onOpen={onOpen} onNotice={onNotice} />
        <div className="flex flex-col gap-2 text-sm">
          <p className="font-medium">{video.title}</p>
          <p className="text-muted-foreground">
            {formatCompact(video.views)} vues
            {video.outlier != null ? `, ${video.outlier >= 10 ? Math.round(video.outlier) : video.outlier.toFixed(1)} fois ce que fait d’habitude sa chaîne` : ""}
            {niche ? ` · niche « ${niche.label} »` : ""}
            {niche?.summary ? ` (note ${niche.summary.score_parts.score}/100)` : ""}
          </p>
          {why ? <p>{why}</p> : null}
          {how ? (
            <p className="text-muted-foreground">
              <b>Comment :</b> {how}
            </p>
          ) : null}
          {video.analysis?.why_it_works?.length ? (
            <ul className="text-muted-foreground list-disc pl-5 text-xs">
              {video.analysis.why_it_works.slice(0, 3).map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

const EXAMPLE_QUESTIONS = [
  "Quelle vidéo je fais en premier cette semaine, et pourquoi ?",
  "Parmi les niches découvertes, laquelle vaut une nouvelle recette ?",
  "Pourquoi « Cabanes et mini-maisons » a la meilleure note ?",
];

/** Questions au stratège (docs/64 §4) : il lit la veille et répond en quelques lignes, vidéos citées à l'appui. */
function AskPanel({
  data,
  byId,
  onOpen,
  onNotice,
}: {
  data: ResearchOverview;
  byId: Map<string, ResearchVideo>;
  onOpen: (v: ResearchVideo) => void;
  onNotice: (n: Notice) => void;
}) {
  const [q, setQ] = React.useState("");
  const [notice, setNotice] = React.useState<Notice>(null);
  const [pending, start] = React.useTransition();
  const nicheBySlug = new Map(data.niches.map((n) => [n.slug, n]));
  const submit = () =>
    start(async () => {
      const res = await askStrategist(q);
      if (res.ok) setQ("");
      setNotice(res);
    });
  return (
    <Card className="gap-3 py-4">
      <CardHeader className="px-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <MessageCircleQuestion className="size-4 text-violet-500" /> Pose ta question au stratège
        </CardTitle>
        <CardDescription>
          Il lit toute la veille (nos niches, les niches découvertes, les vidéos à reproduire, nos temps de fabrication) et répond en quelques
          lignes, chiffres à l’appui.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 px-4">
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Textarea
            rows={2}
            placeholder="Ex. Minecraft, ça vaut le coup pour nous ?"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" size="sm" disabled={pending || q.trim().length < 4}>
              {pending ? <Loader2 className="animate-spin" /> : <Send />} Demander
            </Button>
            {EXAMPLE_QUESTIONS.map((ex) => (
              <button key={ex} type="button" className="text-muted-foreground hover:text-foreground rounded-md border px-2 py-1 text-xs" onClick={() => setQ(ex)}>
                {ex}
              </button>
            ))}
          </div>
          <NoticeLine result={notice} />
        </form>
        {data.asks.map((a) => {
          const vids = a.video_ids.map((id) => byId.get(id)).filter((v): v is ResearchVideo => Boolean(v));
          return (
            <div key={a.id} className="flex flex-col gap-2 rounded-lg border p-3 text-sm">
              <p className="font-medium">{a.question}</p>
              {a.status === "queued" || a.status === "running" ? (
                <p className="flex items-center gap-1.5 text-xs text-violet-600 dark:text-violet-400">
                  <Loader2 className="size-3 animate-spin" /> Le stratège lit la veille…
                </p>
              ) : a.status === "failed" ? (
                <p className="text-destructive text-xs">Pas de réponse : {a.error?.slice(0, 200)}</p>
              ) : (
                <p className="whitespace-pre-line">{a.answer}</p>
              )}
              {a.niches.length ? (
                <div className="flex flex-wrap gap-1">
                  {a.niches.map((slug) => (
                    <Badge key={slug} variant="secondary">
                      {nicheBySlug.get(slug)?.label ?? slug}
                    </Badge>
                  ))}
                </div>
              ) : null}
              {vids.length ? (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
                  {vids.map((v) => (
                    <VideoCard key={v.id} video={v} compact job={data.jobs.find((j) => j.video_id === v.id)} onOpen={onOpen} onNotice={onNotice} />
                  ))}
                </div>
              ) : null}
              <p className="text-muted-foreground text-xs" suppressHydrationWarning>
                {formatRelative(a.at)}
              </p>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

/** Découverte : les niches Shorts hors des nôtres (docs/64 §2), ou les chaînes de vidéos longues qui rapportent (docs/63 §9). */
function DiscoverTab({
  data,
  discovery,
  byId,
  onOpen,
}: {
  data: ResearchOverview;
  discovery: DiscoveryData;
  byId: Map<string, ResearchVideo>;
  onOpen: (v: ResearchVideo) => void;
}) {
  const [part, setPart] = React.useState<"shorts" | "long">("shorts");
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm">
        La Découverte cherche <b>hors de nos niches</b>, pour en ajouter de nouvelles au projet. Deux volets :{" "}
        <b>Shorts</b> (pour nos chaînes de Shorts : quelles niches font des millions de vues et laissent entrer les nouveaux) et{" "}
        <b>Vidéos longues</b> (pour Arzak Parker : quelles chaînes récentes percent et combien elles gagnent).
      </p>
      <div className="bg-muted inline-flex w-fit rounded-lg p-0.5 text-sm">
        {(
          [
            ["shorts", "Shorts : niches hors des nôtres"],
            ["long", "Vidéos longues : chaînes qui rapportent"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setPart(id)}
            className={`rounded-md px-3 py-1 ${part === id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {part === "shorts" ? <DiscoverShortsPanel niches={data.niches} videos={byId} jobs={data.jobs} onOpen={onOpen} /> : <DiscoveryPanel data={discovery} />}
    </div>
  );
}

const WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];

function ExplorePanel({ data }: { data: ResearchOverview }) {
  const [q, setQ] = React.useState("");
  const [lang, setLang] = React.useState("en");
  const [notice, setNotice] = React.useState<Notice>(null);
  const [pending, start] = React.useTransition();
  const [s, setS] = React.useState(data.settings);
  const run = (fn: () => Promise<{ ok: boolean; message: string }>) => start(async () => setNotice(await fn()));
  const proposed = data.niches.filter((n) => n.status === "proposed" && n.origin !== "discover");
  const exploring = data.jobs.filter((j) => j.action === "explore");
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="gap-3">
        <CardHeader>
          <CardTitle className="text-base">Tester une idée de niche précise</CardTitle>
          <CardDescription>
            Tu as une idée en tête (« montres de luxe », « recettes de grand-mère ») ? Tape-la : l’appli mesure ses Shorts les plus vus de la
            semaine et sa courbe sur 6 mois (7 recherches YouTube), puis la note comme nos niches. Elle arrive ci-dessous, à suivre ou non.
            Pour des idées sans rien taper, va dans <b>Découverte</b> : l’appli y balaie seule une soixantaine de grands sujets.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <form
            className="flex flex-wrap gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                const r = await exploreTopic(q, lang);
                if (r.ok) setQ("");
                return r;
              });
            }}
          >
            <Input className="min-w-56 flex-1" placeholder="Ex. tiny house in a forest, ASMR cooking, ancient Egypt facts" value={q} onChange={(e) => setQ(e.target.value)} />
            <Select value={lang} onValueChange={setLang}>
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">anglais</SelectItem>
                <SelectItem value="fr">français</SelectItem>
              </SelectContent>
            </Select>
            <Button type="submit" disabled={pending || q.trim().length < 3}>
              <Search /> Explorer
            </Button>
          </form>
          {exploring.map((j) => (
            <p key={j.id} className="flex items-center gap-1.5 text-xs text-violet-600 dark:text-violet-400">
              <Loader2 className="size-3 animate-spin" /> « {j.q} » : {j.label ?? "en file"}
            </p>
          ))}
          <NoticeLine result={notice} />
          {proposed.length ? (
            <div className="flex flex-col divide-y rounded-lg border">
              {proposed.map((n) => (
                <div key={n.id} className="flex flex-wrap items-center gap-2 p-2.5 text-sm">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{n.label}</p>
                    <p className="text-muted-foreground text-xs">
                      {n.origin === "agent" ? "proposée par le stratège" : "explorée"}
                      {n.summary
                        ? ` · ${formatCompact(n.summary.median_views_month ?? n.summary.median_views_7)} vues médianes · ${n.summary.hits_month ?? n.summary.hits_7 ?? 0} tubes · note ${n.summary.score_parts.score}/100`
                        : " · pas encore relevée"}
                    </p>
                  </div>
                  {n.summary ? <PhaseBadge phase={n.summary.phase} reason={n.summary.phase_reason} /> : null}
                  <Button size="sm" variant="outline" disabled={pending} onClick={() => run(() => setNicheStatus(n.id, "active"))}>
                    <Plus /> Suivre
                  </Button>
                  <Button size="icon-sm" variant="ghost" title="Oublier" disabled={pending} onClick={() => run(() => setNicheStatus(n.id, "archived"))}>
                    <X />
                  </Button>
                </div>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="gap-3">
        <CardHeader>
          <CardTitle className="text-base">Réglages de la veille</CardTitle>
          <CardDescription>
            Google donne 100 recherches YouTube par jour, gratuites. Chaque niche coûte 1 ou 2 recherches par jour, plus 1 par mois de sa
            courbe la première fois (ensuite un mois passé ne change plus).
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          <label className="flex items-center justify-between gap-3">
            Recherches par jour pour la veille (sur 100)
            <Input type="number" min={10} max={95} className="w-24" value={s.daily_searches} onChange={(e) => setS({ ...s, daily_searches: Number(e.target.value) })} />
          </label>
          <label className="flex items-center justify-between gap-3">
            Vidéos que Gemini regarde après chaque relevé
            <Input type="number" min={0} max={15} className="w-24" value={s.auto_watch} onChange={(e) => setS({ ...s, auto_watch: Number(e.target.value) })} />
          </label>
          <label className="flex items-center justify-between gap-3">
            Vues minimum d’une vidéo à classer
            <Input type="number" min={5000} step={5000} className="w-28" value={s.min_views} onChange={(e) => setS({ ...s, min_views: Number(e.target.value) })} />
          </label>
          <label className="flex items-center justify-between gap-3">
            Jour des recommandations
            <Select value={String(s.brief_weekday)} onValueChange={(v) => setS({ ...s, brief_weekday: Number(v) })}>
              <SelectTrigger className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {WEEKDAYS.map((d, i) => (
                  <SelectItem key={d} value={String(i + 1)}>
                    {d}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          <div>
            <Button variant="outline" disabled={pending} onClick={() => run(() => saveResearchSettings(s))}>
              Enregistrer
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
