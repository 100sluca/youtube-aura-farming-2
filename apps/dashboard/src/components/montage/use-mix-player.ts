"use client";

/**
 * Écoute du mixage sur une vraie vidéo (onglet Montage → Son, docs/26-musique.md) : l'image d'une vidéo déjà montée
 * (muette), sa voix et la musique choisie, mixées dans le navigateur aux réglages en cours (même calcul que le montage :
 * lib/audio-mix.ts), relus à chaque image : bouger un curseur pendant la lecture s'entend aussitôt. La vidéo mène :
 * lecture, pause et déplacement dans sa barre entraînent la voix et la musique. « Son d'origine » rend à la vidéo le
 * son de son dernier montage, pour comparer.
 */
import * as React from "react";

import { dbToGain, duckAmount } from "@/lib/audio-mix";

/** Réglages relus à chaque image pendant la lecture. */
export interface LiveMix {
  musicGainDb: number | null; // null : pas de musique sur ce format
  voiceGainDb: number;
  duckDb: number;
  masterDb: number; // ramène l'écoute vers le niveau final (−14 LUFS), comme loudnorm au montage
  segments: [number, number][];
  attackS: number;
  releaseS: number;
  fadeInS: number;
  fadeOutS: number;
  totalS: number;
}

export interface VideoMixOptions {
  video: HTMLVideoElement | null;
  voiceUrl: string | null;
  musicUrl: string | null;
  musicStartS: number;
  musicDurationS: number | null;
  original: boolean; // son d'origine de la vidéo au lieu du mixage
  liveFor: () => LiveMix | null;
}

type Graph = {
  ctx: AudioContext;
  voice: HTMLAudioElement;
  music: HTMLAudioElement;
  voiceGain: GainNode;
  musicGain: GainNode;
  master: GainNode;
  starting: Set<HTMLAudioElement>; // lecture demandée, pas encore commencée
};

const SMOOTH_S = 0.012;
const VOICE_DRIFT_S = 0.08; // au-delà, la voix est recalée sur l'image
const MUSIC_DRIFT_S = 0.25;

/** Position de la musique pour l'instant t de la vidéo : départ réglé, puis boucle comme au montage. */
function musicPosition(t: number, start: number, duration: number | null): number {
  const pos = start + t;
  return duration && pos >= duration ? pos % duration : pos;
}

function createGraph(): Graph {
  const ctx = new AudioContext();
  const voice = new Audio();
  const music = new Audio();
  voice.preload = "auto";
  music.preload = "auto";
  music.loop = true; // une piste plus courte que la vidéo repart au début
  const voiceGain = ctx.createGain();
  const musicGain = ctx.createGain();
  const master = ctx.createGain();
  voiceGain.gain.value = 0;
  musicGain.gain.value = 0;
  const limiter = ctx.createDynamicsCompressor(); // garde-fou contre la saturation, comme le plafond de loudnorm
  limiter.threshold.value = -1;
  limiter.knee.value = 0;
  limiter.ratio.value = 20;
  limiter.attack.value = 0.003;
  limiter.release.value = 0.15;
  ctx.createMediaElementSource(voice).connect(voiceGain).connect(master);
  ctx.createMediaElementSource(music).connect(musicGain).connect(master);
  master.connect(limiter).connect(ctx.destination);
  return { ctx, voice, music, voiceGain, musicGain, master, starting: new Set() };
}

function setSource(el: HTMLAudioElement, url: string | null) {
  const wanted = url ? new URL(url, window.location.href).href : "";
  if (el.src === wanted) return;
  el.pause();
  if (url) el.src = url;
  else el.removeAttribute("src");
}

/** Cale la voix et la musique sur l'image (au-delà d'un petit écart, ou toujours si `force`) et les lance ou les arrête
 * comme elle. */
function follow(g: Graph, o: VideoMixOptions, force: boolean, onError: (message: string) => void) {
  const v = o.video;
  if (!v) return;
  const t = v.currentTime;
  const mixing = !v.paused && !v.ended && !o.original;
  if (o.voiceUrl && (force || Math.abs(g.voice.currentTime - t) > VOICE_DRIFT_S)) {
    g.voice.currentTime = Number.isFinite(g.voice.duration) ? Math.min(t, g.voice.duration) : t;
  }
  const musicAt = musicPosition(t, o.musicStartS, o.musicDurationS);
  if (o.musicUrl && (force || Math.abs(g.music.currentTime - musicAt) > MUSIC_DRIFT_S)) g.music.currentTime = musicAt;
  for (const [el, url] of [
    [g.voice, o.voiceUrl],
    [g.music, o.musicUrl],
  ] as const) {
    if (mixing && url && el.paused && !g.starting.has(el)) {
      g.starting.add(el);
      el.play()
        .catch((e: unknown) => onError(`Lecture impossible : ${e instanceof Error ? e.message : String(e)}`))
        .finally(() => g.starting.delete(el));
    } else if ((!mixing || !url) && !el.paused) {
      el.pause();
    }
  }
}

