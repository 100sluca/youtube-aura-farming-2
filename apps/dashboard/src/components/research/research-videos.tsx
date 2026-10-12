"use client";

import * as React from "react";
import { Ban, CircleCheck, CircleX, Eye, ExternalLink, Languages, Loader2, Pin, RotateCcw, Shuffle, Wand2 } from "lucide-react";

import { reproduceVideo, setVideoStatus, watchVideo } from "@/app/research/actions";
import { ToneBadge, type Tone } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatCompact, formatDuration } from "@/lib/format";
import {
  EFFORT_LABELS,
  RECIPE_LABELS,
  mostlyLatin,
  thumbUrl,
  type Adaptation,
  type ReproduceMode,
  type ResearchJob,
  type ResearchNiche,
  type ResearchVideo,
  type VideoAnalysis,
} from "@/lib/research-types";

type Notice = { ok: boolean; message: string } | null;

const EFFORT_TONES: Record<number, Tone> = { 1: "success", 2: "success", 3: "info", 4: "warning", 5: "danger" };

export function NoticeLine({ result }: { result: Notice }) {
  if (!result) return null;
  return (
    <p className={`flex items-center gap-1.5 text-xs ${result.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`} role="status">
      {result.ok ? <CircleCheck className="size-3.5 shrink-0" /> : <CircleX className="size-3.5 shrink-0" />}
      {result.message}
    </p>
  );
}

export function EffortBadge({ effort }: { effort: number | null | undefined }) {
  if (!effort) return null;
  return (
    <ToneBadge tone={EFFORT_TONES[effort] ?? "neutral"} title={EFFORT_LABELS[effort]}>
      effort {effort}/5
    </ToneBadge>
  );
}

function days(n: number): string {
  if (n < 1) return `${Math.max(1, Math.round(n * 24))} h`;
  return `${Math.round(n)} j`;
}

