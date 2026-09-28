"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { CircleAlert, CircleCheck, CircleX, ExternalLink, LoaderCircle, Mail, Send, Trash2 } from "lucide-react";

import { deleteSmtpPassword, getTestMailState, saveNotificationSettings, saveSmtpPassword, sendTestMail } from "@/app/settings/notify-actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { formatDateTime } from "@/lib/format";
import { APP_PASSWORD_URL, OUTBOX_HOURS, type NotificationSettings, type NotifyStatus, type TestMailState } from "@/lib/notify-types";

type LineState = TestMailState["state"];

const POLL_MS = 2500;
const SLOW_MS = 75_000; // le worker envoie toutes les 20 s : au-delà, il est arrêté ou en train de redémarrer
const STOP_MS = 15 * 60_000; // on guette encore sa réponse (relance après un clip de 10 min), puis on arrête

const LOOK: Record<LineState, { icon: typeof CircleCheck; tone: string }> = {
  sent: { icon: CircleCheck, tone: "text-emerald-600 dark:text-emerald-400" },
  failed: { icon: CircleX, tone: "text-destructive" },
  pending: { icon: LoaderCircle, tone: "text-muted-foreground" },
  unknown: { icon: CircleAlert, tone: "text-amber-700 dark:text-amber-400" },
};

function Line({ state, message }: { state: LineState; message: string }) {
  const { icon: Icon, tone } = LOOK[state];
  return (
    <p className={`flex items-center gap-1.5 text-xs ${tone}`} role="status">
      <Icon className={`size-3.5 shrink-0 ${state === "pending" ? "animate-spin" : ""}`} />
      {message}
    </p>
  );
}

