/**
 * Onglet Montage (docs/23-montage.md) : le modèle de montage de toutes les vidéos, tel que le worker le lit
 * (MontageTemplate de services/worker/worker/montage.py, table montage_templates, migration 0013).
 * Positions en px du final 1080×1920 : x = centre horizontal ; y = haut du titre d'accroche, centre des sous-titres et
 * des textes à l'écran. Tailles : px pour le titre d'accroche (dessiné par Pillow), taille ASS pour les sous-titres et les
 * textes à l'écran (libass : une ligne de texte est haute de la taille).
 */

export const FRAME_W = 1080;
export const FRAME_H = 1920;

/** Formats (recettes du worker) sur lesquels une couche s'affiche. */
export type MontageFormat = "story" | "timelapse" | "tour";
export const MONTAGE_FORMATS: MontageFormat[] = ["story", "timelapse", "tour"];
export const FORMAT_LABELS: Record<MontageFormat, string> = {
  story: "Récits narrés",
  timelapse: "Chantiers",
  tour: "Visites",
};
export const FORMAT_SHORT: Record<MontageFormat, string> = { story: "Récit", timelapse: "Chantier", tour: "Visite" };

export interface HookLayer {
  formats: MontageFormat[];
  duration_s: number | null; // null : toute la vidéo
  font_family: string;
  bold: boolean;
  size: number;
  uppercase: boolean;
  text_color: string;
  background: "plate" | "block" | "none";
  background_color: string;
  background_opacity: number;
  radius: number;
  padding_x: number;
  padding_y: number;
  outline_color: string;
  outline_width: number;
  width_pct: number;
  line_spacing: number;
  align: "left" | "center" | "right";
  x: number;
  y: number;
}

export interface SubtitleStyle {
  font_family: string;
  bold: boolean;
  italic: boolean;
  font_size: number;
  text_transform: "none" | "uppercase" | "lowercase" | "capitalize";
  letter_spacing: number;
  text_color: string;
  highlight_mode: "none" | "word" | "karaoke";
  highlight_color: string;
  outline_color: string;
  outline_width: number;
  shadow_color: string;
  shadow_opacity: number;
  shadow_distance: number;
  shadow_angle: number;
  shadow_blur: number;
  background: "none" | "box";
  background_color: string;
  background_opacity: number;
  background_padding: number;
  max_words: number;
  max_chars: number;
  animation: "none" | "pop" | "bounce" | "fade" | "slide_up";
}

export interface SubtitleLayer extends SubtitleStyle {
  enabled: boolean;
  x: number;
  y: number;
}

export interface TitleLayer {
  formats: MontageFormat[];
  font_family: string;
  bold: boolean;
  size: number;
  uppercase: boolean;
  text_color: string;
  background: "box" | "outline" | "none";
  box_color: string;
  box_opacity: number;
  padding: number;
  outline_color: string;
  outline_width: number;
  x: number;
  y: number;
}

/** Son (worker/montage.py : AudioLayer, docs/26-musique.md) : niveaux en dB, après égalisation automatique de la voix et
 * de chaque musique ; le mixage final est ramené à −14 LUFS. */
export interface AudioLayer {
  formats: MontageFormat[]; // musique de fond sur ces formats
  voice_db: number; // voix IA
  music_db: number; // musique sous la voix, par rapport à la voix
  duck_db: number; // baisse de la musique pendant que la voix parle
  solo_db: number; // musique des vidéos sans voix (chantiers, visites)
  sfx_db: number; // bruitages
}

export interface MontageTemplate {
  version: 1;
  hook: HookLayer;
  subtitles: SubtitleLayer;
  titles: TitleLayer;
  audio: AudioLayer;
}

export type LayerKey = "hook" | "subtitles" | "titles";
/** Onglets des réglages : les trois couches de l'image, puis le son. */
export type PanelKey = LayerKey | "audio";
export const LAYER_LABELS: Record<LayerKey, string> = {
  hook: "Titre d’accroche",
  subtitles: "Sous-titres",
  titles: "Textes à l’écran",
};

/** Un modèle enregistré (table montage_templates). */
export interface MontageTemplateRow {
  id: string;
  name: string;
  template: MontageTemplate;
  isDefault: boolean;
  updatedAt: string;
}

/** Une police (un fichier = une graisse) que le worker sait utiliser, avec ce qu'il faut pour l'aperçu. */
export interface FontFaceInfo {
  id: string; // « app~Montserrat-SemiBold.ttf », « user~… », « win~ariblk.ttf »
  source: "app" | "user" | "win";
  file: string;
  url: string;
  family: string; // nameID 1 : ce que le modèle enregistre (avec `bold`)
  typographicFamily: string; // nameID 16
  fullName: string; // nameID 4 : affiché dans la liste
  subfamily: string;
  weight: number;
  italic: boolean;
  isBold: boolean;
  unitsPerEm: number;
  hheaAscent: number; // Pillow (titre d'accroche) place le texte avec hhea
  hheaDescent: number; // positif
  winAscent: number; // libass (sous-titres) ramène winAscent + winDescent à la taille
  winDescent: number;
}

