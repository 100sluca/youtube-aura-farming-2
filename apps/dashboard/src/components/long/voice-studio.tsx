"use client";

import * as React from "react";
import { Loader2, Mic, Pause, Play, RotateCcw, Save, Square, Trash2, Wand2 } from "lucide-react";

import { deleteVoiceProfile, saveVoiceProfile, setVoiceModifier } from "@/app/long/actions";
import { NoticeLine } from "@/components/long/long-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { getJson } from "@/lib/get-json";
import type { VoiceStudioData } from "@/lib/long";
import {
  formatModValue,
  isNeutral,
  NEUTRAL_PARAMS,
  sameParams,
  VOICE_MOD_ENGINES,
  VOICE_MOD_FIELDS,
  VOICE_MOD_PREFIX,
  type VoiceModEngine,
  type VoiceModField,
  type VoiceModParams,
  type VoiceProfile,
} from "@/lib/voice-mods";

type Notice = { ok: boolean; message: string } | null;
type Source = { take: string } | { sample: string } | null;
type Trial = { status: "idle" | "running" | "ready" | "error"; original?: string; modified?: string; message?: string; slow?: boolean };
type Side = "original" | "modified";

const MIME = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
const SAMPLES = "__extraits";
const MAX_REC_S = 30;

const fileUrl = (name: string) => `/api/voice-studio/file?f=${encodeURIComponent(name)}`;
const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

function clock(s: number): string {
  const v = Math.max(0, Math.floor(s));
  return `${Math.floor(v / 60)}:${String(v % 60).padStart(2, "0")}`;
}

/** Studio du modificateur de voix (docs/67) : un extrait (une prise ou un enregistrement), des curseurs, et l'écoute
 * avant / après au même endroit et au même niveau ; chaque curseur relâché relance un essai (quelques secondes). */
