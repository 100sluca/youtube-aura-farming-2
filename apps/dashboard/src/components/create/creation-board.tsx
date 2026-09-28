"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { CircleCheck, CircleX, ListChecks, LoaderCircle, RotateCcw, Sparkles, Undo2 } from "lucide-react";

import { selectChannel } from "@/app/channel-actions";
import { abandonStoryboard, acceptIdea, generateIdeas, rejectIdea, restoreIdea } from "@/app/create/actions";
import { toggleFavorite } from "@/app/favorites/actions";
import { approveStoryboard } from "@/app/production/actions";
import { ChannelAvatar } from "@/components/channel-badge";
import { IdeaCard } from "@/components/create/idea-card";
import { StoryboardReviewCard, StoryboardSheet } from "@/components/create/storyboard-review";
import { OpenTasksButton } from "@/components/tasks/task-manager";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { CreationData } from "@/lib/creation";
import { LANG_LABELS } from "@/lib/labels";
import type { Channel } from "@/lib/types";
import { cn } from "@/lib/utils";

const COUNTS = [3, 6, 10];

type Notice = { ok: boolean; message: string; undo?: string };

function Step({ n, label, children, className }: { n: number; label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <span className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium">
        <span className="bg-primary text-primary-foreground flex size-4 items-center justify-center rounded-full text-[10px] font-semibold">{n}</span>
        {label}
      </span>
      {children}
    </div>
  );
}

function SectionTitle({ id, title, count, children }: { id?: string; title: string; count: number; children?: React.ReactNode }) {
  return (
    <div id={id} className="flex scroll-mt-20 flex-wrap items-center gap-2">
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      <span className="text-muted-foreground text-sm tabular-nums">{count}</span>
      {children ? <div className="ml-auto flex flex-wrap items-center gap-2">{children}</div> : null}
    </div>
  );
}

/**
 * Page Création : chaîne → thème (le dernier utilisé est présélectionné) → idées notées → ✓ / ✗. Un ✓ lance le script
 * et les images ; le storyboard revient ici, et son ✓ lance la fabrication d'une traite (clips, voix, montage).
 */