export const FONT_SOURCE_LABELS: Record<FontFaceInfo["source"], string> = {
  app: "Livrées avec l’appli",
  user: "Mes polices",
  win: "Windows",
};

/** Fond de l'aperçu : un clip ou une image d'une production (asset). */
export interface MontageBackground {
  assetId: string;
  kind: "clip" | "image";
  url: string;
  format: MontageFormat;
  label: string;
}

/** Textes d'essai pris dans les dernières productions, par format. */
export type MontageSamples = Record<MontageFormat, { hook: string; subtitle: string; title: string }>;

/** Constantes du mixage (worker/music.py), lues dans services/worker/assets/montage/defaults.json (« audio »). */
export interface AudioConstants {
  voice_ref_lufs: number;
  solo_ref_lufs: number;
  unknown_lufs: number;
  max_leveling_db: number;
  duck_merge_gap_s: number;
  duck_attack_s: number;
  duck_release_s: number;
  fade_in_s: number;
  fade_out_s: number;
  output_lufs: number;
  moods: Record<string, [label: string, hint: string]>; // ambiances des pistes (worker/music.py : MOODS)
  related: Record<string, string[]>; // ambiances voisines (RELATED)
  aliases: Record<string, string[]>; // mots anglais et variantes → ambiances (ALIASES)
}

/** Une musique de la bibliothèque (dossier « music » du dépôt, table music_tracks, migration 0018). */
export interface MusicTrack {
  id: string; // nom du fichier sans extension
  file: string;
  url: string; // /api/music/<id>
  title: string;
  description: string;
  moods: string[];
  formats: MontageFormat[]; // vide : nouvelle piste à décrire, jamais choisie
  weight: number; // préférence : 0,5 moins souvent, 1, 2 plus souvent
  enabled: boolean;
  gainDb: number; // volume propre de la piste (tous les modèles)
  startS: number; // départ dans le fichier
  note: string;
  lufs: number | null; // sonie mesurée ; null : pas encore mesurée
  durationS: number | null;
  missing: boolean; // fichier retiré du dossier
  uses: number; // vidéos montées avec cette piste
}

/** Vidéo d'essai de l'onglet Son : une vidéo déjà montée, avec sa voix (récits), pour écouter une musique sur la vraie
 * image et la vraie voix, aux réglages en cours. */
export interface TestVideo {
  videoId: string;
  title: string;
  format: MontageFormat;
  durationS: number;
  videoUrl: string; // aperçu de la vidéo montée : l'image (et son son d'origine, pour comparer)
  posterUrl: string | null;
  hasFinal: boolean; // fichier final présent : « Rendu exact avec le son » possible
  voice: { url: string; lufs: number | null; words: [start: number, end: number][] } | null; // narration (récits)
  musicTrack: string | null; // musique posée au dernier montage (null : aucune enregistrée)
  autoTrack: string | null; // musique que le montage lui donnerait (worker/music.py : choose_track)
}

export interface MusicLibrary {
  folder: string;
  tracks: MusicTrack[];
  videos: TestVideo[];
  constants: AudioConstants;
  error: string | null; // migration 0018 absente, dossier introuvable…
}

export interface MontagePageData {
  templates: MontageTemplateRow[];
  origin: MontageTemplate;
  presets: Record<string, SubtitleStyle>;
  fonts: FontFaceInfo[];
  backgrounds: MontageBackground[];
  samples: MontageSamples;
  music: MusicLibrary;
  mock: boolean;
}

/** État d'un rendu exact (job montage_preview), lu chaque seconde par l'éditeur. */
export interface MontagePreviewState {
  status: "queued" | "running" | "done" | "failed" | "cancelled" | "unknown";
  label: string | null;
  error: string | null;
  videoUrl: string | null;
  posterUrl: string | null;
  elapsedS: number | null;
}

export const PRESET_LABELS: Record<string, string> = {
  impact: "Impact",
  karaoke: "Karaoké",
  sobre: "Sobre",
  affiche: "Affiche",
  bd: "BD",
};

export const FALLBACK_SAMPLES: MontageSamples = {
  story: {
    hook: "Ce miroir cachait un dressing secret",
    subtitle: "Derrière ce miroir se cache une pièce que personne n’avait vue depuis cent vingt ans.",
    title: "1 an plus tard",
  },
  timelapse: {
    hook: "Personne ne voulait de ce terrain",
    subtitle: "Derrière ce miroir se cache une pièce que personne n’avait vue depuis cent vingt ans.",
    title: "Jour 12",
  },
  tour: {
    hook: "Tu paierais combien pour cette villa ?",
    subtitle: "Derrière ce miroir se cache une pièce que personne n’avait vue depuis cent vingt ans.",
    title: "Salon · 60 m²",
  },
};
