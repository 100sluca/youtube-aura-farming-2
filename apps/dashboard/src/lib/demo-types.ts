/** Démos et essais faits hors de l'appli (docs/28) : types partagés serveur / navigateur. Données : lib/demos.ts. */

/** demo : démos des formats (C:\YouTube2\demo) ; bench : bancs d'essai, comparaisons de modèles (C:\YouTube2\bench). */
export type DemoKind = "demo" | "bench";

export const DEMO_KIND_LABELS: Record<DemoKind, string> = { demo: "Démo", bench: "Essai" };

export interface DemoVideo {
  /** Chemin dans le dossier de la démo, avec des « / » (« clips/scene_01.mp4 »). */
  path: string;
  /** Adresse de lecture (/api/demos/…), avec les requêtes partielles que demande la balise <video>. */
  url: string;
  size_bytes: number;
  modified_at: string;
}

/** Un dossier de démo ou d'essai qui contient au moins une vidéo. */
export interface DemoFolder {
  /** « demo/refuge_v2 » : type + nom du dossier, sert à le lire et à le supprimer. */
  id: string;
  kind: DemoKind;
  title: string;
  description: string | null;
  /** Mise en ligne à la main sur YouTube (champ « youtube » de demo.json) : elle est aussi dans Vidéos → Importées. */
  youtube_video_id: string | null;
  /** Dossier sur le PC. */
  location: string;
  /** Date de la dernière vidéo finie du dossier, sinon de la dernière vidéo (ISO). */
  modified_at: string;
  /** Tout le dossier (vidéos, images, journaux), en octets. */
  size_bytes: number;
  /** Les vidéos finies (final…, comparaison…) d'abord, puis les clips et essais intermédiaires. */
  videos: DemoVideo[];
  /** Nombre de vidéos finies en tête de `videos` (toutes quand le dossier n'a pas de vidéo finie). */
  main_count: number;
}
