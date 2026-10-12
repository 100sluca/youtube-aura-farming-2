"use client";

import * as React from "react";
import { ChevronDown, ChevronRight, CircleHelp, Pause, Play, Plus, Trash2 } from "lucide-react";

import { addNiche, setNicheStatus } from "@/app/research/actions";
import { EffortBadge, NoticeLine, VideoCard } from "@/components/research/research-videos";
import { ToneBadge, type Tone } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatCompact, formatPercent, formatRelative } from "@/lib/format";
import {
  PHASE_HELP,
  RECIPE_LABELS,
  type CurvePoint,
  type NichePhase,
  type NicheSummary,
  type ResearchJob,
  type ResearchNiche,
  type ResearchVideo,
} from "@/lib/research-types";

type Notice = { ok: boolean; message: string } | null;

export const PHASE_TONES: Record<NichePhase, Tone> = {
  émergente: "running",
  "en hausse": "success",
  installée: "info",
  "en baisse": "warning",
  "à vide": "danger",
  inconnue: "neutral",
};

const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

function monthLabel(key: string | null | undefined): string {
  if (!key) return "—";
  const [y, m] = key.split("-");
  return `${MONTHS[Number(m) - 1]} ${y.slice(2)}`;
}

export function PhaseBadge({ phase, reason }: { phase: NichePhase | undefined; reason?: string }) {
  const p = phase ?? "inconnue";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <ToneBadge tone={PHASE_TONES[p]}>{p}</ToneBadge>
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">
        <p>{reason || PHASE_HELP[p]}</p>
        <p className="mt-1 opacity-70">{PHASE_HELP[p]}</p>
      </TooltipContent>
    </Tooltip>
  );
}

/** Barres des vues médianes des meilleurs Shorts de chaque mois (la courbe de vie de la niche). */
function Curve({ points, height = 28, labels = false }: { points: CurvePoint[]; height?: number; labels?: boolean }) {
  if (!points.length) return <span className="text-muted-foreground text-xs">pas encore</span>;
  const max = Math.max(...points.map((p) => p.median_views ?? 0), 1);
  return (
    <div className="flex items-end gap-0.5" style={{ height: labels ? height + 30 : height }}>
      {points.map((p) => {
        const h = Math.max(2, Math.round(((p.median_views ?? 0) / max) * height));
        return (
          <div key={p.month} className="flex flex-col items-center gap-0.5" title={`${monthLabel(p.month)} : ${formatCompact(p.median_views)} vues médianes, ${p.hits} tubes (1 M+)`}>
            {labels ? <span className="text-muted-foreground text-[9px] tabular-nums">{p.hits || ""}</span> : null}
            <div className={`${labels ? "w-6" : "w-1.5"} rounded-sm bg-violet-500/80`} style={{ height: h }} />
            {labels ? <span className="text-muted-foreground w-8 truncate text-center text-[9px]">{monthLabel(p.month)}</span> : null}
          </div>
        );
      })}
    </div>
  );
}

