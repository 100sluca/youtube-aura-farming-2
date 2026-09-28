/** Types et constantes des réglages IA, partagés par les actions serveur, la page Réglages et le composant client.
 * (Un fichier « use server » ne peut exporter que des fonctions : les constantes vivent ici.) */

export type Provider = "gemini" | "anthropic" | "mistral" | "ollama";
export const PROVIDER_ORDER: Provider[] = ["gemini", "anthropic", "mistral", "ollama"];

/** Deux chaînes de modèles (docs/24 §3) : « writer » pour l'agent idées, les scénaristes et le relecteur, « default »
 * pour tous les autres agents (SEO, contrôles des images et des clips, stratégie, amélioration, analyse). */
export type ChainKind = "writer" | "default";
export const CHAIN_KINDS: ChainKind[] = ["writer", "default"];
export const CHAIN_MAX = 8;

/** Un choix de la chaîne : un modèle d'un fournisseur ; le worker essaie toutes les clés du fournisseur avant de passer
 * au choix suivant (worker/providers/llm.py : KeyedLLM, FallbackLLM). */
export interface ChainEntry {
  provider: Provider;
  model: string;
}

/** Clé enregistrée : son numéro (1 = gemini_api_key, 2 = gemini_api_key_2…) et ses 4 derniers caractères. */
export interface KeyHint {
  slot: number;
  hint: string;
}
export const KEY_NAME = /^(gemini|anthropic|mistral)_api_key(?:_(\d+))?$/;

export function secretName(provider: Exclude<Provider, "ollama">, slot: number): string {
  return slot <= 1 ? `${provider}_api_key` : `${provider}_api_key_${slot}`;
}

export interface LlmSettings {
  /** Anciens réglages (avant les chaînes) : déduits de la chaîne « default » à l'enregistrement, lus par ce qui ne
   * connaît pas encore les chaînes. */
  provider: Provider;
  fallbacks: Provider[];
  models: Record<Provider, string>;
  writer_models: Record<Provider, string>;
  custom_models: Record<Provider, string[]>;
  /** 1er choix, 2e choix… de chaque chaîne. */
  chains: Record<ChainKind, ChainEntry[]>;
}

const isProvider = (v: unknown): v is Provider => typeof v === "string" && (PROVIDER_ORDER as string[]).includes(v);

/** Choix valides, sans doublon, CHAIN_MAX au plus (même règle que settings_store.parse_chain du worker). */
export function cleanChain(raw: unknown): ChainEntry[] {
  const out: ChainEntry[] = [];
  for (const e of Array.isArray(raw) ? raw : []) {
    const provider = (e as { provider?: unknown })?.provider;
    const model = String((e as { model?: unknown })?.model ?? "").trim();
    if (isProvider(provider) && model && !out.some((x) => x.provider === provider && x.model === model)) out.push({ provider, model });
  }
  return out.slice(0, CHAIN_MAX);
}

/** La chaîne effective, comme le worker la calcule (settings_store.LlmConfig.chain) : celle en base, sinon (pour
 * l'écriture) celle des autres agents, sinon celle des anciens réglages. */
export function effectiveChain(
  v: Partial<Pick<LlmSettings, "provider" | "fallbacks" | "models" | "writer_models">> & { chains?: Partial<Record<ChainKind, unknown>> },
  kind: ChainKind,
  defaults: Pick<LlmSettings, "provider" | "fallbacks" | "models">,
): ChainEntry[] {
  const own = cleanChain(v.chains?.[kind]);
  if (own.length) return own;
  if (kind === "writer") {
    const general = cleanChain(v.chains?.default);
    if (general.length) return general;
  }
  const models = { ...defaults.models, ...(v.models ?? {}) };
  const providers = [...new Set([v.provider ?? defaults.provider, ...(v.fallbacks ?? defaults.fallbacks)])].filter(isProvider);
  const base = providers.map((p) => ({ provider: p, model: models[p] })).filter((e) => e.model);
  const first = providers[0];
  const strong = kind === "writer" && first ? String(v.writer_models?.[first] ?? "").trim() : "";
  return cleanChain(strong && strong !== models[first] ? [{ provider: first, model: strong }, ...base] : base);
}

/** « 1er choix », « 2e choix »… */
export function rankLabel(i: number): string {
  return i === 0 ? "1er choix" : `${i + 1}e choix`;
}