export function CreationBoard({ channels, channel, data }: { channels: Channel[]; channel: Channel; data: CreationData }) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [seriesSlug, setSeriesSlug] = React.useState(data.defaultSeries ?? "");
  const [count, setCount] = React.useState(6);
  const [scope, setScope] = React.useState<"theme" | "all">("theme");
  const [hidden, setHidden] = React.useState<Set<string>>(() => new Set());
  const [notice, setNotice] = React.useState<Notice | null>(null);
  const [sheetId, setSheetId] = React.useState<string | null>(null);
  // Étoiles : l'état affiché tout de suite, avant que la page ne se recharge
  const [starred, setStarred] = React.useState<Record<string, boolean>>({});

  const theme = data.series.find((s) => s.slug === seriesSlug);
  const visibleIdeas = data.ideas.filter((c) => !hidden.has(c.id));
  const themeIdeas = visibleIdeas.filter((c) => c.series_slug === seriesSlug);
  const ideas = scope === "theme" ? themeIdeas : visibleIdeas;
  const writing = data.ideaJobs.filter((j) => j.series === seriesSlug);
  const storyboards = data.storyboards.filter((c) => !hidden.has(c.production.id));
  const sheetCard = storyboards.find((c) => c.production.id === sheetId) ?? null;

  const hide = (id: string) => setHidden((prev) => new Set(prev).add(id));
  const unhide = (id: string) =>
    setHidden((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });

  const act = (id: string, fn: () => Promise<{ ok: boolean; message: string }>, undo?: boolean) => {
    hide(id);
    startTransition(async () => {
      const res = await fn();
      if (!res.ok) unhide(id);
      setNotice({ ...res, undo: res.ok && undo ? id : undefined });
      router.refresh();
    });
  };

  const isFavorite = (productionId: string) => starred[productionId] ?? data.favorites.includes(productionId);
  const toggleStar = (productionId: string) => {
    setStarred((prev) => ({ ...prev, [productionId]: !isFavorite(productionId) }));
    startTransition(async () => {
      const res = await toggleFavorite(productionId);
      setStarred((prev) => ({ ...prev, [productionId]: res.favorite }));
      setNotice({ ok: res.ok, message: res.message });
      router.refresh();
    });
  };

  return (
    <div className="flex flex-col gap-8">
      <Card className="py-5">
        <CardContent className="grid gap-4 sm:grid-cols-2 sm:items-end xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto_auto]">
          <Step n={1} label="Chaîne">
            <Select
              value={channel.slug}
              onValueChange={(slug) =>
                startTransition(async () => {
                  await selectChannel(slug);
                  router.refresh();
                })
              }
            >
              <SelectTrigger className="w-full" aria-label="Chaîne">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {channels.map((c) => (
                  <SelectItem key={c.id} value={c.slug}>
                    <ChannelAvatar channel={c} className="size-5" />
                    {c.name}
                    <span className="text-muted-foreground text-xs">· {LANG_LABELS[c.lang]}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Step>
          <Step n={2} label="Thème">
            <Select value={seriesSlug} onValueChange={setSeriesSlug}>
              <SelectTrigger className="w-full" aria-label="Thème">
                <SelectValue placeholder="Choisir un thème" />
              </SelectTrigger>
              <SelectContent>
                {data.series.map((s) => (
                  <SelectItem key={s.slug} value={s.slug}>
                    {s.name}
                    {s.id === channel.last_series_id ? <span className="text-muted-foreground text-xs">· dernier utilisé</span> : null}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Step>
          <Step n={3} label="Nombre d’idées">
            <div className="bg-muted inline-flex rounded-lg p-0.5" role="radiogroup" aria-label="Nombre d’idées">
              {COUNTS.map((n) => (
                <button
                  key={n}
                  type="button"
                  role="radio"
                  aria-checked={count === n}
                  onClick={() => setCount(n)}
                  className={cn(
                    "h-8 min-w-10 rounded-md px-3 text-sm font-medium tabular-nums transition-colors",
                    count === n ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {n}
                </button>
              ))}
            </div>
          </Step>
          <Button
            size="lg"
            disabled={pending || !seriesSlug}
            onClick={() =>
              startTransition(async () => {
                setNotice(await generateIdeas(channel.id, seriesSlug, count));
                router.refresh();
              })
            }
          >
            <Sparkles />
            Générer des idées
          </Button>
          {writing.length > 0 ? (
            <p className="text-muted-foreground flex items-center gap-2 text-sm sm:col-span-2 xl:col-span-4">
              <LoaderCircle className="size-4 animate-spin" />
              L’agent écrit {writing.reduce((s, j) => s + (j.count ?? 0), 0) || "des"} idées pour « {theme?.name ?? seriesSlug} »
              {writing.some((j) => j.status === "running") ? "…" : " (en file)…"}
            </p>
          ) : null}
        </CardContent>
      </Card>

      {notice ? (
        <p
          className={cn(
            "-mt-4 flex flex-wrap items-center gap-2 text-sm",
            notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive",
          )}
          role="status"
        >
          {notice.ok ? <CircleCheck className="size-4" /> : <CircleX className="size-4" />}
          {notice.message}
          {notice.undo ? (
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0"
              onClick={() => {
                const id = notice.undo!;
                startTransition(async () => {
                  const res = await restoreIdea(id);
                  if (res.ok) unhide(id);
                  setNotice(res);
                  router.refresh();
                });
              }}
            >
              <Undo2 />
              Annuler
            </Button>
          ) : null}
        </p>
      ) : null}

      {storyboards.length > 0 ? (
        <section className="flex flex-col gap-3">
          <SectionTitle id="storyboards" title="Storyboards à regarder" count={storyboards.length} />
          <p className="text-muted-foreground -mt-1 text-sm">
            Les images de chaque scène sont prêtes. Ton ✓ lance les clips, la voix et le montage d’une traite ; tu peux d’abord changer une image.
          </p>
          <ul className="grid gap-4 xl:grid-cols-2">
            {storyboards.map((card) => (
              <StoryboardReviewCard
                key={card.production.id}
                card={card}
                disabled={pending}
                favorite={isFavorite(card.production.id)}
                onOpen={() => setSheetId(card.production.id)}
                geminiQuotaUntil={data.geminiQuotaUntil}
                onApprove={() => act(card.production.id, () => approveStoryboard(card.production.id))}
                onGemini={() => act(card.production.id, () => approveStoryboard(card.production.id, "gemini"))}
                onAbandon={() => act(card.production.id, () => abandonStoryboard(card.production.id))}
                onToggleFavorite={() => toggleStar(card.production.id)}
              />
            ))}
          </ul>
        </section>
      ) : (
        <div id="storyboards" className="scroll-mt-20" />
      )}

      <section className="flex flex-col gap-3">
        <SectionTitle title="Idées à trier" count={ideas.length}>
          <div className="bg-muted inline-flex rounded-lg p-0.5 text-sm" role="tablist" aria-label="Idées affichées">
            {(
              [
                ["theme", `${theme?.name ?? "Ce thème"} (${themeIdeas.length})`],
                ["all", `Tous les thèmes (${visibleIdeas.length})`],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={scope === id}
                onClick={() => setScope(id)}
                className={cn(
                  "h-8 max-w-64 truncate rounded-md px-3 font-medium transition-colors",
                  scope === id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </SectionTitle>
        {ideas.length > 0 ? (
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {ideas.map((concept) => (
              <IdeaCard
                key={concept.id}
                concept={concept}
                showSeries={scope === "all"}
                disabled={pending}
                onAccept={() => act(concept.id, () => acceptIdea(concept.id, channel.id))}
                onReject={() => act(concept.id, () => rejectIdea(concept.id), true)}
              />
            ))}
          </ul>
        ) : (
          <div className="text-muted-foreground flex flex-col items-center gap-2 rounded-xl border border-dashed p-10 text-center text-sm">
            <Sparkles className="size-6" />
            <p>
              {writing.length > 0
                ? "Les idées arrivent : cette page se met à jour toute seule."
                : `Aucune idée à trier${scope === "theme" && theme ? ` pour « ${theme.name} »` : ""}. Clique sur « Générer des idées ».`}
            </p>
          </div>
        )}
      </section>

      {data.preparing.length > 0 ? (
        <section className="flex flex-col gap-3">
          <SectionTitle title="En préparation" count={data.preparing.length}>
            <OpenTasksButton variant="outline" size="sm">
              <ListChecks />
              Suivre dans Tâches
            </OpenTasksButton>
          </SectionTitle>
          <ul className="flex flex-col divide-y rounded-xl border">
            {data.preparing.map((p) => (
              <li key={p.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <LoaderCircle className="text-muted-foreground size-4 shrink-0 animate-spin" />
                <span className="min-w-0 flex-1 truncate">{p.title}</span>
                <span className="text-muted-foreground shrink-0 text-xs">{p.stage}</span>
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground text-xs">Leur storyboard apparaîtra en haut de cette page, prêt à regarder.</p>
        </section>
      ) : null}

      {data.rejected.length > 0 ? (
        <details className="group rounded-xl border px-4 py-3">
          <summary className="text-muted-foreground cursor-pointer text-sm font-medium">Écartées récemment ({data.rejected.length})</summary>
          <ul className="mt-3 flex flex-col divide-y">
            {data.rejected.map((c) => (
                <li key={c.id} className="flex items-center gap-3 py-2 text-sm">
                  <span className="min-w-0 flex-1 truncate">{c.title}</span>
                  {c.series_name ? <span className="text-muted-foreground hidden shrink-0 text-xs sm:inline">{c.series_name}</span> : null}
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={pending}
                    onClick={() =>
                      startTransition(async () => {
                        const res = await restoreIdea(c.id);
                        if (res.ok) unhide(c.id);
                        setNotice(res);
                        router.refresh();
                      })
                    }
                  >
                    <RotateCcw />
                    Remettre
                  </Button>
                </li>
              ))}
          </ul>
        </details>
      ) : null}

      <StoryboardSheet
        card={sheetCard}
        favorite={sheetCard ? isFavorite(sheetCard.production.id) : false}
        disabled={pending}
        geminiQuotaUntil={data.geminiQuotaUntil}
        onClose={() => setSheetId(null)}
        onToggleFavorite={() => {
          if (sheetCard) toggleStar(sheetCard.production.id);
        }}
      />
    </div>
  );
}
