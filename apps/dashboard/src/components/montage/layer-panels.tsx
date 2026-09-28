"use client";

/** Réglages de chaque couche du modèle de montage : titre d'accroche, sous-titres, textes à l'écran (docs/23-montage.md). */
import { AlignCenter, AlignLeft, AlignRight } from "lucide-react";

import { ColorField, Field, FontField, FormatChecks, Group, PositionFields, Segmented, SliderField, SwitchField } from "@/components/montage/fields";
import { Button } from "@/components/ui/button";
import { PRESET_LABELS, type FontFaceInfo, type HookLayer, type SubtitleLayer, type SubtitleStyle, type TitleLayer } from "@/lib/montage-types";

export function HookPanel({ value, onChange, faces }: { value: HookLayer; onChange: (patch: Partial<HookLayer>) => void; faces: FontFaceInfo[] }) {
  const v = value;
  return (
    <div className="flex flex-col gap-5">
      <Group title="Quand">
        <FormatChecks value={v.formats} onChange={(formats) => onChange({ formats })} className="sm:col-span-2" />
        <Segmented
          label="Durée à l’écran"
          value={v.duration_s === null ? "all" : "first"}
          options={[
            { value: "all", label: "Toute la vidéo" },
            { value: "first", label: "Les premières secondes" },
          ]}
          onChange={(mode) => onChange({ duration_s: mode === "all" ? null : (v.duration_s ?? 3) })}
        />
        {v.duration_s !== null ? (
          <SliderField label="Affiché pendant" value={v.duration_s} min={1} max={15} step={0.5} unit="s" onChange={(duration_s) => onChange({ duration_s })} />
        ) : null}
      </Group>

      <Group title="Texte">
        <FontField faces={faces} family={v.font_family} bold={v.bold} onChange={(font_family, bold) => onChange({ font_family, bold })} fallbackNote="Arial Black au montage" />
        <SliderField label="Taille" value={v.size} min={24} max={200} unit="px" onChange={(size) => onChange({ size })} />
        <ColorField label="Couleur du texte" value={v.text_color} onChange={(text_color) => onChange({ text_color })} />
        <SwitchField label="Tout en majuscules" checked={v.uppercase} onChange={(uppercase) => onChange({ uppercase })} className="self-end pb-1" />
      </Group>

      <Group title="Fond">
        <Segmented
          label="Style"
          className="sm:col-span-2"
          value={v.background}
          options={[
            { value: "plate", label: "Une plaque par ligne", title: "Style TikTok (MJClipIt)" },
            { value: "block", label: "Un seul bloc" },
            { value: "none", label: "Aucun, texte contouré" },
          ]}
          onChange={(background) => onChange({ background })}
        />
        {v.background !== "none" ? (
          <>
            <ColorField label="Couleur du fond" value={v.background_color} onChange={(background_color) => onChange({ background_color })} />
            <SliderField label="Opacité" value={v.background_opacity} min={0} max={1} step={0.05} percent onChange={(background_opacity) => onChange({ background_opacity })} />
            <SliderField label="Arrondi des coins" value={v.radius} min={0} max={80} unit="px" onChange={(radius) => onChange({ radius })} />
            <SliderField label="Marge horizontale" value={v.padding_x} min={0} max={120} unit="px" onChange={(padding_x) => onChange({ padding_x })} />
            <SliderField label="Marge verticale" value={v.padding_y} min={0} max={100} unit="px" onChange={(padding_y) => onChange({ padding_y })} />
          </>
        ) : (
          <>
            <ColorField label="Couleur du contour" value={v.outline_color} onChange={(outline_color) => onChange({ outline_color })} />
            <SliderField label="Épaisseur du contour" value={v.outline_width} min={0} max={24} unit="px" onChange={(outline_width) => onChange({ outline_width })} />
          </>
        )}
      </Group>

      <Group title="Mise en page">
        <SliderField label="Largeur maximale" value={v.width_pct} min={0.3} max={1} step={0.01} percent onChange={(width_pct) => onChange({ width_pct })} hint="au-delà, le titre passe à la ligne" />
        <SliderField label="Interligne" value={v.line_spacing} min={0.8} max={2} step={0.05} unit="×" onChange={(line_spacing) => onChange({ line_spacing })} />
        <Segmented
          label="Alignement des lignes"
          value={v.align}
          options={[
            { value: "left", label: <AlignLeft className="size-4" />, title: "À gauche" },
            { value: "center", label: <AlignCenter className="size-4" />, title: "Centré" },
            { value: "right", label: <AlignRight className="size-4" />, title: "À droite" },
          ]}
          onChange={(align) => onChange({ align })}
        />
      </Group>

      <Group title="Position">
        <PositionFields x={v.x} y={v.y} yMin={0} yMax={1800} yLabel="Haut du titre" onChange={(pos) => onChange(pos)} />
      </Group>
    </div>
  );
}

