/**
 * Retouche d'une vidéo montée (Bibliothèque → Retoucher, docs/34-retouche.md) : types partagés serveur / navigateur.
 * Données : lib/retouch.ts ; gestes : app/library/retouch-actions.ts ; worker : services/worker/worker/retouch.py.
 */
import type { VoiceEntry, VoiceLang } from "@/lib/generation-types";
import type { AudioConstants, AudioLayer, MontageFormat, MusicTrack } from "@/lib/montage-types";
import type { VideoStatus } from "@/lib/types";

export const LEVEL_KEYS = ["voice_db", "music_db", "duck_db", "solo_db", "sfx_db"] as const;
export type LevelKey = (typeof LEVEL_KEYS)[number];
export type Levels = Pick<AudioLayer, LevelKey>;

/** Bornes des niveaux (worker/montage.py : AudioLayer). */
export const LEVEL_BOUNDS: Record<LevelKey, [min: number, max: number]> = {
  voice_db: [-12, 12],
  music_db: [-40, 0],
  duck_db: [0, 20],
  solo_db: [-20, 12],
  sfx_db: [-20, 12],
};

/** Bornes du titre d'accroche éphémère (demande de Luca, 29/09) : 5 s au moins, jusqu'à toute la vidéo. */
export const HOOK_MIN_S = 5;

/** videos.retouch (migration 0020), tel que le worker le lit. */
export interface RetouchData {
  hook_title?: string | null;
  hook_display?: { duration_s: number | null } | null; // éphémère : secondes ; null : toute la vidéo ; absent : le modèle
  subtitles?: Record<string, string>;
  music?: { track: string | null; start_s?: number | null } | null;
  audio?: Partial<Levels>;
  voice?: string | null;
  plans?: Record<string, PlanCorrection[]>; // consignes données plan par plan (SQL redo_plan, migration 0028)
}

/** Une correction demandée pour un plan (Retoucher → Plans, docs/38 §6). */
export interface PlanCorrection {
  note: string;
  clip: boolean;
  voice: boolean;
  at: string;
}

/** Un plan de la vidéo montée : où il est, qui parle, son clip, et les corrections déjà demandées. */
export interface RetouchPlan {
  index: number; // ScriptScene.index
  position: number;
  start: number; // sur la vidéo montée (s)
  end: number;
  speaker: string | null; // nom de qui parle ; null : plan sans réplique
  line: string;
  characters: string[]; // noms des personnages à l'image
  clipAssetId: string | null; // le clip tel que le modèle vidéo l'a fait (avec son propre son)
  corrections: PlanCorrection[];
}

/** Une scène parlée : ce que dit la voix, ce que le montage automatique affiche, et la retouche enregistrée. */
export interface RetouchScene {
  index: number; // ScriptScene.index : clé de videos.retouch.subtitles
  position: number;
  start: number; // début de la voix de la scène sur la vidéo (s)
  end: number;
  spoken: string;
  auto: string;
  edited: string | null;
}

export interface RetouchJob {
  id: string;
  type: "generate_clip" | "tts" | "assemble" | "qa";
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  progress: number;
  label: string | null;
  error: string | null;
}

/** Où en est la vidéo : lu toutes les 2 s pendant qu'elle est refaite. */
export interface RetouchState {
  status: VideoStatus;
  error: string | null;
  finalAssetId: string | null;
  posterAssetId: string | null;
  durationS: number | null;
  jobs: RetouchJob[]; // voix, montage, contrôle de la dernière retouche (ou du dernier montage)
  busy: boolean; // voix, montage ou contrôle en file ou en cours
  retouch: boolean; // ces jobs viennent d'une retouche (et non d'un montage ordinaire)
  doneAt: string | null; // fin du contrôle, quand tout est fait
}

export interface RetouchPageData {
  video: {
    id: string;
    title: string;
    lang: VoiceLang;
    format: MontageFormat;
    recipe: string | null; // recette de la série (drama : onglet Plans)
    voiced: boolean; // récit narré : sous-titres et voix
    channelName: string | null;
    youtubeVideoId: string | null;
  };
  /** Pourquoi la vidéo ne peut pas être retouchée (déjà sur YouTube, fichiers effacés…) ; null = retouchable. */
  blocked: string | null;
  hook: { auto: string; shown: boolean; templateDurationS: number | null }; // durée du modèle ; null : toute la vidéo
  subtitlesShown: boolean;
  scenes: RetouchScene[];
  plans: RetouchPlan[]; // tous les plans, dans l'ordre (repère « Plan N » sur la vidéo, onglet Plans des drames)
  retouch: RetouchData;
  template: { name: string; audio: AudioLayer };
  music: {
    tracks: MusicTrack[];
    constants: AudioConstants;
    current: string | null; // musique du dernier montage
    auto: string | null; // celle que le montage prendrait sans elle
    error: string | null;
  };
  voice: {
    current: string | null; // « moteur:voix » du dernier montage
    entries: VoiceEntry[];
    narration: { url: string; lufs: number | null; words: [start: number, end: number][] } | null;
    sample: string; // phrase d'essai : la narration de la vidéo
  };
  state: RetouchState;
}

/** Ce que l'écran envoie : l'état voulu de la retouche (complet), et la voix à refaire s'il y a lieu. */
export interface RetouchInput {
  hookTitle: string | null;
  hookDisplay: { durationS: number | null } | null; // null : la durée du modèle de montage
  subtitles: Record<string, string>;
  music: { track: string | null; startS: number | null } | null;
  audio: Partial<Levels>;
  voice: string | null; // « moteur:voix » à refaire ; null = garder la voix actuelle
}

export const RETOUCHABLE_STATUSES: VideoStatus[] = ["review", "qa", "ready", "failed"];
