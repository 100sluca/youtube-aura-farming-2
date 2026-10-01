"use client";

/**
 * Fiche d'une vidéo : combien de temps sa fabrication a pris, de bout en bout et étape par étape (script, images,
 * chaque clip, voix, montage), docs/45.
 */
import * as React from "react";
import { Timer } from "lucide-react";

import { fetchProductionTiming } from "@/app/library/actions";
import { JOB_TYPE_LABELS } from "@/lib/labels";
import type { ProductionTiming, TimingItem } from "@/lib/timing-types";

/** « 42 s », « 12 min 05 s », « 1 h 05 min » */
export function formatSpent(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${String(s % 60).padStart(2, "0")} s`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
}

const plural = (n: number, word: string) => `${n} ${word}${n > 1 ? "s" : ""}`;

function Items({ title, items }: { title: string; items: TimingItem[] }) {
  if (!items.length) return null;
  const total = items.reduce((s, i) => s + i.seconds, 0);
  return (
    <details className="text-xs">
      <summary className="cursor-pointer select-none">
        {title} · moyenne {formatSpent(total / items.length)}
      </summary>
      <ul className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5 sm:grid-cols-3">
        {items.map((i, k) => (
          <li key={k} className="flex justify-between gap-2 tabular-nums">
            <span className="text-muted-foreground">Scène {i.scene + 1}</span>
            <span>
              {formatSpent(i.seconds)}
              {i.runs > 1 ? <span className="text-muted-foreground"> ({i.runs}&nbsp;passages)</span> : null}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}

export function ProductionTimingPanel({ productionId, videoId }: { productionId: string; videoId: string }) {
  const [loaded, setLoaded] = React.useState<{ key: string; data: ProductionTiming | null } | null>(null);
  const key = `${productionId}/${videoId}`;

  React.useEffect(() => {
    let alive = true;
    fetchProductionTiming(productionId, videoId)
      .then((data) => alive && setLoaded({ key, data }))
      .catch(() => alive && setLoaded({ key, data: null }));
    return () => {
      alive = false;
    };
  }, [productionId, videoId, key]);

  const t = loaded?.key === key ? loaded.data : undefined;
  if (t === undefined) return <p className="text-muted-foreground text-xs">Chargement des temps…</p>;
  if (t === null) return null;
  const max = Math.max(...t.steps.map((s) => s.seconds), 1);

  return (
    <section className="flex flex-col gap-3">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold">
        <Timer className="size-4" />
        Temps de fabrication
      </h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <div className="rounded-md border p-2">
          <p className="text-muted-foreground text-xs">Calcul</p>
          <p className="text-base font-semibold tabular-nums">{formatSpent(t.total_s)}</p>
        </div>
        {t.span_s !== null ? (
          <div className="rounded-md border p-2">
            <p className="text-muted-foreground text-xs">De bout en bout</p>
            <p className="text-base font-semibold tabular-nums">{formatSpent(t.span_s)}</p>
            {t.validation_s !== null && t.validation_s >= 60 ? (
              <p className="text-muted-foreground text-xs">dont {formatSpent(t.validation_s)} avant ta validation</p>
            ) : null}
          </div>
        ) : null}
        <div className="rounded-md border p-2">
          <p className="text-muted-foreground text-xs">Produit</p>
          <p className="text-sm font-medium">
            {plural(t.images.count, "image")} · {plural(t.clips.length, "clip")}
          </p>
        </div>
      </div>
      <ul className="flex flex-col gap-1 text-xs">
        {t.steps.map((s) => (
          <li key={s.type} className="grid grid-cols-[9.5rem_1fr_auto] items-center gap-2">
            <span className="truncate">{JOB_TYPE_LABELS[s.type]}</span>
            <span className="bg-muted h-1.5 overflow-hidden rounded-full">
              <span className="bg-primary block h-full rounded-full" style={{ width: `${Math.max(2, (100 * s.seconds) / max)}%` }} />
            </span>
            <span className="tabular-nums">
              {formatSpent(s.seconds)}
              {s.retries ? <span className="text-muted-foreground"> · {s.retries} relance{s.retries > 1 ? "s" : ""}</span> : null}
              {s.lost ? <span className="text-destructive"> · {s.lost} raté{s.lost > 1 ? "s" : ""}</span> : null}
            </span>
          </li>
        ))}
      </ul>
      <Items title={`Chaque clip (${t.clips.length})`} items={t.clips} />
      <Items title={`Chaque image (${t.images.timed.length})`} items={t.images.timed} />
      {t.approx ? (
        <p className="text-muted-foreground text-xs">
          Vidéo faite avant le journal des temps (30/09) : chiffres approximatifs, sans les passages ratés ni le détail des images.
        </p>
      ) : null}
    </section>
  );
}