export function SubtitlesPanel({
  value,
  onChange,
  faces,
  presets,
}: {
  value: SubtitleLayer;
  onChange: (patch: Partial<SubtitleLayer>) => void;
  faces: FontFaceInfo[];
  presets: Record<string, SubtitleStyle>;
}) {
  const v = value;
  return (
    <div className="flex flex-col gap-5">
      <Group title="Quand">
        <SwitchField
          label="Sous-titres mot à mot"
          checked={v.enabled}
          onChange={(enabled) => onChange({ enabled })}
          hint="Sur les vidéos narrées (récits) : ils suivent la voix. Les chantiers et les visites n’ont pas de voix."
          className="sm:col-span-2"
        />
        <Field label="Partir d’un style" className="sm:col-span-2" hint="Applique police, couleurs, contour, animation… ; la position ne change pas.">
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(presets).map(([key, style]) => (
              <Button key={key} type="button" size="sm" variant="outline" onClick={() => onChange({ ...style })}>
                {PRESET_LABELS[key] ?? key}
              </Button>
            ))}
          </div>
        </Field>
      </Group>

      <Group title="Texte">
        <FontField faces={faces} family={v.font_family} bold={v.bold} onChange={(font_family, bold) => onChange({ font_family, bold })} fallbackNote="police système au montage" />
        <SliderField label="Taille" value={v.font_size} min={24} max={220} onChange={(font_size) => onChange({ font_size })} hint="taille des sous-titres (hauteur d’une ligne en px)" />
        <Segmented
          label="Casse"
          value={v.text_transform}
          options={[
            { value: "none", label: "Normale" },
            { value: "uppercase", label: "MAJ." },
            { value: "lowercase", label: "min." },
            { value: "capitalize", label: "Mots" },
          ]}
          onChange={(text_transform) => onChange({ text_transform })}
        />
        <SliderField label="Espacement des lettres" value={v.letter_spacing} min={-5} max={30} step={0.5} unit="px" onChange={(letter_spacing) => onChange({ letter_spacing })} />
        <ColorField label="Couleur du texte" value={v.text_color} onChange={(text_color) => onChange({ text_color })} />
        <SwitchField label="Italique" checked={v.italic} onChange={(italic) => onChange({ italic })} className="self-end pb-1" />
      </Group>

      <Group title="Mot prononcé">
        <Segmented
          label="Mise en avant"
          value={v.highlight_mode}
          options={[
            { value: "none", label: "Aucune" },
            { value: "word", label: "Mot coloré" },
            { value: "karaoke", label: "Karaoké" },
          ]}
          onChange={(highlight_mode) => onChange({ highlight_mode })}
        />
        {v.highlight_mode !== "none" ? <ColorField label="Couleur d’accent" value={v.highlight_color} onChange={(highlight_color) => onChange({ highlight_color })} /> : null}
      </Group>

      <Group title="Contour et ombre">
        <ColorField label="Couleur du contour" value={v.outline_color} onChange={(outline_color) => onChange({ outline_color })} />
        <SliderField label="Épaisseur du contour" value={v.outline_width} min={0} max={20} step={0.5} unit="px" onChange={(outline_width) => onChange({ outline_width })} />
        <ColorField label="Couleur de l’ombre" value={v.shadow_color} onChange={(shadow_color) => onChange({ shadow_color })} />
        <SliderField label="Opacité de l’ombre" value={v.shadow_opacity} min={0} max={1} step={0.05} percent onChange={(shadow_opacity) => onChange({ shadow_opacity })} />
        {v.shadow_opacity > 0 ? (
          <>
            <SliderField label="Distance" value={v.shadow_distance} min={0} max={40} unit="px" onChange={(shadow_distance) => onChange({ shadow_distance })} />
            <SliderField label="Angle de la lumière" value={v.shadow_angle} min={0} max={359} unit="°" onChange={(shadow_angle) => onChange({ shadow_angle })} />
            <SliderField label="Flou" value={v.shadow_blur} min={0} max={20} step={0.5} unit="px" onChange={(shadow_blur) => onChange({ shadow_blur })} />
          </>
        ) : null}
      </Group>

      <Group title="Fond">
        <Segmented
          label="Boîte derrière la légende"
          value={v.background}
          options={[
            { value: "none", label: "Aucune" },
            { value: "box", label: "Boîte" },
          ]}
          onChange={(background) => onChange({ background })}
          hint={v.background === "box" ? "L’ombre n’est pas dessinée sous une boîte." : undefined}
        />
        {v.background === "box" ? (
          <>
            <ColorField label="Couleur de la boîte" value={v.background_color} onChange={(background_color) => onChange({ background_color })} />
            <SliderField label="Opacité" value={v.background_opacity} min={0} max={1} step={0.05} percent onChange={(background_opacity) => onChange({ background_opacity })} />
            <SliderField label="Marge" value={v.background_padding} min={0} max={80} unit="px" onChange={(background_padding) => onChange({ background_padding })} />
          </>
        ) : null}
      </Group>

      <Group title="Découpage et animation">
        <SliderField label="Mots par légende (max.)" value={v.max_words} min={1} max={8} onChange={(max_words) => onChange({ max_words })} />
        <SliderField label="Caractères par ligne (max.)" value={v.max_chars} min={6} max={60} onChange={(max_chars) => onChange({ max_chars })} hint="deux lignes au plus" />
        <Segmented
          label="Apparition"
          className="sm:col-span-2"
          value={v.animation}
          options={[
            { value: "none", label: "Aucune" },
            { value: "pop", label: "Pop" },
            { value: "bounce", label: "Rebond" },
            { value: "fade", label: "Fondu" },
            { value: "slide_up", label: "Glisse" },
          ]}
          onChange={(animation) => onChange({ animation })}
        />
      </Group>

      <Group title="Position">
        <PositionFields x={v.x} y={v.y} yMin={40} yMax={1880} yLabel="Centre vertical" onChange={(pos) => onChange(pos)} />
      </Group>
    </div>
  );
}

