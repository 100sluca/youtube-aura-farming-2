"use client";

/**
 * Essai du son (onglet Montage → Son, docs/26-musique.md), à la place de l'aperçu 9:16 : une vidéo déjà montée, jouée
 * avec sa voix et la musique choisie, mixées aux réglages en cours (curseurs actifs pendant la lecture : use-mix-player),
 * « Son d'origine » pour comparer avec son dernier montage, et « Rendu exact avec le son » : le worker refait le son de
 * la vraie vidéo avec le code du montage (bruitages compris).
 */
import * as React from "react";
import { AudioLines, CircleX, Clapperboard, LoaderCircle } from "lucide-react";

import { getMontagePreview, requestSoundPreview } from "@/app/montage/actions";
import { useVideoMix, type LiveMix } from "@/components/montage/use-mix-player";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatDuration, musicStart } from "@/lib/audio-mix";
import { FORMAT_LABELS, FORMAT_SHORT, type MontagePreviewState, type MontageTemplate, type MusicTrack, type TestVideo } from "@/lib/montage-types";
import { cn } from "@/lib/utils";

const POLL_MS = 1000;

export function SoundTest({
  videos,
  video,
  onVideoChange,
  track,
  template,
  liveFor,
  mock,
}: {
  videos: TestVideo[];
  video: TestVideo | null;
  onVideoChange: (id: string) => void;
  track: MusicTrack | null;
  template: MontageTemplate;
  liveFor: () => LiveMix | null;
  mock: boolean;
}) {
  const [el, setEl] = React.useState<HTMLVideoElement | null>(null);
  const [original, setOriginal] = React.useState(false);
  const [exact, setExact] = React.useState<{ jobId: string; state: MontagePreviewState; slow: boolean; of: string } | null>(null);
  const exactRef = React.useRef<HTMLVideoElement | null>(null);
  const alive = React.useRef(true);
  React.useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const musicOn = Boolean(video && template.audio.formats.includes(video.format));
  const music = musicOn && track && !track.missing ? track : null;
  const mix = useVideoMix({
    video: el,
    voiceUrl: video?.voice?.url ?? null,
    musicUrl: music?.url ?? null,
    musicStartS: music ? musicStart(music.startS, music.durationS, video?.durationS ?? 0) : 0,
    musicDurationS: music?.durationS ?? null,
    original,
    liveFor,
  });

  const signature = `${video?.videoId}|${music?.id}|${music?.gainDb}|${music?.startS}|${JSON.stringify(template.audio)}`;
  const requestExact = async () => {
    if (!video) return;
    el?.pause();
    setExact(null);
    const res = await requestSoundPreview({ template, videoId: video.videoId, trackId: music?.id ?? null, gainDb: music?.gainDb ?? 0, startS: music?.startS ?? 0 });
    const since = Date.now();
    let state: MontagePreviewState = { status: "queued", label: null, error: res.ok ? null : res.message, videoUrl: null, posterUrl: null, elapsedS: null };
    if (!res.ok || !res.jobId) {
      setExact({ jobId: "", state: { ...state, status: "failed" }, slow: false, of: signature });
      return;
    }
    setExact({ jobId: res.jobId, state, slow: false, of: signature });
    while (alive.current && (state.status === "queued" || state.status === "running")) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      state = await getMontagePreview(res.jobId);
      if (!alive.current) return;
      setExact({ jobId: res.jobId, state, slow: Date.now() - since > 20_000, of: signature });
    }
  };
  const exactBusy = exact !== null && (exact.state.status === "queued" || exact.state.status === "running");

  if (!videos.length) {
    return (
      <p className="text-muted-foreground w-full rounded-lg border border-dashed p-4 text-center text-xs">
        Aucune vidéo montée pour l’instant : l’essai du son arrivera avec la première vidéo.
      </p>
    );
  }

  return (
    <div className="flex w-full flex-col gap-3">
      <label className="flex w-full flex-col gap-1.5">
        <span className="text-muted-foreground text-xs font-medium">Vidéo de test</span>
        <Select value={video?.videoId} onValueChange={onVideoChange}>
          <SelectTrigger className="h-9 w-full" aria-label="Vidéo de test">
            <SelectValue placeholder="Choisir une vidéo" />
          </SelectTrigger>
          <SelectContent className="max-h-80">
            {videos.map((v) => (
              <SelectItem key={v.videoId} value={v.videoId}>
                <span className="truncate">{v.title}</span>
                <span className="text-muted-foreground text-xs">
                  {" "}
                  · {FORMAT_SHORT[v.format]} · {formatDuration(v.durationS)}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      {video ? (
        <video
          key={video.videoId}
          ref={setEl}
          src={video.videoUrl}
          poster={video.posterUrl ?? undefined}
          className="aspect-[9/16] w-full rounded-lg bg-black"
          controls
          muted
          playsInline
          preload="auto"
          onPlay={() => exactRef.current?.pause()}
          // le haut-parleur de la vidéo sert d'interrupteur : son coupé = nouveau mixage, son remis = son d'origine
          onVolumeChange={(e) => setOriginal(!e.currentTarget.muted)}
        />
      ) : null}

      <div className="flex w-full flex-wrap items-center gap-1.5">
        <div role="radiogroup" aria-label="Son de la lecture" className="bg-muted inline-flex gap-0.5 rounded-lg p-0.5">
          {[
            { value: false, label: "Nouveau mixage", title: "Voix et musique choisie, aux réglages en cours" },
            { value: true, label: "Son d’origine", title: "Le son du dernier montage de cette vidéo, pour comparer" },
          ].map((o) => (
            <button
              key={o.label}
              type="button"
              role="radio"
              aria-checked={original === o.value}
              title={o.title}
              onClick={() => setOriginal(o.value)}
              className={cn(
                "rounded-md px-2 py-1 text-xs font-medium transition-colors",
                original === o.value ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {o.label}
            </button>
          ))}
        </div>
        <Button
          size="sm"
          className="ml-auto"
          onClick={() => void requestExact()}
          disabled={exactBusy || mock || !video?.hasFinal}
          title={video?.hasFinal ? "Le worker refait le son de la vraie vidéo avec le code du montage" : "Fichier final absent pour cette vidéo"}
        >
          {exactBusy ? <LoaderCircle className="animate-spin" /> : <Clapperboard />}
          Rendu exact avec le son
        </Button>
      </div>

      <div className="text-muted-foreground flex w-full flex-col gap-1 text-[11px] leading-snug">
        {mix.error ? (
          <p className="text-destructive flex items-center gap-1.5">
            <CircleX className="size-3.5 shrink-0" />
            {mix.error}
          </p>
        ) : null}
        {original ? (
          <p>Son d’origine : ce que la vidéo a aujourd’hui (son dernier montage).</p>
        ) : !musicOn && video ? (
          <p className="text-amber-700 dark:text-amber-300">
            Le modèle ne met pas de musique sur les {FORMAT_LABELS[video.format].toLowerCase()} (Son → Musique de fond sur).
          </p>
        ) : (
          <p className="flex items-start gap-1.5">
            <AudioLines className="mt-px size-3.5 shrink-0" />
            <span>
              ▶ joue la vidéo {video?.voice ? "avec sa voix et " : "avec "}
              {music ? `« ${music.title} »` : "sans musique"}, aux réglages en cours : bouge les curseurs pendant la lecture.
            </span>
          </p>
        )}
        {video && !video.voice && video.format !== "story" && !original ? (
          <p>Sans les bruitages dans cette écoute : « Rendu exact avec le son » les ajoute, comme au montage.</p>
        ) : null}
      </div>

      {exact ? (
        <div className="flex w-full flex-col gap-2 rounded-lg border p-2">
          {exact.state.status === "done" && exact.state.videoUrl ? (
            <>
              <video
                ref={exactRef}
                key={exact.jobId}
                src={exact.state.videoUrl}
                poster={exact.state.posterUrl ?? undefined}
                className="aspect-[9/16] w-full rounded-md bg-black"
                controls
                playsInline
                onPlay={() => el?.pause()}
              />
              <p className="text-muted-foreground text-[11px]">
                Son refait par le worker avec le code du montage{exact.state.elapsedS ? ` (en ${exact.state.elapsedS.toLocaleString("fr-FR")} s)` : ""} :
                exactement ce que donnera la vidéo.
              </p>
              {exact.of !== signature ? (
                <p className="text-[11px] text-amber-600 dark:text-amber-400">Réglages changés depuis ce rendu : relance « Rendu exact avec le son ».</p>
              ) : null}
            </>
          ) : exact.state.status === "queued" || exact.state.status === "running" ? (
            <p className="text-muted-foreground flex items-center gap-2 text-xs">
              <LoaderCircle className="size-3.5 animate-spin" />
              {exact.state.status === "queued"
                ? exact.slow
                  ? "Toujours en file : le worker est-il lancé (fenêtre « Worker - YouTube 2.0 ») ?"
                  : "En file…"
                : (exact.state.label ?? "Mixage…")}
            </p>
          ) : (
            <p className="text-destructive text-xs">{exact.state.error ?? "Rendu interrompu"}</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
