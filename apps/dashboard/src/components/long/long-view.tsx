"use client";

import * as React from "react";
import Link from "next/link";
import {
  CircleCheck,
  CircleX,
  Clapperboard,
  Film,
  Lightbulb,
  Loader2,
  Mic,
  PenLine,
  Plus,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Trash2,
} from "lucide-react";

import { addOwnSubject, archiveLong, proposeIdeas, saveLongSettings, startWriting } from "@/app/long/actions";
import { ModifierVoiceSelect } from "@/components/long/modifier-select";
import { ToneBadge, type Tone } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime, formatRelative } from "@/lib/format";
import {
  FORMAT_HINTS,
  FORMAT_LABELS,
  STAGE_LABELS,
  WEEKDAYS,
  readingMinutes,
  type LongCard,
  type LongFormat,
  type LongOverview,
  type LongSettings,
  type LongStage,
} from "@/lib/long-types";
import type { VoiceProfile } from "@/lib/voice-mods";

type Notice = { ok: boolean; message: string } | null;

export const STAGE_TONES: Record<LongStage, Tone> = {
  idea: "neutral",
  writing: "running",
  script: "warning",
  making: "running",
  assembling: "running",
  review: "success",
  done: "info",
  archived: "neutral",
  failed: "danger",
};

export function NoticeLine({ result }: { result: Notice }) {
  if (!result) return null;
  return (
    <p className={`flex items-center gap-1.5 text-xs ${result.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`} role="status">
      {result.ok ? <CircleCheck className="size-3.5 shrink-0" /> : <CircleX className="size-3.5 shrink-0" />}
      {result.message}
    </p>
  );
}