/** Réglages → Notifications (docs/32) : un mail dès qu'une vidéo est terminée, envoyé par le worker avec un compte Gmail. */
export function NotificationsSettingsCard({ initial, status }: { initial: NotificationSettings; status: NotifyStatus }) {
  const router = useRouter();
  const [form, setForm] = React.useState<NotificationSettings>(initial);
  const [hint, setHint] = React.useState<string | null>(status.passwordHint);
  const [password, setPassword] = React.useState("");
  const [notice, setNotice] = React.useState<{ ok: boolean; message: string } | null>(null);
  const [test, setTest] = React.useState<TestMailState | null>(null);
  const [polling, setPolling] = React.useState(false);
  const [pending, startTransition] = React.useTransition();
  const timer = React.useRef<number | null>(null);

  const stopPolling = React.useCallback(() => {
    if (timer.current !== null) window.clearInterval(timer.current);
    timer.current = null;
    setPolling(false);
  }, []);
  React.useEffect(() => stopPolling, [stopPolling]);

  const save = (next: NotificationSettings) => startTransition(async () => setNotice(await saveNotificationSettings(next)));

  const toggle = (on: boolean) => {
    const next = { ...form, on_video_ready: on };
    setForm(next);
    save(next);
  };

  const storePassword = () =>
    startTransition(async () => {
      const res = await saveSmtpPassword(password);
      setNotice(res);
      if (!res.ok) return;
      setHint(res.hint ?? "…");
      setPassword("");
    });

  const removePassword = () =>
    startTransition(async () => {
      const res = await deleteSmtpPassword();
      setNotice(res);
      if (res.ok) setHint(null);
    });

  // Le mail d'essai suit le chemin des vrais : réglages enregistrés, alerte « test », envoi par le worker dans les 20 s
  const sendTest = () =>
    startTransition(async () => {
      stopPolling();
      setNotice(null);
      const saved = await saveNotificationSettings(form);
      if (!saved.ok) {
        setNotice(saved);
        return;
      }
      const res = await sendTestMail();
      if (!res.ok || !res.alertId) {
        setTest({ state: "failed", message: res.message });
        return;
      }
      setTest({ state: "pending", message: res.message });
      const alertId = res.alertId;
      const started = Date.now();
      let warned = false;
      setPolling(true);
      timer.current = window.setInterval(async () => {
        const state = await getTestMailState(alertId);
        const waited = Date.now() - started;
        if (state.state === "sent" || state.state === "failed") {
          stopPolling();
          setTest(state);
          router.refresh(); // ligne « Dernier mail » à jour
        } else if (waited > STOP_MS) {
          stopPolling();
        } else if (waited > SLOW_MS && !warned) {
          warned = true;
          setTest({
            state: "unknown",
            message: "Toujours en attente : le worker est arrêté ou redémarre (bloc « Machine » de la barre latérale). Le mail partira dès qu’il tourne.",
          });
        }
      }, POLL_MS);
    });

  const last = status.last;

  return (
    <Card id="notifications">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mail className="size-5" />
          Notifications par e-mail
        </CardTitle>
        <CardDescription>
          Un mail dès qu’une vidéo est terminée (montée et contrôlée), avec son image et le lien pour aller la voir. C’est le worker qui l’envoie, avec un
          compte Gmail : gratuit.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
          <div className="flex flex-col gap-0.5">
            <label htmlFor="notify-video-ready" className="text-sm font-medium">
              Vidéo terminée
            </label>
            <p className="text-muted-foreground text-xs">
              Un mail par vidéo, dans les 20 s qui suivent le contrôle final, qu’elle attende ta validation ou parte seule. Refaire son montage n’en renvoie
              pas.
            </p>
          </div>
          <Switch id="notify-video-ready" checked={form.on_video_ready} disabled={pending} onCheckedChange={toggle} aria-label="Mail quand une vidéo est terminée" />
        </div>

        <section className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium" htmlFor="notify-to">
              Adresse qui reçoit
            </label>
            <Input id="notify-to" type="email" value={form.email_to} onChange={(e) => setForm((f) => ({ ...f, email_to: e.target.value }))} autoComplete="email" />
          </div>
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium" htmlFor="notify-sender">
              Compte Gmail qui envoie
            </label>
            <Input
              id="notify-sender"
              type="email"
              value={form.sender}
              onChange={(e) => setForm((f) => ({ ...f, sender: e.target.value }))}
              placeholder={form.email_to || "adresse Gmail"}
              autoComplete="off"
            />
            <p className="text-muted-foreground text-xs">
              Vide : la même adresse, qui s’écrit à elle-même. Si ton téléphone ne sonne pas pour ces mails, mets ici un second compte Gmail.
            </p>
          </div>
        </section>

        <section className="flex flex-col gap-2">
          <label className="text-sm font-medium" htmlFor="notify-password">
            Mot de passe d’application Gmail
          </label>
          {hint ? (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <CircleCheck className="size-4 text-emerald-600" />
              Enregistré
              <code className="bg-muted rounded px-1.5 py-0.5 text-xs">…{hint}</code>
              <Button size="sm" variant="ghost" disabled={pending} onClick={removePassword}>
                <Trash2 />
                Retirer
              </Button>
            </div>
          ) : null}
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              id="notify-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={hint ? "Coller un nouveau mot de passe pour le remplacer" : "Les 16 lettres données par Google"}
            />
            <Button variant="outline" className="shrink-0" disabled={pending || !password.trim()} onClick={storePassword}>
              Enregistrer le mot de passe
            </Button>
          </div>
          <p className="text-muted-foreground text-xs">
            Pas ton mot de passe Google : un code de 16 lettres que Google crée pour une appli (il faut la validation en deux étapes sur le compte).{" "}
            <a href={APP_PASSWORD_URL} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 underline underline-offset-2">
              Le créer
              <ExternalLink className="size-3" />
            </a>{" "}
            en étant connecté au compte qui envoie, avec le nom « YouTube 2.0 ». Il est chiffré en base, comme les clés d’IA.
          </p>
        </section>

        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <Button disabled={pending} onClick={() => save(form)}>
              Enregistrer
            </Button>
            <Button variant="outline" disabled={pending || (polling && test?.state === "pending")} onClick={sendTest}>
              <Send />
              Envoyer un mail d’essai
            </Button>
          </div>
          {notice ? <Line state={notice.ok ? "sent" : "failed"} message={notice.message} /> : null}
          {test ? <Line state={test.state} message={test.message} /> : null}
        </div>

        {last || status.pending ? (
          <div className="text-muted-foreground flex flex-col gap-1 border-t pt-3 text-xs">
            {last ? (
              <p>
                Dernier mail {last.ok ? "parti" : "refusé"} {formatDateTime(last.at)} : {last.title}
                {last.error ? ` · ${last.error}` : ""}
              </p>
            ) : null}
            {status.pending ? (
              <p className="text-amber-700 dark:text-amber-400">
                {status.pending} mail{status.pending > 1 ? "s" : ""} « vidéo terminée » en attente : ils partent dès que l’envoi marche (pendant {OUTBOX_HOURS} h).
              </p>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
