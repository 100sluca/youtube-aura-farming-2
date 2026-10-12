"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CalendarClock,
  Check,
  Clapperboard,
  Film,
  Image as ImageIcon,
  ImageUp,
  Loader2,
  Map as MapIcon,
  Mic,
  PenLine,
  RefreshCw,
  Send,
  SlidersHorizontal,
  Sparkles,
  TriangleAlert,
  Video,
} from "lucide-react";

import {
  approveScript,
  chooseThumbnail,
  dropThumbnail,
  finishRecording,
  moreThumbnails,
  redoShot,
  reopenStudio,
  renderAgain,
  resendThumbnail,
  rewriteAll,
  rewriteChapter,
  saveParagraph,
  savePublishing,
  schedulePublish,
  setVoiceModifier,
  startWriting,
  studyNicheThumbnails,
  toggleAbThumbnail,
  toggleKeepThumbnail,
} from "@/app/long/actions";
import { ConfirmButton } from "@/components/confirm-button";
import { NoticeLine, STAGE_TONES } from "@/components/long/long-view";
import { ModifierVoiceSelect, modifierVoiceLabel } from "@/components/long/modifier-select";
import { ToneBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime } from "@/lib/format";
import {
  FORMAT_LABELS,
  MODIFIER_VOICES,
  STAGE_LABELS,
  allParagraphs,
  chapterLabel,
  readingMinutes,
  titleOf,
  voiceMadeWith,
  voiceCleaningOutdated,
  voiceNeedsRedo,
  type LongDetail as Detail,
  type LongJob,
  type LongShot,
  type LongTake,
} from "@/lib/long-types";
import { VOICE_MOD_PREFIX } from "@/lib/voice-mods";

type Notice = { ok: boolean; message: string } | null;
type Run = (fn: () => Promise<{ ok: boolean; message: string }>) => void;

const ACTION_LABELS: Record<string, string> = {
  write: "Écriture du script",
  chapter: "Réécriture d’un chapitre",
  shots: "Plans du réalisateur",
  packaging: "Titres et miniatures",
  publish: "Envoi sur YouTube",
  thumbnail: "Miniature sur YouTube",
  images: "Images",
  clip: "Clip",
  thumbnails: "Miniatures",
  voice: "Voix finale",
  render: "Montage",
  take: "Vérification d’une prise",
  music: "Musique",
};

function fileUrl(id: string, k: string, extra: Record<string, string | number> = {}, v?: string) {
  const q = new URLSearchParams({ k, ...Object.fromEntries(Object.entries(extra).map(([a, b]) => [a, String(b)])) });
  if (v) q.set("v", v);
  return `/api/long/${id}/file?${q.toString()}`;
}

