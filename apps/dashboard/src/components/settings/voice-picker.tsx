"use client";

/** Choix d'une voix de narration (moteur + voix) et essai d'écoute (job voice_preview du worker, docs/18-voix.md). */
import * as React from "react";
import { LoaderCircle, Volume2 } from "lucide-react";

import { getVoicePreview, previewVoice } from "@/app/settings/actions";
import type { VoiceEntry, VoiceLang } from "@/lib/generation-types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";

const SAMPLES: Record<VoiceLang, string> = {
  fr: "Derrière ce miroir se cache une pièce que personne n'avait vue depuis cent vingt ans. Regardez bien ce qui se passe quand on l'ouvre.",
  en: "Behind this mirror hides a room nobody had seen for a hundred and twenty years. Watch closely what happens when we open it.",
};
const POLL_MS = 1500;
const HISTORY = 6;

interface Heard {
  key: string;
  voice: string;
  engine: string;
  audioUrl: string;
  durationS: number | null;
  elapsedS: number | null;
}

const seconds = (s: number | null) => (s === null ? "?" : `${s.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} s`);

export function VoicePicker({
  lang,
  label,
  entries,
  value,
  onChange,
  sample,
}: {
  lang: VoiceLang;
  label: string;
  entries: VoiceEntry[];
  value: string;
  onChange: (value: string) => void;
  /** Phrase d'essai de départ (écran de retouche : la narration de la vidéo) ; sinon une phrase type. */
  sample?: string;
}) {
  const [text, setText] = React.useState(sample || SAMPLES[lang]);
  const [waiting, setWaiting] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [heard, setHeard] = React.useState<Heard[]>([]);
  const alive = React.useRef(true);
  React.useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const current = entries.find((e) => e.id === value);
  const engines = [...new Set(entries.map((e) => e.engineLabel))];

  const listen = async () => {
    if (!current) return;
    setError(null);
    setWaiting("Mise en file…");
    const started = await previewVoice({ voice: current.id, lang, text });
    if (!started.ok || !started.jobId) {
      setWaiting(null);
      setError(started.message);
      return;
    }
    while (alive.current) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      const s = await getVoicePreview(started.jobId);
      if (s.status === "done" && s.audioUrl) {
        const item = { key: started.jobId, voice: current.label, engine: current.engineLabel, audioUrl: s.audioUrl, durationS: s.durationS, elapsedS: s.elapsedS };
        setHeard((prev) => [item, ...prev].slice(0, HISTORY));
        setWaiting(null);
        return;
      }
      if (s.status === "failed" || s.status === "cancelled" || s.status === "unknown") {
        setWaiting(null);
        setError(s.error ?? "Essai interrompu");
        return;
      }
      setWaiting(s.status === "queued" ? "En file : passe juste après la tâche en cours sur la carte graphique" : (s.label ?? "Génération…"));
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium" htmlFor={`voice-${lang}`}>
        {label}
      </label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={`voice-${lang}`} className="w-full">
          <SelectValue placeholder="Choisir une voix" />
        </SelectTrigger>
        <SelectContent>
          {engines.map((engine) => (
            <SelectGroup key={engine}>
              <SelectLabel>{engine}</SelectLabel>
              {entries
                .filter((e) => e.engineLabel === engine)
                .map((e) => (
                  <SelectItem key={e.id} value={e.id}>
                    {e.label}
                    {!e.publishable ? " — tests seulement" : ""}
                    {e.missing.length > 0 ? " — à installer" : ""}
                  </SelectItem>
                ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
      {current ? (
        <div className="flex flex-col gap-1.5 text-xs">
          <p className="text-muted-foreground">
            {current.engineLabel}
            {current.detail ? ` · ${current.detail}` : ""}
          </p>
          <div className="flex flex-wrap gap-1.5">
            <Badge
              variant="outline"
              className={current.publishable ? "border-emerald-500/50 text-emerald-700 dark:text-emerald-400" : "border-amber-500/50 text-amber-700 dark:text-amber-400"}
            >
              {current.license}
              {current.publishable ? " · publiable" : ""}
            </Badge>
            {current.missing.length === 0 ? (
              <Badge className="bg-emerald-600 text-white dark:bg-emerald-500">installé</Badge>
            ) : (
              <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-400">
                à installer
              </Badge>
            )}
          </div>
          {current.missing.length > 0 ? <p className="text-muted-foreground font-mono break-all">{current.missing.join(", ")}</p> : null}
        </div>
      ) : null}

      <div className="flex gap-2">
        <Input value={text} onChange={(e) => setText(e.target.value)} maxLength={600} aria-label="Phrase d’essai" />
        <Button type="button" variant="outline" disabled={!current || current.missing.length > 0 || waiting !== null} onClick={listen}>
          {waiting ? <LoaderCircle className="size-4 animate-spin" /> : <Volume2 className="size-4" />}
          Écouter
        </Button>
      </div>
      {waiting ? <p className="text-muted-foreground text-xs" role="status">{waiting}</p> : null}
      {error ? (
        <p className="text-destructive text-xs break-words whitespace-pre-line" role="alert">
          {error.slice(0, 600)}
        </p>
      ) : null}
      {heard.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {heard.map((h, i) => (
            <li key={h.key} className="flex flex-col gap-1 rounded-md border p-2">
              <span className="text-xs">
                <span className="font-medium">{h.voice}</span>
                <span className="text-muted-foreground">
                  {" "}
                  · {h.engine} · {seconds(h.durationS)} de voix, calculée en {seconds(h.elapsedS)}
                </span>
              </span>
              <audio controls autoPlay={i === 0} src={h.audioUrl} className="h-8 w-full" preload="auto" />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
