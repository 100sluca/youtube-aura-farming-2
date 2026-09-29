/**
 * Types du domaine — miroir de supabase/migrations/0001_init.sql.
 * Source de vérité : la migration SQL. À terme, générer via
 * `supabase gen types typescript` et ne garder ici que les types dérivés.
 */

export type ChannelLang = "fr" | "en";
export type VideoFormat = "A_voiceover" | "B_visual";
export type ConceptStatus = "proposed" | "approved" | "rejected" | "used";
export type ProductionStatus =
  | "draft"
  | "scripting"
  | "storyboard_review"
  | "generating"
  | "assembling"
  | "ready"
  | "failed"
  | "archived"
  | "cancelled"; // arrêtée depuis le gestionnaire de tâches (migration 0007)
export type VideoStatus =
  | "pending"
  | "rendering"
  | "qa"
  | "review"
  | "ready"
  | "uploading"
  | "scheduled"
  | "published"
  | "failed"
  | "unpublished";
export type JobType =
  | "ideate"
  | "script"
  | "storyboard"
  | "render"
  | "generate_clip"
  | "tts"
  | "seo"
  | "assemble"
  | "qa"
  | "upload"
  | "sync_metrics"
  | "sync_retention"
  | "sync_comments"
  | "improve"
  | "strategy"
  | "import_channel"
  | "voice_preview"
  | "montage_preview"
  | "analyze"
  | "tiktok_publish"
  | "sync_tiktok";

/** Série de contenu (table series, migration 0003) : un « thème » dans l'interface. */
export interface Series {
  id: string;
  slug: string;
  name: string;
  source: "llm" | "wikipedia";
  is_active: boolean;
  weight: number;
  style_preset: string | null;
  recipe?: string; // story | timelapse | tour (migration 0006) | drama (migration 0021)
}

/** Image candidate d'une scène du storyboard (assets kind = storyboard). */
export interface StoryboardCandidate {
  asset_id: string;
  selected: boolean;
  seed: number | null;
  /** Contrôle par vision (formats visuels, worker/keyframe_qc.py) : absent si le contrôle n'a pas tourné. */
  qc?: { ok: boolean; problems: string[] } | null;
}

export interface StoryboardScene {
  index: number;
  role: string | null;
  visual_prompt: string;
  /** Ce que dit la voix pendant la scène, dans la langue de la vidéo (récits) ; absent pour une vidéo sans voix. */
  narration?: string | null;
  /** Drame (docs/35) : le personnage qui dit la réplique, montré à part ; son nom n'est ni dit ni écrit dans la vidéo. */
  speaker?: string | null;
  continues_previous: boolean;
  /** i2v (depuis l'image) ou flf (première + dernière image, chantier en accéléré : impossible avec Gemini). */
  clip_mode?: string;
  /** Passage d'une pièce à la suivante (visites) : jamais d'image, le clip relie la fin de la précédente à la suivante. */
  passage?: boolean;
  /** En cours sur la scène : nouvelles images (Refaire) ou scène réécrite puis illustrée (Réinventer, docs/27). */
  busy?: "redo" | "reinvent" | null;
  /** Ce travail attend la carte graphique (en file) ou tourne (en cours). */
  busy_state?: "queued" | "running" | null;
  /** Pourquoi la scène est refaite quand Luca ne l'a pas demandé (payload.reason), la fiche refaite ou sa remarque. */
  busy_reason?: string | null;
  /** Le job à arrêter (« Arrêter » : les images affichées restent, docs/16 §3) ; null si l'arrêter viderait la scène. */
  busy_job?: string | null;
  /** Scène réinventée (docs/27) : elle a toujours sa propre image, à retenir avant de valider. */
  reinvented?: boolean;
  /** Son nouveau plan en une phrase, écrit par le scénariste pour Luca. */
  idea?: string | null;
  candidates: StoryboardCandidate[];
}
export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";
export type AlertSeverity = "info" | "warning" | "error";

/** Chaîne YouTube : un nom, une langue (voix, sous-titres, métadonnées), une connexion (migration 0008). */
export interface Channel {
  id: string;
  slug: string;
  name: string;
  lang: ChannelLang;
  youtube_channel_id: string | null;
  timezone: string;
  publish_slots: string[]; // "09:00"
  auto_publish: boolean;
  is_active: boolean;
  youtube_title?: string | null; // nom côté YouTube (retour OAuth)
  youtube_thumbnail_url?: string | null;
  history_imported_at?: string | null;
  last_series_id?: string | null; // dernier thème utilisé, présélectionné dans Création
  created_at?: string;
}

