"use client";

/**
 * Retoucher → Récit (docs/53-reecrire-le-recit.md) : le conteur réécrit ce que dit la voix d'une vidéo faite, sur ses
 * plans tels qu'ils sont (tout le récit, ou l'accroche seule), d'après tes remarques. Tu relis et corriges le texte
 * proposé, puis « Faire la vidéo avec ce texte » en fait une nouvelle vidéo : mêmes clips, voix, montage, contrôle.
 * Elle arrive à valider dans la Bibliothèque ; la vidéo ouverte ici ne change pas.
 */
import * as React from "react";
import Link from "next/link";
import { CircleCheck, CircleX, Clapperboard, LoaderCircle, PenLine, Play, Sparkles, Square, TriangleAlert, Undo2 } from "lucide-react";

import { makeRewrite, proposeRewrite, stopRewrite } from "@/app/library/rewrite-actions";
import { VideoStatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime } from "@/lib/format";
import { getJson } from "@/lib/get-json";
import {
  REWRITE_PARTS,
  isStory,
  wordCount,
  type HookProposal,
  type RewriteData,
  type RewriteJob,
  type RewriteMode,
  type RewriteShot,
  type RewriteState,
  type StoryProposal,
} from "@/lib/rewrite-types";
import { cn } from "@/lib/utils";

const POLL_MS = 3000;
const HOOK_WORDS_MAX = 14; // worker/storytelling.py
const OPENING_WORDS_MAX = 22; // accroche + promesse (worker/storycraft.py)
const MAKING = new Set(["pending", "rendering", "qa"]);

type Notice = { ok: boolean; message: string };
/** Le texte en cours de relecture : la proposition d'un job, ou l'ouverture actuelle à réécrire soi-même. */
type Draft = { jobId: string | null; mode: RewriteMode; proposal: StoryProposal | HookProposal; shots: RewriteShot[]; issues: string[]; note: string };

const fromJob = (j: RewriteJob): Draft | null =>
  j.proposal ? { jobId: j.id, mode: j.mode, proposal: structuredClone(j.proposal), shots: j.shots, issues: j.issues, note: j.note } : null;

const busyJob = (j: RewriteJob | null) => Boolean(j && (j.status === "queued" || j.status === "running"));

/** État de la réécriture, par la route GET : en action serveur, cette lecture toutes les 3 s bloquait les boutons (docs/56). */
const fetchRewriteState = (videoId: string) => getJson<RewriteState | null>(`/api/retouch/${videoId}/rewrite`);

