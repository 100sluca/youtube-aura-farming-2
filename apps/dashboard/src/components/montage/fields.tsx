"use client";

/** Champs de réglage de l'onglet Montage : curseur + valeur, couleur, choix segmenté, interrupteur, formats, police. */
import * as React from "react";
import { AlignHorizontalJustifyCenter, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { FONT_SOURCE_LABELS, FORMAT_LABELS, MONTAGE_FORMATS, type FontFaceInfo, type MontageFormat } from "@/lib/montage-types";
import { cssFamily, pickFace } from "@/lib/montage-text";
import { cn } from "@/lib/utils";

export function Field({ label, hint, children, className }: { label: string; hint?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <span className="text-muted-foreground text-xs font-medium">{label}</span>
      {children}
      {hint ? <span className="text-muted-foreground text-[11px] leading-snug">{hint}</span> : null}
    </div>
  );
}

/** Groupe de réglages avec un intitulé. */
export function Group({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3 border-t pt-4 first:border-t-0 first:pt-0">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">{title}</h4>
        {action}
      </div>
      <div className="grid grid-cols-1 gap-x-5 gap-y-4 sm:grid-cols-2">{children}</div>
    </section>
  );
}

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

export function SliderField({
  label,
  value,
  min,
  max,
  step = 1,
  unit,
  percent,
  inputMin,
  onChange,
  hint,
  className,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  inputMin?: number; // une valeur tapée dans la case peut descendre jusque-là, sous le bas du curseur
  step?: number;
  unit?: string;
  percent?: boolean; // valeur 0-1 affichée en %
  onChange: (v: number) => void;
  hint?: React.ReactNode;
  className?: string;
}) {
  const factor = percent ? 100 : 1;
  const shown = Math.round(value * factor * 100) / 100;
  const [draft, setDraft] = React.useState<string | null>(null);
  const commit = (raw: string) => {
    const n = Number(raw.replace(",", "."));
    if (Number.isFinite(n)) onChange(clamp(Math.round((n / factor) / step) * step, Math.min(min, inputMin ?? min), max));
    setDraft(null);
  };
  return (
    <Field label={label} hint={hint} className={className}>
      <div className="flex items-center gap-3">
        <Slider
          value={[value]}
          min={min}
          max={max}
          step={step}
          onValueChange={([v]) => onChange(Math.round(v / step) * step)}
          aria-label={label}
        />
        <div className="relative w-20 shrink-0">
          <Input
            className="h-8 pr-7 text-right tabular-nums"
            inputMode="decimal"
            value={draft ?? String(shown)}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={(e) => commit(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit((e.target as HTMLInputElement).value);
            }}
            aria-label={`${label} (valeur)`}
          />
          <span className="text-muted-foreground pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 text-[11px]">
            {percent ? "%" : unit}
          </span>
        </div>
      </div>
    </Field>
  );
}

export function ColorField({ label, value, onChange, className }: { label: string; value: string; onChange: (v: string) => void; className?: string }) {
  const [draft, setDraft] = React.useState<string | null>(null);
  const commit = (raw: string) => {
    const v = raw.trim().startsWith("#") ? raw.trim() : `#${raw.trim()}`;
    if (/^#[0-9A-Fa-f]{6}$/.test(v)) onChange(v.toUpperCase());
    setDraft(null);
  };
  return (
    <Field label={label} className={className}>
      <div className="flex items-center gap-2">
        <label className="relative size-8 shrink-0 cursor-pointer overflow-hidden rounded-md border shadow-xs" style={{ background: value }}>
          <input
            type="color"
            className="absolute inset-0 size-full cursor-pointer opacity-0"
            value={value.toLowerCase()}
            onChange={(e) => onChange(e.target.value.toUpperCase())}
            aria-label={label}
          />
        </label>
        <Input
          className="h-8 w-28 font-mono text-xs uppercase"
          value={draft ?? value}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={(e) => commit(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit((e.target as HTMLInputElement).value);
          }}
          aria-label={`${label} (hexadécimal)`}
        />
      </div>
    </Field>
  );
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  className,
  hint,
}: {
  label: string;
  value: T;
  options: { value: T; label: React.ReactNode; title?: string }[];
  onChange: (v: T) => void;
  className?: string;
  hint?: React.ReactNode;
}) {
  return (
    <Field label={label} className={className} hint={hint}>
      <div role="radiogroup" aria-label={label} className="bg-muted inline-flex w-full flex-wrap gap-0.5 rounded-lg p-0.5">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={value === o.value}
            title={o.title}
            onClick={() => onChange(o.value)}
            className={cn(
              "flex min-h-7 flex-1 items-center justify-center gap-1 rounded-md px-2 text-xs font-medium whitespace-nowrap transition-colors",
              value === o.value ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </Field>
  );
}

export function SwitchField({ label, checked, onChange, hint, className }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: React.ReactNode; className?: string }) {
  return (
    <label className={cn("flex cursor-pointer items-start justify-between gap-3", className)}>
      <span className="flex flex-col gap-0.5">
        <span className="text-sm">{label}</span>
        {hint ? <span className="text-muted-foreground text-[11px] leading-snug">{hint}</span> : null}
      </span>
      <Switch checked={checked} onCheckedChange={onChange} className="mt-0.5" aria-label={label} />
    </label>
  );
}

/** Types de contenu (formats) sur lesquels une couche s'affiche : une case à cocher par type, avec ce qu'elle y montre. */
export function FormatChecks({
  label = "Afficher sur",
  value,
  onChange,
  hints,
  className,
}: {
  label?: string;
  value: MontageFormat[];
  onChange: (v: MontageFormat[]) => void;
  hints?: Partial<Record<MontageFormat, string>>;
  className?: string;
}) {
  return (
    <Field label={label} className={className}>
      <div className="grid gap-2 sm:grid-cols-3">
        {MONTAGE_FORMATS.map((f) => {
          const on = value.includes(f);
          return (
            <label
              key={f}
              className={cn(
                "flex cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2 transition-colors",
                on ? "border-primary/60 bg-primary/5" : "hover:bg-muted/50",
              )}
            >
              <Checkbox
                checked={on}
                onCheckedChange={(checked) => onChange(MONTAGE_FORMATS.filter((x) => (x === f ? checked === true : value.includes(x))))}
                className="mt-0.5"
                aria-label={FORMAT_LABELS[f]}
              />
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="text-sm font-medium">{FORMAT_LABELS[f]}</span>
                {hints?.[f] ? <span className="text-muted-foreground text-[11px] leading-snug">{hints[f]}</span> : null}
              </span>
            </label>
          );
        })}
      </div>
    </Field>
  );
}

/** Choix de la police : une entrée par fichier (graisse), rendue dans sa propre police. Le modèle garde la famille
 * (nameID 1) et le gras, comme le worker qui choisit le fichier avec FontRegistry.pick. */
export function FontField({
  label = "Police",
  faces,
  family,
  bold,
  onChange,
  fallbackNote,
  className,
}: {
  label?: string;
  faces: FontFaceInfo[];
  family: string;
  bold: boolean;
  onChange: (family: string, bold: boolean) => void;
  fallbackNote: string;
  className?: string;
}) {
  const { face, synthetic } = pickFace(faces, family, bold);
  const groups = (["app", "user", "win"] as const).map((s) => ({ source: s, faces: faces.filter((f) => f.source === s) })).filter((g) => g.faces.length);
  return (
    <Field
      label={label}
      className={className}
      hint={
        !face ? (
          <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
            <TriangleAlert className="size-3" /> « {family} » introuvable sur ce PC : {fallbackNote}
          </span>
        ) : synthetic ? (
          "Pas de graisse grasse dans cette police : gras simulé"
        ) : undefined
      }
    >
      <Select
        value={face?.id ?? ""}
        onValueChange={(id) => {
          const f = faces.find((x) => x.id === id);
          if (f) onChange(f.family, f.isBold);
        }}
      >
        <SelectTrigger className="h-9 w-full" aria-label={label}>
          <SelectValue placeholder={family}>
            {face ? <span style={{ fontFamily: cssFamily(face, "ass", "inherit") }}>{face.fullName}</span> : family}
          </SelectValue>
        </SelectTrigger>
        <SelectContent className="max-h-80">
          {groups.map((g) => (
            <SelectGroup key={g.source}>
              <SelectLabel>{FONT_SOURCE_LABELS[g.source]}</SelectLabel>
              {g.faces.map((f) => (
                <SelectItem key={f.id} value={f.id}>
                  <span className="text-base leading-tight" style={{ fontFamily: cssFamily(f, "ass", "inherit") }}>
                    {f.fullName}
                  </span>
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

/** Position en px du final 1080 × 1920, avec un bouton pour recentrer horizontalement. */
export function PositionFields({
  x,
  y,
  yMin,
  yMax,
  yLabel,
  onChange,
}: {
  x: number;
  y: number;
  yMin: number;
  yMax: number;
  yLabel: string;
  onChange: (pos: { x?: number; y?: number }) => void;
}) {
  return (
    <>
      <SliderField
        label="Horizontal (centre)"
        value={x}
        min={0}
        max={1080}
        unit="px"
        onChange={(v) => onChange({ x: v })}
        hint={
          <Button type="button" variant="link" size="sm" className="h-auto p-0 text-[11px]" onClick={() => onChange({ x: 540 })} disabled={x === 540}>
            <AlignHorizontalJustifyCenter className="size-3" />
            Centrer
          </Button>
        }
      />
      <SliderField label={yLabel} value={y} min={yMin} max={yMax} unit="px" onChange={(v) => onChange({ y: v })} hint="sur 1 920 px de haut" />
    </>
  );
}
