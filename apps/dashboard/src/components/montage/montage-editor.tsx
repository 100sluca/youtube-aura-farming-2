"use client";

/**
 * Onglet Montage (docs/23-montage.md) : l'éditeur du modèle de montage. À gauche, l'aperçu 9:16 (on y déplace les
 * éléments) avec son fond, le format montré et le rendu exact par le worker ; à droite, les réglages de chaque couche,
 * le son (niveaux du modèle et bibliothèque de musiques avec écoute, docs/26-musique.md), les textes d'essai et les
 * polices. « Utiliser pour toutes les vidéos » fait de ce modèle celui du montage.
 */
import * as React from "react";
import { useRouter } from "next/navigation";
import {
  CircleCheck,
  CircleX,
  Clapperboard,
  Copy,
  Eye,
  EyeOff,
  FilePlus2,
  LoaderCircle,
  MoreHorizontal,
  Pause,
  Pencil,
  Play,
  RotateCcw,
  Save,
  Star,
  Trash2,
  Upload,
} from "lucide-react";

import {
  deleteMontageTemplate,
  deleteUserFont,
  getMontagePreview,
  renameMontageTemplate,
  requestMontagePreview,
  saveMontageTemplate,
  setDefaultMontageTemplate,
  updateMusicTrack,
} from "@/app/montage/actions";
import { ConfirmButton } from "@/components/confirm-button";
import { AudioPanel, type TrackPatch } from "@/components/montage/audio-panel";
import { HookPanel, SubtitlesPanel, TitlesPanel } from "@/components/montage/layer-panels";
import { MontageFontFaces, MontageStage } from "@/components/montage/montage-stage";
import { SoundTest } from "@/components/montage/sound-test";
import type { LiveMix } from "@/components/montage/use-mix-player";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { mixLevels, speechSegments } from "@/lib/audio-mix";
import { formatDateTime } from "@/lib/format";
import {
  FORMAT_LABELS,
  FORMAT_SHORT,
  LAYER_LABELS,
  MONTAGE_FORMATS,
  type LayerKey,
  type MontageFormat,
  type MontagePageData,
  type MontagePreviewState,
  type MontageTemplate,
  type MontageTemplateRow,
  type MusicTrack,
  type PanelKey,
} from "@/lib/montage-types";
import { cn } from "@/lib/utils";

type Notice = { ok: boolean; message: string } | null;
const ORIGIN_KEY = "__origin__";
const POLL_MS = 1000;
const TRACK_SAVE_MS = 600; // un curseur de piste s'enregistre 0,6 s après le dernier mouvement

/** Réglages d'une piste, noms de l'éditeur → colonnes de music_tracks. */
function trackColumns(patch: TrackPatch): Record<string, unknown> {
  const { gainDb, startS, ...rest } = patch;
  return { ...rest, ...(gainDb !== undefined ? { gain_db: gainDb } : {}), ...(startS !== undefined ? { start_s: startS } : {}) };
}

