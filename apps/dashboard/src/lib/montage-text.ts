/**
 * Calculs de l'aperçu de l'onglet Montage, recopiés du worker pour que l'aperçu coupe et place les textes comme le
 * montage : découpage des sous-titres en légendes (worker/subtitles.py : distribute_words, group_words, split_lines),
 * nettoyage du titre d'accroche (worker/hooktitle.py : clean_hook) et choix de la police (FontRegistry.pick).
 * Fonctions pures, utilisables côté navigateur.
 */
import type { FontFaceInfo, SubtitleStyle } from "@/lib/montage-types";

const EMOJI = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F1E6}-\u{1F1FF}\u{FE0F}\u{200D}\u{2B00}-\u{2BFF}]/gu;

export function stripEmojis(s: string): string {
  return s.replace(EMOJI, "");
}

export function transform(s: string, mode: SubtitleStyle["text_transform"]): string {
  if (mode === "uppercase") return s.toUpperCase();
  if (mode === "lowercase") return s.toLowerCase();
  if (mode === "capitalize") return s.split(" ").map((w) => w.slice(0, 1).toUpperCase() + w.slice(1)).join(" ");
  return s;
}

export function displayWord(text: string, mode: SubtitleStyle["text_transform"]): string {
  return transform(stripEmojis(text).trim(), mode);
}

/** Une ligne si elle tient, sinon deux lignes coupées au plus près du milieu. */
export function splitLines(words: string[], maxChars: number): string[][] {
  if (words.join(" ").length <= maxChars || words.length < 2) return [words];
  let best = 1;
  let bestCost = Infinity;
  for (let k = 1; k < words.length; k++) {
    const a = words.slice(0, k).join(" ").length;
    const b = words.slice(k).join(" ").length;
    const cost = Math.max(a, b) * 10 + Math.abs(a - b);
    if (cost < bestCost) {
      best = k;
      bestCost = cost;
    }
  }
  return [words.slice(0, best), words.slice(best)];
}

export interface WordTiming {
  text: string;
  start: number;
  end: number;
}

