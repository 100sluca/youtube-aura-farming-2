/**
 * Retoucher → Récit (docs/53-reecrire-le-recit.md) : réécrire ce que dit la voix d'une vidéo faite, sur ses plans tels
 * qu'ils sont. Types partagés par le serveur (lib/rewrite-story.ts, app/library/rewrite-actions.ts) et l'onglet
 * (components/library/retouch-story.tsx).
 */
import type { JobStatus, VideoStatus } from "@/lib/types";

/** Tout le récit, ou seulement l'accroche (1re phrase dite) et la promesse (2e). */
export type RewriteMode = "story" | "hook";

/** Un plan de la vidéo : ce qu'on y voit, ce que la voix disait, la durée de son clip et les mots qu'il peut porter. */
export interface RewriteShot {
  index: number;
  seconds: number;
  shows: string;
  said: string;
  words_max: number;
}

/** Le récit réécrit par le conteur (worker/rewrite.py : StoryRewrite). */
export interface StoryProposal {
  central_idea: string;
  engine: string;
  protagonist: string;
  stakes: string;
  ending: string;
  scenes: { index: number; part: string; text: string; on_screen: string }[];
  hook_title: Record<string, string>;
  title: string;
}

/** La nouvelle ouverture (worker/rewrite.py : HookRewrite). */
export interface HookProposal {
  angle: string;
  hook: string;
  promise: string;
  on_screen: string;
  hook_title: Record<string, string>;
  title: string;
}

/** Un job « rewrite » sur la vidéo : proposer un texte, ou en faire une nouvelle vidéo. */
export interface RewriteJob {
  id: string;
  action: "propose" | "make";
  mode: RewriteMode;
  status: JobStatus;
  progress: number;
  label: string | null;
  error: string | null;
  note: string;
  pages: string[];
  createdAt: string;
  finishedAt: string | null;
  /** Tâche reportée (quota des modèles d'écriture épuisé) : quand elle repartira. */
  runAfter: string | null;
  /** Proposition faite (action « propose ») ou texte envoyé (action « make »). */
  proposal: StoryProposal | HookProposal | null;
  /** Écarts du correcteur et du relecteur, sans bloquer. */
  issues: string[];
  shots: RewriteShot[];
  /** La nouvelle vidéo (action « make » terminée). */
  videoId: string | null;
}

/** Une autre version de la même vidéo (videos.variant_of, migration 0037). */
export interface RewriteVersion {
  id: string;
  title: string;
  status: VideoStatus;
  createdAt: string;
  error: string | null;
}

export interface RewriteState {
  /** Le dernier job « rewrite » de la vidéo. */
  current: RewriteJob | null;
  /** La dernière proposition terminée, tant qu'aucune vidéo n'en a été faite depuis. */
  proposal: RewriteJob | null;
  versions: RewriteVersion[];
}

export interface RewriteData {
  videoId: string;
  lang: string;
  title: string;
  /** Pourquoi la réécriture est impossible pour cette vidéo (null : possible). */
  blocked: string | null;
  /** L'accroche seule : impossible quand le récit n'a pas été écrit par le conteur, ou que l'ouverture tient sur plusieurs plans. */
  hookBlocked: string | null;
  /** L'ouverture actuelle, pour l'écrire soi-même. */
  currentHook: HookProposal | null;
  /** La vidéo dont celle-ci est une autre version. */
  original: { id: string; title: string } | null;
  state: RewriteState;
}

export const REWRITE_PARTS: Record<string, string> = {
  hook: "Accroche",
  promise: "Promesse",
  context: "Contexte",
  conflict: "Conflit",
  twist: "Rebondissement",
  payoff: "Réponse",
  ending: "Chute",
};

/** Mots dits d'un texte, à peu près comme les compte le worker (storytelling.said_words : l'apostrophe et le trait
 * d'union lient deux mots ; un nombre compte pour les mots qui le disent, ici estimés d'après ses chiffres). */
export function wordCount(text: string): number {
  return (text.match(/[\p{L}\p{N}_'’-]+/gu) ?? []).reduce((n, w) => {
    const digits = w.replace(/\D/g, "").length;
    return n + (digits > 2 ? digits - 1 : 1);
  }, 0);
}

export const isStory = (p: StoryProposal | HookProposal | null): p is StoryProposal => Boolean(p && "scenes" in p);