export function StoryPanel({ data, onSeek }: { data: RewriteData; onSeek: (sceneIndex: number) => void }) {
  const [state, setState] = React.useState<RewriteState>(data.state);
  const [mode, setMode] = React.useState<RewriteMode>("story");
  const [note, setNote] = React.useState("");
  const [page, setPage] = React.useState("");
  const [draft, setDraft] = React.useState<Draft | null>(() => (data.state.proposal ? fromJob(data.state.proposal) : null));
  const [notice, setNotice] = React.useState<Notice | null>(null);
  const [pending, startTransition] = React.useTransition();

  const current = state.current;
  const busy = busyJob(current);
  const making = state.versions.some((v) => MAKING.has(v.status));
  const lang = data.lang;
  const currentHook = data.currentHook;

  // Une proposition qui arrive remplace le texte en relecture
  const seen = React.useRef(data.state.proposal?.id ?? null);
  const receive = React.useCallback((next: RewriteState) => {
    setState(next);
    const id = next.proposal?.id ?? null;
    if (id === seen.current) return;
    seen.current = id;
    if (next.proposal) setDraft(fromJob(next.proposal));
  }, []);

  // Pendant que le conteur écrit, ou que la nouvelle vidéo se fabrique : l'état relu toutes les 3 s
  React.useEffect(() => {
    if (!busy && !making) return;
    let alive = true;
    const timer = setInterval(async () => {
      const next = await fetchRewriteState(data.videoId).catch(() => null);
      if (alive && next) receive(next);
    }, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [busy, making, data.videoId, receive]);

  const refresh = async () => {
    const next = await fetchRewriteState(data.videoId).catch(() => null);
    if (next) receive(next);
  };
  const run = (action: () => Promise<Notice>, after?: () => void) =>
    startTransition(async () => {
      const res = await action();
      setNotice(res);
      if (res.ok) after?.();
      await refresh();
    });

  const ask = () => run(() => proposeRewrite(data.videoId, { mode, note, page }));
  const make = () => {
    if (!draft) return;
    run(
      () => makeRewrite(data.videoId, { mode: draft.mode, proposal: draft.proposal, note: draft.note }),
      () => setDraft(null),
    );
  };

  if (data.blocked) {
    return (
      <p className="flex items-start gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 p-3 text-xs leading-relaxed">
        <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
        {data.blocked}
      </p>
    );
  }

  const made = current?.action === "make" && current.status === "done" ? state.versions.find((v) => v.id === current.videoId) : null;

  return (
    <div className="flex flex-col gap-5">
      <p className="text-muted-foreground text-xs leading-relaxed">
        Le conteur réécrit ce que dit la voix, sur les plans tels qu’ils sont : chaque phrase colle à l’image de son plan et tient dans la durée de son clip.
        Tu relis le texte, tu le corriges si besoin, puis il devient une <strong className="text-foreground font-medium">nouvelle vidéo</strong> (mêmes clips,
        nouvelle voix, nouveau montage), à valider dans la Bibliothèque. Celle-ci ne change pas.
        {data.original ? (
          <>
            {" "}
            Cette vidéo est déjà une autre version de{" "}
            <Link href={`/library?video=${data.original.id}`} className="text-foreground underline underline-offset-2">
              « {data.original.title} »
            </Link>
            .
          </>
        ) : null}
      </p>

      <section className="flex flex-col gap-3 rounded-lg border p-3">
        <div role="radiogroup" aria-label="Que réécrire" className="bg-muted inline-flex w-fit gap-0.5 rounded-lg p-0.5">
          {(
            [
              { value: "story", label: "Tout le récit", title: "Toutes les phrases dites, plan par plan", off: null },
              { value: "hook", label: "L’accroche seulement", title: "La 1re phrase dite et la promesse qui suit ; le reste ne bouge pas", off: data.hookBlocked },
            ] as const
          ).map((o) => (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={mode === o.value}
              title={o.off ?? o.title}
              disabled={Boolean(o.off)}
              onClick={() => setMode(o.value)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                mode === o.value ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {o.label}
            </button>
          ))}
        </div>
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">Tes remarques</span>
          <Textarea
            rows={3}
            value={note}
            maxLength={3000}
            disabled={busy}
            onChange={(e) => setNote(e.target.value)}
            placeholder={
              mode === "hook"
                ? "Facultatif. Ex. : l’accroche ne fait rien ressentir ; joue sur le gâchis, ou sur ce que ce lieu a d’unique."
                : "Facultatif. Ce qui ne va pas et l’angle voulu. Ex. : on ne comprend pas pourquoi ce trésor compte ; raconte-le comme une mission jamais achevée."
            }
            className="text-sm"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">Page Wikipédia à ajouter</span>
          <Input value={page} maxLength={200} disabled={busy} onChange={(e) => setPage(e.target.value)} placeholder="Facultatif. Ex. : Joseph Hackin" className="text-sm" />
          <span className="text-muted-foreground text-[11px] leading-snug">
            Le dossier est la seule source des faits : ajoute la page qui raconte ce qui manque au récit (son titre exact sur Wikipédia).
          </span>
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={ask} disabled={busy || pending}>
            {pending && !draft ? <LoaderCircle className="animate-spin" /> : <Sparkles />}
            {mode === "hook" ? "Proposer une nouvelle accroche" : "Proposer une réécriture"}
          </Button>
          {mode === "hook" && currentHook ? (
            <Button
              variant="ghost"
              size="sm"
              disabled={busy}
              onClick={() => setDraft({ jobId: null, mode: "hook", proposal: structuredClone(currentHook), shots: [], issues: [], note: "" })}
            >
              <PenLine />
              L’écrire moi-même
            </Button>
          ) : null}
          {!draft && state.proposal ? (
            <Button variant="ghost" size="sm" disabled={busy} onClick={() => state.proposal && setDraft(fromJob(state.proposal))}>
              <Undo2 />
              Reprendre le dernier texte proposé
            </Button>
          ) : null}
        </div>
        <p className="text-muted-foreground text-[11px] leading-snug">
          {mode === "hook"
            ? "2 à 5 minutes : le conteur écrit, le correcteur compte les mots, une reprise au besoin."
            : "5 à 15 minutes : le conteur écrit, le relecteur relit, jusqu’à 3 versions dont la meilleure est gardée."}{" "}
          Plus l’attente si le worker finit une autre tâche. Rien n’est fabriqué avant que tu valides le texte ; tu peux quitter la page et revenir.
        </p>
      </section>

      {current ? <JobLine job={current} onStop={() => run(() => stopRewrite(data.videoId))} pending={pending} /> : null}

      {made ? (
        <p className="flex flex-wrap items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-3 text-xs">
          <CircleCheck className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
          Nouvelle vidéo « {made.title} » :
          <VideoStatusBadge status={made.status} />
          {MAKING.has(made.status) ? "voix, montage et contrôle en cours." : "regarde-la dans la Bibliothèque."}
          <Link href={`/library?video=${made.id}`} className="text-foreground ml-auto underline underline-offset-2">
            Ouvrir sa fiche
          </Link>
        </p>
      ) : null}

      {draft ? (
        <DraftEditor
          draft={draft}
          lang={lang}
          current={currentHook}
          disabled={busy || pending}
          pending={pending}
          onChange={setDraft}
          onSeek={onSeek}
          onMake={make}
          onDrop={() => setDraft(null)}
        />
      ) : null}

      {notice ? (
        <p className={cn("flex items-start gap-1.5 text-xs", notice.ok ? "text-emerald-700 dark:text-emerald-400" : "text-destructive")} role="status">
          {notice.ok ? <CircleCheck className="mt-px size-3.5 shrink-0" /> : <CircleX className="mt-px size-3.5 shrink-0" />}
          {notice.message}
        </p>
      ) : null}

      {state.versions.length ? (
        <section className="flex flex-col gap-2">
          <h4 className="text-sm font-semibold">Autres versions de cette vidéo</h4>
          <ul className="flex flex-col gap-1.5">
            {state.versions.map((v) => (
              <li key={v.id} className="flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-xs">
                <VideoStatusBadge status={v.status} />
                <span className="min-w-0 flex-1 truncate font-medium" title={v.title}>
                  {v.title}
                </span>
                <span className="text-muted-foreground tabular-nums">{formatDateTime(v.createdAt)}</span>
                <Link href={`/library?video=${v.id}`} className="underline underline-offset-2">
                  Voir
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function JobLine({ job, onStop, pending }: { job: RewriteJob; onStop: () => void; pending: boolean }) {
  const what = job.action === "make" ? "Nouvelle vidéo" : job.mode === "hook" ? "Nouvelle accroche" : "Réécriture du récit";
  if (job.status === "queued" || job.status === "running") {
    const text =
      job.status === "running"
        ? (job.label ?? `${job.progress} %`)
        : job.runAfter
          ? `reportée (${job.error ?? "modèles d’écriture occupés"}) : repart vers ${formatDateTime(job.runAfter)}`
          : "en file : démarre quand le worker a fini sa tâche en cours";
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-lg border p-3 text-xs" aria-live="polite">
        <LoaderCircle className="size-3.5 shrink-0 animate-spin" />
        <span className="font-medium">{what}</span>
        <span className="text-muted-foreground min-w-0 flex-1">{text}</span>
        {job.action === "propose" ? (
          <Button size="sm" variant="ghost" className="h-7 px-2" disabled={pending} onClick={onStop}>
            <Square className="size-3.5" />
            Arrêter
          </Button>
        ) : null}
      </div>
    );
  }
  if (job.status === "failed") {
    return (
      <p className="text-destructive flex items-start gap-1.5 text-xs">
        <CircleX className="mt-px size-3.5 shrink-0" />
        {what} : {job.error ?? "échec"}
      </p>
    );
  }
  if (job.status === "cancelled" && job.action === "propose") {
    return <p className="text-muted-foreground text-xs">{what} arrêtée le {formatDateTime(job.finishedAt ?? job.createdAt)}.</p>;
  }
  return null;
}

function Words({ n, max }: { n: number; max: number }) {
  return <span className={cn("tabular-nums", n > max ? "font-medium text-amber-700 dark:text-amber-300" : "text-muted-foreground")}>≈ {n} mots dits, {max} au plus</span>;
}

function DraftEditor({
  draft,
  lang,
  current,
  disabled,
  pending,
  onChange,
  onSeek,
  onMake,
  onDrop,
}: {
  draft: Draft;
  lang: string;
  current: HookProposal | null;
  disabled: boolean;
  pending: boolean;
  onChange: (d: Draft) => void;
  onSeek: (sceneIndex: number) => void;
  onMake: () => void;
  onDrop: () => void;
}) {
  const p = draft.proposal;
  const set = (patch: Partial<StoryProposal> | Partial<HookProposal>) => onChange({ ...draft, proposal: { ...p, ...patch } as StoryProposal | HookProposal });
  const hookTitle = p.hook_title?.[lang] ?? "";
  const shots = new Map(draft.shots.map((s) => [s.index, s]));
  const empty = isStory(p) ? p.scenes.some((s) => !s.text.trim()) : !p.hook.trim() || !p.promise.trim();

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-primary/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold">{draft.jobId ? "Texte proposé" : "Ton texte"}</h4>
        <Badge variant="secondary">{draft.mode === "hook" ? "accroche seulement" : "tout le récit"}</Badge>
        <span className="text-muted-foreground text-[11px]">corrige ce que tu veux, rien n’est fabriqué avant le bouton du bas</span>
      </div>

      {isStory(p) && (p.central_idea || p.stakes) ? (
        <dl className="text-muted-foreground grid gap-1 text-xs">
          {p.central_idea ? (
            <div>
              <dt className="text-foreground inline font-medium">Idée : </dt>
              <dd className="inline">{p.central_idea}</dd>
            </div>
          ) : null}
          {p.stakes ? (
            <div>
              <dt className="text-foreground inline font-medium">Enjeu : </dt>
              <dd className="inline">{p.stakes}</dd>
            </div>
          ) : null}
        </dl>
      ) : !isStory(p) && p.angle ? (
        <p className="text-muted-foreground text-xs">
          <span className="text-foreground font-medium">Ressort : </span>
          {p.angle}
        </p>
      ) : null}

      {draft.issues.length ? (
        <div className="flex flex-col gap-1 rounded-lg border border-amber-500/40 bg-amber-500/5 p-2.5 text-xs">
          <span className="flex items-center gap-1.5 font-medium">
            <TriangleAlert className="size-3.5 text-amber-600" />
            Remarques du correcteur et du relecteur (elles ne bloquent pas)
          </span>
          <ul className="text-muted-foreground list-disc pl-5 leading-snug">
            {draft.issues.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium">Titre YouTube</span>
          <Input value={p.title} maxLength={100} disabled={disabled} onChange={(e) => set({ title: e.target.value })} className="text-sm" />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium">Titre d’accroche (gravé à l’écran)</span>
          <Input value={hookTitle} maxLength={140} disabled={disabled} onChange={(e) => set({ hook_title: { ...p.hook_title, [lang]: e.target.value } })} className="text-sm" />
        </label>
      </div>

      {isStory(p) ? (
        <ol className="flex flex-col gap-3">
          {p.scenes.map((s, i) => {
            const shot = shots.get(s.index);
            const n = wordCount(s.text);
            const setScene = (patch: Partial<StoryProposal["scenes"][number]>) => set({ scenes: p.scenes.map((x, k) => (k === i ? { ...x, ...patch } : x)) });
            return (
              <li key={s.index} className="flex flex-col gap-1.5 rounded-lg border p-3">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <Button type="button" size="sm" variant="ghost" className="h-7 px-2" onClick={() => onSeek(s.index)} title="Jouer ce plan dans la vidéo">
                    <Play className="size-3.5" />
                    Plan {i + 1}
                  </Button>
                  <Badge variant="outline">{REWRITE_PARTS[s.part] ?? s.part}</Badge>
                  {shot ? <span className="text-muted-foreground tabular-nums">clip de {shot.seconds.toLocaleString("fr-FR")} s</span> : null}
                  {shot ? <Words n={n} max={shot.words_max} /> : null}
                </div>
                {shot?.shows ? (
                  <p className="text-muted-foreground line-clamp-2 text-[11px] leading-snug" title={shot.shows}>
                    On voit : {shot.shows}
                  </p>
                ) : null}
                <Textarea rows={2} value={s.text} disabled={disabled} onChange={(e) => setScene({ text: e.target.value })} aria-label={`Texte dit sur le plan ${i + 1}`} className="text-sm" />
                {shot?.said && shot.said.trim() !== s.text.trim() ? <p className="text-muted-foreground text-[11px] leading-snug">Avant : « {shot.said} »</p> : null}
                {s.on_screen || i === 0 ? (
                  <Input
                    value={s.on_screen}
                    maxLength={80}
                    disabled={disabled}
                    onChange={(e) => setScene({ on_screen: e.target.value })}
                    placeholder="Texte gravé sur ce plan (3 mots au plus), vide le plus souvent"
                    aria-label={`Texte à l’écran du plan ${i + 1}`}
                    className="h-8 text-xs"
                  />
                ) : null}
              </li>
            );
          })}
        </ol>
      ) : (
        <HookFields proposal={p} current={current} disabled={disabled} onChange={set} />
      )}

      <div className="flex flex-wrap items-center gap-2 border-t pt-3">
        <Button onClick={onMake} disabled={disabled || empty}>
          {pending ? <LoaderCircle className="animate-spin" /> : <Clapperboard />}
          Faire la vidéo avec ce texte
        </Button>
        <Button variant="ghost" size="sm" disabled={disabled} onClick={onDrop}>
          <Undo2 />
          Abandonner ce texte
        </Button>
      </div>
      <p className="text-muted-foreground text-[11px] leading-snug">
        Quelques minutes : la même voix redit les phrases changées (les autres plans gardent leur voix), puis montage et contrôle{draft.mode === "story" ? ", titre et description refaits" : ""}, plus l’attente si la carte graphique finit
        un clip. La nouvelle vidéo arrive à valider dans la Bibliothèque ; celle-ci reste telle qu’elle est.
      </p>
    </section>
  );
}

function HookFields({
  proposal: p,
  current,
  disabled,
  onChange,
}: {
  proposal: HookProposal;
  current: HookProposal | null;
  disabled: boolean;
  onChange: (patch: Partial<HookProposal>) => void;
}) {
  const nHook = wordCount(p.hook);
  const nBoth = nHook + wordCount(p.promise);
  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1.5">
        <span className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-medium">Accroche (1re phrase dite)</span>
          <Words n={nHook} max={HOOK_WORDS_MAX} />
        </span>
        <Textarea rows={2} value={p.hook} disabled={disabled} onChange={(e) => onChange({ hook: e.target.value })} className="text-sm" />
        {current && current.hook.trim() !== p.hook.trim() ? <span className="text-muted-foreground text-[11px]">Avant : « {current.hook} »</span> : null}
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-medium">Promesse (2e phrase)</span>
          <Words n={nBoth} max={OPENING_WORDS_MAX} />
          <span className="text-muted-foreground">avec l’accroche</span>
        </span>
        <Textarea rows={2} value={p.promise} disabled={disabled} onChange={(e) => onChange({ promise: e.target.value })} className="text-sm" />
        {current && current.promise.trim() !== p.promise.trim() ? <span className="text-muted-foreground text-[11px]">Avant : « {current.promise} »</span> : null}
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium">Texte gravé sur le plan de l’accroche</span>
        <Input value={p.on_screen} maxLength={80} disabled={disabled} onChange={(e) => onChange({ on_screen: e.target.value })} placeholder="3 mots au plus, vide le plus souvent" className="h-8 text-xs" />
      </label>
    </div>
  );
}
