/**
 * Validation d'un modèle de montage avant enregistrement (mêmes bornes que MontageTemplate de worker/montage.py : un
 * modèle accepté ici est accepté par le worker) et des réglages d'une musique. Serveur (actions de l'onglet Montage).
 */
import { z } from "zod";

const color = z.string().regex(/^#[0-9A-Fa-f]{6}$/, "couleur #RRGGBB attendue").transform((c) => c.toUpperCase());
const formats = z.array(z.enum(["story", "timelapse", "tour"])).transform((list) => [...new Set(list)]);
const int = (min: number, max: number) => z.number().int().min(min).max(max);
const num = (min: number, max: number) => z.number().min(min).max(max);
const family = z.string().trim().min(1).max(120);

export const hookSchema = z.object({
  formats,
  duration_s: num(0.5, 60).nullable(),
  font_family: family,
  bold: z.boolean(),
  size: int(24, 200),
  uppercase: z.boolean(),
  text_color: color,
  background: z.enum(["plate", "block", "none"]),
  background_color: color,
  background_opacity: num(0, 1),
  radius: int(0, 120),
  padding_x: int(0, 160),
  padding_y: int(0, 160),
  outline_color: color,
  outline_width: int(0, 24),
  width_pct: num(0.3, 1),
  line_spacing: num(0.8, 2),
  align: z.enum(["left", "center", "right"]),
  x: int(0, 1080),
  y: int(0, 1800),
});

export const subtitlesSchema = z.object({
  enabled: z.boolean(),
  font_family: family,
  bold: z.boolean(),
  italic: z.boolean(),
  font_size: int(24, 220),
  text_transform: z.enum(["none", "uppercase", "lowercase", "capitalize"]),
  letter_spacing: num(-5, 30),
  text_color: color,
  highlight_mode: z.enum(["none", "word", "karaoke"]),
  highlight_color: color,
  outline_color: color,
  outline_width: num(0, 20),
  shadow_color: color,
  shadow_opacity: num(0, 1),
  shadow_distance: num(0, 40),
  shadow_angle: int(0, 359),
  shadow_blur: num(0, 20),
  background: z.enum(["none", "box"]),
  background_color: color,
  background_opacity: num(0, 1),
  background_padding: int(0, 80),
  max_words: int(1, 8),
  max_chars: int(6, 60),
  animation: z.enum(["none", "pop", "bounce", "fade", "slide_up"]),
  x: int(0, 1080),
  y: int(40, 1880),
});

export const titlesSchema = z.object({
  formats,
  font_family: family,
  bold: z.boolean(),
  size: int(24, 220),
  uppercase: z.boolean(),
  text_color: color,
  background: z.enum(["box", "outline", "none"]),
  box_color: color,
  box_opacity: num(0, 1),
  padding: int(0, 80),
  outline_color: color,
  outline_width: num(0, 20),
  x: int(0, 1080),
  y: int(40, 1880),
});

export const audioSchema = z.object({
  formats,
  voice_db: num(-12, 12),
  music_db: num(-120, 0),
  duck_db: num(0, 20),
  solo_db: num(-120, 12),
  sfx_db: num(-20, 12),
});

export const templateSchema = z.object({
  version: z.literal(1),
  hook: hookSchema,
  subtitles: subtitlesSchema,
  titles: titlesSchema,
  audio: audioSchema,
});

/** Réglages d'une musique de la bibliothèque (table music_tracks : mêmes bornes que la migration 0018). */
export const musicTrackSchema = z
  .object({
    title: z.string().trim().min(1).max(80),
    description: z.string().trim().max(800),
    moods: z.array(z.string().regex(/^[a-z]+$/)).max(10).transform((list) => [...new Set(list)]),
    formats,
    weight: num(0, 5),
    enabled: z.boolean(),
    gain_db: num(-24, 24),
    start_s: num(0, 3600),
    note: z.string().trim().max(300),
  })
  .partial();

/** Premier problème d'un modèle refusé, en clair (« titles.y : … »). */
export function schemaError(error: z.ZodError): string {
  const issue = error.issues[0];
  return issue ? `${issue.path.join(".")} : ${issue.message}` : "modèle invalide";
}
