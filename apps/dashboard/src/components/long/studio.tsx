"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowLeft, Check, ChevronLeft, ChevronRight, Circle, Loader2, Mic, Play, Square } from "lucide-react";

import { chooseTake, finishRecording } from "@/app/long/actions";
import { TakeBadge } from "@/components/long/long-detail";
import { NoticeLine } from "@/components/long/long-view";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { getJson } from "@/lib/get-json";
import type { LongJob, LongTake } from "@/lib/long-types";

type Notice = { ok: boolean; message: string } | null;
type Para = { key: string; text: string; chapter: number; chapterTitle: string };
type State = { stage: string; voice_done_at: string | null; error: string | null; takes: LongTake[]; jobs: LongJob[] };

const MIME = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];

const PREF_EVENT = "yt2:studio-pref";

function readPref(key: string, fallback: string): string {
  try {
    return window.localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

/** Préférence du Studio gardée dans ce navigateur (micro choisi, enchaînement) ; la valeur par défaut au rendu serveur. */
function usePref(key: string, fallback: string): [string, (v: string) => void] {
  const value = React.useSyncExternalStore(
    (cb) => {
      window.addEventListener("storage", cb);
      window.addEventListener(PREF_EVENT, cb);
      return () => {
        window.removeEventListener("storage", cb);
        window.removeEventListener(PREF_EVENT, cb);
      };
    },
    () => readPref(key, fallback),
    () => fallback,
  );
  const set = React.useCallback(
    (v: string) => {
      try {
        window.localStorage.setItem(key, v);
      } catch {
        /* navigation privée : préférence non gardée */
      }
      window.dispatchEvent(new Event(PREF_EVENT));
    },
    [key],
  );
  return [value, set];
}

/** Studio voix (docs/63 §4) : le texte en grand comme un prompteur, paragraphe par paragraphe ; Espace pour
 * enregistrer et arrêter ; chaque prise part tout de suite au worker, qui dit (Whisper) si tout le texte est lu. */
export function Studio({ id, title, paragraphs, initial }: { id: string; title: string; paragraphs: Para[]; initial: State }) {
  const [state, setState] = React.useState<State>(initial);
  const chosen = React.useMemo(() => new Map(state.takes.filter((t) => t.chosen).map((t) => [t.para, t])), [state.takes]);
  const firstTodo = Math.max(0, paragraphs.findIndex((p) => !chosen.has(p.key)));
  const [index, setIndex] = React.useState(firstTodo === -1 ? 0 : firstTodo);
  const [recording, setRecording] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [elapsed, setElapsed] = React.useState(0);
  const [level, setLevel] = React.useState(0);
  const [devices, setDevices] = React.useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = usePref("yt2.studio.mic", "");
  const [autoPref, setAutoPref] = usePref("yt2.studio.auto", "1");
  const auto = autoPref === "1";
  const [notice, setNotice] = React.useState<Notice>(null);
  const [micError, setMicError] = React.useState<string | null>(null);
  const [pending, start] = React.useTransition();

  const streamRef = React.useRef<MediaStream | null>(null);
  const recorderRef = React.useRef<MediaRecorder | null>(null);
  const chunksRef = React.useRef<Blob[]>([]);
  const startedRef = React.useRef(0);
  const ctxRef = React.useRef<AudioContext | null>(null);
  const rafRef = React.useRef(0);

  const para = paragraphs[index];
  const take = para ? chosen.get(para.key) : undefined;
  const takesOfPara = para ? state.takes.filter((t) => t.para === para.key) : [];
  const done = paragraphs.filter((p) => chosen.has(p.key) && chosen.get(p.key)!.status !== "failed").length;
  const checking = state.takes.some((t) => t.status === "checking");

  // relecture de l'état : toutes les 2 s pendant une vérification, sinon toutes les 15 s
  React.useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const s = await getJson<State>(`/api/long/${id}/state`);
        if (!stop) setState(s);
      } catch {
        /* réseau : on réessaie au tour suivant */
      }
    };
    const t = window.setInterval(tick, checking ? 2000 : 15000);
    return () => {
      stop = true;
      window.clearInterval(t);
    };
  }, [id, checking]);

  const openMic = React.useCallback(async () => {
    try {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          deviceId: deviceId ? { exact: deviceId } : undefined,
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
          channelCount: 1,
        },
      });
      streamRef.current = stream;
      setMicError(null);
      setDevices((await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput"));
      ctxRef.current?.close().catch(() => undefined);
      const ctx = new AudioContext();
      ctxRef.current = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const buf = new Float32Array(analyser.fftSize);
      const loop = () => {
        analyser.getFloatTimeDomainData(buf);
        let sum = 0;
        for (const x of buf) sum += x * x;
        setLevel(Math.min(1, Math.sqrt(sum / buf.length) * 4));
        rafRef.current = requestAnimationFrame(loop);
      };
      cancelAnimationFrame(rafRef.current);
      loop();
    } catch (e) {
      setMicError(e instanceof Error ? e.message : String(e));
    }
  }, [deviceId]);

  React.useEffect(() => {
    const t = window.setTimeout(() => void openMic(), 0);
    return () => {
      window.clearTimeout(t);
      cancelAnimationFrame(rafRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      ctxRef.current?.close().catch(() => undefined);
    };
  }, [openMic]);

  React.useEffect(() => {
    if (!recording) return;
    const t = window.setInterval(() => setElapsed((Date.now() - startedRef.current) / 1000), 200);
    return () => window.clearInterval(t);
  }, [recording]);

  const upload = React.useCallback(
    async (blob: Blob, key: string) => {
      setUploading(true);
      try {
        const form = new FormData();
        form.append("para", key);
        form.append("file", blob, `${key}.webm`);
        const res = await fetch(`/api/long/${id}/take`, { method: "POST", body: form });
        const out = (await res.json()) as { ok: boolean; message: string; take_id?: string; take?: number };
        setNotice({ ok: out.ok, message: out.message });
        if (out.ok && out.take_id) {
          setState((s) => ({
            ...s,
            takes: [
              { id: out.take_id!, para: key, take: out.take ?? 1, status: "checking", chosen: true, duration_s: null, check: null, created_at: new Date().toISOString() },
              ...s.takes.map((t) => (t.para === key ? { ...t, chosen: false } : t)),
            ],
          }));
        }
      } catch (e) {
        setNotice({ ok: false, message: `Envoi impossible : ${e instanceof Error ? e.message : String(e)}` });
      } finally {
        setUploading(false);
      }
    },
    [id],
  );

  const startRec = React.useCallback(() => {
    const stream = streamRef.current;
    if (!stream || !para) {
      void openMic();
      return;
    }
    const mimeType = MIME.find((m) => MediaRecorder.isTypeSupported(m)) ?? "";
    const rec = new MediaRecorder(stream, { mimeType, audioBitsPerSecond: 160000 });
    chunksRef.current = [];
    rec.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
    const key = para.key;
    rec.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" });
      if (blob.size > 2000) void upload(blob, key);
    };
    rec.start(250);
    recorderRef.current = rec;
    startedRef.current = Date.now();
    setElapsed(0);
    setRecording(true);
    setNotice(null);
  }, [para, openMic, upload]);

  const stopRec = React.useCallback(() => {
    recorderRef.current?.stop();
    recorderRef.current = null;
    setRecording(false);
    if (auto) setIndex((i) => Math.min(paragraphs.length - 1, i + 1));
  }, [auto, paragraphs.length]);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement | null)?.isContentEditable) return;
      if (e.code === "Space") {
        e.preventDefault();
        if (recording) stopRec();
        else if (!uploading) startRec();
      } else if (!recording && e.key === "ArrowRight") {
        setIndex((i) => Math.min(paragraphs.length - 1, i + 1));
      } else if (!recording && e.key === "ArrowLeft") {
        setIndex((i) => Math.max(0, i - 1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [recording, uploading, startRec, stopRec, paragraphs.length]);

  if (!para) return <p className="text-muted-foreground">Pas de texte à lire.</p>;
  const prev = paragraphs[index - 1];
  const next = paragraphs[index + 1];
  const newChapter = !prev || prev.chapter !== para.chapter;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link href={`/long/${id}`}>
            <ArrowLeft /> Fiche
          </Link>
        </Button>
        <span className="truncate font-medium">{title}</span>
        <span className="text-muted-foreground text-sm">
          {done}/{paragraphs.length} paragraphes
        </span>
        <div className="flex items-center gap-2">
          <Mic className="size-4" />
          <div className="h-2 w-28 overflow-hidden rounded bg-muted">
            <div className={`h-full ${level > 0.85 ? "bg-red-500" : "bg-emerald-500"}`} style={{ width: `${Math.round(level * 100)}%` }} />
          </div>
        </div>
        <Select
          value={deviceId || "default"}
          onValueChange={(v) => {
            setDeviceId(v === "default" ? "" : v);
          }}
        >
          <SelectTrigger className="w-56">
            <SelectValue placeholder="Micro" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="default">Micro par défaut</SelectItem>
            {devices
              .filter((d) => d.deviceId && d.deviceId !== "default")
              .map((d) => (
                <SelectItem key={d.deviceId} value={d.deviceId}>
                  {d.label || "Micro"}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
        <label className="flex items-center gap-2 text-sm">
          <Switch
            checked={auto}
            onCheckedChange={(v) => setAutoPref(v ? "1" : "0")}
          />
          Enchaîner
        </label>
        <Button
          variant="outline"
          onClick={() => start(async () => setNotice(await finishRecording(id)))}
          disabled={pending || done < paragraphs.length || checking}
        >
          <Check /> Terminer l’enregistrement
        </Button>
      </div>
      {micError ? <p className="text-destructive text-sm">Micro indisponible : {micError}. Autorise le micro pour cette page dans le navigateur.</p> : null}
      <NoticeLine result={notice} />

      <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
        <nav className="flex max-h-[70vh] flex-col gap-1 overflow-y-auto pr-1 text-xs">
          {paragraphs.map((p, i) => {
            const t = chosen.get(p.key);
            const dot = !t ? "bg-muted-foreground/30" : t.status === "ok" ? "bg-emerald-500" : t.status === "checking" ? "bg-violet-500" : t.status === "problem" ? "bg-amber-500" : "bg-red-500";
            const head = i === 0 || paragraphs[i - 1].chapter !== p.chapter;
            return (
              <React.Fragment key={p.key}>
                {head ? <p className="text-muted-foreground mt-2 font-semibold">{p.chapter === 0 ? "Ouverture" : `Ch. ${p.chapter} · ${p.chapterTitle}`}</p> : null}
                <button
                  type="button"
                  disabled={recording}
                  onClick={() => setIndex(i)}
                  className={`flex items-center gap-2 rounded px-2 py-1 text-left ${i === index ? "bg-accent" : "hover:bg-accent/50"}`}
                >
                  <span className={`size-2 shrink-0 rounded-full ${dot}`} />
                  <span className="truncate">{p.text.slice(0, 40)}</span>
                </button>
              </React.Fragment>
            );
          })}
        </nav>

        <div className="flex flex-col items-center gap-6">
          {newChapter ? (
            <p className="text-sm font-semibold tracking-wide text-amber-600 uppercase dark:text-amber-400">
              {para.chapter === 0 ? "Ouverture" : `Chapitre ${para.chapter} — ${para.chapterTitle}`}
            </p>
          ) : null}
          {prev ? <p className="text-muted-foreground line-clamp-2 max-w-3xl text-center text-base">{prev.text}</p> : null}
          <p className={`max-w-3xl text-[28px] leading-[1.55] font-medium ${recording ? "text-foreground" : "text-foreground/90"}`}>{para.text}</p>
          {next ? <p className="text-muted-foreground line-clamp-2 max-w-3xl text-center text-base">{next.text}</p> : null}

          <div className="flex items-center gap-4">
            <Button variant="ghost" size="icon" onClick={() => setIndex((i) => Math.max(0, i - 1))} disabled={recording || index === 0}>
              <ChevronLeft />
            </Button>
            {recording ? (
              <Button size="lg" className="h-16 rounded-full bg-red-600 px-8 text-white hover:bg-red-700" onClick={stopRec}>
                <Square className="fill-current" /> Arrêter · {elapsed.toFixed(0)} s
              </Button>
            ) : (
              <Button size="lg" className="h-16 rounded-full px-8" onClick={startRec} disabled={uploading || Boolean(micError)}>
                {uploading ? <Loader2 className="animate-spin" /> : <Circle className="fill-red-500 text-red-500" />}
                {uploading ? "Envoi…" : take ? "Refaire" : "Enregistrer"}
              </Button>
            )}
            <Button variant="ghost" size="icon" onClick={() => setIndex((i) => Math.min(paragraphs.length - 1, i + 1))} disabled={recording || index === paragraphs.length - 1}>
              <ChevronRight />
            </Button>
          </div>
          <p className="text-muted-foreground text-xs">Espace : enregistrer / arrêter · ← → : paragraphe précédent / suivant · reformuler est permis, c’est ce que tu dis qui compte.</p>

          <div className="flex w-full max-w-3xl flex-col gap-2">
            {takesOfPara.length ? (
              takesOfPara.map((t) => (
                <div key={t.id} className={`flex flex-wrap items-center gap-3 rounded-lg border p-2 text-sm ${t.chosen ? "border-emerald-500/60" : ""}`}>
                  <TakeBadge take={t} />
                  <audio src={`/api/long/${id}/file?k=take&t=${t.id}`} controls preload="none" className="h-8 w-64" />
                  {t.check?.ratio != null ? <span className="text-muted-foreground text-xs">texte lu à {Math.round(t.check.ratio * 100)} %</span> : null}
                  {t.check?.missing?.length ? <span className="text-xs text-amber-600">Sauté : « {t.check.missing.join(" » · « ")} »</span> : null}
                  {t.check?.silent ? <span className="text-xs text-red-600">Aucune voix entendue</span> : null}
                  {!t.chosen ? (
                    <Button size="sm" variant="outline" onClick={() => start(async () => setNotice(await chooseTake(id, t.id)))} disabled={pending}>
                      <Play /> Garder celle-ci
                    </Button>
                  ) : null}
                </div>
              ))
            ) : (
              <p className="text-muted-foreground text-center text-sm">Pas encore de prise pour ce paragraphe.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