/** Fiche d'une vidéo longue (docs/63) : script, voix, images, miniature et titre, vidéo et publication. */
export function LongDetailView({ data }: { data: Detail }) {
  const v = data.video;
  const [notice, setNotice] = React.useState<Notice>(null);
  const [pending, start] = React.useTransition();
  const run: Run = (fn) => start(async () => setNotice(await fn()));
  const defaultTab =
    v.stage === "review" || v.stage === "done" ? "video" : v.stage === "making" && !v.voice_done_at ? "voice" : v.stage === "making" ? "images" : "script";
  const [tab, setTab] = React.useState(defaultTab);
  const paragraphs = allParagraphs(v.script);
  const chosen = new Map(data.takes.filter((t) => t.chosen).map((t) => [t.para, t]));
  const recorded = paragraphs.filter((p) => chosen.has(p.key) && chosen.get(p.key)!.status !== "failed").length;
  const shotsDone = data.shots.filter((s) => s.has_image || s.has_clip).length; // images prêtes (un clip suit parfois)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/long">
            <ArrowLeft /> Vidéos longues
          </Link>
        </Button>
        <ToneBadge tone={STAGE_TONES[v.stage]}>{STAGE_LABELS[v.stage]}</ToneBadge>
        <ToneBadge tone="neutral">{FORMAT_LABELS[v.format]}</ToneBadge>
        {v.script?.words ? (
          <span className="text-muted-foreground text-xs">
            {v.script.words} mots · ≈ {Math.round(v.script.words / 150)} min de vidéo · ≈ {readingMinutes(v.script.words)} min de micro
          </span>
        ) : null}
      </div>
      <h1 className="text-2xl font-semibold">{titleOf(v)}</h1>
      <JobsLine jobs={data.jobs} />
      {v.error ? (
        <p className="text-destructive flex items-center gap-1.5 text-sm">
          <TriangleAlert className="size-4" /> {v.error}
        </p>
      ) : null}
      <NoticeLine result={notice} />

      <StageActions data={data} recorded={recorded} total={paragraphs.length} run={run} busy={pending} />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="script">
            <PenLine /> Script
          </TabsTrigger>
          <TabsTrigger value="voice" disabled={!v.script}>
            <Mic /> Voix {paragraphs.length ? `${recorded}/${paragraphs.length}` : ""}
          </TabsTrigger>
          <TabsTrigger value="images" disabled={!data.shots.length}>
            <ImageIcon /> Images {data.shots.length ? `${shotsDone}/${data.shots.length}` : ""}
          </TabsTrigger>
          <TabsTrigger value="packaging" disabled={!v.packaging}>
            <Sparkles /> Titre et miniature
          </TabsTrigger>
          <TabsTrigger value="video" disabled={!v.video_id}>
            <Film /> Vidéo
          </TabsTrigger>
        </TabsList>
        <TabsContent value="script" className="mt-3">
          <ScriptTab data={data} run={run} busy={pending} />
        </TabsContent>
        <TabsContent value="voice" className="mt-3">
          <VoiceTab data={data} chosen={chosen} run={run} busy={pending} />
        </TabsContent>
        <TabsContent value="images" className="mt-3">
          <ImagesTab data={data} run={run} busy={pending} />
        </TabsContent>
        <TabsContent value="packaging" className="mt-3">
          <PackagingTab data={data} run={run} busy={pending} />
        </TabsContent>
        <TabsContent value="video" className="mt-3">
          <VideoTab data={data} run={run} busy={pending} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function JobsLine({ jobs }: { jobs: LongJob[] }) {
  if (!jobs.length) return null;
  const running = jobs.filter((j) => j.status === "running");
  const queued = jobs.length - running.length;
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-violet-600 dark:text-violet-400">
      {running.map((j) => (
        <span key={j.id} className="flex items-center gap-1.5">
          <Loader2 className="size-3.5 animate-spin" />
          {j.label ?? ACTION_LABELS[j.action] ?? j.action}
          {j.progress != null ? ` (${j.progress} %)` : ""}
        </span>
      ))}
      {queued ? <span>{queued} tâche{queued > 1 ? "s" : ""} en file</span> : null}
    </div>
  );
}

function StageActions({ data, recorded, total, run, busy }: { data: Detail; recorded: number; total: number; run: Run; busy: boolean }) {
  const v = data.video;
  if (v.stage === "idea" || v.stage === "failed")
    return (
      <div className="flex gap-2">
        <Button onClick={() => run(() => startWriting(v.id))} disabled={busy}>
          <PenLine /> {v.stage === "failed" ? "Relancer l’écriture" : "Écrire le script"}
        </Button>
      </div>
    );
  if (v.stage === "script")
    return (
      <Card className="border-amber-500/40 bg-amber-500/5">
        <CardContent className="flex flex-wrap items-center gap-3 pt-6">
          <p className="text-sm">Relis le script (tu peux corriger chaque paragraphe ou faire réécrire un chapitre), puis valide : les images partent et le Studio voix s’ouvre.</p>
          <Button className="bg-emerald-600 text-white hover:bg-emerald-700" onClick={() => run(() => approveScript(v.id))} disabled={busy}>
            <Check /> Valider le script
          </Button>
        </CardContent>
      </Card>
    );
  if (v.stage === "making" && !v.voice_done_at)
    return (
      <Card className="border-emerald-500/40 bg-emerald-500/5">
        <CardContent className="flex flex-wrap items-center gap-3 pt-6">
          <Button asChild className="bg-emerald-600 text-white hover:bg-emerald-700">
            <Link href={`/long/${v.id}/studio`}>
              <Mic /> Ouvrir le Studio voix
            </Link>
          </Button>
          <span className="text-sm">
            {recorded}/{total} paragraphes enregistrés
          </span>
          <Progress value={total ? (recorded / total) * 100 : 0} className="w-48" />
          <Button variant="outline" onClick={() => run(() => finishRecording(v.id))} disabled={busy || recorded < total}>
            <Check /> Terminer l’enregistrement
          </Button>
        </CardContent>
      </Card>
    );
  return null;
}

