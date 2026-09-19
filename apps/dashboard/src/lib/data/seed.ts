/** PRNG déterministe (mulberry32) + utilitaires pour les données factices. */

export type Rng = () => number;

export function mulberry32(seed: number): Rng {
  let a = seed >>> 0;
  return function next() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** FNV-1a 32 bits : dérive une graine d'une chaîne. */
export function hashSeed(input: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

export function between(rng: Rng, min: number, max: number): number {
  return min + (max - min) * rng();
}

export function int(rng: Rng, min: number, max: number): number {
  return Math.floor(between(rng, min, max + 1));
}

export function pick<T>(rng: Rng, items: readonly T[]): T {
  return items[Math.floor(rng() * items.length)];
}

const HEX = "0123456789abcdef";

/** UUID v4 (format) déterministe. */
export function uuid(rng: Rng): string {
  let out = "";
  for (let i = 0; i < 36; i++) {
    if (i === 8 || i === 13 || i === 18 || i === 23) out += "-";
    else if (i === 14) out += "4";
    else if (i === 19) out += HEX[8 + Math.floor(rng() * 4)];
    else out += HEX[Math.floor(rng() * 16)];
  }
  return out;
}

const YT_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

/** Identifiant vidéo YouTube (11 caractères) déterministe. */
export function youtubeId(rng: Rng): string {
  let out = "";
  for (let i = 0; i < 11; i++) out += YT_ALPHABET[Math.floor(rng() * YT_ALPHABET.length)];
  return out;
}
