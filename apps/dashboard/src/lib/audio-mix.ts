/**
 * Calculs du mixage (docs/26-musique.md) recopiés de worker/music.py pour l'écoute de l'onglet Montage : mêmes
 * formules, mêmes constantes (services/worker/assets/montage/defaults.json, « audio »). La voix et chaque musique sont
 * d'abord ramenées au même niveau (sonie mesurée), puis les réglages du modèle et de la piste s'ajoutent.
 */
import type { AudioConstants, AudioLayer } from "@/lib/montage-types";

export const dbToGain = (db: number) => 10 ** (db / 20);
const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

function leveling(target: number, measured: number | null, unknown: number, max: number): number {
  return clamp(target - (measured ?? unknown), -max, max);
}

export interface MixLevels {
  voiceGainDb: number;
  musicGainDb: number;
  duckDb: number;
  sfxGainDb: number;
}

/** worker/music.py : mix_levels. */
export function mixLevels(
  audio: AudioLayer,
  c: AudioConstants,
  o: { withVoice: boolean; trackLufs: number | null; trackGainDb: number; narrationLufs: number | null },
): MixLevels {
  const voice =
    (o.narrationLufs !== null ? leveling(c.voice_ref_lufs, o.narrationLufs, c.voice_ref_lufs, c.max_leveling_db) : 0) + audio.voice_db;
  const target = o.withVoice ? c.voice_ref_lufs + audio.music_db : c.solo_ref_lufs + audio.solo_db;
  const music = leveling(target, o.trackLufs, c.unknown_lufs, c.max_leveling_db) + o.trackGainDb;
  return { voiceGainDb: voice, musicGainDb: music, duckDb: o.withVoice ? audio.duck_db : 0, sfxGainDb: audio.sfx_db };
}

/** worker/music.py : speech_segments (deux mots séparés de moins de `gap` s : même passage parlé). */
export function speechSegments(words: [number, number][], gap: number): [number, number][] {
  const out: [number, number][] = [];
  for (const [start, end] of [...words].sort((a, b) => a[0] - b[0])) {
    if (end <= start) continue;
    const last = out[out.length - 1];
    if (last && start - last[1] < gap) last[1] = Math.max(last[1], end);
    else out.push([start, end]);
  }
  return out;
}

/** worker/music.py : duck_amount (0 : musique à son niveau, 1 : baissée de duck_db). */
export function duckAmount(t: number, segments: [number, number][], attack: number, release: number): number {
  let level = 0;
  for (const [a, b] of segments) level = Math.max(level, clamp(Math.min((t - (a - attack)) / attack, (b + release - t) / release), 0, 1));
  return level;
}

/** worker/music.py : music_start (départ avancé pour ne pas dépasser la fin du fichier ; 0 si la piste est plus courte). */
export function musicStart(startS: number, durationS: number | null, totalS: number): number {
  let start = Math.max(0, startS);
  if (durationS) start = Math.min(start, Math.max(0, durationS - totalS));
  return start;
}

/** « 3:47 ». */
export function formatDuration(s: number | null): string {
  if (s === null || !Number.isFinite(s)) return "—";
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}
