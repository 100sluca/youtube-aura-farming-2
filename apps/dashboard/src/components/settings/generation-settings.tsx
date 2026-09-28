"use client";

import * as React from "react";
import { CircleAlert, CircleCheck, CircleX, Clapperboard } from "lucide-react";

import { saveGenerationSettings } from "@/app/settings/actions";
import type { CatalogEntry, GenerationCatalog, GenerationSettings, VoiceLang } from "@/lib/generation-types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { VoicePicker } from "@/components/settings/voice-picker";

const VOICE_LABELS: Record<VoiceLang, string> = { fr: "Voix française", en: "Voix anglaise" };

function Notice({ result }: { result: { ok: boolean; message: string } | null }) {
  if (!result) return null;
  return (
    <p className={`flex items-center gap-1.5 text-xs ${result.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`} role="status">
      {result.ok ? <CircleCheck className="size-3.5" /> : <CircleX className="size-3.5" />}
      {result.message}
    </p>
  );
}

function EntryStatus({ entry }: { entry: CatalogEntry | undefined }) {
  if (!entry) return null;
  const warn = "border-amber-500/50 text-amber-700 dark:text-amber-400";
  return (
    <div className="flex flex-col gap-1.5 text-xs">
      <p className="text-muted-foreground">{entry.detail}</p>
      <div className="flex flex-wrap gap-1.5">
        <Badge variant="outline" className={entry.publishable ? "border-emerald-500/50 text-emerald-700 dark:text-emerald-400" : warn}>
          {entry.license}
          {entry.publishable ? " · publiable" : ""}
        </Badge>
        {entry.missing === null ? (
          <Badge variant="outline">installation non vérifiée</Badge>
        ) : entry.missing.length === 0 ? (
          <Badge className="bg-emerald-600 text-white dark:bg-emerald-500">installé</Badge>
        ) : (
          <Badge variant="outline" className={warn}>
            {entry.missing.length} fichier{entry.missing.length > 1 ? "s" : ""} à installer
          </Badge>
        )}
      </div>
      {entry.missing && entry.missing.length > 0 ? <p className="text-muted-foreground font-mono break-all">{entry.missing.join(", ")}</p> : null}
    </div>
  );
}

function ModelSelect({
  id,
  label,
  entries,
  value,
  onChange,
}: {
  id: string;
  label: string;
  entries: CatalogEntry[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium" htmlFor={id}>
        {label}
      </label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder="Choisir un modèle" />
        </SelectTrigger>
        <SelectContent>
          {entries.map((e) => (
            <SelectItem key={e.name} value={e.name}>
              {e.label}
              {!e.publishable ? " — tests seulement" : ""}
              {e.missing && e.missing.length > 0 ? " — à installer" : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <EntryStatus entry={entries.find((e) => e.name === value)} />
    </div>
  );
}

export function GenerationSettingsCard({ initial, catalog }: { initial: GenerationSettings; catalog: GenerationCatalog }) {
  const [image, setImage] = React.useState(initial.image_workflow);
  const [video, setVideo] = React.useState(initial.video_workflow);
  const [candidates, setCandidates] = React.useState(String(initial.storyboard_candidates));
  const [voices, setVoices] = React.useState(initial.voices);
  const [pending, startTransition] = React.useTransition();
  const [notice, setNotice] = React.useState<{ ok: boolean; message: string } | null>(null);

  const save = () =>
    startTransition(async () =>
      setNotice(await saveGenerationSettings({ image_workflow: image, video_workflow: video, storyboard_candidates: Number(candidates), voices })),
    );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clapperboard className="size-4" />
          Modèles de génération
        </CardTitle>
        <CardDescription>
          Les modèles locaux (ComfyUI) qui dessinent les images du storyboard puis les animent, et la voix de la narration. Chaque
          nouvelle production retient les modèles choisis ici ; pour comparer, ouvrir une production et « Refaire avec les réglages actuels ».
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {!catalog.comfyOnline ? (
          <p className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm" role="status">
            <CircleAlert className="size-4 shrink-0 text-amber-600" />
            ComfyUI est éteint : impossible de vérifier quels modèles sont installés. Le choix reste enregistrable.
          </p>
        ) : null}

        <section className="grid gap-6 md:grid-cols-2">
          <ModelSelect id="gen-image" label="Images du storyboard" entries={catalog.image} value={image} onChange={setImage} />
          <ModelSelect id="gen-video" label="Animation des images (vidéo)" entries={catalog.video} value={video} onChange={setVideo} />
        </section>

        <section className="grid gap-4 sm:grid-cols-3">
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium" htmlFor="gen-candidates">
              Images par scène
            </label>
            <Select value={candidates} onValueChange={setCandidates}>
              <SelectTrigger id="gen-candidates" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {["1", "2", "3", "4"].map((n) => (
                  <SelectItem key={n} value={n}>
                    {n} image{n === "1" ? "" : "s"} au choix
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </section>

        <section className="flex flex-col gap-3">
          <div>
            <h3 className="text-sm font-semibold">Voix de la narration</h3>
            <p className="text-muted-foreground text-xs">
              Plusieurs moteurs de voix, rangés par moteur dans la liste. « Écouter » fait dire la phrase par la voix choisie sur ce PC
              (juste après la tâche en cours sur la carte graphique), sans rien enregistrer : on peut comparer avant de choisir.
            </p>
          </div>
          <div className="grid gap-6 md:grid-cols-2">
            {(["fr", "en"] as VoiceLang[]).map((lang) => (
              <VoicePicker
                key={lang}
                lang={lang}
                label={VOICE_LABELS[lang]}
                entries={catalog.voices[lang]}
                value={voices[lang]}
                onChange={(v) => setVoices((prev) => ({ ...prev, [lang]: v }))}
              />
            ))}
          </div>
        </section>

        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={pending} onClick={save}>
            Enregistrer les modèles
          </Button>
          <Notice result={notice} />
        </div>
      </CardContent>
    </Card>
  );
}