export interface Concept {
  id: string;
  title: string;
  hook: string | null;
  category: string | null;
  premise: string | null;
  visual_beats: string[];
  source: "agent" | "manual" | "clone";
  score: number | null;
  status: ConceptStatus;
  created_at: string;
  // Séries et sources (migration 0003) — absents du mock
  angle?: string | null;
  series_slug?: string | null;
  series_name?: string | null;
  facts_count?: number;
  production_id?: string | null;
  channel_id?: string | null; // chaîne pour laquelle l'idée a été demandée (migration 0008)
}

/** Script produit par l'agent script (productions.script, version 1). */
export interface ScriptScene {
  index: number;
  duration_s: number;
  visual_prompt: string;
  role?: string | null; // hook | setup | reveal | escalation | payoff | loop
  motion_prompt?: string | null;
  continues_previous?: boolean; // le clip part de la dernière image du précédent
  clip_mode?: string; // i2v | flf (première + dernière image, formats visuels)
  passage?: boolean; // visites : scène de passage entre deux pièces, insérée par le code, sans image de storyboard
  narration: Partial<Record<ChannelLang, string>>;
  on_screen_text?: Partial<Record<ChannelLang, string>>;
  sfx?: string;
  /** Drame (recette drama, docs/35) : personnages à l'image (clés du cast) et la réplique du plan. */
  characters?: string[];
  lines?: { who: string; text: string; tone?: string }[];
}
/** Personnage d'un drame : sa fiche (image) sert de référence à chaque plan où il apparaît. */
export interface CastMember {
  key: string;
  name: string;
  look: string;
  voice?: string;
  tts_voice?: string;
  role?: string;
}
export interface ScriptV1 {
  version: 1;
  scenes: ScriptScene[];
  loop_note?: string;
  metadata: Record<ChannelLang, { title: string; description: string; tags: string[] }>;
  cast?: CastMember[];
}

/** Fiche d'un personnage de drame dans Création (assets kind = character, retenue). */
export interface CharacterSheet {
  key: string;
  name: string;
  role: string | null;
  look: string;
  asset_id: string | null;
  /** Fiche ou plans en cours de refaçon (job storyboard payload.characters). */
  busy: boolean;
}

export interface Production {
  id: string;
  concept_id: string | null;
  format: VideoFormat;
  status: ProductionStatus;
  script: ScriptV1 | null;
  target_duration_s: number;
  style_preset: string | null;
  video_provider: string | null;
  image_workflow?: string | null; // modèle d'image du storyboard, figé au script (migration 0005)
  error: string | null;
  created_at: string;
  updated_at: string;
  series_slug?: string | null;
  series_name?: string | null;
  lint?: string[]; // problèmes de storytelling restants (worker/storytelling.py)
  channel_id?: string | null; // chaîne visée (migration 0008)
  channel_name?: string | null;
}

export interface Video {
  id: string;
  production_id: string;
  channel_id: string;
  lang: ChannelLang;
  format: VideoFormat;
  status: VideoStatus;
  title: string | null;
  description: string | null;
  tags: string[];
  duration_s: number | null;
  scheduled_at: string | null;
  youtube_video_id: string | null;
  youtube_publish_at: string | null;
  published_at: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  final_asset_id?: string | null; // lu par /api/media/[id]
  preview_asset_id?: string | null;
}

export interface Job {
  id: string;
  type: JobType;
  status: JobStatus;
  priority: number;
  production_id: string | null;
  video_id: string | null;
  channel_id: string | null;
  progress: number; // 0-100
  progress_label: string | null;
  attempts: number;
  max_attempts: number;
  run_after: string;
  locked_by: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  created_at: string;
}

export interface VideoMetricsDaily {
  video_id: string;
  day: string; // YYYY-MM-DD
  views: number;
  likes: number;
  comments: number;
  shares: number;
  subscribers_gained: number;
  average_view_duration_s: number | null;
  average_view_pct: number | null;
}

export interface RetentionPoint {
  t: number; // elapsedVideoTimeRatio 0..1
  w: number; // audienceWatchRatio 0..1+
  rel?: "ABOVE_AVERAGE" | "AVERAGE" | "BELOW_AVERAGE";
}

