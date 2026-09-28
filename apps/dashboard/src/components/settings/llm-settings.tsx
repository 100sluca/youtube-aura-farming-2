"use client";

import * as React from "react";
import { ArrowDown, ArrowUp, CircleCheck, CircleX, KeyRound, Plus, RefreshCw, Sparkles, Trash2 } from "lucide-react";

import { deleteSecret, listGeminiModels, saveLlmSettings, saveSecret, testLlm } from "@/app/settings/actions";
import { ConfirmButton } from "@/components/confirm-button";
import {
  CHAIN_MAX,
  PROVIDER_ORDER,
  rankLabel,
  type ChainEntry,
  type ChainKind,
  type KeyHint,
  type LlmSettings,
  type Provider,
} from "@/lib/llm-types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const LABELS: Record<Provider, string> = { gemini: "Gemini (Google)", anthropic: "Claude (Anthropic)", mistral: "Mistral", ollama: "Ollama (local)" };
const SHORT: Record<Provider, string> = { gemini: "Gemini", anthropic: "Claude", mistral: "Mistral", ollama: "Ollama" };
const KEYED: Provider[] = ["gemini", "anthropic", "mistral"];
const CHAINS: { kind: ChainKind; title: string; hint: string }[] = [
  {
    kind: "writer",
    title: "Chaîne d’écriture",
    hint: "Agent idées, scénaristes et relecteur : quelques appels par vidéo, les modèles les plus forts d’abord.",
  },
  {
    kind: "default",
    title: "Chaîne des autres agents",
    hint: "SEO, contrôles des images et des clips, stratégie, amélioration, analyse : beaucoup d’appels, un modèle au grand quota convient.",
  },
];

type Notice = { ok: boolean; message: string } | null;

function NoticeLine({ result }: { result: Notice }) {
  if (!result) return null;
  return (
    <p className={`flex items-center gap-1.5 text-xs ${result.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`} role="status">
      {result.ok ? <CircleCheck className="size-3.5 shrink-0" /> : <CircleX className="size-3.5 shrink-0" />}
      {result.message}
    </p>
  );
}

/**
 * Réglages IA (docs/24 §3) : plusieurs clés par fournisseur (quota épuisé ou clé refusée → la suivante) et deux chaînes
 * de modèles, 1er choix, 2e choix… (surcharge, modèle indisponible → le choix suivant). Le worker relit tout à chaque
 * appel (worker/settings_store.py, worker/providers/llm.py).
 */