/** Comment lire la veille, chiffre par chiffre (demande de Luca, 04/10 ; docs/64 §1). */
export function HowToRead({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div className="bg-muted/30 rounded-lg border text-sm">
      <button type="button" className="flex w-full items-center gap-2 p-3 text-left font-medium" onClick={() => setOpen(!open)}>
        <CircleHelp className="size-4 shrink-0 text-violet-500" />
        Comment lire ces chiffres
        {open ? <ChevronDown className="ml-auto size-4" /> : <ChevronRight className="ml-auto size-4" />}
      </button>
      {open ? (
        <div className="grid gap-x-6 gap-y-3 px-3 pb-3 md:grid-cols-2">
          <Help title="Vues médianes">
            Pour chaque niche, l’appli demande à YouTube les 50 Shorts les plus vus publiés pendant le dernier mois jugé (un mois se juge 3
            semaines après sa fin, quand les vues se sont tassées). La moitié de ces 50 a fait plus que ce chiffre. C’est le niveau du{" "}
            <b>haut du panier</b> : ce qu’une vidéo de la niche peut faire quand elle prend, pas ce que fait une vidéo moyenne ni une chaîne
            qui démarre. Il sert à comparer les niches entre elles.
          </Help>
          <Help title="Tubes">
            Parmi ces 50 Shorts, ceux qui dépassent 1 million de vues. 30 tubes sur 50 : dans cette niche, les meilleures vidéos font souvent
            des millions.
          </Help>
          <Help title="Porte ouverte">
            La part de ces tubes faits par une petite chaîne (moins de 10 000 abonnés) ou une chaîne de moins de 6 mois. Haute (50 % et
            plus) : YouTube pousse encore les nouveaux venus, c’est là qu’on a notre chance. Basse : quelques grosses chaînes tiennent la
            niche.
          </Help>
          <Help title="Phase">
            Les deux derniers mois jugés comparés aux trois d’avant, <b>par rapport à l’ensemble des niches</b> (en juillet 2026 presque
            toutes ont bondi d’un coup). En hausse : elle monte plus vite que les autres ; installée : elle suit le marché ; en baisse : elle
            monte moins ou retombe ; émergente : ses premiers tubes ont moins de 4 mois.
          </Help>
          <Help title="Note sur 100">
            35 points de <b>demande</b> (vues médianes : 10 000 → 0, 10 millions → 35) + 25 d’<b>élan</b> (la phase) + 20 de{" "}
            <b>porte ouverte</b> + 20 de <b>faisabilité</b> (l’effort moyen de ses vidéos pour nos recettes). Une note haute : beaucoup de
            vues possibles, une niche qui monte, de la place pour les nouveaux, et on sait la faire. Le détail s’ouvre d’un clic sur la
            niche.
          </Help>
          <Help title="Effort">
            1 : une de nos recettes le fait telle quelle ; 2 : avec un réglage ; 3 : une nouvelle recette à écrire (quelques jours de
            travail) ; 4 : difficile pour l’IA aujourd’hui ; 5 : impossible sans tournage, visage ou jeu vidéo.
          </Help>
          <Help title="× N sur une vidéo">
            Ses vues divisées par ce que fait d’habitude sa chaîne (la médiane de ses Shorts). Un × 100 sur une petite chaîne : c’est le
            sujet qui a porté la vidéo, pas l’audience de la chaîne. C’est celle-là qu’il faut refaire.
          </Help>
          <Help title="Alors, que faire ?">
            Prendre une niche à note haute et effort 1 ou 2, puis y refaire fidèlement les vidéos au plus fort × (onglet Vidéos à
            reproduire, bouton <b>Refaire</b> : même sujet, même déroulé, nos mots en français). Un doute : pose la question au stratège,
            onglet <b>Que faire</b>.
          </Help>
        </div>
      ) : null}
    </div>
  );
}

function Help({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="font-semibold">{title}</p>
      <p className="text-muted-foreground">{children}</p>
    </div>
  );
}

/** Les quatre parts de la note, en points gagnés sur le maximum de chacune. */
export function ScoreParts({ parts }: { parts: NicheSummary["score_parts"] }) {
  const rows: [string, number, number, string][] = [
    ["Demande", parts.demand, 35, "vues médianes du mois : 10 000 → 0, 10 millions → plein"],
    ["Élan", parts.momentum, 25, "la phase, comparée à l’ensemble des niches"],
    ["Porte ouverte", parts.open, 20, "part des tubes faits par de petites ou nouvelles chaînes"],
    ["Faisabilité", parts.feasibility, 20, "effort moyen de ses vidéos pour nos recettes"],
  ];
  return (
    <div className="flex flex-col gap-1">
      {rows.map(([label, v, max, help]) => (
        <div key={label} className="grid grid-cols-[96px_1fr_52px] items-center gap-2 text-xs" title={help}>
          <span className="text-muted-foreground">{label}</span>
          <div className="bg-muted h-1.5 overflow-hidden rounded-full">
            <div className="h-full rounded-full bg-violet-500" style={{ width: `${Math.round(Math.max(0, Math.min(1, v)) * 100)}%` }} />
          </div>
          <span className="text-right tabular-nums">
            {Math.round(v * max)} / {max}
          </span>
        </div>
      ))}
    </div>
  );
}

export function ScoreBar({ score }: { score: number | undefined }) {
  if (score == null) return <span className="text-muted-foreground">—</span>;
  return (
    <div className="flex items-center gap-2">
      <span className="w-7 text-right font-semibold tabular-nums">{score}</span>
      <div className="bg-muted h-1.5 w-16 overflow-hidden rounded-full">
        <div className="h-full rounded-full bg-violet-500" style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
      </div>
    </div>
  );
}