export interface ChannelMetricsDaily {
  channel_id: string;
  day: string;
  subscribers: number | null;
  subscribers_gained: number;
  views: number;
  estimated_minutes_watched: number | null;
  likes: number;
  comments: number;
}

export interface Alert {
  id: string;
  severity: AlertSeverity;
  title: string;
  body: string | null;
  job_id: string | null;
  video_id: string | null;
  acknowledged_at: string | null;
  created_at: string;
}

/** Ligne de la vue v_video_overview (bibliothèque : vidéos produites par l'appli et vidéos importées). */
export interface VideoOverview {
  id: string;
  production_id: string | null; // null : vidéo importée de YouTube (migration 0008)
  channel_id: string;
  channel_slug: string;
  lang: ChannelLang;
  format: VideoFormat | null;
  status: VideoStatus;
  title: string | null;
  category: string | null;
  scheduled_at: string | null;
  youtube_video_id: string | null;
  youtube_publish_at: string | null;
  published_at: string | null;
  duration_s: number | null;
  views: number;
  likes: number;
  comments: number;
  shares: number | null;
  subscribers_gained: number | null;
  average_view_pct: number | null;
  poster_url?: string | null;
  // Bibliothèque (migration 0008)
  channel_name?: string;
  origin?: "app" | "imported";
  created_at?: string;
  error?: string | null;
  description?: string | null;
  final_asset_id?: string | null;
  preview_asset_id?: string | null;
  poster_asset_id?: string | null;
  thumbnail_url?: string | null; // vignette YouTube
  files_deleted_at?: string | null;
  series_slug?: string | null;
  series_name?: string | null;
  hook?: string | null;
  production_status?: string | null;
  // Dashboard (migration 0016, docs/25) : totaux YouTube Analytics de toute la vie de la vidéo, relevés horaires
  engaged_views?: number | null;
  average_view_duration_s?: number | null;
  hook_retention_pct?: number | null; // audience encore là à 3 s
  end_retention_pct?: number | null; // audience encore là à la fin
  views_24h?: number | null;
  views_7d?: number | null;
  subscribers_lost?: number | null;
  estimated_minutes_watched?: number | null;
  stats_fetched_at?: string | null;
  analytics_through?: string | null; // dernier jour publié par YouTube Analytics
  recipe?: "story" | "timelapse" | "tour" | null;
  video_provider?: string | null;
  image_workflow?: string | null;
  tags?: string[];
  music_track?: string | null; // piste posée au montage (migration 0018)
  music_title?: string | null;
}

/** Carte "en production" : une production + ses vidéos + l'agrégat des jobs. */
export interface ProductionCard {
  production: Production;
  concept: Pick<Concept, "id" | "title" | "hook" | "category"> | null;
  videos: Video[];
  jobs: Job[];
  progress_pct: number;
  current_step: string | null; // ex. "Clips 5/8"
  eta_minutes: number | null;
  storyboard?: StoryboardScene[]; // images à valider (route image → vidéo)
  characters?: CharacterSheet[]; // drame : fiches des personnages, avant les plans
}

/** Créneau du calendrier : rempli (vidéo) ou vide (à combler). */
export interface ScheduleSlot {
  channel_slug: string;
  at: string; // ISO
  video: Pick<Video, "id" | "title" | "status" | "format" | "youtube_video_id"> | null;
}

export interface OverviewKpis {
  subscribers: number;
  subscribers_delta_7d: number;
  views_7d: number;
  views_7d_delta_pct: number | null; // vs 7 jours précédents
  average_view_pct_28d: number | null;
  watch_hours_28d: number;
  published_7d: number;
  pipeline: { generating: number; ready: number; scheduled: number; failed: number };
  ypp: { subs_target: number; views_90d: number; views_90d_target: number };
  // docs/25 : abonnés et vues à jour (relevés horaires + YouTube Analytics, publié 2 à 3 jours après)
  subscribers_delta_known?: boolean; // false : évolution sur 7 jours pas encore mesurable
  views_7d_estimated?: boolean; // les derniers jours viennent des compteurs, pas encore d'Analytics
  analytics_through?: string | null; // dernier jour publié par YouTube Analytics
  counters_at?: string | null; // dernier relevé des compteurs
  unattributed_views?: number; // vues comptées mais pas encore réparties par jour
}

/** Vues d'un jour, une clé par chaîne (slug → vues). */
export type DailyViewsPoint = { day: string } & Record<string, string | number>;
