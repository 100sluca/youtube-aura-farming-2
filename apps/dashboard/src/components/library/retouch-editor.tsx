"use client";

/**
 * Retouche d'une vidéo montée (Bibliothèque → Retoucher, docs/34-retouche.md). À gauche la vidéo, qu'on peut écouter
 * avec le nouveau mixage, et « Refaire la vidéo » ; à droite trois onglets : Textes (titre d'accroche, sous-titres scène
 * par scène, nombres en chiffres), Musique et son (une musique choisie dans un menu, son départ, les niveaux), Voix (une
 * autre voix, écoutée avant). Pour cette vidéo seulement : la chaîne de production ne change pas.
 */
import * as React from "react";
import { useRouter } from "next/navigation";
import { AudioLines, CircleCheck, CircleX, Clapperboard, Hash, Info, LoaderCircle, Play, RotateCcw, TriangleAlert, Undo2 } from "lucide-react";

import { fetchRetouchState, retouchVideo, suggestDigits } from "@/app/library/retouch-actions";
import { SliderField } from "@/components/montage/fields";
import { useVideoMix, type LiveMix } from "@/components/montage/use-mix-player";
import { VideoDecision, isDecidable } from "@/components/production/video-panel";
import { VoicePicker } from "@/components/settings/voice-picker";
import { VideoStatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { formatDuration, mixLevels, musicStart, speechSegments } from "@/lib/audio-mix";
import { formatDateTime } from "@/lib/format";
import { FORMAT_LABELS, FORMAT_SHORT, type AudioLayer, type MusicTrack } from "@/lib/montage-types";
import { HOOK_MIN_S, LEVEL_KEYS, type Levels, type RetouchInput, type RetouchJob, type RetouchPageData, type RetouchScene, type RetouchState } from "@/lib/retouch-types";
import { cn } from "@/lib/utils";

const KEEP = "__keep";
const NONE = "__none";
const POLL_MS = 2000;

type Notice = { ok: boolean; message: string };
type Listen = "current" | "draft";

interface Draft {
  hook: string;
  hookEphemeral: boolean; // titre d'accroche affiché quelques secondes puis effacé en fondu (29/09)
  hookS: number; // sa durée d'affichage
  subs: Record<string, string>; // index de scène → texte affiché
  music: string; // KEEP, NONE ou identifiant de piste
  startS: number | null; // départ de la musique choisie ; null = celui de la piste
  levels: Levels;
  voice: string; // « moteur:voix »
}

/** Deux textes affichés identiques, espaces (insécables comprises) mises à part. */
const same = (a: string, b: string) => a.replace(/\s+/g, " ").trim() === b.replace(/\s+/g, " ").trim();
const levelsOf = (a: AudioLayer): Levels => ({ voice_db: a.voice_db, music_db: a.music_db, duck_db: a.duck_db, solo_db: a.solo_db, sfx_db: a.sfx_db });
/** Durée d'affichage du titre d'accroche : celle de la retouche, sinon celle du modèle ; null = toute la vidéo. */
const hookTime = (durationS: number | null) => ({ hookEphemeral: durationS !== null, hookS: durationS ?? HOOK_MIN_S });
const seconds = (s: number) => `${s.toLocaleString("fr-FR")} s`;

function savedDraft(d: RetouchPageData): Draft {
  const r = d.retouch;
  return {
    hook: r.hook_title?.trim() || d.hook.auto,
    ...hookTime(r.hook_display ? r.hook_display.duration_s : d.hook.templateDurationS),
    subs: Object.fromEntries(d.scenes.map((s) => [String(s.index), s.edited ?? s.auto])),
    music: r.music ? (r.music.track ?? NONE) : KEEP,
    startS: r.music?.start_s ?? null,
    levels: { ...levelsOf(d.template.audio), ...r.audio },
    voice: d.voice.current ?? "",
  };
}

function automaticDraft(d: RetouchPageData): Draft {
  return {
    hook: d.hook.auto,
    ...hookTime(d.hook.templateDurationS),
    subs: Object.fromEntries(d.scenes.map((s) => [String(s.index), s.auto])),
    music: KEEP,
    startS: null,
    levels: levelsOf(d.template.audio),
    voice: d.voice.current ?? "",
  };
}

/** Ce que la retouche enregistre : ce qui diffère du montage automatique et du modèle de montage. */
function toInput(d: RetouchPageData, draft: Draft): RetouchInput {
  const base = levelsOf(d.template.audio);
  const shownFor = draft.hookEphemeral ? draft.hookS : null;
  return {
    hookTitle: same(draft.hook, d.hook.auto) ? null : draft.hook.trim(),
    hookDisplay: shownFor === d.hook.templateDurationS ? null : { durationS: shownFor },
    subtitles: Object.fromEntries(
      d.scenes.flatMap((s) => {
        const text = draft.subs[String(s.index)] ?? s.auto;
        return same(text, s.auto) ? [] : [[String(s.index), text]];
      }),
    ),
    music: draft.music === KEEP ? null : { track: draft.music === NONE ? null : draft.music, startS: draft.music === NONE ? null : draft.startS },
    audio: Object.fromEntries(LEVEL_KEYS.filter((k) => draft.levels[k] !== base[k]).map((k) => [k, draft.levels[k]])),
    voice: draft.voice && draft.voice !== d.voice.current ? draft.voice : null,
  };
}

/** Ce qui changera sur la vidéo par rapport à celle d'aujourd'hui. */
function changes(d: RetouchPageData, draft: Draft, before: Draft, trackTitle: (id: string) => string): string[] {
  const out: string[] = [];
  if (!same(draft.hook, before.hook)) out.push("Titre d’accroche");
  if (draft.hookEphemeral !== before.hookEphemeral || (draft.hookEphemeral && draft.hookS !== before.hookS)) {
    out.push(draft.hookEphemeral ? `Titre d’accroche · ${seconds(draft.hookS)}` : "Titre d’accroche · toute la vidéo");
  }
  const subs = d.scenes.filter((s) => !same(draft.subs[String(s.index)] ?? "", before.subs[String(s.index)] ?? "")).length;
  if (subs) out.push(`Sous-titres · ${subs} scène${subs > 1 ? "s" : ""}`);
  if (draft.music !== before.music || draft.startS !== before.startS) {
    out.push(draft.music === NONE ? "Sans musique" : draft.music === KEEP ? "Musique d’origine" : `Musique « ${trackTitle(draft.music)} »`);
  }
  if (LEVEL_KEYS.some((k) => draft.levels[k] !== before.levels[k])) out.push("Mixage");
  if (draft.voice && draft.voice !== before.voice) out.push("Voix");
  return out;
}

const STEP: Record<RetouchJob["type"], string> = { tts: "Voix", assemble: "Montage", qa: "Contrôle" };

function JobLine({ job }: { job: RetouchJob }) {
  const text =
    job.status === "running"
      ? (job.label ?? `${job.progress} %`)
      : job.status === "queued"
        ? job.type === "tts"
          ? "en file : passe sur la carte graphique après la tâche en cours"
          : "en file : démarre quand le worker a fini sa tâche en cours (un clip dure jusqu’à 10 min)"
        : job.status === "done"
          ? "fait"
          : job.status === "failed"
            ? (job.error ?? "échec")
            : "annulé";
  return (
    <li className="flex items-start gap-2">
      {job.status === "done" ? (
        <CircleCheck className="mt-px size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
      ) : job.status === "running" ? (
        <LoaderCircle className="mt-px size-3.5 shrink-0 animate-spin" />
      ) : job.status === "queued" ? (
        <span className="border-muted-foreground/60 mt-px size-3.5 shrink-0 rounded-full border" />
      ) : (
        <CircleX className="text-destructive mt-px size-3.5 shrink-0" />
      )}
      <span className="font-medium">{STEP[job.type]}</span>
      <span className={cn("min-w-0 break-words", job.status === "failed" ? "text-destructive" : "text-muted-foreground")}>{text}</span>
    </li>
  );
}

function SceneRow({
  scene,
  text,
  onChange,
  onPlay,
  disabled,
}: {
  scene: RetouchScene;
  text: string;
  onChange: (text: string) => void;
  onPlay: () => void;
  disabled: boolean;
}) {
  const changed = !same(text, scene.auto);
  return (
    <li className={cn("flex flex-col gap-1.5 rounded-lg border p-3", changed && "border-primary/50 bg-primary/5")}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Button type="button" size="sm" variant="ghost" className="h-7 px-2" onClick={onPlay} title="Jouer la scène dans la vidéo">
          <Play className="size-3.5" />
          Scène {scene.position + 1}
        </Button>
        <span className="text-muted-foreground tabular-nums">
          {formatDuration(scene.start)} → {formatDuration(scene.end)}
        </span>
        {changed ? (
          <>
            <Badge variant="secondary" className="ml-auto">
              retouchée
            </Badge>
            <Button type="button" size="sm" variant="ghost" className="h-7 px-2" disabled={disabled} onClick={() => onChange(scene.auto)}>
              <RotateCcw className="size-3.5" />
              Rétablir
            </Button>
          </>
        ) : null}
      </div>
      <Textarea rows={2} value={text} disabled={disabled} onChange={(e) => onChange(e.target.value)} aria-label={`Sous-titres de la scène ${scene.position + 1}`} className="text-sm" />
      {!text.trim() ? <p className="text-[11px] text-amber-700 dark:text-amber-300">Aucun sous-titre sur cette scène.</p> : null}
      {!same(scene.spoken, text) ? <p className="text-muted-foreground text-[11px] leading-snug">La voix dit : « {scene.spoken} »</p> : null}
    </li>
  );
}

function TrackCard({ track, moods, start, onStart, adjustable, disabled }: {
  track: MusicTrack;
  moods: Record<string, [string, string]>;
  start: number;
  onStart: (s: number) => void;
  adjustable: boolean;
  disabled: boolean;
}) {
  const maxStart = Math.max(0, Math.floor((track.durationS ?? 60) - 10));
  return (
    <div className="flex flex-col gap-2 rounded-lg border p-3 text-xs">
      {track.description ? <p className="text-sm leading-snug">{track.description}</p> : null}
      <div className="flex flex-wrap items-center gap-1.5">
        {track.formats.map((f) => (
          <Badge key={f} variant="secondary">
            {FORMAT_SHORT[f]}
          </Badge>
        ))}
        {track.moods.map((m) => (
          <Badge key={m} variant="outline" title={moods[m]?.[1]}>
            {moods[m]?.[0] ?? m}
          </Badge>
        ))}
        <span className="text-muted-foreground">
          {formatDuration(track.durationS)} · {track.lufs === null ? "sonie pas encore mesurée" : `${track.lufs.toLocaleString("fr-FR")} LUFS`}
        </span>
      </div>
      {track.note ? (
        <p className="flex items-center gap-1.5 text-amber-700 dark:text-amber-300">
          <TriangleAlert className="size-3.5 shrink-0" />
          {track.note}
        </p>
      ) : null}
      {adjustable && maxStart > 0 && !disabled ? (
        <SliderField
          label="Début dans le fichier"
          value={Math.min(start, maxStart)}
          min={0}
          max={maxStart}
          step={1}
          unit="s"
          onChange={onStart}
          hint="pour cette vidéo seulement : passer une intro trop calme"
        />
      ) : null}
    </div>
  );
}

export function RetouchEditor({ data: d }: { data: RetouchPageData }) {
  const router = useRouter();
  const before = React.useMemo(() => savedDraft(d), [d]);
  const [draft, setDraft] = React.useState<Draft>(before);
  const [state, setState] = React.useState<RetouchState>(d.state);
  const [notice, setNotice] = React.useState<Notice | null>(null);
  const [pending, startTransition] = React.useTransition();
  const [listen, setListen] = React.useState<Listen>("current");
  // L'élément vidéo : en état pour l'écoute (use-mix-player), en ref pour le piloter (▶ d'une scène)
  const [el, setEl] = React.useState<HTMLVideoElement | null>(null);
  const videoRef = React.useRef<HTMLVideoElement | null>(null);
  const attachVideo = React.useCallback((node: HTMLVideoElement | null) => {
    videoRef.current = node;
    setEl(node);
  }, []);

  const c = d.music.constants;
  const locked = Boolean(d.blocked) || state.busy || pending;
  const tracks = d.music.tracks;
  const present = tracks.filter((t) => !t.missing);
  const trackOf = (id: string | null) => (id ? (present.find((t) => t.id === id) ?? null) : null);
  const trackTitle = (id: string) => tracks.find((t) => t.id === id)?.title ?? id;
  const musicOnFormat = d.template.audio.formats.includes(d.video.format);
  const kept = trackOf(d.music.current ?? d.music.auto);
  const draftTrack = draft.music === NONE ? null : draft.music === KEEP ? (musicOnFormat ? kept : null) : trackOf(draft.music);
  const start = draftTrack ? (draft.music !== KEEP && draft.startS !== null ? draft.startS : draftTrack.startS) : 0;
  const totalS = state.durationS ?? d.scenes[d.scenes.length - 1]?.end ?? 30;
  const narration = d.voice.narration;
  const voiceChanged = Boolean(draft.voice) && draft.voice !== d.voice.current;

  const input = toInput(d, draft);
  // Titre d'accroche éphémère : de 5 s à toute la vidéo ; « Rétablir » revient au texte et à la durée automatiques
  const hookMax = Math.max(HOOK_MIN_S, Math.floor(totalS * 2) / 2);
  const hookFromTemplate = input.hookDisplay === null && d.hook.templateDurationS !== null;
  const hookTouched = !same(draft.hook, d.hook.auto) || input.hookDisplay !== null;
  const dirty = JSON.stringify(input) !== JSON.stringify(toInput(d, before));
  const summary = changes(d, draft, before, trackTitle);
  const automatic = JSON.stringify(input) === JSON.stringify(toInput(d, automaticDraft(d)));

  // Écoute : la voix actuelle et la musique choisie, aux niveaux en cours (même calcul que le montage, lib/audio-mix.ts)
  const segments = React.useMemo(() => (narration ? speechSegments(narration.words, c.duck_merge_gap_s) : []), [narration, c]);
  const liveFor = (): LiveMix | null => {
    const withVoice = Boolean(narration);
    const levels = mixLevels({ ...d.template.audio, ...draft.levels }, c, {
      withVoice,
      trackLufs: draftTrack?.lufs ?? null,
      trackGainDb: draftTrack?.gainDb ?? 0,
      narrationLufs: narration?.lufs ?? null,
    });
    return {
      musicGainDb: draftTrack ? levels.musicGainDb : null,
      voiceGainDb: levels.voiceGainDb,
      duckDb: levels.duckDb,
      masterDb: c.output_lufs - (withVoice ? c.voice_ref_lufs : c.solo_ref_lufs),
      segments,
      attackS: c.duck_attack_s,
      releaseS: c.duck_release_s,
      fadeInS: c.fade_in_s,
      fadeOutS: c.fade_out_s,
      totalS,
    };
  };
  const mix = useVideoMix({
    video: el,
    voiceUrl: narration?.url ?? null,
    musicUrl: draftTrack?.url ?? null,
    musicStartS: draftTrack ? musicStart(start, draftTrack.durationS, totalS) : 0,
    musicDurationS: draftTrack?.durationS ?? null,
    original: listen === "current",
    liveFor,
  });

  // Pendant que la vidéo est refaite : son avancement toutes les 2 s, puis la page relue (nouvelle vidéo, textes)
  React.useEffect(() => {
    if (!state.busy) return;
    let alive = true;
    const timer = setInterval(async () => {
      const next = await fetchRetouchState(d.video.id).catch(() => null);
      if (!alive || !next) return;
      setState(next);
      if (!next.busy) {
        clearInterval(timer);
        router.refresh();
      }
    }, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [state.busy, d.video.id, router]);

  const edit = (patch: Partial<Draft>, sound = false) => {
    setDraft((cur) => ({ ...cur, ...patch }));
    if (sound) setListen("draft");
  };
  const seek = (t: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = Math.max(0, t - 0.15);
    void video.play().catch(() => undefined);
  };
  const submit = () =>
    startTransition(async () => {
      const res = await retouchVideo(d.video.id, input);
      setNotice(res);
      if (res.ok) router.refresh();
    });
  const digits = () =>
    startTransition(async () => {
      const keys = d.scenes.map((s) => String(s.index));
      const texts = [draft.hook, ...keys.map((k) => draft.subs[k] ?? "")];
      const res = await suggestDigits(texts, d.video.lang);
      if (!res.ok) {
        setNotice(res);
        return;
      }
      const [hook, ...subs] = res.texts;
      const changed = res.texts.filter((t, i) => t !== texts[i]).length;
      setDraft((cur) => ({ ...cur, hook, subs: { ...cur.subs, ...Object.fromEntries(keys.map((k, i) => [k, subs[i]])) } }));
      setNotice({
        ok: true,
        message: changed
          ? `${changed} texte${changed > 1 ? "s" : ""} avec des nombres en chiffres : relis-les, puis « Refaire la vidéo »`
          : "Aucun nombre écrit en lettres",
      });
    });

  const failed = state.jobs.find((j) => j.status === "failed");
  // Dernière tentative ratée (contrôle refusé, montage en échec) : « Refaire la vidéo » relance même sans changement
  const retry = Boolean(failed) || (state.status === "failed" && !(state.error ?? "").startsWith("Refusée"));
  const voiceLabel = (id: string | null) => {
    const e = d.voice.entries.find((x) => x.id === id);
    return e ? `${e.engineLabel} · ${e.label}` : (id ?? "inconnue");
  };
  const levelHint = (k: keyof Levels) => (draft.levels[k] === d.template.audio[k] ? `réglage du modèle « ${d.template.name} »` : `modèle : ${d.template.audio[k]} dB`);
  const keepLabel = d.music.current
    ? `Garder la musique actuelle · « ${trackTitle(d.music.current)} »`
    : musicOnFormat
      ? `Choix du montage${d.music.auto ? ` · « ${trackTitle(d.music.auto)} »` : ""}`
      : "Pas de musique (modèle de montage)";

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h2 className="text-2xl font-semibold tracking-tight">{d.video.title}</h2>
        <div className="flex flex-wrap items-center gap-1.5">
          <VideoStatusBadge status={state.status} />
          <Badge variant="outline">{FORMAT_LABELS[d.video.format]}</Badge>
          {d.video.channelName ? <Badge variant="outline">{d.video.channelName}</Badge> : null}
        </div>
        <p className="text-muted-foreground max-w-3xl text-sm">
          Tes corrections, pour cette vidéo seulement : titre d’accroche, sous-titres, musique, mixage, voix. « Refaire la vidéo » la remonte avec les mêmes clips ;
          la chaîne de production ne change pas.
        </p>
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
        <aside className="flex flex-col gap-3 lg:sticky lg:top-20">
          {state.finalAssetId ? (
            <video
              key={state.finalAssetId}
              ref={attachVideo}
              src={`/api/media/${state.finalAssetId}`}
              poster={state.posterAssetId ? `/api/media/${state.posterAssetId}` : undefined}
              controls
              playsInline
              preload="auto"
              className="mx-auto aspect-[9/16] max-h-[62vh] w-full rounded-lg bg-black object-contain"
              onVolumeChange={(e) => {
                if (listen === "draft" && !e.currentTarget.muted) setListen("current");
              }}
            />
          ) : (
            <p className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-sm">Pas de vidéo montée.</p>
          )}

          <div className="flex flex-col gap-1.5">
            <div role="radiogroup" aria-label="Son de la lecture" className="bg-muted inline-flex w-fit gap-0.5 rounded-lg p-0.5">
              {(
                [
                  { value: "current", label: "Son actuel", title: "Le son de la vidéo telle qu’elle est" },
                  { value: "draft", label: "Nouveau mixage", title: "La voix actuelle et la musique choisie, aux niveaux réglés à droite" },
                ] as const
              ).map((o) => (
                <button
                  key={o.value}
                  type="button"
                  role="radio"
                  aria-checked={listen === o.value}
                  title={o.title}
                  onClick={() => setListen(o.value)}
                  className={cn(
                    "rounded-md px-2 py-1 text-xs font-medium transition-colors",
                    listen === o.value ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {o.label}
                </button>
              ))}
            </div>
            <p className="text-muted-foreground flex items-start gap-1.5 text-[11px] leading-snug">
              <AudioLines className="mt-px size-3.5 shrink-0" />
              <span>
                {listen === "draft"
                  ? `▶ joue la vidéo ${narration ? "avec sa voix et " : "avec "}${draftTrack ? `« ${draftTrack.title} »` : "sans musique"}, aux niveaux réglés${d.video.voiced ? "" : " (sans les bruitages)"}.${voiceChanged ? " La nouvelle voix s’entend dans Voix → Écouter, puis dans la vidéo refaite." : ""}`
                  : "Le son de la vidéo telle qu’elle est. Titre et sous-titres corrigés : visibles une fois la vidéo refaite."}
              </span>
            </p>
            {mix.error ? <p className="text-destructive text-[11px]">{mix.error}</p> : null}
          </div>

          <section className="flex flex-col gap-2 rounded-lg border p-3">
            <div className="flex flex-wrap gap-1.5">
              {summary.length ? (
                summary.map((s) => (
                  <Badge key={s} variant="secondary">
                    {s}
                  </Badge>
                ))
              ) : (
                <span className="text-muted-foreground text-xs">{state.busy ? "Vidéo en train d’être refaite." : "Aucune modification pour l’instant."}</span>
              )}
            </div>
            <Button onClick={submit} disabled={(!dirty && !retry) || locked}>
              {pending || state.busy ? <LoaderCircle className="animate-spin" /> : <Clapperboard />}
              Refaire la vidéo
            </Button>
            <p className="text-muted-foreground text-[11px] leading-snug">
              {voiceChanged
                ? "Quelques minutes : nouvelle voix sur la carte graphique, puis montage et contrôle."
                : "≈ 1 min de montage et de contrôle, avec les mêmes clips et la même voix."}{" "}
              Plus l’attente si le worker finit un clip. La vidéo actuelle est remplacée et revient à valider.
            </p>
            {!automatic ? (
              <Button variant="ghost" size="sm" className="w-fit" disabled={locked} onClick={() => setDraft(automaticDraft(d))}>
                <Undo2 />
                Revenir au montage automatique
              </Button>
            ) : null}
          </section>

          {d.blocked ? (
            <p className="flex items-start gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 p-3 text-xs leading-relaxed">
              <Info className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
              {d.blocked}
            </p>
          ) : null}
          {state.busy || failed ? (
            <ol className="flex flex-col gap-1.5 rounded-lg border p-3 text-xs" aria-live="polite">
              {state.jobs.map((j) => (
                <JobLine key={j.id} job={j} />
              ))}
            </ol>
          ) : state.retouch && state.doneAt ? (
            <p className="flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-400">
              <CircleCheck className="size-3.5 shrink-0" />
              Refaite le {formatDateTime(state.doneAt)} : regarde-la, puis publie-la si elle te va.
            </p>
          ) : null}
          {state.status === "failed" && state.error && !failed ? (
            <p className="text-destructive text-xs">
              {state.error.startsWith("Refusée")
                ? `${state.error} : la refaire la remet à valider.`
                : `Dernier montage en échec (${state.error}) : « Refaire la vidéo » le relance.`}
            </p>
          ) : null}
          {notice ? (
            <p className={cn("flex items-start gap-1.5 text-xs", notice.ok ? "text-emerald-700 dark:text-emerald-400" : "text-destructive")} role="status">
              {notice.ok ? <CircleCheck className="mt-px size-3.5 shrink-0" /> : <CircleX className="mt-px size-3.5 shrink-0" />}
              {notice.message}
            </p>
          ) : null}
          {isDecidable(state.status) && !state.busy && !d.video.youtubeVideoId ? (
            <section className="flex flex-col gap-2 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
              <h3 className="text-sm font-semibold">Publier cette vidéo ?</h3>
              <VideoDecision videoId={d.video.id} onDone={() => router.refresh()} />
            </section>
          ) : null}
        </aside>

        <Tabs defaultValue="textes" className="min-w-0 gap-4">
          <TabsList className="w-full">
            <TabsTrigger value="textes">Textes</TabsTrigger>
            <TabsTrigger value="son">Musique et son</TabsTrigger>
            <TabsTrigger value="voix">Voix</TabsTrigger>
          </TabsList>

          <TabsContent value="textes" className="flex flex-col gap-6">
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" onClick={digits} disabled={locked}>
                <Hash />
                Nombres en chiffres
              </Button>
              <span className="text-muted-foreground text-[11px] leading-snug">
                propose « 1 350 tonnes » pour « treize cent cinquante tonnes » dans le titre et les sous-titres ; tu relis, rien n’est refait avant « Refaire la vidéo »
              </span>
            </div>

            <section className="flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2">
                <h4 className="text-sm font-semibold">Titre d’accroche</h4>
                {hookTouched ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-xs"
                    disabled={locked}
                    onClick={() => edit({ hook: d.hook.auto, ...hookTime(d.hook.templateDurationS) })}
                  >
                    <RotateCcw className="size-3.5" />
                    Rétablir
                  </Button>
                ) : null}
              </div>
              <Input value={draft.hook} maxLength={140} disabled={locked || !d.hook.shown} onChange={(e) => edit({ hook: e.target.value })} aria-label="Titre d’accroche" />
              <p className="text-muted-foreground text-[11px] leading-snug">
                {!d.hook.shown
                  ? `Le modèle de montage « ${d.template.name} » n’affiche pas de titre d’accroche sur les ${FORMAT_LABELS[d.video.format].toLowerCase()}.`
                  : same(draft.hook, d.hook.auto)
                    ? "Celui du montage automatique."
                    : `Montage automatique : « ${d.hook.auto} »`}
                {draft.hook.trim().length > 70 ? " Plus de 70 caractères : le titre risque de tenir sur 3 lignes." : ""}
              </p>
              {d.hook.shown ? (
                <div className="flex flex-col gap-3 rounded-lg border p-3">
                  <label className="flex cursor-pointer items-start gap-2.5">
                    <Checkbox
                      checked={draft.hookEphemeral}
                      disabled={locked}
                      onCheckedChange={(checked) => edit({ hookEphemeral: checked === true })}
                      className="mt-0.5"
                      aria-label="Titre d’accroche éphémère"
                    />
                    <span className="flex min-w-0 flex-col gap-0.5">
                      <span className="text-sm font-medium">Éphémère</span>
                      <span className="text-muted-foreground text-[11px] leading-snug">
                        {draft.hookEphemeral
                          ? `Affiché les ${seconds(Math.min(draft.hookS, hookMax))} du début, puis il s’efface en fondu.`
                          : "Décoché : affiché pendant toute la vidéo."}
                        {hookFromTemplate ? ` Réglage du modèle « ${d.template.name} ».` : ""}
                      </span>
                    </span>
                  </label>
                  {draft.hookEphemeral ? (
                    <SliderField
                      label="Affiché pendant"
                      value={Math.min(draft.hookS, hookMax)}
                      min={Math.min(HOOK_MIN_S, draft.hookS)}
                      max={hookMax}
                      step={0.5}
                      unit="s"
                      onChange={(hookS) => edit({ hookS })}
                      hint={`de ${seconds(HOOK_MIN_S)} à toute la vidéo (${formatDuration(totalS)}) ; visible une fois la vidéo refaite`}
                    />
                  ) : null}
                </div>
              ) : null}
            </section>

            <section className="flex flex-col gap-3">
              <h4 className="text-sm font-semibold">Sous-titres</h4>
              {!d.video.voiced ? (
                <p className="text-muted-foreground text-sm">Pas de sous-titres : cette vidéo n’a pas de voix.</p>
              ) : !d.scenes.length ? (
                <p className="text-muted-foreground text-sm">Pas de narration horodatée pour cette vidéo.</p>
              ) : (
                <>
                  <p className="text-muted-foreground text-[11px] leading-snug">
                    Tu changes ce qui s’affiche, pas ce que dit la voix. Un mot gardé garde son moment ; un passage réécrit prend la place des mots qu’il remplace.
                    ▶ joue la scène dans la vidéo.
                    {!d.subtitlesShown ? ` Le modèle « ${d.template.name} » n’affiche pas les sous-titres pour l’instant.` : ""}
                  </p>
                  <ol className="flex flex-col gap-3">
                    {d.scenes.map((s) => (
                      <SceneRow
                        key={s.index}
                        scene={s}
                        text={draft.subs[String(s.index)] ?? s.auto}
                        disabled={locked}
                        onPlay={() => seek(s.start)}
                        onChange={(text) => setDraft((cur) => ({ ...cur, subs: { ...cur.subs, [String(s.index)]: text } }))}
                      />
                    ))}
                  </ol>
                </>
              )}
            </section>
          </TabsContent>

          <TabsContent value="son" className="flex flex-col gap-6">
            <section className="flex flex-col gap-3">
              <h4 className="text-sm font-semibold">Musique</h4>
              {d.music.error ? <p className="text-destructive text-xs">{d.music.error}</p> : null}
              <Select value={draft.music} disabled={locked} onValueChange={(music) => edit({ music, startS: null }, true)}>
                <SelectTrigger className="h-9 w-full" aria-label="Musique">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-96">
                  <SelectItem value={KEEP}>{keepLabel}</SelectItem>
                  <SelectItem value={NONE}>Sans musique</SelectItem>
                  <SelectSeparator />
                  <SelectGroup>
                    <SelectLabel>Bibliothèque · {present.length} musiques</SelectLabel>
                    {present.map((t) => (
                      <SelectItem key={t.id} value={t.id}>
                        <span>{t.title}</span>
                        <span className="text-muted-foreground text-xs">
                          {" "}
                          · {t.id}
                          {t.id === d.music.current ? " · actuelle" : ""}
                          {t.id === d.music.auto && t.id !== d.music.current ? " · choix du montage pour cette histoire" : ""}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              {draftTrack ? (
                <TrackCard
                  key={draftTrack.id}
                  track={draftTrack}
                  moods={c.moods}
                  start={start}
                  onStart={(s) => edit({ startS: s }, true)}
                  adjustable={draft.music !== KEEP}
                  disabled={locked}
                />
              ) : (
                <p className="text-muted-foreground text-xs">
                  {draft.music === NONE ? "La vidéo n’aura pas de musique." : "Le modèle de montage ne met pas de musique sur ce format : choisis-en une dans la liste pour en mettre une."}
                </p>
              )}
            </section>

            <section className="flex flex-col gap-4 border-t pt-4">
              <div className="flex items-center justify-between gap-2">
                <h4 className="text-sm font-semibold">Mixage de cette vidéo</h4>
                {LEVEL_KEYS.some((k) => draft.levels[k] !== d.template.audio[k]) ? (
                  <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" disabled={locked} onClick={() => edit({ levels: levelsOf(d.template.audio) }, true)}>
                    <RotateCcw className="size-3.5" />
                    Niveaux du modèle
                  </Button>
                ) : null}
              </div>
              <fieldset disabled={locked} className="grid grid-cols-1 gap-x-5 gap-y-4 sm:grid-cols-2">
                {d.video.voiced ? (
                  <>
                    <SliderField
                      label="Voix IA"
                      value={draft.levels.voice_db}
                      min={-12}
                      max={12}
                      step={0.5}
                      unit="dB"
                      onChange={(voice_db) => edit({ levels: { ...draft.levels, voice_db } }, true)}
                      hint={levelHint("voice_db")}
                    />
                    <SliderField
                      label="Musique sous la voix"
                      value={draft.levels.music_db}
                      min={-30}
                      max={0}
                      step={0.5}
                      unit="dB"
                      onChange={(music_db) => edit({ levels: { ...draft.levels, music_db } }, true)}
                      hint={levelHint("music_db")}
                    />
                    <SliderField
                      label="Baisse pendant que la voix parle"
                      value={draft.levels.duck_db}
                      min={0}
                      max={15}
                      step={0.5}
                      unit="dB"
                      onChange={(duck_db) => edit({ levels: { ...draft.levels, duck_db } }, true)}
                      hint={levelHint("duck_db")}
                    />
                  </>
                ) : (
                  <>
                    <SliderField
                      label="Musique"
                      value={draft.levels.solo_db}
                      min={-20}
                      max={12}
                      step={0.5}
                      unit="dB"
                      onChange={(solo_db) => edit({ levels: { ...draft.levels, solo_db } }, true)}
                      hint={levelHint("solo_db")}
                    />
                    <SliderField
                      label="Bruitages"
                      value={draft.levels.sfx_db}
                      min={-20}
                      max={12}
                      step={0.5}
                      unit="dB"
                      onChange={(sfx_db) => edit({ levels: { ...draft.levels, sfx_db } }, true)}
                      hint={levelHint("sfx_db")}
                    />
                  </>
                )}
              </fieldset>
              <p className="text-muted-foreground text-[11px] leading-snug">
                Pour cette vidéo seulement ; le modèle de montage garde ses niveaux. « Nouveau mixage », sous la vidéo, fait entendre ces réglages pendant la
                lecture. Le son final est toujours ramené au niveau des Shorts (−14 LUFS) : ces curseurs règlent l’équilibre, pas le volume.
              </p>
            </section>
          </TabsContent>

          <TabsContent value="voix" className="flex flex-col gap-4">
            {d.video.voiced ? (
              <>
                <p className="text-sm">
                  Voix actuelle : <span className="font-medium">{voiceLabel(d.voice.current)}</span>
                </p>
                <fieldset disabled={locked}>
                  <VoicePicker lang={d.video.lang} label="Voix de cette vidéo" entries={d.voice.entries} value={draft.voice} onChange={(voice) => edit({ voice })} sample={d.voice.sample} />
                </fieldset>
                {voiceChanged ? (
                  <p className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-xs leading-relaxed">
                    « Refaire la vidéo » fera dire la narration par {voiceLabel(draft.voice)}, puis remontera la vidéo : la durée des scènes suit la nouvelle voix et tes
                    sous-titres retouchés sont recalés dessus. La voix passe sur la carte graphique après la tâche en cours.
                  </p>
                ) : null}
                <p className="text-muted-foreground text-[11px] leading-snug">
                  « Écouter » fait dire la phrase d’essai (une phrase de cette vidéo) par la voix choisie. La voix par défaut des prochaines vidéos se règle dans
                  Réglages.
                </p>
              </>
            ) : (
              <p className="text-muted-foreground text-sm">Pas de voix sur cette vidéo : les chantiers et les visites n’ont que la musique et les bruitages.</p>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