const PAUSE_SHORT = /[,;:–—]$/;
const PAUSE_LONG = /[.!?…]+[»"')\]]*$/;

/** Horodate les mots d'une phrase lue entre start et end (poids = longueur, pauses après la ponctuation). */
export function distributeWords(text: string, start: number, end: number): WordTiming[] {
  const words = text.split(/\s+/).filter((w) => stripEmojis(w).trim());
  if (!words.length || end <= start) return [];
  const weights: number[] = [];
  const pauses: number[] = [];
  for (const w of words) {
    const letters = [...w].filter((ch) => /[\p{L}\p{N}]/u.test(ch)).length;
    weights.push(Math.max(1, letters) + 1.5);
    pauses.push(PAUSE_LONG.test(w) ? 5.0 : PAUSE_SHORT.test(w) ? 2.5 : 0.0);
  }
  pauses[pauses.length - 1] = 0;
  const unit = (end - start) / (weights.reduce((a, b) => a + b, 0) + pauses.reduce((a, b) => a + b, 0));
  const out: WordTiming[] = [];
  let t = start;
  words.forEach((w, i) => {
    out.push({ text: w, start: t, end: t + weights[i] * unit });
    t += (weights[i] + pauses[i]) * unit;
  });
  return out;
}

export interface Caption {
  words: WordTiming[];
  start: number;
  end: number;
}

/** Regroupe les mots en légendes : max_words mots et deux lignes au plus, coupe aux fins de phrase et aux silences. */
export function groupWords(words: WordTiming[], style: Pick<SubtitleStyle, "max_words" | "max_chars" | "text_transform">,
  maxGap = 0.6, hold = 0.25): Caption[] {
  const captions: Caption[] = [];
  let current: WordTiming[] = [];
  for (const w of words) {
    if (!displayWord(w.text, style.text_transform)) continue;
    if (current.length) {
      const texts = [...current, w].map((x) => displayWord(x.text, style.text_transform));
      const lines = splitLines(texts, style.max_chars);
      const tooLong = lines.length > 1 && lines.some((line) => line.join(" ").length > style.max_chars);
      if (current.length >= style.max_words || tooLong || PAUSE_LONG.test(current[current.length - 1].text)
        || w.start - current[current.length - 1].end > maxGap) {
        captions.push({ words: current, start: current[0].start, end: current[current.length - 1].end });
        current = [];
      }
    }
    current.push(w);
  }
  if (current.length) captions.push({ words: current, start: current[0].start, end: current[current.length - 1].end });
  for (let i = 0; i + 1 < captions.length; i++) {
    const a = captions[i];
    const b = captions[i + 1];
    a.end = b.start > a.end ? Math.min(b.start, a.end + hold) : b.start;
  }
  if (captions.length) captions[captions.length - 1].end += hold;
  return captions.filter((c) => c.end - c.start >= 0.04);
}

/** Titre d'accroche : guillemets, hashtags, émojis et point final retirés, majuscule en tête (clean_hook). */
export function cleanHook(text: string): string {
  let t = stripEmojis(text ?? "");
  t = t.replace(/#[\p{L}\p{N}_]+/gu, "");
  t = t.replace(/[«»"“”]/g, "");
  t = t.replace(/\s+/g, " ").trim().replace(/^['’ ]+|['’ ]+$/g, "");
  t = t.replace(/(?<![.!?])\.$/, "").trim();
  return t.slice(0, 1).toUpperCase() + t.slice(1);
}

const BOLD_WORDS = ["black", "heavy", "extrabold", "ultrabold", "bold", "semibold", "demibold"];
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

export function faceIsBold(f: Pick<FontFaceInfo, "weight" | "subfamily" | "family">): boolean {
  const s = `${f.subfamily} ${f.family}`.toLowerCase().replace(/[ -]/g, "");
  return f.weight >= 600 || BOLD_WORDS.some((w) => s.includes(w));
}

/** Même choix que le worker (FontRegistry.pick) : nom exact d'abord, puis famille typographique ; la graisse la plus
 * proche de 700 (gras) ou de 400 ; `synthetic` = gras simulé faute de graisse grasse ; face null = police introuvable. */
export function pickFace(faces: FontFaceInfo[], wanted: string, bold: boolean): { face: FontFaceInfo | null; synthetic: boolean } {
  const key = norm(wanted);
  let cands = faces.filter((f) => norm(f.family) === key);
  if (!cands.length) cands = faces.filter((f) => norm(f.typographicFamily) === key);
  if (!cands.length) return { face: null, synthetic: bold };
  const upright = cands.filter((f) => !f.italic).length ? cands.filter((f) => !f.italic) : cands;
  const closest = (list: FontFaceInfo[], target: number) =>
    list.reduce((best, f) => (Math.abs(f.weight - target) < Math.abs(best.weight - target) ? f : best));
  if (bold) {
    const bolds = upright.filter((f) => f.isBold);
    if (bolds.length) return { face: closest(bolds, 700), synthetic: false };
    return { face: upright[0], synthetic: true };
  }
  const regular = upright.filter((f) => !f.isBold).length ? upright.filter((f) => !f.isBold) : upright;
  return { face: closest(regular, 400), synthetic: false };
}

/** Taille du cadratin en px pour une taille ASS (libass ramène winAscent + winDescent à la taille). */
export function assEm(face: FontFaceInfo | null, size: number): number {
  const h = face ? face.winAscent + face.winDescent : 0;
  return face && h > 0 ? (size * face.unitsPerEm) / h : size * 0.8;
}

/** Décalage de l'ombre portée (angle façon logiciel de retouche : 135° = en bas à droite). */
export function shadowOffset(distance: number, angle: number): [number, number] {
  const a = (angle * Math.PI) / 180;
  return [Math.round(-Math.cos(a) * distance), Math.round(Math.sin(a) * distance)];
}

/** Nom CSS des deux variantes d'une police dans l'aperçu : métriques libass (a) ou Pillow (p). */
export function cssFamily(face: FontFaceInfo | null, kind: "ass" | "pil", fallback: string): string {
  if (!face) return fallback;
  return `"yt2${kind === "ass" ? "a" : "p"}-${face.id.replace(/[^A-Za-z0-9_-]/g, "_")}", ${fallback}`;
}

export function hexToRgba(hex: string, opacity = 1): string {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 6 ? h : "000000", 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${Math.max(0, Math.min(1, opacity))})`;
}