// ---- Script ---------------------------------------------------------------------------------------------------------

function ScriptTab({ data, run, busy }: { data: Detail; run: Run; busy: boolean }) {
  const v = data.video;
  const s = v.script;
  const editable = v.stage === "script" || v.stage === "making";
  const [note, setNote] = React.useState("");
  if (!s?.chapters?.length)
    return (
      <p className="text-muted-foreground text-sm">
        {v.stage === "writing" ? "Le script s’écrit : dossier Wikipédia, plan en chapitres, texte, relecture (10 à 20 min)." : "Pas encore de script."}
      </p>
    );
  const problems = [...(v.review?.problems ?? []), ...(s.lint ?? [])];
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="grid gap-2 pt-6 text-sm md:grid-cols-2">
          {s.central_idea ? (
            <p>
              <span className="text-muted-foreground">Idée centrale : </span>
              {s.central_idea}
            </p>
          ) : null}
          {s.promise ? (
            <p>
              <span className="text-muted-foreground">Promesse : </span>
              {s.promise}
            </p>
          ) : null}
          {s.stakes ? (
            <p>
              <span className="text-muted-foreground">Enjeu : </span>
              {s.stakes}
            </p>
          ) : null}
          {s.ending ? (
            <p>
              <span className="text-muted-foreground">Dernière phrase : </span>« {s.ending} »
            </p>
          ) : null}
        </CardContent>
      </Card>
      <FactsCard script={s} sources={v.dossier?.sources ?? []} />
      {problems.length ? (
        <Card className="border-amber-500/40">
          <CardHeader>
            <CardTitle className="text-base">Remarques de la relecture</CardTitle>
            <CardDescription>{v.review?.ok ? "Le relecteur a validé le script ; restent ces points mesurés." : (v.review?.strengths ?? "")}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-1 text-sm">
            {problems.slice(0, 12).map((p, i) => (
              <p key={i}>
                <span className="text-muted-foreground">
                  {chapterLabel(p.chapter)}
                  {p.paragraph != null ? `, § ${p.paragraph + 1}` : ""} :{" "}
                </span>
                {p.problem}
                {p.fix ? <span className="text-muted-foreground"> → {p.fix}</span> : null}
              </p>
            ))}
          </CardContent>
        </Card>
      ) : null}
      {s.chapters.map((c) => (
        <ChapterBlock key={`${c.index}-${c.paragraphs.map((p) => p.text.length).join(".")}`} id={v.id} chapter={c} editable={editable} run={run} busy={busy} />
      ))}
      {editable ? (
        <Card>
          <CardContent className="flex flex-col gap-2 pt-6">
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ce qui ne va pas dans tout le script (angle, ton, ce qui manque)…" />
            <div>
              <Button variant="outline" onClick={() => run(() => rewriteAll(v.id, note))} disabled={busy || note.trim().length < 5}>
                <RefreshCw /> Tout réécrire avec cette remarque
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

const FACT_LABELS: Record<string, { label: string; tone: "success" | "info" | "warning" | "danger" }> = {
  confirmed: { label: "confirmé", tone: "success" },
  hypothesis: { label: "hypothèse dite comme telle", tone: "info" },
  unsupported: { label: "pas dans les sources", tone: "warning" },
  contradicted: { label: "contredit par les sources", tone: "danger" },
};

/** Les sources du dossier et la vérification des faits : chaque fait du script confronté aux sources (docs/63 §9). */
function FactsCard({ script, sources }: { script: NonNullable<Detail["video"]["script"]>; sources: NonNullable<Detail["video"]["dossier"]>["sources"] }) {
  const f = script.factcheck;
  const problems = (f?.claims ?? []).filter((c) => c.status === "unsupported" || c.status === "contradicted");
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Sources et faits vérifiés</CardTitle>
        <CardDescription>
          {f
            ? `${f.total} faits relevés : ${f.confirmed} confirmés par les sources, ${f.hypothesis} hypothèses dites comme telles${
                problems.length ? `, ${problems.length} à revoir` : ", aucun à revoir"
              }${f.corrected?.length ? ` (${f.corrected.length} corrigés avant relecture)` : ""}.`
            : "La vérification des faits se fait pendant l’écriture (vidéos écrites après le 04/10)."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {problems.length ? (
          <div className="flex flex-col gap-1">
            {problems.map((c, i) => (
              <p key={i}>
                <ToneBadge tone={FACT_LABELS[c.status].tone}>{FACT_LABELS[c.status].label}</ToneBadge> {chapterLabel(c.chapter)}
                {c.paragraph != null ? `, § ${c.paragraph + 1}` : ""} : « {c.claim} »{c.fix ? <span className="text-muted-foreground"> → {c.fix}</span> : null}
              </p>
            ))}
          </div>
        ) : null}
        {sources?.length ? (
          <ol className="flex flex-col gap-0.5 text-xs">
            {sources.map((src) => (
              <li key={src.n}>
                [{src.n}] {src.label ?? (src.lang === "en" ? "Wikipédia (anglais)" : "Wikipédia")} ·{" "}
                <a href={src.url} target="_blank" rel="noreferrer" className="underline underline-offset-2">
                  {src.title}
                </a>
              </li>
            ))}
          </ol>
        ) : null}
        {f?.claims?.length ? (
          <details className="text-xs">
            <summary className="cursor-pointer">Tous les faits vérifiés ({f.claims.length})</summary>
            <ul className="mt-1 flex flex-col gap-0.5">
              {f.claims.map((c, i) => (
                <li key={i}>
                  <span className={c.status === "confirmed" ? "text-emerald-600" : c.status === "hypothesis" ? "text-sky-600" : "text-amber-600"}>
                    {FACT_LABELS[c.status]?.label ?? c.status}
                  </span>{" "}
                  {c.source} — {c.claim}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ChapterBlock({
  id,
  chapter,
  editable,
  run,
  busy,
}: {
  id: string;
  chapter: NonNullable<Detail["video"]["script"]>["chapters"][number];
  editable: boolean;
  run: Run;
  busy: boolean;
}) {
  const [note, setNote] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const words = chapter.paragraphs.reduce((n, p) => n + (p.words ?? p.text.split(" ").length), 0);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {chapterLabel(chapter.index)} — {chapter.title}
        </CardTitle>
        <CardDescription>
          {words} mots · ≈ {(words / 150).toFixed(1)} min{chapter.question ? ` · finit sur : ${chapter.question}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {chapter.paragraphs.map((p) => (
          <ParagraphEditor key={`${p.key}-${p.text.length}`} id={id} pkey={p.key} text={p.text} show={p.show} editable={editable} run={run} />
        ))}
        {editable ? (
          open ? (
            <div className="flex flex-col gap-2">
              <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ce qu’il faut changer dans ce chapitre" />
              <div className="flex gap-2">
                <Button size="sm" onClick={() => run(() => rewriteChapter(id, chapter.index, note))} disabled={busy}>
                  <RefreshCw /> Réécrire ce chapitre
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
                  Annuler
                </Button>
              </div>
            </div>
          ) : (
            <div>
              <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
                <RefreshCw /> Réécrire avec une remarque
              </Button>
            </div>
          )
        ) : null}
      </CardContent>
    </Card>
  );
}

function ParagraphEditor({ id, pkey, text, show, editable, run }: { id: string; pkey: string; text: string; show?: string; editable: boolean; run: Run }) {
  const [value, setValue] = React.useState(text);
  const changed = value.trim() !== text.trim();
  return (
    <div className="flex flex-col gap-1">
      {editable ? (
        <Textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={() => changed && run(() => saveParagraph(id, pkey, value))}
          className="min-h-20 text-[15px] leading-relaxed"
        />
      ) : (
        <p className="text-[15px] leading-relaxed">{text}</p>
      )}
      {show ? <p className="text-muted-foreground text-xs">On voit : {show}</p> : null}
    </div>
  );
}

// ---- Voix -----------------------------------------------------------------------------------------------------------

function VoiceTab({ data, chosen, run, busy }: { data: Detail; chosen: Map<string, LongTake>; run: Run; busy: boolean }) {
  const v = data.video;
  const [modifier, setModifier] = React.useState(Boolean(v.voice?.modifier));
  const profiles = data.voiceProfiles;
  const [voice, setVoice] = React.useState(v.voice?.modifier_voice || (profiles[0] ? VOICE_MOD_PREFIX + profiles[0].id : MODIFIER_VOICES[0].id));
  const paragraphs = allParagraphs(v.script);
  const made = voiceMadeWith(v.voice);
  const redo = voiceNeedsRedo(v.voice, v.voice_done_at, modifier, voice, profiles);
  const madeLabel = made?.modifier ? `modifiée (${modifierVoiceLabel(made.voice, profiles)})` : "ta voix telle quelle";
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-3 pt-6 text-sm">
          {v.stage === "making" && !v.voice_done_at ? (
            <Button asChild className="bg-emerald-600 text-white hover:bg-emerald-700">
              <Link href={`/long/${v.id}/studio`}>
                <Mic /> Studio voix
              </Link>
            </Button>
          ) : null}
          <span className="text-muted-foreground">Modificateur de voix pour cette vidéo</span>
          <Switch checked={modifier} onCheckedChange={setModifier} />
          <ModifierVoiceSelect value={voice} onChange={setVoice} profiles={profiles} />
          <Button size="sm" variant={redo ? "default" : "outline"} onClick={() => run(() => setVoiceModifier(v.id, modifier, voice))} disabled={busy}>
            {redo ? "Appliquer à mes prises" : "Enregistrer"}
          </Button>
          <Button asChild size="sm" variant="ghost">
            <Link href={`/long/voix?video=${v.id}`}>
              <SlidersHorizontal /> Studio du modificateur
            </Link>
          </Button>
          {made ? <span className="text-muted-foreground">Voix du montage : {madeLabel}</span> : null}
          {voiceCleaningOutdated(v.voice) ? (
            <span className="text-amber-600 dark:text-amber-400">Nouveau nettoyage : plus de « toc » ni de souffle au début et à la fin des prises</span>
          ) : null}
          {v.voice_done_at ? (
            <>
              <span className="text-emerald-600 dark:text-emerald-400">Enregistrement terminé le {formatDateTime(v.voice_done_at)}</span>
              <Button size="sm" variant="outline" onClick={() => run(() => reopenStudio(v.id, false))} disabled={busy}>
                <Mic /> Refaire certains paragraphes
              </Button>
              <ConfirmButton
                size="sm"
                variant="ghost"
                onConfirm={() => run(() => reopenStudio(v.id, true))}
                disabled={busy}
                confirmLabel="Effacer toutes les prises ?"
              >
                Tout réenregistrer
              </ConfirmButton>
            </>
          ) : null}
        </CardContent>
      </Card>
      <div className="flex flex-col gap-2">
        {paragraphs.map((p) => {
          const t = chosen.get(p.key);
          return (
            <div key={p.key} className="flex flex-col gap-1 rounded-lg border p-3 text-sm md:flex-row md:items-center md:gap-4">
              <span className="text-muted-foreground w-14 shrink-0 text-xs">
                {p.chapter === 0 ? "Ouv." : `Ch. ${p.chapter}`} · {p.key.split("p")[1] ? Number(p.key.split("p")[1]) + 1 : ""}
              </span>
              <p className="line-clamp-2 flex-1">{p.text}</p>
              <TakeBadge take={t} />
              {t ? <audio src={fileUrl(v.id, "take", { t: t.id })} controls preload="none" className="h-8 w-56" /> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function TakeBadge({ take }: { take: LongTake | undefined }) {
  if (!take) return <ToneBadge tone="neutral">À lire</ToneBadge>;
  if (take.status === "checking")
    return (
      <ToneBadge tone="running">
        <Loader2 className="animate-spin" /> Vérification
      </ToneBadge>
    );
  if (take.status === "ok") return <ToneBadge tone="success">Prise {take.take} ✓</ToneBadge>;
  if (take.status === "problem")
    return (
      <ToneBadge tone="warning" title={take.check?.missing?.join(" · ")}>
        Prise {take.take} : à vérifier
      </ToneBadge>
    );
  return <ToneBadge tone="danger">Prise ratée</ToneBadge>;
}

// ---- Images ---------------------------------------------------------------------------------------------------------

function ImagesTab({ data, run, busy }: { data: Detail; run: Run; busy: boolean }) {
  const v = data.video;
  const chapters = [...new Set(data.shots.map((s) => s.chapter))];
  const titleOfChapter = new Map((v.script?.chapters ?? []).map((c) => [c.index, c.title]));
  const [open, setOpen] = React.useState<LongShot | null>(null);
  return (
    <div className="flex flex-col gap-5">
      {chapters.map((c) => {
        const shots = data.shots.filter((s) => s.chapter === c);
        return (
          <section key={c} className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">
              {chapterLabel(c)} — {titleOfChapter.get(c)}{" "}
              <span className="text-muted-foreground font-normal">
                ({shots.filter((s) => s.has_image || s.has_clip).length}/{shots.length} images, {shots.filter((s) => s.has_clip).length}/{shots.filter((s) => s.kind !== "image").length} clips)
              </span>
            </h3>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6">
              {shots.map((s) => (
                <button
                  key={s.idx}
                  type="button"
                  onClick={() => setOpen(s)}
                  className="group relative aspect-video overflow-hidden rounded-md border bg-muted text-left"
                  title={s.visual_prompt}
                >
                  {s.has_image ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={fileUrl(v.id, "shot", { i: s.idx }, s.updated_at)} alt="" className="size-full object-cover" loading="lazy" />
                  ) : (
                    <span className="text-muted-foreground flex size-full items-center justify-center text-xs">
                      {s.status === "failed" ? "ratée" : s.status === "running" ? <Loader2 className="size-4 animate-spin" /> : "à faire"}
                    </span>
                  )}
                  <span className="absolute top-1 left-1 flex gap-1">
                    {s.kind === "clip" ? (
                      <span className="rounded bg-black/70 px-1 text-[10px] text-white">
                        <Video className="inline size-3" /> {s.has_clip ? "clip" : "clip…"}
                      </span>
                    ) : null}
                    {s.kind === "map" ? (
                      <span className="rounded bg-black/70 px-1 text-[10px] text-white">
                        <MapIcon className="inline size-3" /> carte
                      </span>
                    ) : null}
                    {s.qc?.redone ? <span className="rounded bg-amber-500/80 px-1 text-[10px] text-black">refaite</span> : null}
                  </span>
                  <span className="absolute right-1 bottom-1 rounded bg-black/70 px-1 text-[10px] text-white">{s.idx + 1}</span>
                </button>
              ))}
            </div>
          </section>
        );
      })}
      {open ? (
        <Card className="fixed inset-x-4 bottom-4 z-50 mx-auto max-w-3xl shadow-2xl">
          <CardContent className="flex flex-col gap-3 pt-6">
            {open.has_clip ? (
              <video src={fileUrl(v.id, "clip", { i: open.idx }, open.updated_at)} controls autoPlay loop className="w-full rounded" />
            ) : open.has_image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={fileUrl(v.id, "shot", { i: open.idx }, open.updated_at)} alt="" className="w-full rounded" />
            ) : null}
            <p className="text-sm">
              <span className="text-muted-foreground">Plan {open.idx + 1} · {open.kind} · </span>
              {open.visual_prompt}
            </p>
            {open.motion ? <p className="text-muted-foreground text-xs">Mouvement : {open.motion}</p> : null}
            {open.qc?.first_problem ? <p className="text-xs text-amber-600">Refaite après le contrôle : {open.qc.first_problem}</p> : null}
            {open.error ? <p className="text-destructive text-xs">{open.error}</p> : null}
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => run(() => redoShot(v.id, open.idx))} disabled={busy}>
                <RefreshCw /> Refaire ce plan
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setOpen(null)}>
                Fermer
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

// ---- Titre et miniature ---------------------------------------------------------------------------------------------

function PackagingTab({ data, run, busy }: { data: Detail; run: Run; busy: boolean }) {
  const v = data.video;
  const p = v.packaging!;
  const cands = v.thumbnail?.candidates ?? [];
  const chosenThumb = v.thumbnail?.chosen ?? 0;
  const abCount = cands.filter((c) => c.ab).length;
  const thumbsBusy = data.jobs.some((j) => j.action === "thumbnails");
  const [title, setTitle] = React.useState(titleOf(v));
  const [description, setDescription] = React.useState(p.final_description ?? p.description ?? "");
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Miniatures</CardTitle>
          <CardDescription>
            Notées par la vision comme vues à 160 × 90 px sur un téléphone. <strong>Principale</strong> : celle posée à l’envoi.{" "}
            <strong>Garder</strong> : jamais remplacée quand tu en demandes d’autres. <strong>A/B</strong> : les 3 à tester dans YouTube Studio
            (Test & Compare).
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => run(() => moreThumbnails(v.id, 3))} disabled={busy || !v.approved_at || thumbsBusy}>
              {thumbsBusy ? <Loader2 className="animate-spin" /> : <Sparkles />} Proposer 3 autres miniatures
            </Button>
            <Button size="sm" variant="ghost" onClick={() => run(studyNicheThumbnails)} disabled={busy || data.thumbStyleRunning}>
              {data.thumbStyleRunning ? <Loader2 className="animate-spin" /> : <RefreshCw />} Étudier les miniatures de la niche
            </Button>
            <span className="text-muted-foreground text-xs">
              {abCount}/3 pour le test A/B · {cands.filter((c) => c.kept).length} gardée(s) · {cands.length} en tout
            </span>
          </div>
          {data.thumbStyle ? (
            <details className="text-muted-foreground rounded-md border p-2 text-xs">
              <summary className="cursor-pointer">
                Style de la niche relevé sur {data.thumbStyle.n ?? "?"} miniatures qui marchent (suivi par chaque nouvelle miniature)
              </summary>
              <p className="mt-1">{data.thumbStyle.style}</p>
              <ul className="mt-1 list-disc pl-4">
                {data.thumbStyle.rules.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </details>
          ) : (
            <p className="text-muted-foreground text-xs">
              Style de la niche : la consigne « histoire et mystères » par défaut ; « Étudier les miniatures de la niche » le relève sur les vidéos qui
              marchent (page Recherche → Découverte).
            </p>
          )}
          <div className="grid gap-3 md:grid-cols-3">
            {cands.map((c, i) => (
              <div key={`${i}-${c.file?.slice(-12)}`} className={`flex flex-col gap-1.5 rounded-lg border-2 p-1.5 ${i === chosenThumb ? "border-emerald-500" : c.ab ? "border-sky-500/70" : "border-transparent"}`}>
                {c.file ? (
                  <a href={fileUrl(v.id, "thumb", { i }, c.file.slice(-16))} target="_blank" rel="noreferrer" title="Ouvrir en grand (clic droit pour enregistrer)">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={fileUrl(v.id, "thumb", { i }, c.file.slice(-16))} alt="" className="aspect-video w-full rounded object-cover" />
                  </a>
                ) : null}
                <span className="text-xs">
                  {c.score != null ? <strong>{c.score}/10 · </strong> : null}
                  {c.note ?? c.idea}
                </span>
                <div className="flex flex-wrap gap-1">
                  <Button size="sm" variant={i === chosenThumb ? "default" : "outline"} onClick={() => run(() => chooseThumbnail(v.id, i))} disabled={busy}>
                    <Check /> Principale
                  </Button>
                  <Button size="sm" variant={c.kept ? "default" : "outline"} onClick={() => run(() => toggleKeepThumbnail(v.id, i))} disabled={busy}>
                    {c.kept ? "Gardée" : "Garder"}
                  </Button>
                  <Button size="sm" variant={c.ab ? "default" : "outline"} onClick={() => run(() => toggleAbThumbnail(v.id, i))} disabled={busy}>
                    A/B
                  </Button>
                  {!c.kept && i !== chosenThumb ? (
                    <Button size="sm" variant="ghost" onClick={() => run(() => dropThumbnail(v.id, i))} disabled={busy}>
                      Retirer
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
            {!cands.length ? <p className="text-muted-foreground text-sm">Les miniatures se font après la validation du script.</p> : null}
          </div>
          {abCount ? (
            <p className="text-muted-foreground text-xs">
              Test A/B : à l’envoi, la principale est posée sur YouTube. Pour tester les autres, ouvre la vidéo dans YouTube Studio → « Tester et
              comparer », et ajoute les miniatures A/B (clique une miniature pour l’ouvrir en grand, puis enregistre-la).
            </p>
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Titre et description</CardTitle>
          <CardDescription>Le nom connu et l’accroche dans les 45 premiers caractères ; jamais le texte de la miniature.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            {p.titles.map((t, i) => (
              <button key={i} type="button" onClick={() => setTitle(t.title)} className={`rounded-md border px-3 py-2 text-left text-sm ${title === t.title ? "border-emerald-500" : ""}`}>
                {t.title} <span className="text-muted-foreground text-xs">({t.title.length} car.{t.angle ? ` · ${t.angle}` : ""})</span>
              </button>
            ))}
          </div>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          <span className="text-muted-foreground text-xs">{title.length} caractères</span>
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} className="min-h-40" />
          <p className="text-muted-foreground text-xs">Le code ajoute à l’envoi : les chapitres horodatés, les sources Wikipédia, la mention de l’IA et les hashtags.</p>
          {p.pinned_comment ? <p className="text-sm">Commentaire à épingler : « {p.pinned_comment} »</p> : null}
          <div>
            <Button onClick={() => run(() => savePublishing(v.id, title, description))} disabled={busy}>
              Enregistrer
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ---- Vidéo ----------------------------------------------------------------------------------------------------------

function VideoTab({ data, run, busy }: { data: Detail; run: Run; busy: boolean }) {
  const v = data.video;
  const [when, setWhen] = React.useState(data.nextSlot);
  const published = Boolean(data.final?.youtube_video_id);
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-col gap-3 pt-6">
          {v.video_id ? (
            <video src={fileUrl(v.id, "preview", {}, v.rendered_at ?? "")} poster={fileUrl(v.id, "poster", {}, v.rendered_at ?? "")} controls className="w-full rounded-lg bg-black" />
          ) : null}
          {v.timeline?.chapters?.length ? (
            <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {v.timeline.chapters.map((c) => (
                <span key={c.at}>
                  {Math.floor(c.at / 60)}:{String(Math.floor(c.at % 60)).padStart(2, "0")} {c.title}
                </span>
              ))}
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="outline" onClick={() => run(() => renderAgain(v.id))} disabled={busy}>
              <Clapperboard /> Remonter
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarClock className="size-4" /> Publication
          </CardTitle>
          <CardDescription>
            Envoyée en privé sur ta chaîne avec sa date de sortie, la miniature choisie, les chapitres et les sources dans la description.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          {published ? (
            <>
              <p className="text-sm">
                Programmée sur YouTube{data.final?.scheduled_at ? ` pour le ${formatDateTime(data.final.scheduled_at)}` : ""} ·{" "}
                <a className="underline" href={`https://studio.youtube.com/video/${data.final?.youtube_video_id}/edit`} target="_blank" rel="noreferrer">
                  ouvrir dans YouTube Studio
                </a>
              </p>
              <Button variant="outline" onClick={() => run(() => resendThumbnail(v.id))} disabled={busy}>
                <ImageUp /> Reposer la miniature
              </Button>
              <div className="flex w-full flex-wrap items-center gap-3 border-t pt-3">
                <span className="text-muted-foreground w-full text-xs">
                  Supprimée dans YouTube Studio ? Envoie-la à nouveau : nouvelle date, miniature choisie (refusé si l’ancienne est encore sur YouTube).
                </span>
                <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} className="w-60" />
                <ConfirmButton variant="outline" onConfirm={() => run(() => schedulePublish(v.id, when, true))} disabled={busy} confirmLabel="Renvoyer ?">
                  <Send /> Envoyer à nouveau
                </ConfirmButton>
              </div>
            </>
          ) : (
            <>
              <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} className="w-60" />
              <Button className="bg-emerald-600 text-white hover:bg-emerald-700" onClick={() => run(() => schedulePublish(v.id, when))} disabled={busy || !v.video_id}>
                <Send /> Programmer sur YouTube
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