export function VoiceStudio({ data, videoId }: { data: VoiceStudioData; videoId: string | null }) {
  const [profiles, setProfiles] = React.useState<VoiceProfile[]>(data.profiles);
  const [profileId, setProfileId] = React.useState(data.profiles[0]?.id ?? "");
  const [name, setName] = React.useState(data.profiles[0]?.name ?? "");
  const [params, setParams] = React.useState<VoiceModParams>(data.profiles[0]?.params ?? NEUTRAL_PARAMS);
  const [committed, setCommitted] = React.useState<VoiceModParams>(params);
  const [samples, setSamples] = React.useState(data.samples);
  const firstVideo = data.sources.find((s) => s.id === videoId) ?? data.sources[0];
  const [group, setGroup] = React.useState<string>(firstVideo?.id ?? (data.samples.length ? SAMPLES : ""));
  const [source, setSource] = React.useState<Source>(
    firstVideo?.takes[0] ? { take: firstVideo.takes[0].id } : data.samples[0] ? { sample: data.samples[0].name } : null,
  );
  const [trial, setTrial] = React.useState<Trial>({ status: "idle" });
  const [notice, setNotice] = React.useState<Notice>(null);
  const [pending, start] = React.useTransition();

  const profile = profiles.find((p) => p.id === profileId);
  const dirty = !profile || !sameParams(profile.params, params) || profile.name !== name.trim();

  // ---- essais ------------------------------------------------------------------------------------------------------
  const reqRef = React.useRef(0);
  const runTrial = React.useCallback(async (src: Source, p: VoiceModParams) => {
    if (!src) return;
    const n = ++reqRef.current;
    setTrial((t) => ({ ...t, status: "running", message: undefined, slow: false }));
    try {
      const res = await fetch("/api/voice-studio", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ ...src, params: p }) });
      const out = (await res.json()) as { ok: boolean; message: string; job?: string };
      if (!out.ok || !out.job) throw new Error(out.message);
      const started = Date.now();
      for (;;) {
        await sleep(350);
        if (n !== reqRef.current) return;
        const j = await getJson<{ status: string; result: { original: string; modified: string } | null; error: string | null }>(`/api/voice-studio?job=${out.job}`);
        if (j.status === "done" && j.result) {
          setTrial({ status: "ready", original: j.result.original, modified: j.result.modified });
          return;
        }
        if (j.status === "failed" || j.status === "cancelled") throw new Error(j.error || "essai en échec");
        if (Date.now() - started > 6000) setTrial((t) => ({ ...t, slow: true }));
        if (Date.now() - started > 180000) throw new Error("le worker ne répond pas (bloc Machine de la barre latérale)");
      }
    } catch (e) {
      if (n === reqRef.current) setTrial((t) => ({ ...t, status: "error", message: e instanceof Error ? e.message : String(e) }));
    }
  }, []);

  const sourceKey = source ? JSON.stringify(source) : "";
  const paramsKey = JSON.stringify(committed);
  React.useEffect(() => {
    const t = window.setTimeout(() => void runTrial(source, committed), 150);
    return () => window.clearTimeout(t);
    // sourceKey / paramsKey : relancer seulement quand l'extrait ou un réglage relâché change vraiment
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceKey, paramsKey, runTrial]);

  // ---- écoute avant / après ----------------------------------------------------------------------------------------
  const origRef = React.useRef<HTMLAudioElement>(null);
  const modRef = React.useRef<HTMLAudioElement>(null);
  const [side, setSide] = React.useState<Side>("modified");
  const [playing, setPlaying] = React.useState(false);
  const [time, setTime] = React.useState(0);
  const [duration, setDuration] = React.useState(0);
  const posRef = React.useRef(0);
  const playingRef = React.useRef(false);
  const el = React.useCallback((s: Side) => (s === "original" ? origRef.current : modRef.current), []);

  const play = React.useCallback(
    (s: Side) => {
      const a = el(s);
      if (!a) return;
      if (Math.abs(a.currentTime - posRef.current) > 0.05) a.currentTime = Math.min(posRef.current, a.duration || posRef.current);
      void a.play().catch(() => undefined);
      playingRef.current = true;
      setPlaying(true);
    },
    [el],
  );
  const pause = React.useCallback(() => {
    origRef.current?.pause();
    modRef.current?.pause();
    playingRef.current = false;
    setPlaying(false);
  }, []);
  const switchTo = React.useCallback(
    (s: Side) => {
      if (s === side) return;
      el(side)?.pause();
      setSide(s);
      if (playingRef.current) play(s);
      else {
        const a = el(s);
        if (a) a.currentTime = Math.min(posRef.current, a.duration || posRef.current);
      }
    },
    [side, el, play],
  );
  const seek = (v: number) => {
    posRef.current = v;
    setTime(v);
    const a = el(side);
    if (a) a.currentTime = v;
  };

  // nouvel essai chargé pendant l'écoute : on reprend au même endroit
  const onLoaded = (s: Side) => {
    const a = el(s);
    if (!a) return;
    if (s === "original") setDuration(a.duration || 0);
    a.currentTime = Math.min(posRef.current, a.duration || 0);
    if (s === side && playingRef.current) void a.play().catch(() => undefined);
  };
  const onTime = (s: Side) => {
    const a = el(s);
    if (!a || s !== side) return;
    posRef.current = a.currentTime;
    setTime(a.currentTime);
  };

  // nouvel extrait : on repart du début
  React.useEffect(() => {
    posRef.current = 0;
    setTime(0);
  }, [trial.original]);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (["INPUT", "TEXTAREA"].includes(target.tagName) || target.isContentEditable || target.getAttribute("role") === "slider")) return;
      if (e.code === "Space") {
        e.preventDefault();
        if (playingRef.current) pause();
        else play(side);
      } else if (e.key === "a" || e.key === "A") {
        switchTo(side === "original" ? "modified" : "original");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [side, play, pause, switchTo]);

  // ---- enregistrer un extrait ----------------------------------------------------------------------------------------
  const [recording, setRecording] = React.useState(false);
  const [recElapsed, setRecElapsed] = React.useState(0);
  const recRef = React.useRef<MediaRecorder | null>(null);
  const stopTimer = React.useRef<number>(0);

  const stopRec = React.useCallback(() => {
    window.clearTimeout(stopTimer.current);
    recRef.current?.stop();
    recRef.current = null;
    setRecording(false);
  }, []);

  const startRec = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
      });
      const mimeType = MIME.find((m) => MediaRecorder.isTypeSupported(m)) ?? "";
      const rec = new MediaRecorder(stream, { mimeType, audioBitsPerSecond: 160000 });
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
        const form = new FormData();
        form.append("file", blob, "extrait.webm");
        const res = await fetch("/api/voice-studio", { method: "POST", body: form });
        const out = (await res.json()) as { ok: boolean; message: string; sample?: string };
        setNotice({ ok: out.ok, message: out.message });
        if (out.ok && out.sample) {
          setSamples((s) => [{ name: out.sample!, at: new Date().toISOString() }, ...s]);
          setGroup(SAMPLES);
          setSource({ sample: out.sample });
        }
      };
      rec.start(250);
      recRef.current = rec;
      const t0 = Date.now();
      setRecElapsed(0);
      setRecording(true);
      stopTimer.current = window.setTimeout(stopRec, MAX_REC_S * 1000);
      const tick = window.setInterval(() => {
        if (!recRef.current) window.clearInterval(tick);
        else setRecElapsed((Date.now() - t0) / 1000);
      }, 200);
    } catch (e) {
      setNotice({ ok: false, message: `Micro indisponible : ${e instanceof Error ? e.message : String(e)}` });
    }
  };

  // ---- réglages -----------------------------------------------------------------------------------------------------
  const setField = (key: VoiceModField["key"], v: number, commit: boolean) => {
    const next = { ...params, [key]: v };
    setParams(next);
    if (commit) setCommitted(next);
  };
  const applyParams = (p: VoiceModParams) => {
    setParams(p);
    setCommitted(p);
  };
  const chooseProfile = (id: string) => {
    setProfileId(id);
    const p = profiles.find((x) => x.id === id);
    setName(p?.name ?? "");
    applyParams(p?.params ?? NEUTRAL_PARAMS);
    setNotice(null);
  };

  const save = (then?: (id: string) => Promise<{ ok: boolean; message: string }>) =>
    start(async () => {
      const res = await saveVoiceProfile(profileId, name, params);
      if (!res.ok || !res.id) {
        setNotice(res);
        return;
      }
      const id = res.id;
      const saved: VoiceProfile = { id, name: name.trim(), params };
      setProfiles((list) => (list.some((p) => p.id === id) ? list.map((p) => (p.id === id ? saved : p)) : [...list, saved]));
      setProfileId(id);
      setNotice(then ? await then(id) : res);
    });

  const remove = () =>
    start(async () => {
      const res = await deleteVoiceProfile(profileId);
      setNotice(res);
      if (res.ok) {
        setProfiles((list) => list.filter((p) => p.id !== profileId));
        setProfileId("");
        setName("");
      }
    });

  const takes = data.sources.find((s) => s.id === group)?.takes ?? [];
  const sourceValue = source && "take" in source ? source.take : source?.sample ?? "";

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Extrait</CardTitle>
          <CardDescription>Les 25 premières secondes d’une de tes prises, ou un extrait enregistré ici (30 s au plus).</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-2">
          <Select
            value={group}
            onValueChange={(g) => {
              setGroup(g);
              const first = g === SAMPLES ? (samples[0] ? { sample: samples[0].name } : null) : (data.sources.find((s) => s.id === g)?.takes[0] ? { take: data.sources.find((s) => s.id === g)!.takes[0].id } : null);
              setSource(first);
            }}
          >
            <SelectTrigger className="w-72">
              <SelectValue placeholder="Aucune prise" />
            </SelectTrigger>
            <SelectContent>
              {data.sources.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.title}
                </SelectItem>
              ))}
              {samples.length ? <SelectItem value={SAMPLES}>Mes extraits enregistrés</SelectItem> : null}
            </SelectContent>
          </Select>
          <Select value={sourceValue} onValueChange={(v) => setSource(group === SAMPLES ? { sample: v } : { take: v })}>
            <SelectTrigger className="w-96 max-w-full">
              <SelectValue placeholder="Choisis un passage" />
            </SelectTrigger>
            <SelectContent>
              {group === SAMPLES
                ? samples.map((s) => (
                    <SelectItem key={s.name} value={s.name}>
                      Extrait du {new Date(s.at).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                    </SelectItem>
                  ))
                : takes.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.label}
                    </SelectItem>
                  ))}
            </SelectContent>
          </Select>
          {recording ? (
            <Button variant="destructive" onClick={stopRec}>
              <Square /> Arrêter ({clock(recElapsed)} / {clock(MAX_REC_S)})
            </Button>
          ) : (
            <Button variant="outline" onClick={() => void startRec()}>
              <Mic /> Enregistrer un extrait
            </Button>
          )}
        </CardContent>
      </Card>

      <Card className="sticky top-16 z-20">
        <CardContent className="flex flex-col gap-3 pt-6">
          <div className="flex flex-wrap items-center gap-3">
            <Button size="icon" onClick={() => (playing ? pause() : play(side))} disabled={!trial.original} aria-label={playing ? "Pause" : "Écouter"}>
              {playing ? <Pause /> : <Play />}
            </Button>
            <div className="bg-muted inline-flex rounded-md p-0.5">
              {(["original", "modified"] as const).map((s) => (
                <Button key={s} size="sm" variant={side === s ? "default" : "ghost"} onClick={() => switchTo(s)}>
                  {s === "original" ? "Ta voix" : "Modifiée"}
                </Button>
              ))}
            </div>
            <span className="text-muted-foreground font-mono text-xs tabular-nums">
              {clock(time)} / {clock(duration)}
            </span>
            <span className="text-muted-foreground flex items-center gap-1.5 text-xs">
              {trial.status === "running" ? (
                <>
                  <Loader2 className="size-3.5 animate-spin" />
                  {trial.slow ? "Le worker finit une autre tâche…" : "Essai en cours…"}
                </>
              ) : trial.status === "error" ? (
                <span className="text-destructive">{trial.message}</span>
              ) : trial.status === "ready" ? (
                isNeutral(committed) ? "Aucun changement : les deux sont identiques" : "Prêt"
              ) : null}
            </span>
          </div>
          <Slider value={[time]} min={0} max={Math.max(duration, 0.1)} step={0.05} onValueChange={([v]) => seek(v)} disabled={!trial.original} />
          <p className="text-muted-foreground text-xs">Espace : écouter / pause · A : passer de ta voix à la voix modifiée, au même endroit. Les deux sont au même volume.</p>
          {trial.original ? (
            <audio ref={origRef} src={fileUrl(trial.original)} preload="auto" onLoadedMetadata={() => onLoaded("original")} onTimeUpdate={() => onTime("original")} onEnded={pause} hidden />
          ) : null}
          {trial.modified ? (
            <audio ref={modRef} src={fileUrl(trial.modified)} preload="auto" onLoadedMetadata={() => onLoaded("modified")} onTimeUpdate={() => onTime("modified")} onEnded={pause} hidden />
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Réglage</CardTitle>
          <CardDescription>Petits pas : quelques demi-tons ou quelques pour cent suffisent pour que la voix change sans sonner faux.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <div className="flex flex-wrap items-center gap-2">
            <Select value={profileId || "__nouveau"} onValueChange={(v) => chooseProfile(v === "__nouveau" ? "" : v)}>
              <SelectTrigger className="w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectLabel>Mes réglages</SelectLabel>
                  {profiles.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                  <SelectItem value="__nouveau">Nouveau réglage</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nom du réglage" className="w-56" maxLength={60} />
            <Button onClick={() => save()} disabled={pending || !name.trim() || !dirty}>
              <Save /> Enregistrer
            </Button>
            {videoId ? (
              <Button
                variant="outline"
                onClick={() => save((id) => setVoiceModifier(videoId, true, VOICE_MOD_PREFIX + id))}
                disabled={pending || !name.trim()}
              >
                <Wand2 /> Enregistrer et appliquer à la vidéo
              </Button>
            ) : null}
            {profile ? (
              <Button variant="ghost" onClick={remove} disabled={pending}>
                <Trash2 /> Supprimer
              </Button>
            ) : null}
            <Button variant="ghost" onClick={() => applyParams({ ...NEUTRAL_PARAMS, engine: params.engine })} disabled={isNeutral(params)}>
              <RotateCcw /> Tout remettre à zéro
            </Button>
          </div>
          <NoticeLine result={notice} />

          <div className="grid gap-8 lg:grid-cols-2">
            {(["voix", "son"] as const).map((g) => (
              <div key={g} className="flex flex-col gap-5">
                <h3 className="text-sm font-medium">{g === "voix" ? "La voix" : "Le son"}</h3>
                {VOICE_MOD_FIELDS.filter((f) => f.group === g).map((f) => (
                  <div key={f.key} className="flex flex-col gap-2">
                    <div className="flex items-baseline justify-between gap-2 text-sm">
                      <span>{f.label}</span>
                      <button
                        type="button"
                        className="text-muted-foreground hover:text-foreground font-mono text-xs tabular-nums"
                        title="Remettre au neutre"
                        onClick={() => setField(f.key, f.neutral, true)}
                      >
                        {formatModValue(f, params[f.key])}
                      </button>
                    </div>
                    <Slider
                      value={[params[f.key]]}
                      min={f.min}
                      max={f.max}
                      step={f.step}
                      onValueChange={([v]) => setField(f.key, v, false)}
                      onValueCommit={([v]) => setField(f.key, v, true)}
                    />
                    <p className="text-muted-foreground text-xs">{f.hint}</p>
                  </div>
                ))}
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted-foreground">Méthode pour la hauteur et le timbre</span>
            <Select value={params.engine} onValueChange={(v) => applyParams({ ...params, engine: v as VoiceModEngine })}>
              <SelectTrigger className="w-60">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {VOICE_MOD_ENGINES.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-muted-foreground text-xs">{VOICE_MOD_ENGINES.find((m) => m.id === params.engine)?.hint}</span>
          </div>
          {!videoId ? (
            <p className="text-muted-foreground text-xs">
              Pour t’en servir : onglet Voix d’une vidéo longue, choisis ce réglage, puis « Appliquer à mes prises ». La voix et le montage se refont sans
              rien réenregistrer.
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