/** Ce que Gemini a vu dans la vidéo, la version fidèle en français, et les deux façons de la refaire. */
export function AnalysisDialog({
  video,
  open,
  onOpenChange,
  onReproduce,
  onAdapt,
  job,
  busy,
}: {
  video: ResearchVideo | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onReproduce: (v: ResearchVideo, mode: ReproduceMode) => void;
  onAdapt: (v: ResearchVideo) => void;
  job?: ResearchJob;
  busy: boolean;
}) {
  const a: VideoAnalysis | null = video?.analysis ?? null;
  const done = video?.status === "reproduced";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="pr-6 leading-snug">{video?.title}</DialogTitle>
          <DialogDescription>
            {video?.channel_title} · {formatCompact(video?.views)} vues · {video ? days(video.age_days) : ""}
            {a?.model ? ` · regardée par ${a.model}` : ""}
          </DialogDescription>
        </DialogHeader>
        {video && a ? (
          <div className="grid gap-5 text-sm md:grid-cols-[180px_1fr]">
            <a href={video.url} target="_blank" rel="noreferrer" className="block">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={thumbUrl(video.external_id)} alt="" className="aspect-[9/16] w-full rounded-md object-cover" loading="lazy" />
            </a>
            <div className="flex flex-col gap-4">
              <p>{a.summary}</p>
              <Section title="L’accroche">
                <p>{a.hook_visual}</p>
                {a.hook_text ? <p className="text-muted-foreground mt-1 italic">« {a.hook_text} »</p> : null}
              </Section>
              {a.structure?.length ? (
                <Section title="Déroulé">
                  <ol className="flex flex-col gap-1">
                    {a.structure.map((b, i) => (
                      <li key={i} className="grid grid-cols-[64px_1fr] gap-2">
                        <span className="text-muted-foreground tabular-nums">{b.t}</span>
                        <span>{b.what}</span>
                      </li>
                    ))}
                  </ol>
                </Section>
              ) : null}
              <Section title="Pourquoi ça marche">
                <ul className="list-disc pl-5">
                  {a.why_it_works.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </Section>
              {a.weak_points?.length ? (
                <Section title="Ce qui est raté">
                  <ul className="text-muted-foreground list-disc pl-5">
                    {a.weak_points.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </Section>
              ) : null}
              <div className="text-muted-foreground grid gap-1 text-xs sm:grid-cols-2">
                {a.pacing ? <p><b>Rythme :</b> {a.pacing}</p> : null}
                {a.audio ? <p><b>Son :</b> {a.audio}</p> : null}
                {a.on_screen_text ? <p><b>Textes :</b> {a.on_screen_text}</p> : null}
                {a.emotion ? <p><b>Émotion :</b> {a.emotion}</p> : null}
                {a.ending ? <p><b>Fin :</b> {a.ending}</p> : null}
              </div>
              <FaithfulSection video={video} job={job} busy={busy} onAdapt={onAdapt} onReproduce={onReproduce} />
              <div className="flex flex-col gap-2 rounded-lg border border-dashed p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Shuffle className="size-4 text-violet-500" />
                  <span className="font-medium">Autre voie, même mécanique, histoire nouvelle : {a.remake.title}</span>
                  <Badge variant="outline">{RECIPE_LABELS[a.recipe] ?? a.recipe}</Badge>
                  {a.series ? <Badge variant="outline">{a.series}</Badge> : null}
                  <EffortBadge effort={a.effort} />
                </div>
                <p>{a.remake.premise}</p>
                {a.remake.hook ? <p className="text-muted-foreground"><b>Ouverture :</b> {a.remake.hook}</p> : null}
                {a.remake.scenario ? <p className="text-muted-foreground whitespace-pre-line"><b>Scénario :</b> {a.remake.scenario}</p> : null}
                {a.remake.keep?.length ? <p className="text-xs"><b>On garde :</b> {a.remake.keep.join(" ; ")}</p> : null}
                {a.remake.change?.length ? <p className="text-xs"><b>On change :</b> {a.remake.change.join(" ; ")}</p> : null}
                <div>
                  <Button size="sm" variant="outline" onClick={() => onReproduce(video, "mecanique")} disabled={busy || done || Boolean(job)}>
                    <Shuffle />
                    {done ? "Déjà en fabrication" : "Faire une histoire nouvelle"}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        ) : video ? (
          <div className="flex flex-col gap-3 text-sm">
            <p className="text-muted-foreground">Gemini n’a pas encore regardé cette vidéo.</p>
            <FaithfulSection video={video} job={job} busy={busy} onAdapt={onAdapt} onReproduce={onReproduce} />
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

/** La version fidèle (docs/64 §3) : même sujet, même déroulé, même accroche, nos mots en français. */
function FaithfulSection({
  video,
  job,
  busy,
  onAdapt,
  onReproduce,
}: {
  video: ResearchVideo;
  job?: ResearchJob;
  busy: boolean;
  onAdapt: (v: ResearchVideo) => void;
  onReproduce: (v: ResearchVideo, mode: ReproduceMode) => void;
}) {
  const ad: Adaptation | null = video.adaptation;
  const done = video.status === "reproduced";
  const working = Boolean(job);
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-violet-500/40 bg-violet-500/5 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Languages className="size-4 text-violet-500" />
        <span className="font-medium">{ad ? `Version fidèle : ${ad.title}` : "Version fidèle en français"}</span>
        {ad ? <Badge variant="outline">{RECIPE_LABELS[ad.recipe] ?? ad.recipe}</Badge> : null}
        {ad?.source_language ? <Badge variant="outline">depuis : {ad.source_language}</Badge> : null}
        {ad ? <Badge variant="outline">{ad.duration_s} s</Badge> : null}
      </div>
      <p className="text-muted-foreground text-xs">
        Même sujet, même déroulé, même accroche et même fin que l’original ; réécrite avec nos mots, fabriquée avec nos images et notre voix.
      </p>
      {ad ? (
        <>
          <p>
            <b>Sujet :</b> {ad.subject}
          </p>
          <p>
            <b>Ouverture :</b> {ad.hook}
          </p>
          {ad.beats?.length ? (
            <ol className="flex flex-col gap-1">
              {ad.beats.map((b, i) => (
                <li key={i} className="grid grid-cols-[64px_1fr] gap-2">
                  <span className="text-muted-foreground tabular-nums">{b.t}</span>
                  <span>
                    {b.image}
                    {b.words ? <span className="text-muted-foreground italic"> — « {b.words} »</span> : null}
                  </span>
                </li>
              ))}
            </ol>
          ) : null}
          {ad.narration ? (
            <p className="text-muted-foreground whitespace-pre-line">
              <b>Voix off :</b> {ad.narration}
            </p>
          ) : null}
          {ad.scenario ? (
            <p className="text-muted-foreground whitespace-pre-line">
              <b>Scénario :</b> {ad.scenario}
            </p>
          ) : null}
          {ad.ending ? (
            <p className="text-muted-foreground">
              <b>Fin :</b> {ad.ending}
            </p>
          ) : null}
          {ad.facts_to_check?.length ? (
            <p className="text-xs text-amber-700 dark:text-amber-400">
              <b>Faits à vérifier :</b> {ad.facts_to_check.join(" ; ")}
            </p>
          ) : null}
        </>
      ) : null}
      {working ? (
        <p className="flex items-center gap-1.5 text-xs text-violet-600 dark:text-violet-400">
          <Loader2 className="size-3 animate-spin" /> {job?.label ?? (job?.action === "adapt" ? "Gemini l’écrit en français…" : "En cours…")}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => onReproduce(video, "fidele")} disabled={busy || done || working}>
          {busy ? <Loader2 className="animate-spin" /> : <Wand2 />}
          {done ? "Déjà en fabrication" : "Refaire fidèlement"}
        </Button>
        {!ad ? (
          <Button size="sm" variant="outline" onClick={() => onAdapt(video)} disabled={busy || working}>
            <Languages /> Écrire la version fidèle d’abord
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="mb-1 text-xs font-semibold tracking-wide uppercase">{title}</h4>
      {children}
    </div>
  );
}

export function VideoCard({
  video,
  niche,
  job,
  onOpen,
  onNotice,
  compact = false,
}: {
  video: ResearchVideo;
  niche?: string | null;
  job?: ResearchJob;
  onOpen: (v: ResearchVideo) => void;
  onNotice: (n: Notice) => void;
  compact?: boolean;
}) {
  const [pending, start] = React.useTransition();
  const run = (fn: () => Promise<{ ok: boolean; message: string }>) => start(async () => onNotice(await fn()));
  const c = video.classification;
  const working = Boolean(job) || pending;
  return (
    <div className="bg-card flex flex-col overflow-hidden rounded-lg border">
      <a href={video.url} target="_blank" rel="noreferrer" className="group relative block">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={thumbUrl(video.external_id)}
          alt=""
          className="aspect-[9/16] w-full object-cover transition-transform group-hover:scale-[1.02]"
          loading="lazy"
        />
        <div className="absolute inset-x-0 bottom-0 flex items-end justify-between bg-gradient-to-t from-black/80 to-transparent p-2 text-white">
          <span className="text-lg font-semibold tabular-nums">{formatCompact(video.views)}</span>
          {video.outlier != null ? (
            <span
              className="rounded bg-violet-600/90 px-1.5 py-0.5 text-xs font-semibold tabular-nums"
              title={video.outlier_base === "chaîne" ? "vues ÷ médiane des Shorts de la chaîne" : "vues ÷ abonnés de la chaîne"}
            >
              × {video.outlier >= 10 ? Math.round(video.outlier) : video.outlier.toFixed(1)}
            </span>
          ) : null}
        </div>
        {video.status === "shortlisted" ? (
          <span className="absolute top-2 left-2 rounded bg-amber-500 px-1.5 py-0.5 text-[10px] font-semibold text-black">retenue</span>
        ) : null}
        {video.status === "reproduced" ? (
          <span className="absolute top-2 left-2 rounded bg-emerald-500 px-1.5 py-0.5 text-[10px] font-semibold text-black">en fabrication</span>
        ) : null}
      </a>
      <div className="flex flex-1 flex-col gap-2 p-2.5">
        <p className="line-clamp-2 text-sm leading-snug font-medium" title={video.title}>
          {video.title}
        </p>
        <p className="text-muted-foreground text-xs">
          {video.channel_title} · {video.channel_subs != null ? `${formatCompact(video.channel_subs)} abonnés` : "abonnés masqués"}
        </p>
        <p className="text-muted-foreground text-xs tabular-nums">
          {formatCompact(video.views_per_day)}/jour · {days(video.age_days)} · {formatDuration(video.duration_s)}
        </p>
        {!compact ? (
          <>
            <div className="flex flex-wrap gap-1">
              {niche ? <Badge variant="secondary" className="max-w-full truncate">{niche}</Badge> : null}
              {c?.format ? <Badge variant="outline">{c.format}</Badge> : null}
              <EffortBadge effort={c?.effort} />
            </div>
            {c?.angle ? <p className="text-muted-foreground line-clamp-3 text-xs">{c.angle}</p> : null}
          </>
        ) : null}
        {job ? (
          <p className="flex items-center gap-1.5 text-xs text-violet-600 dark:text-violet-400">
            <Loader2 className="size-3 animate-spin" />
            {job.label ??
              (job.action === "watch" ? "Gemini regarde…" : job.action === "adapt" ? "Gemini l’écrit en français…" : "En route vers la fabrication…")}
          </p>
        ) : null}
        <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
          {video.analysis ? (
            <Button size="sm" variant="secondary" onClick={() => onOpen(video)}>
              <Eye /> Pourquoi ça marche
            </Button>
          ) : (
            <Button size="sm" variant="secondary" disabled={working} onClick={() => run(() => watchVideo(video.id))}>
              <Eye /> Analyser
            </Button>
          )}
          {video.status !== "reproduced" ? (
            <Button
              size="sm"
              disabled={working}
              onClick={() => run(() => reproduceVideo(video.id, "fidele"))}
              title="Version fidèle : même sujet, même déroulé, même accroche, réécrite en français avec nos mots, puis en fabrication (storyboard à valider dans Création)"
            >
              {working ? <Loader2 className="animate-spin" /> : <Wand2 />} Refaire
            </Button>
          ) : null}
          {!compact && video.status === "new" ? (
            <Button size="icon-sm" variant="ghost" title="Garder en tête de liste" onClick={() => run(() => setVideoStatus(video.id, "shortlisted"))}>
              <Pin />
            </Button>
          ) : null}
          {!compact && video.status === "shortlisted" ? (
            <Button size="icon-sm" variant="ghost" title="Retirer de la tête de liste" onClick={() => run(() => setVideoStatus(video.id, "new"))}>
              <RotateCcw />
            </Button>
          ) : null}
          {!compact && video.status !== "reproduced" ? (
            <Button size="icon-sm" variant="ghost" title="Écarter" onClick={() => run(() => setVideoStatus(video.id, "dismissed"))}>
              <Ban />
            </Button>
          ) : null}
          <Button size="icon-sm" variant="ghost" asChild title="Ouvrir sur YouTube">
            <a href={video.url} target="_blank" rel="noreferrer">
              <ExternalLink />
            </a>
          </Button>
        </div>
      </div>
    </div>
  );
}

/** Onglet « Vidéos à reproduire » : les Shorts qui dépassent le plus leur chaîne, faciles à refaire, les plus frais. */
export function VideosPanel({
  videos,
  reproduced,
  niches,
  jobs,
  onOpen,
}: {
  videos: ResearchVideo[];
  reproduced: ResearchVideo[];
  niches: ResearchNiche[];
  jobs: ResearchJob[];
  onOpen: (v: ResearchVideo) => void;
}) {
  const [niche, setNiche] = React.useState("all");
  const [effort, setEffort] = React.useState("3");
  const [lang, setLang] = React.useState("latin");
  const [notice, setNotice] = React.useState<Notice>(null);
  const labels = React.useMemo(() => new Map(niches.map((n) => [n.id, n.label])), [niches]);
  const jobOf = React.useMemo(() => new Map(jobs.filter((j) => j.video_id).map((j) => [j.video_id as string, j])), [jobs]);
  const shown = videos.filter(
    (v) =>
      (niche === "all" || v.niche_id === niche) &&
      (v.classification?.effort ?? 3) <= Number(effort) &&
      (lang === "all" || mostlyLatin(v.title)),
  );
  const origin = React.useMemo(() => new Map(niches.map((n) => [n.id, n.origin])), [niches]);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={niche} onValueChange={setNiche}>
          <SelectTrigger className="w-72">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Toutes les niches</SelectItem>
            {niches
              .filter((n) => videos.some((v) => v.niche_id === n.id))
              .sort((a, b) => Number(a.origin === "discover") - Number(b.origin === "discover"))
              .map((n) => (
                <SelectItem key={n.id} value={n.id}>
                  {n.label}
                  {n.origin === "discover" ? " (découverte)" : ""}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
        <Select value={effort} onValueChange={setEffort}>
          <SelectTrigger className="w-64">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="2">Effort 1-2 : nos recettes</SelectItem>
            <SelectItem value="3">Effort 1-3 : faisable</SelectItem>
            <SelectItem value="4">Effort 1-4 : tout</SelectItem>
          </SelectContent>
        </Select>
        <Select value={lang} onValueChange={setLang}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="latin">Anglais, français et proches</SelectItem>
            <SelectItem value="all">Toutes les langues</SelectItem>
          </SelectContent>
        </Select>
        <span className="text-muted-foreground text-xs">
          {shown.length} vidéos · classées par surperformance, vitesse, fraîcheur et facilité
        </span>
        <NoticeLine result={notice} />
      </div>
      {shown.length ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
          {shown.map((v) => (
            <VideoCard
              key={v.id}
              video={v}
              niche={v.niche_id ? `${labels.get(v.niche_id) ?? ""}${origin.get(v.niche_id) === "discover" ? " · découverte" : ""}` : null}
              job={jobOf.get(v.id)}
              onOpen={onOpen}
              onNotice={setNotice}
            />
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-sm">
          Rien pour l’instant : lance un relevé, les vidéos arrivent classées au bout de quelques minutes.
        </p>
      )}
      {reproduced.length ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Déjà reproduites</h3>
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
            {reproduced.map((v) => (
              <VideoCard key={v.id} video={v} compact onOpen={onOpen} onNotice={setNotice} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
