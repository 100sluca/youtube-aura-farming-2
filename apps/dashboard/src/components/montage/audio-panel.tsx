"use client";

/**
 * Onglet « Son » de l'onglet Montage (docs/26-musique.md) : une musique choisie dans un menu (celle qu'on écoute sur la
 * vidéo de test, à gauche) avec ses réglages — volume, début dans le fichier, et sa fiche : description, formats,
 * ambiances, préférence —, puis les niveaux du modèle (voix IA, musique sous la voix et sa baisse pendant la parole,
 * musique des vidéos sans voix, bruitages). Les niveaux font partie du modèle (bouton Enregistrer) ; les réglages d'une
 * musique s'enregistrent aussitôt, pour tous les modèles.
 */
import * as React from "react";
import { ChevronDown, ChevronUp, FolderOpen, TriangleAlert } from "lucide-react";

import { Field, FormatChecks, Group, Segmented, SliderField, SwitchField } from "@/components/montage/fields";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { formatDuration } from "@/lib/audio-mix";
import { FORMAT_SHORT, type AudioLayer, type MusicLibrary, type MusicTrack, type TestVideo } from "@/lib/montage-types";
import { cn } from "@/lib/utils";

export type TrackPatch = Partial<Pick<MusicTrack, "title" | "description" | "moods" | "formats" | "weight" | "enabled" | "gainDb" | "startS" | "note">>;

const PREFERENCES = [
  { value: "0.5", label: "Moins souvent" },
  { value: "1", label: "Normale" },
  { value: "2", label: "Souvent" },
];

function trackState(t: MusicTrack): string | null {
  return t.missing ? "absente du dossier" : !t.formats.length ? "à décrire" : !t.enabled ? "coupée" : null;
}

function LevelsPanel({ value, onChange }: { value: AudioLayer; onChange: (patch: Partial<AudioLayer>) => void }) {
  const v = value;
  return (
    <div className="flex flex-col gap-5">
      <Group title="Récits narrés : voix et musique">
        <SliderField
          label="Voix IA"
          value={v.voice_db}
          min={-12}
          max={12}
          step={0.5}
          unit="dB"
          onChange={(voice_db) => onChange({ voice_db })}
          hint="0 = voix égalisée automatiquement ; plus haut, elle passe devant la musique"
        />
        <SliderField
          label="Musique sous la voix"
          value={v.music_db}
          min={-30}
          max={0}
          step={0.5}
          unit="dB"
          onChange={(music_db) => onChange({ music_db })}
          hint="écart avec la voix : −10 dB, bien audible sans gêner ; −20 dB, discrète"
        />
        <SliderField
          label="Baisse pendant que la voix parle"
          value={v.duck_db}
          min={0}
          max={15}
          step={0.5}
          unit="dB"
          onChange={(duck_db) => onChange({ duck_db })}
          hint="la musique remonte entre les phrases ; 0 = niveau constant"
        />
      </Group>
      <Group title="Chantiers et visites : sans voix">
        <SliderField
          label="Musique"
          value={v.solo_db}
          min={-20}
          max={12}
          step={0.5}
          unit="dB"
          onChange={(solo_db) => onChange({ solo_db })}
          hint="0 = niveau standard, sous les bruitages"
        />
        <SliderField
          label="Bruitages"
          value={v.sfx_db}
          min={-20}
          max={12}
          step={0.5}
          unit="dB"
          onChange={(sfx_db) => onChange({ sfx_db })}
          hint="engins, portes, passages : 0 = niveau d’origine"
        />
      </Group>
      <Group title="Musique de fond">
        <FormatChecks
          label="Sur"
          value={v.formats}
          onChange={(formats) => onChange({ formats })}
          hints={{ story: "sous la voix", timelapse: "avec les bruitages", tour: "avec les bruitages" }}
          className="sm:col-span-2"
        />
      </Group>
      <p className="text-muted-foreground text-[11px] leading-snug">
        Voix et musiques sont d’abord égalisées (volume réel mesuré). Le mixage final est ramené au niveau des Shorts (−14 LUFS) : ces curseurs règlent
        l’équilibre entre voix, musique et bruitages, pas le volume du téléphone. Ils font partie du modèle : « Enregistrer ».
      </p>
    </div>
  );
}