function age(n: ResearchNiche): string {
  const a = n.summary?.age_months;
  if (a == null) return "—";
  const first = n.summary?.curve?.[0];
  if (first && first.hits > 0 && a >= (n.summary?.curve.length ?? 0)) return "1 an et +";
  return `${a} mois`;
}

function NicheDetail({
  niche,
  videos,
  jobs,
  onOpen,
  onNotice,
}: {
  niche: ResearchNiche;
  videos: Map<string, ResearchVideo>;
  jobs: ResearchJob[];
  onOpen: (v: ResearchVideo) => void;
  onNotice: (n: Notice) => void;
}) {
  const s = niche.summary;
  const parts = s?.score_parts;
  const tops = niche.top.map((id) => videos.get(id)).filter((v): v is ResearchVideo => Boolean(v));
  const jobOf = new Map(jobs.filter((j) => j.video_id).map((j) => [j.video_id as string, j]));
  return (
    <div className="flex flex-col gap-4 p-3">
      {niche.description ? <p className="text-muted-foreground text-sm">{niche.description}</p> : null}
      <div className="grid gap-4 lg:grid-cols-[auto_1fr]">
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold uppercase">Courbe sur 12 mois</span>
            <span className="text-muted-foreground text-xs">vues médianes des meilleurs Shorts publiés chaque mois · tubes à 1 M+ au-dessus</span>
            <Curve points={s?.curve ?? []} height={70} labels />
          </div>
          {parts ? (
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold uppercase">Note : {parts.score} / 100</span>
              <ScoreParts parts={parts} />
            </div>
          ) : null}
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
          <Fact label="Phase" value={s ? `${s.phase} : ${s.phase_reason}` : "—"} wide />
          <Fact label="Pic" value={monthLabel(s?.peak_month)} />
          <Fact label="Âge" value={age(niche)} />
          <Fact label="Ces 7 jours" value={s?.median_views_7 != null ? `${formatCompact(s.median_views_7)} vues médianes, ${s.hits_7 ?? 0} à 100 k+` : "—"} />
          <Fact label="Porte ouverte" value={s?.open_share_month != null ? `${formatPercent(s.open_share_month * 100)} des tubes par de petites ou nouvelles chaînes` : "—"} wide />
          <Fact label="Concentration" value={s?.concentration_month != null ? `${formatPercent(s.concentration_month * 100)} des tubes chez 3 chaînes` : "—"} />
          <Fact
            label="Vues médianes"
            value={
              s?.median_views_month != null
                ? `${formatCompact(s.median_views_month)} : la moitié des ${s.sample_month ?? 50} Shorts les plus vus publiés en ${monthLabel(s.last_month)} a fait plus`
                : "—"
            }
            wide
          />
          <Fact label="Recherches" value={niche.queries.map((q) => `« ${q.q} »`).join(", ") || "—"} wide />
          <Fact label="Dernier relevé" value={niche.last_scan_at ? formatRelative(niche.last_scan_at) : "jamais"} />
        </div>
      </div>
      {tops.length ? (
        <div className="flex flex-col gap-2">
          <span className="text-xs font-semibold uppercase">Ses Shorts les plus vus ce mois-ci</span>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
            {tops.map((v) => (
              <VideoCard key={v.id} video={v} compact job={jobOf.get(v.id)} onOpen={onOpen} onNotice={onNotice} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Fact({ label, value, wide = false }: { label: string; value: string; wide?: boolean }) {
  return (
    <p className={wide ? "sm:col-span-2" : ""}>
      <span className="text-muted-foreground">{label} : </span>
      {value}
    </p>
  );
}

/** Onglet « Niches » : chaque niche suivie, sa phase, sa note et sa courbe ; un clic ouvre le détail. */
export function NichesPanel({
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
  const [open, setOpen] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<Notice>(null);
  const [pending, start] = React.useTransition();
  const [form, setForm] = React.useState({ label: "", q1: "", q2: "" });
  const tracked = niches.filter((n) => n.status === "active" || n.status === "paused");
  const run = (fn: () => Promise<{ ok: boolean; message: string }>) => start(async () => setNotice(await fn()));
  return (
    <div className="flex flex-col gap-3">
      <HowToRead />
      <div className="overflow-x-auto rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead>Niche</TableHead>
              <TableHead title="Où en est la niche, comparée à l’ensemble des niches">Phase</TableHead>
              <TableHead title="35 demande + 25 élan + 20 porte ouverte + 20 faisabilité ; le détail s’ouvre d’un clic">Note</TableHead>
              <TableHead className="text-right" title="La moitié des 50 Shorts les plus vus du dernier mois jugé a fait plus : le haut du panier">
                Vues médianes
              </TableHead>
              <TableHead className="text-right" title="Parmi ces 50 Shorts, ceux à 1 million de vues et plus">
                Tubes
              </TableHead>
              <TableHead className="text-right" title="Part des tubes faits par une chaîne de moins de 10 000 abonnés ou de moins de 6 mois">
                Porte ouverte
              </TableHead>
              <TableHead>Âge</TableHead>
              <TableHead>Chez nous</TableHead>
              <TableHead>12 mois</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {tracked.map((n) => {
              const s = n.summary;
              const isOpen = open === n.id;
              return (
                <React.Fragment key={n.id}>
                  <TableRow className={`cursor-pointer ${n.status === "paused" ? "opacity-60" : ""}`} onClick={() => setOpen(isOpen ? null : n.id)}>
                    <TableCell>{isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}</TableCell>
                    <TableCell className="max-w-72">
                      <p className="truncate font-medium" title={n.label}>
                        {n.label}
                      </p>
                      <p className="text-muted-foreground truncate text-xs">{s?.formats.join(" · ") || "pas encore relevée"}</p>
                    </TableCell>
                    <TableCell>{s ? <PhaseBadge phase={s.phase} reason={s.phase_reason} /> : <ToneBadge tone="neutral">à relever</ToneBadge>}</TableCell>
                    <TableCell>
                      <ScoreBar score={s?.score_parts.score} />
                    </TableCell>
                    <TableCell className="text-right tabular-nums" title={s?.last_month ? `meilleurs Shorts publiés en ${monthLabel(s.last_month)}` : ""}>
                      {formatCompact(s?.median_views_month ?? s?.median_views_7)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums" title="Shorts à 1 M de vues et plus, dernier mois jugé">
                      {s?.hits_month ?? "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {s?.open_share_month != null ? formatPercent(s.open_share_month * 100) : "—"}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">{age(n)}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap items-center gap-1">
                        {n.recipe ? <Badge variant="outline">{RECIPE_LABELS[n.recipe] ?? n.recipe}</Badge> : <Badge variant="outline">nouvelle recette</Badge>}
                        <EffortBadge effort={s?.effort != null ? Math.round(s.effort) : null} />
                      </div>
                    </TableCell>
                    <TableCell>
                      <Curve points={s?.curve ?? []} />
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex gap-0.5">
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          disabled={pending}
                          title={n.status === "paused" ? "Reprendre le suivi" : "Mettre en pause (plus de recherche chaque jour)"}
                          onClick={() => run(() => setNicheStatus(n.id, n.status === "paused" ? "active" : "paused"))}
                        >
                          {n.status === "paused" ? <Play /> : <Pause />}
                        </Button>
                        <Button size="icon-sm" variant="ghost" disabled={pending} title="Retirer de la veille" onClick={() => run(() => setNicheStatus(n.id, "archived"))}>
                          <Trash2 />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                  {isOpen ? (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={11} className="bg-muted/30 whitespace-normal">
                        <NicheDetail niche={n} videos={videos} jobs={jobs} onOpen={onOpen} onNotice={setNotice} />
                      </TableCell>
                    </TableRow>
                  ) : null}
                </React.Fragment>
              );
            })}
          </TableBody>
        </Table>
      </div>
      <NoticeLine result={notice} />
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          run(async () => {
            const r = await addNiche(form.label, [form.q1, form.q2]);
            if (r.ok) setForm({ label: "", q1: "", q2: "" });
            return r;
          });
        }}
      >
        <label className="flex flex-col gap-1 text-xs">
          Nouvelle niche
          <Input className="w-64" placeholder="Ex. maisons dans des conteneurs" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          Recherche YouTube (anglais)
          <Input className="w-64" placeholder="container house build" value={form.q1} onChange={(e) => setForm({ ...form, q1: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          Recherche (français, facultatif)
          <Input className="w-64" placeholder="maison conteneur" value={form.q2} onChange={(e) => setForm({ ...form, q2: e.target.value })} />
        </label>
        <Button type="submit" variant="outline" disabled={pending}>
          <Plus /> Suivre
        </Button>
      </form>
    </div>
  );
}
