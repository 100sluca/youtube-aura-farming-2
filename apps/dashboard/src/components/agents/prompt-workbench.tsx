"use client";

import * as React from "react";
import { CircleCheck, CircleX, Eye, GitCompare, Pencil, RotateCcw, Save, TriangleAlert, Undo2, WandSparkles } from "lucide-react";

import { activatePrompt, savePrompt } from "@/app/agents/actions";
import { DiffView } from "@/components/agents/diff-view";
import { ConfirmButton } from "@/components/confirm-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ORIGIN_LABELS, type PromptState, type PromptVersion } from "@/lib/agent-types";
import { formatDateTime, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

type Notice = { ok: boolean; message: string } | null;

/** Même normalisation que l'action serveur : fins de ligne Unix, pas d'espaces en fin de texte. */
const normalize = (text: string) => text.replace(/\r\n?/g, "\n").replace(/\s+$/, "");

function NoticeLine({ notice }: { notice: Notice }) {
  if (!notice) return null;
  return (
    <p className={cn("flex items-center gap-1.5 text-xs", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")} role="status">
      {notice.ok ? <CircleCheck className="size-3.5 shrink-0" /> : <CircleX className="size-3.5 shrink-0" />}
      {notice.message}
    </p>
  );
}

function OriginBadge({ version }: { version: PromptVersion }) {
  const style = {
    code: "border-sky-500/40 text-sky-700 dark:text-sky-300",
    human: "border-emerald-500/40 text-emerald-700 dark:text-emerald-300",
    improve_agent: "border-violet-500/40 text-violet-700 dark:text-violet-300",
  }[version.origin];
  return (
    <Badge variant="outline" className={style}>
      {ORIGIN_LABELS[version.origin]}
    </Badge>
  );
}

function counts(text: string): string {
  const lines = text ? text.split("\n").length : 0;
  return `${formatNumber(text.length)} caractère${text.length > 1 ? "s" : ""} · ${lines} ligne${lines > 1 ? "s" : ""}`;
}

/**
 * Éditeur d'un prompt (agent ou consigne commune) et historique de ses versions. Enregistrer crée une nouvelle version,
 * active tout de suite : le worker la lit à la prochaine tâche. Toute version de l'historique peut revenir en service.
 */
export function PromptWorkbench({ promptKey, kind, state }: { promptKey: string; kind: "agent" | "consigne"; state: PromptState }) {
  const active = state.active;
  const [text, setText] = React.useState(active?.content ?? "");
  const [parentId, setParentId] = React.useState<string | null>(active?.id ?? null);
  const [notes, setNotes] = React.useState("");
  const [showChanges, setShowChanges] = React.useState(false);
  const [open, setOpen] = React.useState<{ id: string; mode: "view" | "diff" } | null>(null);
  const [notice, setNotice] = React.useState<Notice>(null);
  const [pending, startTransition] = React.useTransition();
  const editorRef = React.useRef<HTMLTextAreaElement>(null);

  // La version en service a changé (enregistrement, « Utiliser ») : l'éditeur repart de la nouvelle version. Avec des
  // modifications en cours, « Utiliser » demande d'abord confirmation.
  const [syncedId, setSyncedId] = React.useState(active?.id ?? null);
  if (active && active.id !== syncedId) {
    setSyncedId(active.id);
    setText(active.content);
    setParentId(active.id);
    setShowChanges(false);
  }

  const dirty = active ? normalize(text) !== normalize(active.content) : false;

  React.useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const save = () => {
    if (!dirty || pending) return;
    startTransition(async () => {
      const res = await savePrompt({ key: promptKey, content: text, notes, parentId });
      setNotice(res);
      if (res.ok) setNotes("");
    });
  };

  const activate = (v: PromptVersion) =>
    startTransition(async () => {
      setNotice(await activatePrompt(promptKey, v.version));
    });

  /** Remettre une version en service ; avec des modifications non enregistrées, un second clic confirme leur perte. */
  const activateButton = (version: PromptVersion, label: string, variant: "outline" | "default" = "outline") =>
    dirty ? (
      <ConfirmButton size="sm" variant={variant} disabled={pending} onConfirm={() => activate(version)} confirmLabel="Perdre mes modifications ?">
        <RotateCcw />
        {label}
      </ConfirmButton>
    ) : (
      <Button size="sm" variant={variant} disabled={pending} onClick={() => activate(version)}>
        <RotateCcw />
        {label}
      </Button>
    );

  const loadIntoEditor = (v: PromptVersion) => {
    setText(v.content);
    setParentId(v.id);
    setNotice({ ok: true, message: `Version ${v.version} copiée dans l’éditeur : modifie-la puis enregistre.` });
    editorRef.current?.focus();
    editorRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const reset = () => {
    setText(active?.content ?? "");
    setParentId(active?.id ?? null);
    setNotice(null);
  };

  if (!active) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{kind === "agent" ? "Prompt système" : "Consigne"}</CardTitle>
          <CardDescription>
            Le worker n’a pas encore enregistré ce texte en base : il le fait à chaque démarrage. Lance le worker (ou `yt2 prompts sync`), puis recharge la page.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {state.codeUpdate ? (
        <div className="flex flex-col gap-3 rounded-lg border border-amber-500/50 bg-amber-500/10 p-4 text-sm" role="note">
          <p className="flex items-start gap-2">
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-amber-600" />
            <span>
              Le texte du code a changé depuis la version en service (nouvelle version {state.codeUpdate.version}, {formatDateTime(state.codeUpdate.createdAt)}).
              La version {active.version} reste utilisée tant que tu ne choisis pas.
            </span>
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setOpen(open?.id === state.codeUpdate!.id && open.mode === "diff" ? null : { id: state.codeUpdate!.id, mode: "diff" })}
            >
              <GitCompare />
              Voir les différences
            </Button>
            {activateButton(state.codeUpdate, "Utiliser le texte du code", "default")}
          </div>
          {open?.id === state.codeUpdate.id && open.mode === "diff" ? <DiffView before={active.content} after={state.codeUpdate.content} /> : null}
        </div>
      ) : null}

      {state.proposals.length ? (
        <p className="flex items-center gap-2 rounded-lg border border-violet-500/50 bg-violet-500/10 p-3 text-sm">
          <WandSparkles className="size-4 shrink-0 text-violet-600" />
          L’agent amélioration propose {state.proposals.length > 1 ? `${state.proposals.length} nouvelles versions` : "une nouvelle version"} : voir
          l’historique ci-dessous (« Différences » puis « Utiliser »).
        </p>
      ) : null}

      <Card className="gap-4">
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            {kind === "agent" ? "Prompt système" : "Consigne"}
            <Badge className="bg-emerald-600 text-white dark:bg-emerald-500">Version {active.version} en service</Badge>
            <OriginBadge version={active} />
            {dirty ? <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-300">Modifié, non enregistré</Badge> : null}
          </CardTitle>
          <CardDescription>
            {kind === "agent"
              ? "Les instructions permanentes de l’agent. Les données de chaque tâche (thème, idée, faits, statistiques…) et les consignes communes s’ajoutent ensuite dans son message."
              : "Ce bloc est ajouté au message des agents qui le reçoivent, avec les données de la tâche."}{" "}
            Enregistrer crée une nouvelle version, utilisée dès la prochaine tâche ; l’historique garde toutes les autres.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Textarea
            ref={editorRef}
            aria-label={kind === "agent" ? "Prompt système" : "Consigne"}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
                e.preventDefault();
                save();
              }
            }}
            spellCheck={false}
            className="min-h-[26rem] resize-y font-mono text-[13px] leading-relaxed md:text-[13px]"
          />
          <div className="text-muted-foreground flex flex-wrap items-center justify-between gap-2 text-xs">
            <span>{counts(text)}</span>
            <span>Ctrl + S pour enregistrer</span>
          </div>
          {dirty ? (
            <div className="flex flex-col gap-3 rounded-lg border p-3">
              <Input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Note pour l’historique (facultatif) : pourquoi ce changement ?"
                maxLength={500}
                aria-label="Note de version"
              />
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={save} disabled={pending || !normalize(text)}>
                  <Save />
                  Enregistrer la version {Math.max(...state.versions.map((v) => v.version)) + 1}
                </Button>
                <Button variant="outline" onClick={() => setShowChanges((s) => !s)}>
                  <GitCompare />
                  {showChanges ? "Masquer mes changements" : "Voir mes changements"}
                </Button>
                <Button variant="ghost" onClick={reset} disabled={pending}>
                  <Undo2 />
                  Annuler les modifications
                </Button>
              </div>
              {showChanges ? <DiffView before={active.content} after={normalize(text)} /> : null}
            </div>
          ) : null}
          <NoticeLine notice={notice} />
        </CardContent>
      </Card>

      <Card className="gap-4">
        <CardHeader>
          <CardTitle>Historique des versions</CardTitle>
          <CardDescription>
            Texte du code (enregistré par le worker à chaque démarrage), tes versions et les propositions de l’agent amélioration. « Utiliser » remet une
            version en service ; « Différences » montre ce qui changerait par rapport à la version en service.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col divide-y px-0">
          {state.versions.map((v) => {
            const isOpen = open?.id === v.id;
            return (
              <div key={v.id} className="flex flex-col gap-2 px-6 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium tabular-nums">Version {v.version}</span>
                  <OriginBadge version={v} />
                  {v.active ? <Badge className="bg-emerald-600 text-white dark:bg-emerald-500">En service</Badge> : null}
                  <span className="text-muted-foreground text-xs tabular-nums">{formatDateTime(v.createdAt)}</span>
                  <span className="text-muted-foreground text-xs">· {formatNumber(v.content.length)} caractères</span>
                  <div className="ml-auto flex flex-wrap gap-1">
                    <Button size="sm" variant="ghost" onClick={() => setOpen(isOpen && open.mode === "view" ? null : { id: v.id, mode: "view" })}>
                      <Eye />
                      Lire
                    </Button>
                    {!v.active ? (
                      <Button size="sm" variant="ghost" onClick={() => setOpen(isOpen && open.mode === "diff" ? null : { id: v.id, mode: "diff" })}>
                        <GitCompare />
                        Différences
                      </Button>
                    ) : null}
                    <Button size="sm" variant="ghost" onClick={() => loadIntoEditor(v)}>
                      <Pencil />
                      Repartir de celle-ci
                    </Button>
                    {!v.active ? activateButton(v, "Utiliser") : null}
                  </div>
                </div>
                {v.notes ? <p className="text-muted-foreground text-xs">{v.notes}</p> : null}
                {isOpen && open.mode === "view" ? (
                  <pre className="bg-muted/40 max-h-96 overflow-auto rounded-md border p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap">{v.content}</pre>
                ) : null}
                {isOpen && open.mode === "diff" ? <DiffView before={active.content} after={v.content} /> : null}
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