export function LlmSettingsCard({
  initial,
  hints,
  presets,
}: {
  initial: LlmSettings;
  hints: Partial<Record<Provider, KeyHint[]>>;
  presets: Record<Provider, string[]>;
}) {
  const [chains, setChains] = React.useState<Record<ChainKind, ChainEntry[]>>(initial.chains);
  const [custom, setCustom] = React.useState<Record<Provider, string[]>>(initial.custom_models);
  const [keys, setKeys] = React.useState<Partial<Record<Provider, KeyHint[]>>>(hints);
  const [draft, setDraft] = React.useState<Record<string, string>>({});
  const [newModel, setNewModel] = React.useState<{ provider: Provider; name: string }>({ provider: "gemini", name: "" });
  const [pending, startTransition] = React.useTransition();
  const [notice, setNotice] = React.useState<Notice>(null);
  const [keyNotice, setKeyNotice] = React.useState<Notice>(null);
  const [modelNotice, setModelNotice] = React.useState<Notice>(null);

  const run = (fn: () => Promise<{ ok: boolean; message: string }>, setter: (n: Notice) => void = setNotice) =>
    startTransition(async () => {
      const res = await fn();
      setter({ ok: res.ok, message: res.message });
    });

  const optionsFor = (p: Provider, current?: string) => [...new Set([...(presets[p] ?? []), ...(custom[p] ?? []), ...(current ? [current] : [])])];
  const hasKey = (p: Provider) => p === "ollama" || (keys[p]?.length ?? 0) > 0;
  /** Modèle pour tester une clé : le premier de ce fournisseur dans les chaînes, sinon le premier proposé. */
  const testModel = (p: Provider) => [...chains.writer, ...chains.default].find((e) => e.provider === p)?.model ?? optionsFor(p)[0] ?? "";

  const setChain = (kind: ChainKind, entries: ChainEntry[]) => setChains((prev) => ({ ...prev, [kind]: entries }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="size-4" />
          Intelligence artificielle
        </CardTitle>
        <CardDescription>
          Les modèles qui écrivent les idées, les scripts, le SEO et qui contrôlent les images. En cas d’erreur, le worker essaie
          la clé suivante du même fournisseur (quota épuisé, clé refusée), puis le choix suivant de la chaîne (surcharge, modèle
          indisponible) ; ce qui vient d’échouer passe après le reste pendant quelques minutes. Les clés sont chiffrées en base et
          ne reviennent jamais dans le navigateur.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <section className="flex flex-col gap-3">
          <div>
            <h4 className="text-sm font-semibold">Clés API</h4>
            <p className="text-muted-foreground text-xs">
              Plusieurs clés d’un même fournisseur (par exemple plusieurs projets Google) : la clé 1 sert d’abord, les suivantes
              prennent le relais quand elle a épuisé son quota ou qu’elle est refusée.
            </p>
          </div>
          {KEYED.map((p) => {
            const list = keys[p] ?? [];
            return (
              <div key={p} className="flex flex-col gap-2 rounded-lg border p-3">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <KeyRound className="text-muted-foreground size-4" />
                  {LABELS[p]}
                  {list.length ? (
                    <Badge className="bg-emerald-600 text-white dark:bg-emerald-500">
                      {list.length} clé{list.length > 1 ? "s" : ""}
                    </Badge>
                  ) : (
                    <Badge variant="outline">aucune clé</Badge>
                  )}
                </div>
                {list.map((k, i) => (
                  <div key={k.slot} className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="w-14 shrink-0">Clé {i + 1}</span>
                    <code className="bg-muted rounded px-1.5 py-0.5 text-xs">…{k.hint}</code>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={pending || !testModel(p)}
                      onClick={() => run(() => testLlm(p, testModel(p), k.slot), setKeyNotice)}
                    >
                      Tester avec {testModel(p) || "—"}
                    </Button>
                    <ConfirmButton
                      size="sm"
                      variant="ghost"
                      disabled={pending}
                      confirmLabel="Retirer ?"
                      onConfirm={() =>
                        run(async () => {
                          const res = await deleteSecret(p, k.slot);
                          if (res.ok) setKeys((prev) => ({ ...prev, [p]: (prev[p] ?? []).filter((x) => x.slot !== k.slot) }));
                          return res;
                        }, setKeyNotice)
                      }
                    >
                      Retirer
                    </ConfirmButton>
                  </div>
                ))}
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Input
                    type="password"
                    autoComplete="off"
                    aria-label={`Nouvelle clé ${SHORT[p]}`}
                    placeholder={list.length ? "Coller une clé de secours" : "Coller la clé"}
                    value={draft[p] ?? ""}
                    onChange={(e) => setDraft((prev) => ({ ...prev, [p]: e.target.value }))}
                    className="sm:flex-1"
                  />
                  <Button
                    size="sm"
                    disabled={pending || !(draft[p] ?? "").trim()}
                    onClick={() =>
                      run(async () => {
                        const res = await saveSecret(p, draft[p] ?? "");
                        if (res.ok && res.slot) {
                          const added = { slot: res.slot, hint: res.hint ?? "…" };
                          setKeys((prev) => ({ ...prev, [p]: [...(prev[p] ?? []), added].sort((a, b) => a.slot - b.slot) }));
                          setDraft((prev) => ({ ...prev, [p]: "" }));
                        }
                        return res;
                      }, setKeyNotice)
                    }
                  >
                    <Plus />
                    Ajouter
                  </Button>
                </div>
              </div>
            );
          })}
          <NoticeLine result={keyNotice} />
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          {CHAINS.map((c) => (
            <ChainEditor
              key={c.kind}
              title={c.title}
              hint={c.hint}
              entries={chains[c.kind]}
              onChange={(entries) => setChain(c.kind, entries)}
              optionsFor={optionsFor}
              hasKey={hasKey}
              disabled={pending}
              onTest={(e) => run(() => testLlm(e.provider, e.model))}
            />
          ))}
        </section>

        <section className="flex flex-col gap-2">
          <h4 className="text-sm font-semibold">Modèles proposés dans les listes</h4>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Select value={newModel.provider} onValueChange={(v) => setNewModel((prev) => ({ ...prev, provider: v as Provider }))}>
              <SelectTrigger className="sm:w-40" aria-label="Fournisseur du modèle à ajouter">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROVIDER_ORDER.map((p) => (
                  <SelectItem key={p} value={p}>
                    {SHORT[p]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              placeholder="Identifiant d’un modèle (ex. gemini-3.9-flash-preview)"
              value={newModel.name}
              onChange={(e) => setNewModel((prev) => ({ ...prev, name: e.target.value }))}
              className="sm:flex-1"
            />
            <Button
              variant="outline"
              size="sm"
              disabled={!newModel.name.trim()}
              onClick={() => {
                const m = newModel.name.trim();
                setCustom((prev) => ({ ...prev, [newModel.provider]: [...new Set([...(prev[newModel.provider] ?? []), m])] }));
                setNewModel((prev) => ({ ...prev, name: "" }));
                setModelNotice({ ok: true, message: `« ${m} » ajouté aux listes ${SHORT[newModel.provider]} (à enregistrer)` });
              }}
            >
              Ajouter
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={pending || !hasKey("gemini")}
              onClick={() =>
                run(async () => {
                  const res = await listGeminiModels();
                  if (res.ok) setCustom((prev) => ({ ...prev, gemini: [...new Set([...(prev.gemini ?? []), ...res.models])] }));
                  return res;
                }, setModelNotice)
              }
            >
              <RefreshCw />
              Charger la liste depuis Google
            </Button>
          </div>
          <NoticeLine result={modelNotice} />
        </section>

        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={pending} onClick={() => run(() => saveLlmSettings({ chains, custom_models: custom }))}>
            Enregistrer les réglages
          </Button>
          <NoticeLine result={notice} />
        </div>
      </CardContent>
    </Card>
  );
}

function ChainEditor({
  title,
  hint,
  entries,
  onChange,
  optionsFor,
  hasKey,
  disabled,
  onTest,
}: {
  title: string;
  hint: string;
  entries: ChainEntry[];
  onChange: (entries: ChainEntry[]) => void;
  optionsFor: (p: Provider, current?: string) => string[];
  hasKey: (p: Provider) => boolean;
  disabled: boolean;
  onTest: (e: ChainEntry) => void;
}) {
  const move = (i: number, d: number) => {
    const next = [...entries];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    onChange(next);
  };
  const addChoice = () => {
    const provider = entries.at(-1)?.provider ?? "gemini";
    const model = optionsFor(provider).find((m) => !entries.some((e) => e.provider === provider && e.model === m)) ?? optionsFor(provider)[0] ?? "";
    onChange([...entries, { provider, model }]);
  };
  return (
    <div className="flex flex-col gap-3 rounded-lg border p-3">
      <div>
        <h4 className="text-sm font-semibold">{title}</h4>
        <p className="text-muted-foreground text-xs">{hint}</p>
      </div>
      <ol className="flex flex-col gap-2">
        {entries.map((e, i) => (
          <li key={`${i}-${e.provider}-${e.model}`} className="flex flex-wrap items-center gap-1.5">
            <span className="w-16 shrink-0 text-xs font-medium">{rankLabel(i)}</span>
            <Select
              value={e.provider}
              onValueChange={(v) => onChange(entries.map((x, j) => (j === i ? { provider: v as Provider, model: optionsFor(v as Provider)[0] ?? "" } : x)))}
            >
              <SelectTrigger className="w-32" aria-label={`${rankLabel(i)} : fournisseur`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROVIDER_ORDER.map((p) => (
                  <SelectItem key={p} value={p}>
                    {SHORT[p]}
                    {hasKey(p) ? "" : " — sans clé"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={e.model} onValueChange={(v) => onChange(entries.map((x, j) => (j === i ? { ...x, model: v } : x)))}>
              <SelectTrigger className="min-w-44 flex-1" aria-label={`${rankLabel(i)} : modèle`}>
                <SelectValue placeholder="Choisir un modèle" />
              </SelectTrigger>
              <SelectContent>
                {optionsFor(e.provider, e.model).map((m) => (
                  <SelectItem key={m} value={m}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {hasKey(e.provider) ? null : <Badge variant="outline">sans clé : sauté</Badge>}
            <Button size="icon" variant="ghost" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Monter le ${rankLabel(i)}`}>
              <ArrowUp />
            </Button>
            <Button size="icon" variant="ghost" disabled={i === entries.length - 1} onClick={() => move(i, 1)} aria-label={`Descendre le ${rankLabel(i)}`}>
              <ArrowDown />
            </Button>
            <Button size="sm" variant="outline" disabled={disabled || !e.model} onClick={() => onTest(e)}>
              Tester
            </Button>
            <Button
              size="icon"
              variant="ghost"
              disabled={entries.length <= 1}
              onClick={() => onChange(entries.filter((_, j) => j !== i))}
              aria-label={`Retirer le ${rankLabel(i)}`}
            >
              <Trash2 />
            </Button>
          </li>
        ))}
      </ol>
      <Button variant="outline" size="sm" className="self-start" disabled={entries.length >= CHAIN_MAX} onClick={addChoice}>
        <Plus />
        Ajouter un choix
      </Button>
    </div>
  );
}
