"use client";

import * as React from "react";
import { CircleAlert, CircleCheck, CircleX, ExternalLink, RefreshCw } from "lucide-react";

import { checkGeminiBrowser, openGemini, saveGeminiSettings } from "@/app/settings/gemini-actions";
import { GeminiLogo } from "@/components/gemini-logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatDateTime, formatTime } from "@/lib/format";
import { GEMINI_DURATIONS, GEMINI_QUOTA_NOTE, type GeminiBrowserInfo, type GeminiDuration, type GeminiSettings, type GeminiStatus } from "@/lib/gemini-types";

const DURATION_LABELS: Record<GeminiDuration, string> = {
  auto: "Ajustée à chaque scène (4 à 10 s)",
  "4": "4 s",
  "6": "6 s",
  "8": "8 s",
  "10": "10 s",
};

function Notice({ result }: { result: { ok: boolean; message: string } | null }) {
  if (!result) return null;
  return (
    <p className={`flex items-center gap-1.5 text-xs ${result.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`} role="status">
      {result.ok ? <CircleCheck className="size-3.5 shrink-0" /> : <CircleX className="size-3.5 shrink-0" />}
      {result.message}
    </p>
  );
}

/** Réglages → Gemini en ligne : séparé des modèles locaux, comme le bouton Gemini est séparé de « Valider et fabriquer ». */
export function GeminiSettingsCard({ initial, status, browser }: { initial: GeminiSettings; status: GeminiStatus; browser: GeminiBrowserInfo }) {
  const [authuser, setAuthuser] = React.useState(String(initial.authuser));
  const [duration, setDuration] = React.useState<GeminiDuration>(initial.duration);
  const [model, setModel] = React.useState(initial.model);
  const [info, setInfo] = React.useState(browser);
  const [pending, startTransition] = React.useTransition();
  const [notice, setNotice] = React.useState<{ ok: boolean; message: string } | null>(null);
  const [connNotice, setConnNotice] = React.useState<{ ok: boolean; message: string } | null>(null);

  const save = () => startTransition(async () => setNotice(await saveGeminiSettings({ authuser: Number(authuser), duration, model })));
  const open = () => startTransition(async () => setConnNotice(await openGemini()));
  const verify = () =>
    startTransition(async () => {
      const res = await checkGeminiBrowser();
      if (res.info) setInfo(res.info);
      setConnNotice({ ok: res.ok, message: res.message });
    });

  const google =
    !info.running ? (
      <Badge variant="outline">Chrome dédié fermé</Badge>
    ) : info.signedIn ? (
      <Badge className="bg-emerald-600 text-white dark:bg-emerald-500">connecté à Google</Badge>
    ) : info.signedIn === false ? (
      <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-400">
        pas connecté à Google
      </Badge>
    ) : (
      <Badge variant="outline">Chrome dédié ouvert</Badge>
    );

  return (
    <Card id="gemini">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <GeminiLogo />
          Gemini en ligne (vidéo)
        </CardTitle>
        <CardDescription>
          Sur demande, à la place des modèles locaux : le bouton Gemini de Création envoie l’image de chaque scène à l’appli Gemini (ton abonnement
          Google AI) et récupère les clips ; la voix et le montage restent sur le PC. Le worker pilote un Chrome à part, où tu te connectes une fois.{" "}
          {GEMINI_QUOTA_NOTE}.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">Connexion</span>
            {google}
            {!info.chrome ? (
              <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-400">
                Chrome introuvable
              </Badge>
            ) : null}
          </div>
          {info.profile ? (
            <p className="text-muted-foreground text-xs">
              Profil dédié : <span className="font-mono break-all">{info.profile}</span> · port de pilotage {info.port} (sur ce PC seulement)
            </p>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" disabled={pending || !info.chrome} onClick={open}>
              <ExternalLink />
              Ouvrir Gemini dans Chrome
            </Button>
            <Button variant="ghost" disabled={pending} onClick={verify}>
              <RefreshCw />
              Vérifier la connexion
            </Button>
          </div>
          <Notice result={connNotice} />
          <p className="text-muted-foreground text-xs">
            Première fois : ouvre Gemini, connecte-toi au compte Google AI Pro dans cette fenêtre (ne t’en sers pas pour autre chose), puis dans Gemini →
            Paramètres, coupe le filigrane visible des médias pour que les Shorts n’aient pas l’étoile dans un coin.
          </p>
        </section>

        {status.message || status.quota_until ? (
          <section className="flex flex-col gap-1.5 rounded-lg border p-3 text-sm">
            <div className="flex items-center gap-2">
              {status.quota_until ? (
                <CircleAlert className="size-4 shrink-0 text-amber-600" />
              ) : status.ok ? (
                <CircleCheck className="size-4 shrink-0 text-emerald-600" />
              ) : (
                <CircleX className="text-destructive size-4 shrink-0" />
              )}
              <span className="font-medium">Dernier passage du worker</span>
              {status.at ? <span className="text-muted-foreground text-xs">{formatDateTime(status.at)}</span> : null}
            </div>
            {status.quota_until ? <p className="text-xs">Limite atteinte : les clips Gemini reprendront vers {formatTime(status.quota_until)}.</p> : null}
            {status.message ? <p className="text-muted-foreground text-xs break-words">{status.message}</p> : null}
          </section>
        ) : null}

        <section className="grid gap-4 md:grid-cols-3">
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium" htmlFor="gemini-account">
              Compte Google
            </label>
            <Select value={authuser} onValueChange={setAuthuser}>
              <SelectTrigger id="gemini-account" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {["0", "1", "2", "3"].map((n) => (
                  <SelectItem key={n} value={n}>
                    {n === "0" ? "Le premier connecté (u/0)" : `Le compte n° ${n} (u/${n})`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-muted-foreground text-xs">Seul compte du Chrome dédié : laisser u/0.</p>
          </div>
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium" htmlFor="gemini-duration">
              Durée des clips
            </label>
            <Select value={duration} onValueChange={(v) => setDuration(v as GeminiDuration)}>
              <SelectTrigger id="gemini-duration" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {GEMINI_DURATIONS.map((d) => (
                  <SelectItem key={d} value={d}>
                    {DURATION_LABELS[d]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-muted-foreground text-xs">Le montage coupe chaque clip à la durée de sa scène.</p>
          </div>
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium" htmlFor="gemini-model">
              Modèle (menu de l’appli)
            </label>
            <Input id="gemini-model" value={model} onChange={(e) => setModel(e.target.value)} placeholder="Celui proposé par Gemini" maxLength={60} />
            <p className="text-muted-foreground text-xs">Texte du menu des modèles, ex. « 3.5 Flash » ou « Pro ». Vide : Gemini choisit (Omni aujourd’hui).</p>
          </div>
        </section>

        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={pending} onClick={save}>
            Enregistrer
          </Button>
          <Notice result={notice} />
        </div>
      </CardContent>
    </Card>
  );
}
