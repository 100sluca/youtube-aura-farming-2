"use client";

/**
 * Corriger les plans d'une vidéo montée (Bibliothèque → Retoucher → Plans, docs/38 §6 et docs/49 §7). Demande de Luca
 * (29/09) devant « Mamie Pomme » : regarder la vidéo d'une traite avec le numéro du plan affiché, puis dire en une phrase
 * ce qui ne va pas sur un plan et le faire refaire. Puis (01/10, « Tout le collège le détestait ») : corriger toutes les
 * voix d'un coup, sans refaire la vidéo à chaque réplique.
 *
 * - la consigne de chaque plan s'enregistre pendant qu'elle s'écrit ;
 * - « Nouvelles prises de voix » redit toutes les répliques qui ont une consigne, en un lot, sans toucher à la vidéo ;
 * - chaque prise s'écoute, avec ce que Whisper y entend (une réplique dite en anglais se voit tout de suite), et se
 *   valide ou non ; refusée, sa consigne se rouvre et le plan repart au lot suivant ; validée, on passe au plan suivant ;
 * - quand toutes les prises sont jugées : un seul rendu complet avec les prises validées.
 * « Refaire le clip » refait toujours l'animation d'un plan, puis remonte la vidéo.
 *
 * Puis (01/10, même vidéo) : une prise à écouter se voit en bleu dans le menu et s'ouvre d'un bouton ; la consigne de jeu
 * de base (voix du personnage, ton de la réplique) s'affiche, et celle que la voix a reçue sur chaque prise ; « Prendre
 * cette voix » fait de la voix du clip brut (celle du modèle vidéo) une prise ; la consigne d'un plan sans réplique ne
 * compte plus parmi les voix à redire (elle sert au clip).
 *
 * Puis (01/10 soir, même vidéo) : « Couper le son » — cocher les plans dont le son du clip n'apporte rien (bruits,
 * ambiance trop forte), puis un seul bouton refait la vidéo ; un plan parlé garde sa réplique (voix isolée), la musique
 * continue (docs/49 §13).
 */
import * as React from "react";
import { Check, Clapperboard, Ear, History, LoaderCircle, Mic, Play, TriangleAlert, VolumeX, X } from "lucide-react";

import { applyTakes, keepTake, muteClips, redoPlan, retakeVoices, savePlanNote, takeClipVoice } from "@/app/library/retouch-actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { formatDuration } from "@/lib/audio-mix";
import { formatDateTime } from "@/lib/format";
import { TAKE_OK, type RetouchPlan } from "@/lib/retouch-types";
import { cn } from "@/lib/utils";

type Result = { ok: boolean; message: string };

/** Le plan affiché à l'instant `t` de la vidéo montée. */
export function planAt(plans: RetouchPlan[], t: number): RetouchPlan | null {
  return plans.find((p) => t >= p.start - 0.001 && t < p.end) ?? (plans.length && t >= plans[plans.length - 1].start ? plans[plans.length - 1] : null);
}