function MoodChips({ moods, value, onChange }: { moods: MusicLibrary["constants"]["moods"]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {Object.entries(moods).map(([id, [label, hint]]) => {
        const on = value.includes(id);
        return (
          <button
            key={id}
            type="button"
            title={hint}
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((m) => m !== id) : [...value, id])}
            className={cn(
              "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
              on ? "border-primary/60 bg-primary/10 text-foreground" : "text-muted-foreground hover:bg-muted",
            )}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

/** Réglages et fiche de la musique choisie. `key` = id de la piste : les champs repartent de ses valeurs. */
function TrackSettings({
  track,
  moods,
  onChange,
  disabled,
}: {
  track: MusicTrack;
  moods: MusicLibrary["constants"]["moods"];
  onChange: (patch: TrackPatch, now?: boolean) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = React.useState(!track.formats.length && !track.missing);
  const [title, setTitle] = React.useState(track.title);
  const [description, setDescription] = React.useState(track.description);
  const [note, setNote] = React.useState(track.note);
  const maxStart = Math.max(0, Math.floor((track.durationS ?? 60) - 10));
  const state = trackState(track);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="text-muted-foreground">
          {track.file} · {formatDuration(track.durationS)} · {track.lufs === null ? "mesure en attente" : `${track.lufs.toLocaleString("fr-FR")} LUFS mesurés`} ·{" "}
          {track.uses ? `${track.uses} vidéo${track.uses > 1 ? "s" : ""}` : "pas encore utilisée"}
        </span>
        {state ? (
          <Badge variant="outline" className={cn(state === "absente du dossier" ? "text-destructive" : "text-amber-700 dark:text-amber-300")}>
            {state}
          </Badge>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        {track.formats.map((f) => (
          <Badge key={f} variant="secondary">
            {FORMAT_SHORT[f]}
          </Badge>
        ))}
        {track.moods.map((m) => (
          <Badge key={m} variant="outline" title={moods[m]?.[1]}>
            {moods[m]?.[0] ?? m}
          </Badge>
        ))}
        {track.weight !== 1 ? (
          <Badge variant="outline" className="text-muted-foreground">
            {track.weight > 1 ? "Souvent" : track.weight > 0 ? "Moins souvent" : "Jamais tirée"}
          </Badge>
        ) : null}
      </div>
      {track.note ? (
        <p className="flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-300">
          <TriangleAlert className="size-3.5 shrink-0" />
          {track.note}
        </p>
      ) : null}
      <div className="grid grid-cols-1 gap-x-5 gap-y-3 sm:grid-cols-2">
        <SliderField
          label="Volume de cette musique"
          value={track.gainDb}
          min={-12}
          max={12}
          step={0.5}
          unit="dB"
          onChange={(gainDb) => onChange({ gainDb })}
          hint="0 = égalisée comme les autres ; baisse-la si elle couvre la voix"
        />
        {maxStart > 0 ? (
          <SliderField
            label="Début dans le fichier"
            value={Math.min(track.startS, maxStart)}
            min={0}
            max={maxStart}
            step={1}
            unit="s"
            onChange={(startS) => onChange({ startS })}
            hint="pour passer une intro trop calme"
          />
        ) : null}
      </div>
      <div>
        <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? <ChevronUp /> : <ChevronDown />}
          Fiche : description, formats, ambiances, préférence
        </Button>
      </div>
      {open ? (
        <div className="flex flex-col gap-4 rounded-lg border p-3">
          <div className="grid grid-cols-1 gap-x-5 gap-y-3 sm:grid-cols-2">
            <Field label="Nom">
              <Input
                value={title}
                maxLength={80}
                disabled={disabled}
                onChange={(e) => setTitle(e.target.value)}
                onBlur={() => title.trim() && title !== track.title && onChange({ title: title.trim() }, true)}
              />
            </Field>
            <SwitchField
              label="Utiliser cette musique"
              checked={track.enabled}
              onChange={(enabled) => onChange({ enabled }, true)}
              hint="coupée : jamais choisie, même par un nouveau montage"
              className="self-end pb-1"
            />
          </div>
          <Field label="À quoi elle sert">
            <Textarea
              rows={2}
              value={description}
              maxLength={800}
              disabled={disabled}
              onChange={(e) => setDescription(e.target.value)}
              onBlur={() => description !== track.description && onChange({ description: description.trim() }, true)}
            />
          </Field>
          <FormatChecks label="Peut servir pour" value={track.formats} onChange={(formats) => onChange({ formats }, true)} />
          <Field label="Ambiances" hint="Le scénariste donne l’ambiance de chaque histoire ; le montage tire une musique qui la porte.">
            <MoodChips moods={moods} value={track.moods} onChange={(v) => onChange({ moods: v }, true)} />
          </Field>
          <div className="grid grid-cols-1 gap-x-5 gap-y-3 sm:grid-cols-2">
            <Segmented
              label="Préférence"
              value={PREFERENCES.some((p) => Number(p.value) === track.weight) ? String(track.weight) : "1"}
              options={PREFERENCES}
              onChange={(w) => onChange({ weight: Number(w) }, true)}
              hint="« Souvent » : deux fois plus de chances d’être tirée"
            />
            <Field label="Mise en garde">
              <Input
                value={note}
                maxLength={300}
                placeholder="Ex. droits d’auteur à surveiller"
                disabled={disabled}
                onChange={(e) => setNote(e.target.value)}
                onBlur={() => note !== track.note && onChange({ note: note.trim() }, true)}
              />
            </Field>
          </div>
          {track.description ? null : <p className="text-muted-foreground text-[11px]">Description vide : elle ne sert qu’à toi, le choix passe par les formats et les ambiances.</p>}
        </div>
      ) : null}
    </div>
  );
}

export function AudioPanel({
  value,
  onChange,
  library,
  tracks,
  trackId,
  onTrackSelect,
  onTrackChange,
  video,
  mock,
}: {
  value: AudioLayer;
  onChange: (patch: Partial<AudioLayer>) => void;
  library: MusicLibrary;
  tracks: MusicTrack[];
  trackId: string | null;
  onTrackSelect: (id: string) => void;
  onTrackChange: (id: string, patch: TrackPatch, now?: boolean) => void;
  video: TestVideo | null;
  mock: boolean;
}) {
  const { constants } = library;
  const track = tracks.find((t) => t.id === trackId) ?? null;
  const auto = video?.autoTrack ? tracks.find((t) => t.id === video.autoTrack) : undefined;
  const present = tracks.filter((t) => !t.missing);
  const toDescribe = present.filter((t) => !t.formats.length).length;

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <h4 className="text-sm font-semibold">Musique</h4>
          {toDescribe ? (
            <span className="text-xs text-amber-700 dark:text-amber-300">
              {toDescribe} nouvelle{toDescribe > 1 ? "s" : ""} à décrire
            </span>
          ) : null}
        </div>
        {library.error ? <p className="text-destructive text-xs">{library.error}</p> : null}
        <Select value={trackId ?? undefined} onValueChange={onTrackSelect}>
          <SelectTrigger className="h-9 w-full" aria-label="Musique">
            <SelectValue placeholder="Choisir une musique" />
          </SelectTrigger>
          <SelectContent className="max-h-96">
            {tracks.map((t) => {
              const state = trackState(t);
              return (
                <SelectItem key={t.id} value={t.id}>
                  <span>{t.title}</span>
                  <span className="text-muted-foreground text-xs">
                    {" "}
                    · {t.id}
                    {t.id === video?.autoTrack ? " · choix auto pour cette vidéo" : ""}
                    {state ? ` · ${state}` : ""}
                  </span>
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
        {video && auto ? (
          auto.id === trackId ? (
            <p className="text-muted-foreground text-[11px]">C’est la musique que le montage donne à « {video.title} ».</p>
          ) : (
            <p className="text-muted-foreground flex flex-wrap items-center gap-1 text-[11px]">
              Pour « {video.title} », le montage choisirait « {auto.title} ».
              <Button variant="link" size="sm" className="h-auto p-0 text-[11px]" onClick={() => onTrackSelect(auto.id)}>
                L’écouter
              </Button>
            </p>
          )
        ) : null}
        {track ? (
          <TrackSettings key={track.id} track={track} moods={constants.moods} onChange={(patch, now) => onTrackChange(track.id, patch, now)} disabled={mock} />
        ) : (
          <p className="text-muted-foreground text-xs">Aucune musique dans le dossier.</p>
        )}
        <p className="text-muted-foreground flex items-start gap-1 text-[11px] leading-snug" title={library.folder}>
          <FolderOpen className="mt-px size-3.5 shrink-0" />
          <span>
            {present.length} musique{present.length > 1 ? "s" : ""} dans <span className="break-all">{library.folder}</span>. Dépose un fichier audio dans ce
            dossier : il apparaît dans la liste à la prochaine ouverture de la page, à décrire (formats et ambiances) avant de servir. Les réglages d’une musique
            s’enregistrent aussitôt et valent pour tous les modèles.
          </span>
        </p>
      </section>

      <section className="flex flex-col gap-3 border-t pt-4">
        <h4 className="text-sm font-semibold">Niveaux du modèle</h4>
        <LevelsPanel value={value} onChange={onChange} />
      </section>
    </div>
  );
}
