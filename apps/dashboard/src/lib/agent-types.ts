/** Types de l'onglet Agents, partagés par les lectures serveur (lib/agents.ts), les actions et les composants client. */
import type { JobType } from "@/lib/types";
import type { ModelSlot, WaitingKey } from "@/lib/agent-catalog";

/** Origine d'une version : le texte du code du worker, une version écrite dans le dashboard, une proposition de
 * l'agent d'amélioration. */
export type PromptOrigin = "code" | "human" | "improve_agent";

export interface PromptVersion {
  id: string;
  version: number;
  content: string;
  notes: string | null;
  origin: PromptOrigin;
  createdAt: string;
  active: boolean;
  parentId: string | null;
}

export interface PromptState {
  key: string;
  /** Toutes les versions, de la plus récente à la plus ancienne. */
  versions: PromptVersion[];
  /** La version que le worker utilise ; null si le worker n'a encore rien enregistré. */
  active: PromptVersion | null;
  /** Le dernier texte du code. */
  latestCode: PromptVersion | null;
  /** Le texte du code a changé depuis la version active (écrite à la main, ou ancienne version du code). */
  codeUpdate: PromptVersion | null;
  /** Propositions de l'agent d'amélioration plus récentes que la version active. */
  proposals: PromptVersion[];
}

export interface AgentActivity {
  /** Tâches terminées sur 7 jours. */
  done: number;
  failed: number;
  running: number;
  queued: number;
  lastAt: string | null;
  /** Contrôleurs d'images et de clips : verdicts rendus et refus sur 7 jours. */
  checked?: number;
  refused?: number;
}

export interface PipelineLive {
  models: Record<ModelSlot, string>;
  jobs: Partial<Record<JobType, { running: number; queued: number }>>;
  waiting: Record<WaitingKey, number>;
}

export const ORIGIN_LABELS: Record<PromptOrigin, string> = {
  code: "texte du code",
  human: "écrite dans le dashboard",
  improve_agent: "proposée par l’agent amélioration",
};