export function useVideoMix(opts: VideoMixOptions): { playing: boolean; error: string | null } {
  const { video, voiceUrl, musicUrl, original } = opts;
  const latest = React.useRef(opts);
  const graph = React.useRef<Graph | null>(null);
  const raf = React.useRef<number | null>(null);
  const tick = React.useRef<() => void>(() => undefined);
  const [playing, setPlaying] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    latest.current = opts;
  });

  // Une image : gains du mixage à l'instant de la vidéo (baisse sous la voix, fondus), puis recalage
  React.useEffect(() => {
    tick.current = () => {
      const g = graph.current;
      const o = latest.current;
      if (!g || !o.video) return;
      const m = o.liveFor();
      const now = g.ctx.currentTime;
      const t = o.video.currentTime;
      if (m && !o.original) {
        const duck = m.duckDb > 0 ? 1 - (1 - dbToGain(-m.duckDb)) * duckAmount(t, m.segments, m.attackS, m.releaseS) : 1;
        const fade = Math.min(1, Math.max(0, t / m.fadeInS), Math.max(0, (m.totalS - t) / m.fadeOutS));
        g.musicGain.gain.setTargetAtTime(m.musicGainDb === null ? 0 : dbToGain(m.musicGainDb) * duck * fade, now, SMOOTH_S);
        g.voiceGain.gain.setTargetAtTime(o.voiceUrl ? dbToGain(m.voiceGainDb) : 0, now, SMOOTH_S);
        g.master.gain.setTargetAtTime(dbToGain(m.masterDb), now, SMOOTH_S);
      } else {
        g.musicGain.gain.setTargetAtTime(0, now, SMOOTH_S);
        g.voiceGain.gain.setTargetAtTime(0, now, SMOOTH_S);
      }
      follow(g, o, false, setError);
      raf.current = requestAnimationFrame(() => tick.current());
    };
  });

  // Nouvelle voix ou nouvelle musique : chargées puis calées sur l'image
  React.useEffect(() => {
    const g = graph.current;
    if (!g) return;
    setSource(g.voice, voiceUrl);
    setSource(g.music, musicUrl);
    const onReady = () => follow(g, latest.current, true, setError);
    g.voice.addEventListener("loadedmetadata", onReady);
    g.music.addEventListener("loadedmetadata", onReady);
    return () => {
      g.voice.removeEventListener("loadedmetadata", onReady);
      g.music.removeEventListener("loadedmetadata", onReady);
    };
  }, [voiceUrl, musicUrl]);

  // Son d'origine ↔ nouveau mixage (l'élément vient de la ref : c'est un objet du navigateur, pas une valeur de React)
  React.useEffect(() => {
    const el = latest.current.video;
    if (!el) return;
    el.muted = !original;
    if (graph.current) follow(graph.current, latest.current, true, setError);
  }, [original, video]);

  // La vidéo mène : lecture, pause, fin, déplacement
  React.useEffect(() => {
    if (!video) return;
    const onPlay = () => {
      graph.current ??= createGraph(); // après un clic de l'utilisateur : le navigateur autorise le son
      const g = graph.current;
      setSource(g.voice, latest.current.voiceUrl);
      setSource(g.music, latest.current.musicUrl);
      setError(null);
      void g.ctx.resume();
      setPlaying(true);
      follow(g, latest.current, true, setError);
      if (raf.current === null) raf.current = requestAnimationFrame(() => tick.current());
    };
    const onStop = () => {
      setPlaying(false);
      if (graph.current) follow(graph.current, latest.current, true, setError);
      if (raf.current !== null) cancelAnimationFrame(raf.current);
      raf.current = null;
    };
    const onSeeked = () => {
      if (graph.current) follow(graph.current, latest.current, true, setError);
    };
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onStop);
    video.addEventListener("ended", onStop);
    video.addEventListener("seeked", onSeeked);
    return () => {
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onStop);
      video.removeEventListener("ended", onStop);
      video.removeEventListener("seeked", onSeeked);
      onStop();
    };
  }, [video]);

  React.useEffect(
    () => () => {
      if (raf.current !== null) cancelAnimationFrame(raf.current);
      const g = graph.current;
      graph.current = null;
      if (g) {
        g.voice.pause();
        g.music.pause();
        void g.ctx.close();
      }
    },
    [],
  );

  return { playing, error };
}