/** Comparaison indépendante de l'ordre des clés (la base renvoie le JSON dans son propre ordre). */
function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value as Record<string, unknown>)
      .sort()
      .map((k) => `${JSON.stringify(k)}:${stable((value as Record<string, unknown>)[k])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function NoticeLine({ notice }: { notice: Notice }) {
  if (!notice) return null;
  return (
    <p className={cn("flex items-center gap-1.5 text-xs", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")} role="status">
      {notice.ok ? <CircleCheck className="size-3.5 shrink-0" /> : <CircleX className="size-3.5 shrink-0" />}
      {notice.message}
    </p>
  );
}

function NameDialog({
  open,
  onOpenChange,
  title,
  description,
  initial,
  submitLabel,
  withDefault,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  initial: string;
  submitLabel: string;
  withDefault?: boolean;
  onSubmit: (name: string, makeDefault: boolean) => Promise<Notice>;
}) {
  const [name, setName] = React.useState(initial);
  const [makeDefault, setMakeDefault] = React.useState(Boolean(withDefault));
  const [error, setError] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            startTransition(async () => {
              const res = await onSubmit(name, makeDefault);
              if (res?.ok) onOpenChange(false);
              else setError(res?.message ?? "Échec");
            });
          }}
        >
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium">Nom du modèle</span>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex. Ma patte" autoFocus maxLength={60} />
          </label>
          {withDefault !== undefined ? (
            <label className="flex cursor-pointer items-center justify-between gap-3 text-sm">
              <span>Utiliser pour toutes les vidéos</span>
              <Switch checked={makeDefault} onCheckedChange={setMakeDefault} aria-label="Utiliser pour toutes les vidéos" />
            </label>
          ) : null}
          {error ? <p className="text-destructive text-sm">{error}</p> : null}
          <DialogFooter>
            <Button type="submit" disabled={pending || !name.trim()}>
              {pending ? <LoaderCircle className="animate-spin" /> : null}
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function MontageEditor({ data }: { data: MontagePageData }) {
  const router = useRouter();
  const { templates, origin, fonts, backgrounds, presets } = data;
  const defaultRow = templates.find((t) => t.isDefault) ?? null;

  const [currentId, setCurrentId] = React.useState<string>(defaultRow?.id ?? templates[0]?.id ?? ORIGIN_KEY);
  const current: MontageTemplateRow | null = templates.find((t) => t.id === currentId) ?? null;
  const baseline = current?.template ?? origin;
  const [draft, setDraft] = React.useState<MontageTemplate>(baseline);
  const dirty = stable(draft) !== stable(baseline);

  // Le modèle affiché a été enregistré, renommé ou supprimé (nouvelles données du serveur) : on suit. Un modèle tout
  // juste créé n'est pas encore dans la liste (elle arrive avec le rafraîchissement) : on l'attend.
  const [created, setCreated] = React.useState<string | null>(null);
  const [syncedKey, setSyncedKey] = React.useState(`${currentId}|${stable(baseline)}`);
  const key = `${currentId}|${stable(baseline)}`;
  if (key !== syncedKey) {
    setSyncedKey(key);
    if (!templates.some((t) => t.id === currentId) && currentId !== ORIGIN_KEY && currentId !== created) {
      const next = defaultRow?.id ?? templates[0]?.id ?? ORIGIN_KEY;
      setCurrentId(next);
      setDraft(templates.find((t) => t.id === next)?.template ?? origin);
    } else if (!dirty) {
      setDraft(baseline);
    }
  }

  const [format, setFormat] = React.useState<MontageFormat>(() => (draft.hook.formats[0] as MontageFormat | undefined) ?? "timelapse");
  const [panel, setPanel] = React.useState<PanelKey>("hook");
  const layer: LayerKey | null = panel === "audio" ? null : panel;
  const [texts, setTexts] = React.useState(data.samples);
  const [playing, setPlaying] = React.useState(true);
  const [showSafe, setShowSafe] = React.useState(false);
  const [bgId, setBgId] = React.useState<string | null>(() => backgrounds.find((b) => b.format === format)?.assetId ?? backgrounds[0]?.assetId ?? null);
  const [bgManual, setBgManual] = React.useState(false);
  const background = backgrounds.find((b) => b.assetId === bgId) ?? null;
  const [notice, setNotice] = React.useState<Notice>(null);
  const [pending, startTransition] = React.useTransition();
  const [dialog, setDialog] = React.useState<"create" | "copy" | "rename" | null>(null);
  const [stageW, setStageW] = React.useState(360);
  const [exact, setExact] = React.useState<{ jobId: string; state: MontagePreviewState; slow: boolean; of: string } | null>(null);
  const alive = React.useRef(true);

  React.useEffect(() => {
    alive.current = true;
    const fit = () => setStageW(Math.max(240, Math.min(380, window.innerWidth - 48)));
    fit();
    window.addEventListener("resize", fit);
    return () => {
      alive.current = false;
      window.removeEventListener("resize", fit);
    };
  }, []);

  React.useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // Ctrl+S : enregistrer (comme l'éditeur de prompts de l'onglet Agents)
  const saveRef = React.useRef<() => void>(() => undefined);
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        saveRef.current();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const patch = <K extends PanelKey>(key: K, value: Partial<MontageTemplate[K]>) => setDraft((d) => ({ ...d, [key]: { ...d[key], ...value } }));

  // ---- Son : musiques de la bibliothèque (enregistrées aussitôt, pour tous les modèles) et écoute ----
  const music = data.music;
  const [tracks, setTracks] = React.useState<MusicTrack[]>(music.tracks);
  const [testVideoId, setTestVideoId] = React.useState<string | null>(music.videos[0]?.videoId ?? null);
  const testVideo = music.videos.find((v) => v.videoId === testVideoId) ?? null;
  const [trackId, setTrackId] = React.useState<string | null>(
    () =>
      music.videos[0]?.autoTrack ??
      music.tracks.find((t) => t.enabled && !t.missing && t.formats.length)?.id ??
      music.tracks[0]?.id ??
      null,
  );
  const pendingTracks = React.useRef(new Map<string, { patch: Record<string, unknown>; timer: ReturnType<typeof setTimeout> }>());

  const flushTrack = React.useCallback(async (id: string) => {
    const pending = pendingTracks.current.get(id);
    if (!pending) return;
    clearTimeout(pending.timer);
    pendingTracks.current.delete(id);
    const res = await updateMusicTrack(id, pending.patch);
    if (!res.ok && alive.current) setNotice(res);
  }, []);

  const updateTrack = (id: string, change: TrackPatch, now = false) => {
    setTracks((list) => list.map((t) => (t.id === id ? { ...t, ...change } : t)));
    const before = pendingTracks.current.get(id);
    if (before) clearTimeout(before.timer);
    const patch = { ...(before?.patch ?? {}), ...trackColumns(change) };
    pendingTracks.current.set(id, { patch, timer: setTimeout(() => void flushTrack(id), now ? 0 : TRACK_SAVE_MS) });
  };

  React.useEffect(() => {
    const pending = pendingTracks.current;
    return () => {
      for (const id of [...pending.keys()]) void flushTrack(id); // quitter la page n'oublie pas le dernier réglage
    };
  }, [flushTrack]);

  // Écoute sur la vidéo de test : mêmes niveaux que le montage (lib/audio-mix.ts), relus à chaque image
  const voice = testVideo?.voice ?? null;
  const segments = React.useMemo(() => (voice ? speechSegments(voice.words, music.constants.duck_merge_gap_s) : []), [voice, music.constants]);
  const liveFor = (): LiveMix | null => {
    if (!testVideo) return null;
    const t = tracks.find((x) => x.id === trackId) ?? null;
    const c = music.constants;
    const withVoice = Boolean(voice);
    const levels = mixLevels(draft.audio, c, { withVoice, trackLufs: t?.lufs ?? null, trackGainDb: t?.gainDb ?? 0, narrationLufs: voice?.lufs ?? null });
    return {
      musicGainDb: t && draft.audio.formats.includes(testVideo.format) ? levels.musicGainDb : null,
      voiceGainDb: levels.voiceGainDb,
      duckDb: levels.duckDb,
      masterDb: c.output_lufs - (withVoice ? c.voice_ref_lufs : c.solo_ref_lufs),
      segments,
      attackS: c.duck_attack_s,
      releaseS: c.duck_release_s,
      fadeInS: c.fade_in_s,
      fadeOutS: c.fade_out_s,
      totalS: testVideo.durationS,
    };
  };

  const chooseFormat = (f: MontageFormat) => {
    setFormat(f);
    if (!bgManual) {
      const bg = backgrounds.find((b) => b.format === f);
      if (bg) setBgId(bg.assetId);
    }
  };

  const selectLayer = (l: LayerKey | null) => {
    if (!l) return;
    setPanel(l);
  };

  const switchTemplate = (id: string) => {
    if (id === currentId) return;
    if (dirty && !window.confirm("Perdre les modifications non enregistrées de ce modèle ?")) return;
    setCurrentId(id);
    setDraft(templates.find((t) => t.id === id)?.template ?? origin);
    setNotice(null);
  };

  const run = (fn: () => Promise<Notice>) =>
    startTransition(async () => {
      const res = await fn();
      setNotice(res);
      if (res?.ok) router.refresh();
    });

  const save = () => {
    if (pending) return;
    if (!current) {
      setDialog("create");
      return;
    }
    if (!dirty) return;
    run(() => saveMontageTemplate({ id: current.id, name: current.name, template: draft }));
  };
  React.useEffect(() => {
    saveRef.current = save;
  });

  const useForAll = () => {
    if (!current) {
      setDialog("create");
      return;
    }
    run(() =>
      dirty
        ? saveMontageTemplate({ id: current.id, name: current.name, template: draft, makeDefault: true })
        : setDefaultMontageTemplate(current.id),
    );
  };

  const createAs = async (name: string, makeDefault: boolean): Promise<Notice> => {
    const res = await saveMontageTemplate({ id: null, name, template: draft, makeDefault });
    if (res.ok && res.id) {
      setCreated(res.id);
      setCurrentId(res.id);
      setNotice(res);
      router.refresh();
    }
    return res;
  };

  // ---- Rendu exact (job montage_preview du worker) ----
  const requestExact = async () => {
    setExact(null);
    const res = await requestMontagePreview({ template: draft, recipe: format, assetId: background?.assetId ?? null, texts: texts[format] });
    if (!res.ok || !res.jobId) {
      setNotice(res);
      return;
    }
    const since = Date.now();
    const of = `${format}|${background?.assetId ?? ""}|${stable(draft)}|${stable(texts[format])}`;
    let state: MontagePreviewState = { status: "queued", label: null, error: null, videoUrl: null, posterUrl: null, elapsedS: null };
    setExact({ jobId: res.jobId, state, slow: false, of });
    while (alive.current && (state.status === "queued" || state.status === "running")) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      state = await getMontagePreview(res.jobId);
      if (!alive.current) return;
      setExact({ jobId: res.jobId, state, slow: Date.now() - since > 20_000, of });
    }
  };
  const exactBusy = exact !== null && (exact.state.status === "queued" || exact.state.status === "running");

  const uploadFont = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/fonts", { method: "POST", body: form });
    const body = (await res.json().catch(() => ({ ok: false, message: "Envoi impossible" }))) as { ok: boolean; message: string };
    setNotice(body);
    if (body.ok) router.refresh();
  };
  const userFonts = fonts.filter((f) => f.source === "user");
  const usedFamilies = new Set([draft.hook.font_family, draft.subtitles.font_family, draft.titles.font_family]);

  const shownOn = (l: LayerKey) =>
    l === "subtitles"
      ? draft.subtitles.enabled
        ? "Récits"
        : "Masqués"
      : draft[l].formats.length
        ? draft[l].formats.map((f) => FORMAT_SHORT[f]).join(", ")
        : "Nulle part";

  return (
    <div className="grid gap-6 lg:grid-cols-[auto_minmax(0,1fr)]">
      <MontageFontFaces faces={fonts} />

      {/* ---------------- Aperçu (onglet Son : la vidéo de test avec sa voix et la musique) ---------------- */}
      <div className="flex flex-col items-center gap-3 self-start lg:sticky lg:top-4" style={{ width: stageW }}>
        {panel === "audio" ? (
          <SoundTest
            videos={music.videos}
            video={testVideo}
            onVideoChange={setTestVideoId}
            track={tracks.find((t) => t.id === trackId) ?? null}
            template={draft}
            liveFor={liveFor}
            mock={data.mock}
          />
        ) : (
          <>
        <div role="radiogroup" aria-label="Format montré" className="bg-muted inline-flex w-full gap-0.5 rounded-lg p-0.5">
          {MONTAGE_FORMATS.map((f) => (
            <button
              key={f}
              type="button"
              role="radio"
              aria-checked={format === f}
              onClick={() => chooseFormat(f)}
              className={cn(
                "flex-1 rounded-md px-2 py-1.5 text-xs font-medium transition-colors",
                format === f ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {FORMAT_LABELS[f]}
            </button>
          ))}
        </div>

        <MontageStage
          template={draft}
          format={format}
          faces={fonts}
          background={background}
          texts={texts[format]}
          selected={layer}
          onSelect={selectLayer}
          onMove={(l, pos) => patch(l, pos)}
          playing={playing}
          showSafe={showSafe}
          width={stageW}
        />

        <div className="flex w-full flex-wrap items-center gap-1.5">
          <Button size="sm" variant="outline" onClick={() => setPlaying((p) => !p)} aria-pressed={playing}>
            {playing ? <Pause /> : <Play />}
            {playing ? "Pause" : "Lecture"}
          </Button>
          <Button size="sm" variant={showSafe ? "secondary" : "outline"} onClick={() => setShowSafe((s) => !s)} aria-pressed={showSafe}>
            {showSafe ? <EyeOff /> : <Eye />}
            Zones YouTube
          </Button>
          <Button size="sm" className="ml-auto" onClick={() => void requestExact()} disabled={exactBusy || data.mock}>
            {exactBusy ? <LoaderCircle className="animate-spin" /> : <Clapperboard />}
            Rendu exact
          </Button>
        </div>
        <p className="text-muted-foreground w-full text-[11px] leading-snug">
          Clique un élément pour le régler, fais-le glisser pour le placer (flèches du clavier : 1 px, Maj : 10 px). « Rendu exact » monte 5 s avec le vrai
          moteur du montage.
        </p>

        {exact ? (
          <div className="flex w-full flex-col gap-2 rounded-lg border p-2">
            {exact.state.status === "done" && exact.state.videoUrl ? (
              <>
                <video
                  key={exact.jobId}
                  src={exact.state.videoUrl}
                  poster={exact.state.posterUrl ?? undefined}
                  className="aspect-[9/16] w-full rounded-md bg-black"
                  controls
                  autoPlay
                  loop
                  muted
                  playsInline
                />
                <p className="text-muted-foreground text-[11px]">
                  Rendu FFmpeg du worker (5 s{exact.state.elapsedS ? `, fait en ${exact.state.elapsedS.toLocaleString("fr-FR")} s` : ""}) : exactement ce que
                  donnera le montage.
                </p>
                {exact.of !== `${format}|${background?.assetId ?? ""}|${stable(draft)}|${stable(texts[format])}` ? (
                  <p className="text-[11px] text-amber-600 dark:text-amber-400">Réglages changés depuis ce rendu : relance « Rendu exact » pour voir les nouveaux.</p>
                ) : null}
              </>
            ) : exact.state.status === "queued" || exact.state.status === "running" ? (
              <p className="text-muted-foreground flex items-center gap-2 text-xs">
                <LoaderCircle className="size-3.5 animate-spin" />
                {exact.state.status === "queued"
                  ? exact.slow
                    ? "Toujours en file : le worker est-il lancé (fenêtre « Worker - YouTube 2.0 ») ?"
                    : "En file…"
                  : (exact.state.label ?? "Montage de l’aperçu…")}
              </p>
            ) : (
              <p className="text-destructive text-xs">{exact.state.error ?? "Rendu interrompu"}</p>
            )}
          </div>
        ) : null}

        {backgrounds.length ? (
          <div className="flex w-full flex-col gap-1.5">
            <span className="text-muted-foreground text-xs font-medium">Fond de l’aperçu</span>
            <div className="flex w-full gap-1.5 overflow-x-auto pb-1">
              {backgrounds.map((b) => (
                <button
                  key={b.assetId}
                  type="button"
                  title={`${FORMAT_SHORT[b.format]} · ${b.label}`}
                  onClick={() => {
                    setBgId(b.assetId);
                    setBgManual(true);
                  }}
                  className={cn(
                    "relative h-16 w-9 shrink-0 overflow-hidden rounded-md border-2 bg-black",
                    b.assetId === bgId ? "border-sky-400" : "border-transparent opacity-80 hover:opacity-100",
                  )}
                >
                  {b.kind === "clip" ? (
                    <video src={`${b.url}#t=0.5`} className="size-full object-cover" muted preload="metadata" playsInline />
                  ) : (
                    // eslint-disable-next-line @next/next/no-img-element -- fichier local servi par /api/media
                    <img src={b.url} alt="" className="size-full object-cover" loading="lazy" />
                  )}
                </button>
              ))}
              <button
                type="button"
                title="Dégradé neutre"
                onClick={() => {
                  setBgId(null);
                  setBgManual(true);
                }}
                className={cn("h-16 w-9 shrink-0 rounded-md border-2", bgId === null ? "border-sky-400" : "border-transparent")}
                style={{ background: "linear-gradient(160deg, #2B3A55, #C9A66B)" }}
              />
            </div>
            {background ? <span className="text-muted-foreground truncate text-[11px]">{`${FORMAT_SHORT[background.format]} · ${background.label}`}</span> : null}
          </div>
        ) : null}
          </>
        )}
      </div>

      {/* ---------------- Réglages ---------------- */}
      <div className="flex min-w-0 flex-col gap-4">
        <Card className="gap-3">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">
              Modèle
              {!current && currentId === created ? (
                <Badge variant="outline" className="text-muted-foreground">
                  <LoaderCircle className="size-3 animate-spin" />
                  Enregistrement…
                </Badge>
              ) : current?.isDefault || (!current && !defaultRow) ? (
                <Badge className="bg-emerald-600 text-white dark:bg-emerald-500">
                  <Star className="size-3" />
                  Utilisé pour toutes les vidéos
                </Badge>
              ) : (
                <Badge variant="outline" className="text-muted-foreground">
                  Pas utilisé pour l’instant
                </Badge>
              )}
              {dirty && !(currentId === created && !current) ? (
                <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-300">
                  Modifié, non enregistré
                </Badge>
              ) : null}
            </CardTitle>
            <CardDescription>
              {current
                ? `Enregistré le ${formatDateTime(current.updatedAt)}. `
                : "Aucun modèle enregistré : le montage suit le modèle d’origine (le rendu actuel). "}
              Le modèle utilisé sert à tous les montages suivants ; les vidéos déjà montées gardent le leur (« Refaire le montage » dans leur fiche).
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Select value={currentId} onValueChange={switchTemplate}>
                <SelectTrigger className="h-9 min-w-56" aria-label="Modèle affiché">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {templates.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.name}
                      {t.isDefault ? " ★" : ""}
                    </SelectItem>
                  ))}
                  {!templates.length || currentId === ORIGIN_KEY ? <SelectItem value={ORIGIN_KEY}>Modèle d’origine (non enregistré)</SelectItem> : null}
                </SelectContent>
              </Select>
              <Button size="sm" onClick={save} disabled={pending || (!dirty && Boolean(current))}>
                {pending ? <LoaderCircle className="animate-spin" /> : <Save />}
                {current ? "Enregistrer" : "Enregistrer comme mon modèle"}
              </Button>
              {current && !current.isDefault ? (
                <Button size="sm" variant="outline" onClick={useForAll} disabled={pending}>
                  <Star />
                  Utiliser pour toutes les vidéos
                </Button>
              ) : null}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="icon" variant="ghost" className="size-8" aria-label="Autres actions sur le modèle">
                    <MoreHorizontal />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={() => setDialog("copy")}>
                    <Copy />
                    Enregistrer sous un autre nom
                  </DropdownMenuItem>
                  {current ? (
                    <DropdownMenuItem onSelect={() => setDialog("rename")}>
                      <Pencil />
                      Renommer
                    </DropdownMenuItem>
                  ) : null}
                  <DropdownMenuItem
                    onSelect={() => {
                      setDraft(origin);
                      setNotice({ ok: true, message: "Réglages d’origine chargés dans l’éditeur : enregistre pour les garder." });
                    }}
                  >
                    <RotateCcw />
                    Repartir des réglages d’origine
                  </DropdownMenuItem>
                  {dirty ? (
                    <DropdownMenuItem onSelect={() => setDraft(baseline)}>
                      <RotateCcw />
                      Annuler les modifications
                    </DropdownMenuItem>
                  ) : null}
                  {current ? (
                    <>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        variant="destructive"
                        onSelect={() => {
                          if (window.confirm(`Supprimer le modèle « ${current.name} » ?`)) run(() => deleteMontageTemplate(current.id));
                        }}
                      >
                        <Trash2 />
                        Supprimer ce modèle
                      </DropdownMenuItem>
                    </>
                  ) : null}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
            <NoticeLine notice={notice} />
          </CardContent>
        </Card>

        <Card className="gap-3">
          <CardContent>
            <Tabs value={panel} onValueChange={(v) => setPanel(v as PanelKey)} className="gap-4">
              <TabsList className="h-auto w-full flex-wrap">
                {(["hook", "subtitles", "titles"] as LayerKey[]).map((l) => (
                  <TabsTrigger key={l} value={l} className="flex-col gap-0 py-1.5">
                    <span>{LAYER_LABELS[l]}</span>
                    <span className="text-muted-foreground text-[10px] font-normal">{shownOn(l)}</span>
                  </TabsTrigger>
                ))}
                <TabsTrigger value="audio" className="flex-col gap-0 py-1.5">
                  <span>Son</span>
                  <span className="text-muted-foreground text-[10px] font-normal">
                    Voix et musiques
                    {tracks.some((t) => !t.missing && !t.formats.length) ? " · à décrire" : ""}
                  </span>
                </TabsTrigger>
              </TabsList>
              {layer === null ? null : layer !== "subtitles" && !draft[layer].formats.includes(format) ? (
                <p className="rounded-md border border-dashed p-2 text-xs">
                  Pas affiché sur les {FORMAT_LABELS[format].toLowerCase()} : l’aperçu le montre en transparence pour pouvoir le placer.
                </p>
              ) : layer === "subtitles" && format !== "story" ? (
                <p className="rounded-md border border-dashed p-2 text-xs">
                  Les sous-titres n’existent que sur les récits narrés.{" "}
                  <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={() => chooseFormat("story")}>
                    Voir un récit
                  </Button>
                </p>
              ) : null}
              <TabsContent value="hook">
                <HookPanel value={draft.hook} onChange={(p) => patch("hook", p)} faces={fonts} />
              </TabsContent>
              <TabsContent value="subtitles">
                <SubtitlesPanel value={draft.subtitles} onChange={(p) => patch("subtitles", p)} faces={fonts} presets={presets} />
              </TabsContent>
              <TabsContent value="titles">
                <TitlesPanel value={draft.titles} onChange={(p) => patch("titles", p)} faces={fonts} />
              </TabsContent>
              <TabsContent value="audio">
                <AudioPanel
                  value={draft.audio}
                  onChange={(p) => patch("audio", p)}
                  library={music}
                  tracks={tracks}
                  trackId={trackId}
                  onTrackSelect={setTrackId}
                  onTrackChange={updateTrack}
                  video={testVideo}
                  mock={data.mock}
                />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        <Card className="gap-3">
          <CardHeader>
            <CardTitle className="text-base">Textes d’essai · {FORMAT_LABELS[format].toLowerCase()}</CardTitle>
            <CardDescription>Pris dans tes dernières productions ; seulement pour l’aperçu, jamais enregistrés dans le modèle.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5 text-xs font-medium">
              <span className="text-muted-foreground">Titre d’accroche</span>
              <Input value={texts[format].hook} onChange={(e) => setTexts((t) => ({ ...t, [format]: { ...t[format], hook: e.target.value } }))} />
            </label>
            <label className="flex flex-col gap-1.5 text-xs font-medium">
              <span className="text-muted-foreground">{format === "timelapse" ? "Compteur" : "Texte à l’écran"}</span>
              <Input value={texts[format].title} onChange={(e) => setTexts((t) => ({ ...t, [format]: { ...t[format], title: e.target.value } }))} />
            </label>
            {format === "story" ? (
              <label className="flex flex-col gap-1.5 text-xs font-medium sm:col-span-2">
                <span className="text-muted-foreground">Phrase de la voix (sous-titres)</span>
                <Input value={texts.story.subtitle} onChange={(e) => setTexts((t) => ({ ...t, story: { ...t.story, subtitle: e.target.value } }))} />
              </label>
            ) : null}
          </CardContent>
        </Card>

        <Card className="gap-3">
          <CardHeader>
            <CardTitle className="text-base">Polices</CardTitle>
            <CardDescription>
              {fonts.length} polices disponibles (livrées, les tiennes, Windows). Ajoute un fichier .ttf ou .otf, par exemple une police gratuite de{" "}
              <a className="underline underline-offset-2" href="https://fonts.google.com" target="_blank" rel="noreferrer">
                Google Fonts
              </a>{" "}
              (licence libre, utilisable sur YouTube) : elle apparaît dans les listes et sert au montage.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <label className={cn("inline-flex w-fit", data.mock && "pointer-events-none opacity-50")}>
              <input
                type="file"
                accept=".ttf,.otf,font/ttf,font/otf"
                className="sr-only"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void uploadFont(file);
                  e.target.value = "";
                }}
              />
              <span className="border-input hover:bg-accent inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border px-3 text-sm font-medium shadow-xs">
                <Upload className="size-4" />
                Ajouter une police
              </span>
            </label>
            {userFonts.length ? (
              <ul className="flex flex-col divide-y rounded-md border">
                {userFonts.map((f) => (
                  <li key={f.id} className="flex items-center justify-between gap-2 px-3 py-2">
                    <span className="min-w-0 truncate text-base" style={{ fontFamily: `"yt2a-${f.id.replace(/[^A-Za-z0-9_-]/g, "_")}"` }}>
                      {f.fullName}
                    </span>
                    <span className="text-muted-foreground shrink-0 text-xs">{usedFamilies.has(f.family) ? "utilisée" : f.file}</span>
                    <ConfirmButton
                      size="sm"
                      variant="ghost"
                      confirmLabel="Retirer ?"
                      onConfirm={() => run(() => deleteUserFont(f.id))}
                      aria-label={`Retirer ${f.fullName}`}
                    >
                      <Trash2 />
                    </ConfirmButton>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
                <FilePlus2 className="size-3.5" /> Aucune police ajoutée pour l’instant.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <NameDialog
        key={`create-${dialog}`}
        open={dialog === "create" || dialog === "copy"}
        onOpenChange={(open) => !open && setDialog(null)}
        title={dialog === "copy" ? "Enregistrer sous un autre nom" : "Enregistrer mon modèle"}
        description={
          dialog === "copy"
            ? "Une copie des réglages affichés, sous un nouveau nom."
            : "Tes réglages deviennent un modèle ; tu pourras en garder plusieurs et choisir celui des vidéos."
        }
        initial={dialog === "copy" && current ? `${current.name} (copie)` : "Ma patte"}
        submitLabel="Enregistrer"
        withDefault={dialog === "create" ? !defaultRow : false}
        onSubmit={createAs}
      />
      {current ? (
        <NameDialog
          key={`rename-${current.id}-${dialog}`}
          open={dialog === "rename"}
          onOpenChange={(open) => !open && setDialog(null)}
          title="Renommer le modèle"
          description="Le nom sert seulement à t’y retrouver."
          initial={current.name}
          submitLabel="Renommer"
          onSubmit={async (name) => {
            const res = await renameMontageTemplate(current.id, name);
            setNotice(res);
            if (res.ok) router.refresh();
            return res;
          }}
        />
      ) : null}
    </div>
  );
}