/** Page Vidéos longues (docs/63) : ce qui attend Luca (lire, relire, regarder), ce qui se fabrique, les sujets proposés. */
export function LongView({ data }: { data: LongOverview }) {
  const [notice, setNotice] = React.useState<Notice>(null);
  const [pending, start] = React.useTransition();
  const run = (fn: () => Promise<{ ok: boolean; message: string }>) => start(async () => setNotice(await fn()));
  const by = (...stages: LongStage[]) => data.cards.filter((c) => stages.includes(c.stage));
  const toRead = data.cards.filter((c) => c.stage === "making" && !c.voice_done_at);
  const ideasJob = data.jobs.find((j) => j.action === "ideas");
  const jobsOf = (id: string) => data.jobs.filter((j) => j.long_id === id);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <IdeasButton busy={Boolean(ideasJob) || pending} onRun={(n, note) => run(() => proposeIdeas(n, note))} />
        <OwnSubject onRun={(s, f, n) => run(() => addOwnSubject(s, f, n))} busy={pending} />
        {ideasJob ? (
          <span className="flex items-center gap-1.5 text-xs text-violet-600 dark:text-violet-400">
            <Loader2 className="size-3.5 animate-spin" />
            {ideasJob.status === "queued" ? "Recherche de sujets en file" : (ideasJob.label ?? "Recherche de sujets")}
          </span>
        ) : null}
        <NoticeLine result={notice} />
      </div>

      {toRead.length ? (
        <Card className="border-emerald-500/40 bg-emerald-500/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mic className="size-5" /> À lire au micro
            </CardTitle>
            <CardDescription>
              {toRead.length} vidéo{toRead.length > 1 ? "s" : ""} : tout est prêt sauf ta voix (≈{" "}
              {toRead.reduce((n, c) => n + readingMinutes(c.words), 0)} min de micro en tout).
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2">
            {toRead.map((c) => (
              <div key={c.id} className="flex items-center justify-between gap-3 rounded-lg border bg-background p-3">
                <div className="min-w-0">
                  <Link href={`/long/${c.id}`} className="block truncate font-medium hover:underline">
                    {c.title}
                  </Link>
                  <p className="text-muted-foreground text-xs">
                    {c.takes_ok}/{c.paragraphs} paragraphes enregistrés · ≈ {readingMinutes(c.words)} min · images {c.shots_done}/{c.shots_total || "…"}
                  </p>
                </div>
                <Button asChild className="bg-emerald-600 text-white hover:bg-emerald-700">
                  <Link href={`/long/${c.id}/studio`}>
                    <Mic /> Studio voix
                  </Link>
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <Section title="À relire et valider" icon={<PenLine className="size-4" />} cards={by("script")} jobsOf={jobsOf} empty="" />
      <Section title="Prêtes à regarder" icon={<Film className="size-4" />} cards={by("review")} jobsOf={jobsOf} empty="" />
      <Section
        title="En cours"
        icon={<Clapperboard className="size-4" />}
        cards={[...by("writing", "assembling", "failed"), ...by("making").filter((c) => c.voice_done_at)]}
        jobsOf={jobsOf}
        empty=""
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Lightbulb className="size-5" /> Sujets proposés
          </CardTitle>
          <CardDescription>
            Chaque sujet arrive avec son titre, sa miniature et sa promesse : l’emballage décide du clic. « Écrire » lance le dossier, le plan
            en chapitres, le texte et sa relecture.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 lg:grid-cols-2">
          {by("idea").length ? (
            by("idea").map((c) => (
              <IdeaCard
                key={c.id}
                card={c}
                busy={pending}
                onWrite={(note) => run(() => startWriting(c.id, note))}
                onDrop={() => run(() => archiveLong(c.id))}
              />
            ))
          ) : (
            <p className="text-muted-foreground text-sm">Aucun sujet en attente : « Proposer des sujets » en demande de nouveaux.</p>
          )}
        </CardContent>
      </Card>

      <Section title="Programmées et publiées" icon={<Sparkles className="size-4" />} cards={by("done")} jobsOf={jobsOf} empty="" />

      <SettingsCard initial={data.settings} profiles={data.voiceProfiles} />
    </div>
  );
}

function Section({
  title,
  icon,
  cards,
  jobsOf,
  empty,
}: {
  title: string;
  icon: React.ReactNode;
  cards: LongCard[];
  jobsOf: (id: string) => LongOverview["jobs"];
  empty: string;
}) {
  if (!cards.length && !empty) return null;
  return (
    <section className="flex flex-col gap-2">
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        {icon}
        {title}
      </h2>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {cards.map((c) => (
          <VideoCard key={c.id} card={c} jobs={jobsOf(c.id)} />
        ))}
      </div>
    </section>
  );
}

function VideoCard({ card, jobs }: { card: LongCard; jobs: LongOverview["jobs"] }) {
  const running = jobs.find((j) => j.status === "running") ?? jobs[0];
  return (
    <Link href={`/long/${card.id}`} className="hover:border-foreground/30 flex flex-col gap-2 rounded-xl border p-3 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <p className="line-clamp-2 font-medium">{card.title}</p>
        <ToneBadge tone={STAGE_TONES[card.stage]}>{STAGE_LABELS[card.stage]}</ToneBadge>
      </div>
      <p className="text-muted-foreground text-xs">
        {FORMAT_LABELS[card.format]}
        {card.words ? ` · ${card.words} mots (≈ ${Math.round(card.words / 150)} min)` : ""}
        {card.shots_total ? ` · images ${card.shots_done}/${card.shots_total}` : ""}
        {card.paragraphs && card.stage === "making" ? ` · voix ${card.takes_ok}/${card.paragraphs}` : ""}
      </p>
      {running ? (
        <p className="flex items-center gap-1.5 text-xs text-violet-600 dark:text-violet-400">
          <Loader2 className="size-3 animate-spin" />
          {running.status === "queued" ? "En file" : `${running.label ?? running.action}${running.progress != null ? ` (${running.progress} %)` : ""}`}
          {jobs.length > 1 ? ` · ${jobs.length} tâches` : ""}
        </p>
      ) : null}
      {card.scheduled_at ? <p className="text-xs text-sky-600 dark:text-sky-400">Sortie le {formatDateTime(card.scheduled_at)}</p> : null}
      {card.error ? <p className="text-destructive line-clamp-2 text-xs">{card.error}</p> : null}
    </Link>
  );
}

function IdeaCard({
  card,
  busy,
  onWrite,
  onDrop,
}: {
  card: LongCard;
  busy: boolean;
  onWrite: (note: string) => void;
  onDrop: () => void;
}) {
  const idea = card.idea;
  const [note, setNote] = React.useState("");
  const [open, setOpen] = React.useState(false);
  return (
    <div className="flex flex-col gap-2 rounded-xl border p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="font-semibold">{idea?.title ?? card.subject}</p>
        <div className="flex shrink-0 items-center gap-1.5">
          <ToneBadge tone="neutral">{FORMAT_LABELS[card.format]}</ToneBadge>
          {idea?.score != null ? <ToneBadge tone={idea.score >= 85 ? "success" : "info"}>{Math.round(idea.score)}/100</ToneBadge> : null}
        </div>
      </div>
      {idea?.alt_titles?.length ? <p className="text-muted-foreground text-xs">Autres titres : {idea.alt_titles.join(" · ")}</p> : null}
      <p className="text-sm">{card.subject}</p>
      {idea?.hook ? (
        <p className="text-sm">
          <span className="text-muted-foreground">Ouverture : </span>« {idea.hook} »
        </p>
      ) : null}
      {idea?.promise ? (
        <p className="text-sm">
          <span className="text-muted-foreground">Promesse : </span>
          {idea.promise}
        </p>
      ) : null}
      {idea?.thumbnail ? (
        <p className="text-sm">
          <span className="text-muted-foreground">Miniature : </span>
          {idea.thumbnail.idea}
          {idea.thumbnail.text ? (
            <span className="ml-1 rounded bg-yellow-400 px-1.5 py-0.5 text-xs font-black text-black">{idea.thumbnail.text}</span>
          ) : null}
        </p>
      ) : null}
      {idea?.proof?.length ? (
        <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-2 text-xs">
          <p className="font-medium">A déjà marché :</p>
          {idea.proof.map((p) => (
            <p key={p.title}>
              {p.url ? (
                <a href={p.url} target="_blank" rel="noreferrer" className="underline underline-offset-2">
                  « {p.title} »
                </a>
              ) : (
                `« ${p.title} »`
              )}{" "}
              <span className="text-muted-foreground">
                {p.views ? `${new Intl.NumberFormat("fr-FR").format(p.views)} vues` : ""}
                {p.channel ? ` · ${p.channel}` : ""}
              </span>
            </p>
          ))}
          {idea.new_angle ? <p className="mt-1">Notre angle : {idea.new_angle}</p> : null}
        </div>
      ) : null}
      {idea?.why ? <p className="text-muted-foreground text-xs">Pourquoi : {idea.why}</p> : null}
      {idea?.wikipedia?.length ? <p className="text-muted-foreground text-xs">Sources : {idea.wikipedia.join(", ")}</p> : null}
      {open ? (
        <Textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Une remarque pour l’écriture (facultatif) : un angle, ce qu’il faut absolument raconter…"
          className="min-h-16 text-sm"
        />
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => onWrite(note)} disabled={busy}>
          <PenLine /> Écrire
        </Button>
        {!open ? (
          <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
            Avec une remarque
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" onClick={onDrop} disabled={busy}>
          <Trash2 /> Écarter
        </Button>
      </div>
    </div>
  );
}

function IdeasButton({ busy, onRun }: { busy: boolean; onRun: (n: number, note: string) => void }) {
  const [open, setOpen] = React.useState(false);
  const [n, setN] = React.useState("6");
  const [note, setNote] = React.useState("");
  if (!open)
    return (
      <Button onClick={() => setOpen(true)} disabled={busy}>
        {busy ? <Loader2 className="animate-spin" /> : <Lightbulb />} Proposer des sujets
      </Button>
    );
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border p-2">
      <Select value={n} onValueChange={setN}>
        <SelectTrigger className="w-24">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {["3", "6", "9", "12"].map((v) => (
            <SelectItem key={v} value={v}>
              {v} sujets
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Une envie ? (Égypte, Moyen Âge, Titanic…)" className="w-72" />
      <Button
        onClick={() => {
          onRun(Number(n), note);
          setOpen(false);
        }}
        disabled={busy}
      >
        <Lightbulb /> Proposer
      </Button>
      <Button variant="ghost" onClick={() => setOpen(false)}>
        Annuler
      </Button>
    </div>
  );
}

function OwnSubject({ busy, onRun }: { busy: boolean; onRun: (subject: string, format: LongFormat, notes: string) => void }) {
  const [open, setOpen] = React.useState(false);
  const [subject, setSubject] = React.useState("");
  const [format, setFormat] = React.useState<LongFormat>("mystere");
  const [notes, setNotes] = React.useState("");
  if (!open)
    return (
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Plus /> Mon sujet
      </Button>
    );
  return (
    <div className="flex w-full flex-col gap-2 rounded-lg border p-3">
      <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Le sujet en une phrase (ex. : le trésor perdu des Templiers)" />
      <div className="flex flex-wrap items-center gap-2">
        <Select value={format} onValueChange={(v) => setFormat(v as LongFormat)}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(FORMAT_LABELS) as LongFormat[]).map((f) => (
              <SelectItem key={f} value={f}>
                {FORMAT_LABELS[f]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-muted-foreground text-xs">{FORMAT_HINTS[format]}</span>
      </div>
      <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Ce que tu veux absolument dedans (facultatif)" className="min-h-14" />
      <div className="flex gap-2">
        <Button
          onClick={() => {
            onRun(subject, format, notes);
            setOpen(false);
            setSubject("");
            setNotes("");
          }}
          disabled={busy || subject.trim().length < 8}
        >
          <PenLine /> Écrire ce sujet
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)}>
          Annuler
        </Button>
      </div>
    </div>
  );
}

function SettingsCard({ initial, profiles }: { initial: LongSettings; profiles: VoiceProfile[] }) {
  const [s, setS] = React.useState(initial);
  const [notice, setNotice] = React.useState<Notice>(null);
  const [pending, start] = React.useTransition();
  const toggleDay = (d: number) => setS((v) => ({ ...v, weekdays: v.weekdays.includes(d) ? v.weekdays.filter((x) => x !== d) : [...v.weekdays, d].sort() }));
  const toggleFormat = (f: LongFormat) => setS((v) => ({ ...v, formats: v.formats.includes(f) ? v.formats.filter((x) => x !== f) : [...v.formats, f] }));
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Settings2 className="size-5" /> Réglages des vidéos longues
        </CardTitle>
        <CardDescription>Jours et heure de sortie, durée visée, formats proposés, modificateur de voix par défaut et sous-titres.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-40 text-muted-foreground">Jours de sortie</span>
          {WEEKDAYS.map((d, i) => (
            <Button key={d} size="sm" variant={s.weekdays.includes(i + 1) ? "default" : "outline"} onClick={() => toggleDay(i + 1)}>
              {d.slice(0, 3)}
            </Button>
          ))}
          <Input type="time" value={s.hour} onChange={(e) => setS({ ...s, hour: e.target.value })} className="w-28" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-40 text-muted-foreground">Durée visée</span>
          <Input
            type="number"
            min={8}
            max={60}
            value={s.target_minutes}
            onChange={(e) => setS({ ...s, target_minutes: Number(e.target.value) })}
            className="w-24"
          />
          <span className="text-muted-foreground">min (≈ {s.target_minutes * 150} mots, ≈ {readingMinutes(s.target_minutes * 150)} min de micro)</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-40 text-muted-foreground">Formats proposés</span>
          {(["mystere", "epoque"] as LongFormat[]).map((f) => (
            <Button key={f} size="sm" variant={s.formats.includes(f) ? "default" : "outline"} onClick={() => toggleFormat(f)}>
              {FORMAT_LABELS[f]}
            </Button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="w-40 text-muted-foreground">Modificateur de voix</span>
          <Switch checked={s.voice_modifier} onCheckedChange={(v) => setS({ ...s, voice_modifier: v })} />
          <ModifierVoiceSelect value={s.modifier_voice} onChange={(v) => setS({ ...s, modifier_voice: v })} profiles={profiles} className="w-72" />
          <Button asChild size="sm" variant="ghost">
            <Link href="/long/voix">
              <SlidersHorizontal /> Studio du modificateur
            </Link>
          </Button>
          <span className="text-muted-foreground text-xs">
            Tes réglages se font et s’écoutent dans le Studio du modificateur : ta voix, juste un peu déplacée. Réglable aussi vidéo par vidéo.
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="w-40 text-muted-foreground">Sous-titres</span>
          <Switch checked={s.subtitles} onCheckedChange={(v) => setS({ ...s, subtitles: v })} />
          <span className="text-muted-foreground text-xs">
            Le texte du script en bas de l’image, calé sur ta voix, le mot dit en jaune comme dans les Shorts. Compté au prochain montage.
          </span>
        </div>
        <div className="flex items-center gap-3">
          <Button onClick={() => start(async () => setNotice(await saveLongSettings(s)))} disabled={pending}>
            {pending ? <Loader2 className="animate-spin" /> : null} Enregistrer
          </Button>
          <NoticeLine result={notice} />
          <span className="text-muted-foreground text-xs">Mis à jour {formatRelative(new Date())}</span>
        </div>
      </CardContent>
    </Card>
  );
}