const excerpt = (text: string, n = 42) => (text.length > n ? `${text.slice(0, n - 1).trimEnd()}…` : text);
const SAVE_MS = 700;
/** Ce que Whisper entend, sans les guillemets qu'il ajoute parfois. */
const said = (text: string) => text.replace(/[«»"“”]/g, "").replace(/\s+/g, " ").trim() || "rien";

type VoiceState = "note" | "listen" | "kept" | "refused" | "clip";

/** Où en est la voix d'un plan, pour le menu et les compteurs. Plan sans réplique : sa consigne sert au clip, aucune
 * voix n'est à redire (le lot de prises le saute). */
function voiceState(plan: RetouchPlan, note: string, keep: boolean | null | undefined): VoiceState | null {
  if (plan.take && keep === null) return "listen";
  if (plan.take && keep === false) return "refused";
  if (note.trim()) return plan.line ? "note" : "clip";
  if (plan.take && keep === true) return "kept";
  return null;
}
const STATE_LABEL: Record<VoiceState, string> = {
  note: "consigne prête",
  listen: "prise à écouter",
  kept: "prise validée",
  refused: "prise refusée",
  clip: "consigne pour le clip",
};
/** Couleur de chaque état dans le menu des plans : une prise à écouter saute aux yeux (demande de Luca, 01/10). */
const STATE_CLASS: Record<VoiceState, string> = {
  listen: "text-sky-600 dark:text-sky-400",
  note: "text-amber-700 dark:text-amber-400",
  refused: "text-destructive",
  kept: "text-emerald-600 dark:text-emerald-400",
  clip: "text-muted-foreground",
};
const ENGINE_LABEL: Record<string, string> = {
  gemini: "Gemini",
  qwen3: "Qwen3 (local)",
  qwen3_emotion: "Qwen3, références émues (local)",
  qwen3_instruct: "Qwen3 VoiceDesign (local)",
};

export function PlansPanel({
  videoId,
  plans,
  muted = [],
  now,
  locked,
  confirm,
  onSeek,
  onResult,
}: {
  videoId: string;
  plans: RetouchPlan[];
  muted?: number[]; // plans au son du clip coupé (videos.retouch.muted)
  now: number;
  locked: boolean;
  confirm?: string | null; // vidéo déjà programmée sur YouTube : question posée avant de la refaire (docs/44)
  onSeek: (t: number) => void;
  onResult: (res: Result) => void;
}) {
  const [follow, setFollow] = React.useState(true);
  const [chosen, setChosen] = React.useState<number | null>(null);
  const [notes, setNotes] = React.useState<Record<number, string>>(() => Object.fromEntries(plans.map((p) => [p.index, p.draft])));
  // décision prise à l'instant, par prise (identifiant du fichier) : une nouvelle prise repart « à écouter »
  const [keeps, setKeeps] = React.useState<Record<string, boolean | null>>({});
  const [saved, setSaved] = React.useState<Record<number, "saving" | "saved" | "error">>({});
  const [mute, setMute] = React.useState<Set<number>>(() => new Set(muted));
  const [pending, startTransition] = React.useTransition();
  const timers = React.useRef<Record<number, ReturnType<typeof setTimeout>>>({});
  const noteRef = React.useRef<HTMLTextAreaElement | null>(null);

  React.useEffect(() => () => Object.values(timers.current).forEach(clearTimeout), []);

  const keepOf = (p: RetouchPlan) => (p.take && p.take.asset_id in keeps ? keeps[p.take.asset_id] : (p.take?.keep ?? null));
  const noteOf = (p: RetouchPlan) => notes[p.index] ?? "";
  const states = plans.map((p) => ({ plan: p, state: voiceState(p, noteOf(p), keepOf(p)) }));
  const count = (s: string) => states.filter((x) => x.state === s).length;
  const toRedo = count("note") + count("refused");
  const toListen = count("listen");
  const kept = plans.filter((p) => p.take && keepOf(p) === true).length;

  const current = planAt(plans, now);
  const picked = plans.find((p) => p.index === chosen) ?? null;
  // Le plan affiché suit la tête de lecture, sauf dès qu'un plan est choisi ou qu'une consigne s'écrit (« Suivre la
  // vidéo » le remet en suivi)
  const plan = (follow && chosen === null ? current : (picked ?? current)) ?? plans[0];
  if (!plan) return <p className="text-muted-foreground text-sm">Pas de plans pour cette vidéo.</p>;
  const note = noteOf(plan);
  const keep = keepOf(plan);
  const busy = locked || pending;

  const go = (p: RetouchPlan) => {
    setChosen(p.index);
    onSeek(p.start);
  };
  const choose = (value: string) => {
    const next = plans.find((p) => String(p.index) === value);
    if (next) go(next);
  };
  const write = (value: string) => {
    const index = plan.index;
    setChosen(index);
    setNotes((cur) => ({ ...cur, [index]: value }));
    setSaved((cur) => ({ ...cur, [index]: "saving" }));
    clearTimeout(timers.current[index]);
    timers.current[index] = setTimeout(async () => {
      const res = await savePlanNote(videoId, index, value).catch(() => ({ ok: false, message: "" }));
      setSaved((cur) => ({ ...cur, [index]: res.ok ? "saved" : "error" }));
    }, SAVE_MS);
  };
  const judge = (value: boolean) => {
    const index = plan.index;
    const take = plan.take?.asset_id ?? "";
    setKeeps((cur) => ({ ...cur, [take]: value }));
    startTransition(async () => {
      const res = await keepTake(videoId, index, value);
      if (!res.ok) {
        setKeeps((cur) => ({ ...cur, [take]: plan.take?.keep ?? null }));
        onResult(res);
        return;
      }
      if (!value) {
        // refusée : la consigne se rouvre, partie de la précédente, pour en donner une autre
        if (!noteOf(plan).trim() && plan.take?.note) write(plan.take.note);
        setTimeout(() => noteRef.current?.focus(), 0);
        return;
      }
      // validée : le plan suivant qui attend une écoute (sinon le suivant qui a une consigne)
      const after = plans.filter((p) => p.position > plan.position);
      const next =
        after.find((p) => p.take && keepOf(p) === null) ??
        plans.find((p) => p.index !== index && p.take && keepOf(p) === null) ??
        after.find((p) => noteOf(p).trim());
      if (next) go(next);
    });
  };
  const flush = async () => {
    // consignes encore en attente d'enregistrement : enregistrées avant le lot
    const waiting = Object.entries(timers.current);
    for (const [k, t] of waiting) {
      clearTimeout(t);
      await savePlanNote(videoId, Number(k), notes[Number(k)] ?? "");
    }
    timers.current = {};
  };
  const retake = () =>
    startTransition(async () => {
      await flush();
      onResult(await retakeVoices(videoId));
    });
  const render = () => {
    if (confirm && !window.confirm(confirm)) return;
    startTransition(async () => onResult(await applyTakes(videoId)));
  };
  const redoClip = () => {
    if (confirm && !window.confirm(confirm)) return;
    startTransition(async () => {
      await flush();
      const res = await redoPlan(videoId, { scene: plan.index, clip: true, voice: false, note });
      onResult(res);
      if (res.ok) write("");
    });
  };
  const clipVoice = () =>
    startTransition(async () => {
      await flush();
      onResult(await takeClipVoice(videoId, plan.index));
    });
  // Couper le son : la sélection en cours face à celle de la vidéo, appliquée en un seul rendu
  const savedMute = new Set(muted);
  const muteChanged = mute.size !== savedMute.size || [...mute].some((i) => !savedMute.has(i));
  const toggleMute = (index: number, on: boolean) =>
    setMute((cur) => {
      const next = new Set(cur);
      if (on) next.add(index);
      else next.delete(index);
      return next;
    });
  const applyMute = () => {
    if (confirm && !window.confirm(confirm)) return;
    startTransition(async () => {
      await flush();
      onResult(await muteClips(videoId, [...mute]));
    });
  };
  const muteLabel = !muteChanged
    ? mute.size
      ? `Son coupé sur ${mute.size} plan${mute.size > 1 ? "s" : ""}`
      : "Coche les plans à couper"
    : mute.size
      ? `Couper le son de ${mute.size} plan${mute.size > 1 ? "s" : ""} et refaire la vidéo`
      : "Rendre le son à tous les plans et refaire la vidéo";
  // Prochaine prise à écouter : après le plan affiché, sinon la première
  const listening = states.filter((x) => x.state === "listen").map((x) => x.plan);
  const nextListen = listening.find((p) => p.position > plan.position) ?? listening.find((p) => p.index !== plan.index) ?? null;
  const listenHere = voiceState(plan, note, keep) === "listen";

  const heardBad = plan.heard && plan.heard.ratio < TAKE_OK;
  const takeBad = plan.take?.ratio !== null && plan.take?.ratio !== undefined && plan.take.ratio < TAKE_OK;
  const doubtful = plans.filter((p) => p.heard && p.heard.ratio < TAKE_OK && !p.take);

  return (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground text-[11px] leading-snug">
        Regarde la vidéo : le numéro du plan s’affiche dessus et ce menu le suit. Sur chaque plan dont la voix ne va pas, écris ta consigne (elle s’enregistre seule),
        puis demande toutes les nouvelles prises d’un coup. Écoute chaque prise, valide-la ou non ; quand toutes sont jugées, refais la vidéo une seule fois.
      </p>

      <section className="flex flex-col gap-2 rounded-lg border p-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant={toRedo ? "default" : "secondary"}>{toRedo} à redire</Badge>
          <Badge variant="secondary" className={cn(toListen && "bg-sky-500/15 text-sky-700 dark:text-sky-300")}>
            {toListen} à écouter
          </Badge>
          <Badge variant="secondary">{kept} validée{kept > 1 ? "s" : ""}</Badge>
          {doubtful.length ? (
            <span className="flex items-center gap-1 text-amber-700 dark:text-amber-400">
              <TriangleAlert className="size-3.5" />
              {doubtful.length} réplique{doubtful.length > 1 ? "s" : ""} douteuse{doubtful.length > 1 ? "s" : ""} dans la vidéo (plans {doubtful.map((p) => p.position + 1).join(", ")})
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {nextListen ? (
            <Button className="bg-sky-600 text-white hover:bg-sky-500 dark:bg-sky-500 dark:hover:bg-sky-400" onClick={() => go(nextListen)}>
              <Ear />
              Écouter la prise du plan {nextListen.position + 1}
            </Button>
          ) : null}
          <Button onClick={retake} disabled={busy || !toRedo}>
            {pending ? <LoaderCircle className="animate-spin" /> : <Mic />}
            Nouvelles prises de voix ({toRedo})
          </Button>
          <Button variant={toListen ? "outline" : "default"} onClick={render} disabled={busy || !kept || toListen > 0}>
            <Clapperboard />
            Refaire la vidéo avec {kept} prise{kept > 1 ? "s" : ""} validée{kept > 1 ? "s" : ""}
          </Button>
        </div>
        {toListen && kept ? <p className="text-muted-foreground text-[11px]">Écoute d’abord les {toListen} prises qui restent, puis la vidéo se refait en une fois.</p> : null}
      </section>

      <section className="flex flex-col gap-2 rounded-lg border p-3">
        <h4 className="flex items-center gap-1.5 text-sm font-semibold">
          <VolumeX className="size-4" />
          Couper le son de plans
        </h4>
        <p className="text-muted-foreground text-[11px] leading-snug">
          Coche les plans dont le son du clip n’apporte rien (bruits, ambiance trop forte), puis refais la vidéo une fois. Un plan avec une réplique la garde : seule la voix
          reste, isolée du bruit. La musique continue. Décoche un plan pour lui rendre son son.
        </p>
        <div className="grid max-h-72 grid-cols-1 gap-x-3 gap-y-1 overflow-y-auto sm:grid-cols-2">
          {plans.map((p) => (
            <div key={p.index} className={cn("flex min-w-0 items-center gap-2 rounded-md px-1.5 py-1 text-xs", mute.has(p.index) && "bg-muted")}>
              <Checkbox
                checked={mute.has(p.index)}
                disabled={busy}
                onCheckedChange={(on) => toggleMute(p.index, on === true)}
                aria-label={`Couper le son du plan ${p.position + 1}`}
              />
              <button type="button" className="hover:text-primary min-w-0 truncate text-left" onClick={() => go(p)} title="Voir ce plan dans la vidéo">
                <span className="font-medium">Plan {p.position + 1}</span>
                <span className="text-muted-foreground"> · {p.line ? `« ${excerpt(p.line, 30)} »` : "sans réplique"}</span>
              </button>
              {savedMute.has(p.index) ? <VolumeX className="text-muted-foreground ml-auto size-3.5 shrink-0" aria-label="son coupé dans la vidéo" /> : null}
            </div>
          ))}
        </div>
        <div>
          <Button variant={muteChanged ? "default" : "outline"} onClick={applyMute} disabled={busy || !muteChanged}>
            {pending ? <LoaderCircle className="animate-spin" /> : <VolumeX />}
            {muteLabel}
          </Button>
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <Select value={String(plan.index)} onValueChange={choose}>
          <SelectTrigger
            className={cn("h-9 min-w-0 flex-1", listenHere && "border-sky-500/60 bg-sky-500/10")}
            aria-label="Plan"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="max-h-96">
            {states.map(({ plan: p, state }) => (
              <SelectItem key={p.index} value={String(p.index)} className={cn(state === "listen" && "bg-sky-500/10")}>
                {state === "listen" ? <Ear className="size-3.5 text-sky-600 dark:text-sky-400" /> : null}
                <span className={cn("font-medium", state === "listen" && STATE_CLASS.listen)}>Plan {p.position + 1}</span>
                <span className={cn("text-xs", state === "listen" ? STATE_CLASS.listen : "text-muted-foreground")}>
                  {" "}
                  · {p.speaker ?? "sans réplique"}
                  {p.line ? ` · « ${excerpt(p.line, 34)} »` : ""}
                  {state ? (
                    <>
                      {" · "}
                      <span className={cn("font-medium", STATE_CLASS[state])}>{STATE_LABEL[state]}</span>
                    </>
                  ) : p.heard && p.heard.ratio < TAKE_OK ? (
                    " · voix douteuse"
                  ) : (
                    ""
                  )}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="flex items-center gap-2 text-xs">
          <Switch
            checked={follow && chosen === null}
            onCheckedChange={(on) => {
              setFollow(on);
              if (on) setChosen(null);
            }}
            aria-label="Suivre la vidéo"
          />
          Suivre la vidéo
        </label>
      </div>

      <section className="flex flex-col gap-3 rounded-lg border p-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant={current?.index === plan.index ? "default" : "secondary"}>Plan {plan.position + 1}</Badge>
          <span className="text-muted-foreground tabular-nums">
            {formatDuration(plan.start)} → {formatDuration(plan.end)}
          </span>
          <Button type="button" size="sm" variant="ghost" className="ml-auto h-7 px-2" onClick={() => onSeek(plan.start)}>
            <Play className="size-3.5" />
            Voir dans la vidéo
          </Button>
        </div>
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_9rem]">
          <div className="flex min-w-0 flex-col gap-1.5 text-sm">
            <p>
              <span className="text-muted-foreground">Qui parle : </span>
              <span className="font-medium">{plan.speaker ?? "personne (plan sans réplique)"}</span>
            </p>
            {plan.characters.length ? (
              <p>
                <span className="text-muted-foreground">À l’image : </span>
                {plan.characters.join(", ")}
              </p>
            ) : null}
            {plan.line ? <p className="leading-snug">« {plan.line} »</p> : null}
            {plan.direction && (plan.direction.tone || plan.direction.voice) ? (
              <p className="text-muted-foreground text-xs leading-snug" title="Ce que la voix reçoit avec la réplique, en plus de « parle français, mot pour mot » ; avec Gemini, ta consigne s’y ajoute">
                <span className="text-foreground font-medium">Jeu demandé à la voix</span>
                {plan.direction.tone ? ` : ton « ${plan.direction.tone} »` : ""}
                {plan.direction.voice ? `${plan.direction.tone ? " ;" : " :"} personnage « ${plan.direction.voice} »` : ""}
              </p>
            ) : null}
            {plan.replaced ? (
              <p className="text-muted-foreground flex items-start gap-1 text-xs leading-snug">
                <Mic className="mt-px size-3.5 shrink-0" />
                Réplique dite par une prise de synthèse validée, à la place de la voix du clip.
              </p>
            ) : null}
            {plan.heard ? (
              <p className={cn("flex items-start gap-1 text-xs leading-snug", heardBad ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground")}>
                {heardBad ? <TriangleAlert className="mt-px size-3.5 shrink-0" /> : <Ear className="mt-px size-3.5 shrink-0" />}
                <span>
                  Entendu dans la vidéo : « {said(plan.heard.text)} »{heardBad ? " : ce n’est pas la réplique (autre langue ?), à redire" : ""}
                </span>
              </p>
            ) : null}
          </div>
          {plan.clipAssetId ? (
            <figure className="flex flex-col gap-1">
              <video
                key={plan.clipAssetId}
                src={`/api/media/${plan.clipAssetId}`}
                controls
                playsInline
                preload="metadata"
                className="aspect-[9/16] w-full rounded-md bg-black object-contain"
              />
              <figcaption className="text-muted-foreground text-[10px] leading-tight">Le clip brut, avec la voix du modèle vidéo : on voit quelle bouche bouge.</figcaption>
              {plan.line ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-auto py-1.5 text-xs whitespace-normal"
                  onClick={clipVoice}
                  disabled={busy}
                  title="La voix de ce clip, coupée à la réplique et mise au niveau des autres, devient une prise à écouter puis valider (≈ 1 min)"
                >
                  <Mic />
                  Prendre cette voix
                </Button>
              ) : null}
            </figure>
          ) : null}
        </div>

        {plan.take ? (
          <div
            className={cn(
              "flex flex-col gap-2 rounded-md border p-2.5",
              keep === true && "border-emerald-500/50 bg-emerald-500/5",
              keep === false && "border-destructive/40 bg-destructive/5",
              keep === null && "border-sky-500/50 bg-sky-500/5",
            )}
          >
            <p className={cn("flex flex-wrap items-center gap-2 text-xs font-medium", keep === null && "text-sky-700 dark:text-sky-300")}>
              {plan.take.source === "clip" ? <Clapperboard className="size-3.5" /> : <Mic className="size-3.5" />}
              {plan.take.source === "clip" ? "Voix du clip" : "Nouvelle prise"} · {keep === null ? "à écouter" : keep ? "validée" : "refusée"}
              {plan.take.note && plan.take.source !== "clip" ? (
                <span className="text-muted-foreground font-normal">· consigne « {excerpt(plan.take.note, 60)} »</span>
              ) : null}
            </p>
            <audio key={plan.take.asset_id} src={`/api/media/${plan.take.asset_id}`} controls preload="metadata" className="h-8 w-full" />
            {plan.take.direction || plan.take.engine ? (
              <p className="text-muted-foreground text-[11px] leading-snug">
                {plan.take.engine ? `Dite par ${ENGINE_LABEL[plan.take.engine] ?? plan.take.engine}` : "Reçu par la voix"}
                {plan.take.direction ? ` · jeu reçu : « ${plan.take.direction} »` : ""}
              </p>
            ) : plan.take.source === "clip" ? (
              <p className="text-muted-foreground text-[11px] leading-snug">La voix que le modèle vidéo a donnée au plan, coupée à ses paroles et mise au niveau des autres répliques.</p>
            ) : null}
            {plan.take.heard !== null ? (
              <p className={cn("flex items-start gap-1 text-xs leading-snug", takeBad ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground")}>
                {takeBad ? <TriangleAlert className="mt-px size-3.5 shrink-0" /> : <Ear className="mt-px size-3.5 shrink-0" />}
                Entendu : « {said(plan.take.heard)} »{takeBad ? " : pas la réplique, sans doute pas en français" : ""}
              </p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant={keep === true ? "default" : "outline"} onClick={() => judge(true)} disabled={busy}>
                <Check />
                Oui, je valide cette prise
              </Button>
              <Button size="sm" variant={keep === false ? "destructive" : "outline"} onClick={() => judge(false)} disabled={busy}>
                <X />
                Non, je ne la valide pas
              </Button>
            </div>
          </div>
        ) : null}

        <Textarea
          ref={noteRef}
          rows={2}
          value={note}
          disabled={busy}
          maxLength={600}
          onChange={(e) => write(e.target.value)}
          placeholder={
            plan.line
              ? "Ta consigne pour ce plan. Ex. : en français, plus lentement ; ou : c’est l’ananas qui parle, pas la mère."
              : "Ta consigne pour ce plan. Ex. : la mère se tait, l’ananas regarde la caméra."
          }
          aria-label="Consigne pour ce plan"
          className="text-sm"
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={redoClip} disabled={busy}>
            <Clapperboard />
            Refaire le clip
          </Button>
          <span className="text-muted-foreground text-[11px]">
            {saved[plan.index] === "saving"
              ? "Enregistrement…"
              : saved[plan.index] === "error"
                ? "Consigne pas enregistrée (migration 0038 ?)"
                : note.trim()
                  ? plan.line
                    ? "Consigne enregistrée : la voix sera redite au prochain lot."
                    : "Consigne enregistrée pour « Refaire le clip » : plan sans réplique, il n’y a pas de voix à redire."
                  : ""}
          </span>
        </div>
        <p className="text-muted-foreground text-[11px] leading-snug">
          <strong>Voix</strong> : la même voix redit la réplique en français ; ta consigne peut demander un autre débit ou une prononciation (« dis A-pi »).{" "}
          <strong>Refaire le clip</strong> : le modèle vidéo refait l’animation du plan avec ta consigne (qui parle, qui se tait, gestes, regard), ≈ 7 min sur la
          carte graphique, puis la vidéo est remontée.
        </p>
      </section>

      {plan.corrections.length ? (
        <section className="flex flex-col gap-1.5">
          <h4 className="flex items-center gap-1.5 text-xs font-semibold">
            <History className="size-3.5" />
            Déjà fait sur ce plan
          </h4>
          <ol className="flex flex-col gap-1 text-xs">
            {[...plan.corrections].reverse().map((c, i) => (
              <li key={`${c.at}-${i}`} className="text-muted-foreground flex flex-wrap gap-x-2">
                <span className="tabular-nums">{c.at ? formatDateTime(c.at) : ""}</span>
                <span className="text-foreground">{[c.clip ? "clip" : "", c.voice ? "voix" : ""].filter(Boolean).join(" + ")}</span>
                {c.note ? <span className="min-w-0 break-words">« {c.note} »</span> : <span>sans consigne</span>}
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}

/** Le repère posé sur la vidéo : le plan à l'écran et qui parle. */
export function PlanBadge({ plan }: { plan: RetouchPlan | null }) {
  if (!plan) return null;
  return (
    <div
      className={cn(
        "pointer-events-none absolute top-2 left-2 z-10 flex max-w-[85%] items-center gap-1 rounded-md bg-black/70 px-2 py-1 text-[11px] font-medium text-white",
      )}
      aria-live="off"
    >
      <span>Plan {plan.position + 1}</span>
      {plan.speaker ? <span className="truncate font-normal opacity-80">· {plan.speaker}</span> : null}
    </div>
  );
}