export function TitlesPanel({ value, onChange, faces }: { value: TitleLayer; onChange: (patch: Partial<TitleLayer>) => void; faces: FontFaceInfo[] }) {
  const v = value;
  return (
    <div className="flex flex-col gap-5">
      <Group title="Quand">
        <p className="text-muted-foreground text-xs sm:col-span-2">
          Des repères posés sur l’image en plus des sous-titres, pour montrer le temps qui passe ou l’endroit où l’on est. Coche les types de vidéos où
          ils apparaissent ; un texte trop large rapetisse pour tenir dans l’image.
        </p>
        <FormatChecks
          value={v.formats}
          onChange={(formats) => onChange({ formats })}
          className="sm:col-span-2"
          hints={{
            story: "Une courte légende par scène (« 1 an plus tard ») ; en général inutile, les sous-titres suffisent",
            timelapse: "Les jours qui défilent (Jour 1 → Jour 120)",
            tour: "Le nom de chaque pièce (« Salon · 60 m² »)",
          }}
        />
      </Group>

      <Group title="Texte">
        <FontField faces={faces} family={v.font_family} bold={v.bold} onChange={(font_family, bold) => onChange({ font_family, bold })} fallbackNote="police système au montage" />
        <SliderField label="Taille" value={v.size} min={24} max={220} onChange={(size) => onChange({ size })} hint="comme les sous-titres (hauteur d’une ligne en px)" />
        <ColorField label="Couleur du texte" value={v.text_color} onChange={(text_color) => onChange({ text_color })} />
        <SwitchField label="Tout en majuscules" checked={v.uppercase} onChange={(uppercase) => onChange({ uppercase })} className="self-end pb-1" />
      </Group>

      <Group title="Fond">
        <Segmented
          label="Style"
          className="sm:col-span-2"
          value={v.background}
          options={[
            { value: "box", label: "Boîte" },
            { value: "outline", label: "Texte contouré" },
            { value: "none", label: "Texte seul" },
          ]}
          onChange={(background) => onChange({ background })}
        />
        {v.background === "box" ? (
          <>
            <ColorField label="Couleur de la boîte" value={v.box_color} onChange={(box_color) => onChange({ box_color })} />
            <SliderField label="Opacité" value={v.box_opacity} min={0} max={1} step={0.05} percent onChange={(box_opacity) => onChange({ box_opacity })} />
            <SliderField label="Marge" value={v.padding} min={0} max={80} unit="px" onChange={(padding) => onChange({ padding })} />
          </>
        ) : v.background === "outline" ? (
          <>
            <ColorField label="Couleur du contour" value={v.outline_color} onChange={(outline_color) => onChange({ outline_color })} />
            <SliderField label="Épaisseur du contour" value={v.outline_width} min={0} max={20} step={0.5} unit="px" onChange={(outline_width) => onChange({ outline_width })} />
          </>
        ) : null}
      </Group>

      <Group title="Position">
        <PositionFields x={v.x} y={v.y} yMin={40} yMax={1880} yLabel="Centre vertical" onChange={(pos) => onChange(pos)} />
      </Group>
    </div>
  );
}
