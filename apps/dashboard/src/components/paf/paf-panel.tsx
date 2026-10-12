"use client";

import * as React from "react";
import { CalendarDays, Camera, CircleCheck, CircleX, Clock, Dices, ExternalLink, FolderOpen, KeyRound, Plus, RefreshCw, RotateCcw, X } from "lucide-react";

import { deletePafKey, refreshPafAccounts, retryPaf, savePafHour, savePafKey, savePafSettings, setPafEnabled } from "@/app/paf-j-achete/actions";
import { ToneBadge, type Tone } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { formatBytes, formatDate, formatDateTime, formatTime } from "@/lib/format";
import {
  normalizePafHour,
  PAF_DATE_MODES,
  PAF_DATE_TAG,
  PAF_STATUS_LABELS,
  pafDateLabel,
  pafHourLabel,
  renderPafCaption,
  type PafAccount,
  type PafDateMode,
  type PafOverview,
  type PafStatus,
} from "@/lib/paf-types";

type Notice = { ok: boolean; message: string } | null;

const START_SLOTS = 5; // cinq légendes proposées au départ

const TONES: Record<PafStatus, Tone> = {
  queued: "neutral",
  sending: "running",
  scheduled: "info",
  pending: "running",
  publishing: "running",
  processing: "running",
  uploading: "running",
  published: "success",
  failed: "danger",
  cancelled: "neutral",
};

function NoticeLine({ result }: { result: Notice }) {
  if (!result) return null;
  return (
    <p className={`flex items-center gap-1.5 text-xs ${result.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`} role="status">
      {result.ok ? <CircleCheck className="size-3.5 shrink-0" /> : <CircleX className="size-3.5 shrink-0" />}
      {result.message}
    </p>
  );
}

/** Onglet « Paf, j'achète » (docs/50) : la même vidéo chaque vendredi, à l'heure choisie, sur un compte Instagram à part. */
export function PafPanel({ overview }: { overview: PafOverview }) {
  const { settings, video, folder, posts, job } = overview;
  const [pending, startTransition] = React.useTransition();
  const [keyHint, setKeyHint] = React.useState(overview.keyHint);
  const [keyValue, setKeyValue] = React.useState("");
  const [accounts, setAccounts] = React.useState<PafAccount[] | null>(null);
  const [form, setForm] = React.useState({
    account_id: settings.account_id,
    captions: settings.captions.length ? settings.captions : Array.from({ length: START_SLOTS }, () => ""),
    share_to_feed: settings.share_to_feed,
    date_caption: settings.date_caption,
  });
  const setCaption = (i: number, value: string) => setForm((f) => ({ ...f, captions: f.captions.map((c, j) => (j === i ? value : c)) }));
  const filled = form.captions.filter((c) => c.trim()).length;
  const captionRefs = React.useRef<(HTMLTextAreaElement | null)[]>([]);
  /** Écrit {date} là où est le curseur de la légende i. */
  const insertDate = (i: number) => {
    const el = captionRefs.current[i];
    const c = form.captions[i] ?? "";
    const start = el?.selectionStart ?? c.length;
    const end = el?.selectionEnd ?? c.length;
    setCaption(i, c.slice(0, start) + PAF_DATE_TAG + c.slice(end));
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(start + PAF_DATE_TAG.length, start + PAF_DATE_TAG.length);
    });
  };
  const [hour, setHour] = React.useState(settings.hour);
  const [toggleNotice, setToggleNotice] = React.useState<Notice>(null);
  const [hourNotice, setHourNotice] = React.useState<Notice>(null);
  const [keyNotice, setKeyNotice] = React.useState<Notice>(null);
  const [formNotice, setFormNotice] = React.useState<Notice>(null);

  const loadAccounts = React.useCallback(
    () =>
      startTransition(async () => {
        const res = await refreshPafAccounts();
        setAccounts(res.accounts);
        setKeyNotice(res.ok ? null : { ok: false, message: res.message });
      }),
    [],
  );
  React.useEffect(() => {
    if (overview.keyHint) loadAccounts();
  }, [overview.keyHint, loadAccounts]);

  const known: PafAccount[] =
    accounts ?? (settings.account_id ? [{ id: settings.account_id, username: settings.username, displayName: settings.username, avatar: null, active: true, kind: null }] : []);
  const username = known.find((a) => a.id === form.account_id)?.username ?? (form.account_id === settings.account_id ? settings.username : "");
  const twin = accounts?.find((a) => a.sameAsMain) ?? null;
  const savedIsTwin = Boolean(accounts?.find((a) => a.id === settings.account_id)?.sameAsMain);
  const nextSlot = new Date(overview.nextSlot);
  const nextPost = posts.find((p) => p.friday === overview.nextFriday) ?? null;
  const fridayAfter = new Date(Date.parse(`${overview.nextFriday}T12:00:00Z`) + 7 * 86_400_000).toISOString().slice(0, 10);
  const [focused, setFocused] = React.useState(0);
  const previewIndex = form.captions[focused]?.trim() ? focused : form.captions.findIndex((c) => c.trim());
  const preview =
    form.date_caption === "only" || previewIndex >= 0
      ? renderPafCaption(previewIndex >= 0 ? form.captions[previewIndex] : "", overview.nextFriday, form.date_caption)
      : "";
  const hourOk = normalizePafHour(hour);

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-col gap-1">
              <span className="text-lg font-semibold">{settings.enabled ? "En marche" : "À l’arrêt"}</span>
              <span className="text-muted-foreground text-sm">
                {settings.enabled
                  ? `Prochain envoi : vendredi ${formatDate(nextSlot, "d MMMM")} à ${pafHourLabel(settings.hour)}${settings.username ? ` sur @${settings.username}` : ""}`
                  : "Rien ne part tant que l’interrupteur est coupé."}
              </span>
              {nextPost ? (
                <span className="flex items-center gap-2 text-xs">
                  <ToneBadge tone={TONES[nextPost.status]}>{PAF_STATUS_LABELS[nextPost.status]}</ToneBadge>
                  {nextPost.error ? <span className="text-destructive">{nextPost.error}</span> : null}
                </span>
              ) : null}
              {job?.label ? <span className="text-muted-foreground text-xs">{job.label}</span> : null}
              {settings.enabled && savedIsTwin ? (
                <span className="text-destructive text-xs">
                  @{settings.username} est l’Instagram du compte principal : rien ne partira tant que @paf.jachete n’est pas branché et choisi ci-dessous.
                </span>
              ) : null}
            </div>
            <Switch
              className="scale-125"
              checked={settings.enabled}
              disabled={pending}
              aria-label="Publication automatique du vendredi"
              onCheckedChange={(on) => startTransition(async () => setToggleNotice(await setPafEnabled(on)))}
            />
          </div>
          <NoticeLine result={toggleNotice} />
          <div className="flex flex-wrap items-end gap-3 border-t pt-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="paf-hour" className="flex items-center gap-1.5 text-sm font-medium">
                <Clock className="size-4" />
                Heure de publication
              </label>
              <Input id="paf-hour" type="time" className="w-32" value={hour} onChange={(e) => setHour(e.target.value)} />
            </div>
            <Button
              variant="outline"
              disabled={pending || !hourOk || hourOk === settings.hour}
              onClick={() => startTransition(async () => setHourNotice(await savePafHour(hour)))}
            >
              Changer l’heure
            </Button>
            <span className="text-muted-foreground basis-full text-xs">
              Chaque vendredi, heure de Paris. Changée après coup, le Reel déjà programmé chez Zernio est reprogrammé à la nouvelle heure.
            </span>
          </div>
          <NoticeLine result={hourNotice} />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FolderOpen className="size-5" />
              La vidéo
            </CardTitle>
            <CardDescription>Le .mp4 le plus récent de ce dossier part chaque vendredi. Pour la changer, remplacer le fichier.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <code className="bg-muted rounded px-2 py-1 text-xs break-all">{folder ?? "dossier de données du worker inconnu"}</code>
            {video ? (
              <>
                <video src={`/api/paf/video?v=${encodeURIComponent(video.modified)}`} controls preload="metadata" className="mx-auto max-h-96 rounded-lg bg-black" />
                <p className="text-muted-foreground text-xs">
                  {video.name} · {formatBytes(video.size)} · déposée le {formatDateTime(video.modified)}
                </p>
              </>
            ) : (
              <p className="text-sm text-amber-700 dark:text-amber-400">Aucune vidéo .mp4 dans le dossier pour l’instant.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="size-5" />
              Compte Zernio à part
            </CardTitle>
            <CardDescription>
              La clé API de l’autre compte Zernio (pas celle de TikTok / @arzakparker), puis le compte Instagram qui reçoit la vidéo.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              {keyHint ? <span className="text-sm">Clé enregistrée : …{keyHint}</span> : null}
              <div className="flex gap-2">
                <Input type="password" autoComplete="off" placeholder={keyHint ? "Remplacer la clé" : "Clé API Zernio (sk_…)"} value={keyValue} onChange={(e) => setKeyValue(e.target.value)} />
                <Button
                  disabled={pending || !keyValue.trim()}
                  onClick={() =>
                    startTransition(async () => {
                      const res = await savePafKey(keyValue);
                      setKeyNotice(res);
                      if (res.ok) {
                        setKeyValue("");
                        setKeyHint(res.hint ?? null);
                        setAccounts(res.accounts ?? []);
                      }
                    })
                  }
                >
                  Enregistrer
                </Button>
                {keyHint ? (
                  <Button
                    variant="ghost"
                    disabled={pending}
                    onClick={() =>
                      startTransition(async () => {
                        const res = await deletePafKey();
                        setKeyNotice(res);
                        if (res.ok) setKeyHint(null);
                      })
                    }
                  >
                    Retirer
                  </Button>
                ) : null}
              </div>
              <NoticeLine result={keyNotice} />
            </div>

            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2 text-sm">
                <span className="font-medium">Compte Instagram</span>
                <Button variant="ghost" size="sm" disabled={pending || !keyHint} onClick={loadAccounts}>
                  <RefreshCw />
                  Actualiser
                </Button>
              </div>
              {accounts && accounts.length === 0 ? (
                <p className="text-muted-foreground text-xs">
                  Aucun compte Instagram sur ce compte Zernio : Accounts → Connect → Instagram, puis Actualiser.{" "}
                  <a className="inline-flex items-center gap-1 underline" href="https://zernio.com/dashboard" target="_blank" rel="noreferrer noopener">
                    Ouvrir Zernio
                    <ExternalLink className="size-3" />
                  </a>
                </p>
              ) : null}
              {twin ? (
                <div className="flex flex-col gap-1 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs">
                  <span className="font-medium">
                    @{twin.username} est le même Instagram que celui du compte Zernio principal : la clé est bonne, c’est l’Instagram branché sur ce
                    compte Zernio qui n’est pas le bon.
                  </span>
                  <span>Instagram branche le compte ouvert dans le navigateur au moment de la connexion. Pour brancher @paf.jachete :</span>
                  <ol className="list-decimal pl-4">
                    <li>Fenêtre de navigation privée → instagram.com → se connecter en @paf.jachete (compte pro : Créateur ou Entreprise).</li>
                    <li>Dans la même fenêtre, zernio.com avec le second compte Zernio → Accounts → Connect → Instagram : vérifier que c’est bien @paf.jachete qui s’affiche.</li>
                    <li>Revenir ici → Actualiser → choisir @paf.jachete → Enregistrer.</li>
                  </ol>
                  <span className="text-muted-foreground">
                    Ne pas déconnecter @{twin.username} sur le compte Zernio principal : c’est lui qui publie les vidéos YouTube / TikTok sur Instagram.
                  </span>
                </div>
              ) : null}
              <Select value={form.account_id || "none"} onValueChange={(v) => setForm((f) => ({ ...f, account_id: v === "none" ? "" : v }))} disabled={!known.length}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Choisir le compte" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Aucun</SelectItem>
                  {known.map((a) => (
                    <SelectItem key={a.id} value={a.id} disabled={a.sameAsMain && a.id !== settings.account_id}>
                      <Camera className="size-4" />@{a.username}
                      {a.sameAsMain ? " (compte principal, pas celui du vendredi)" : a.active ? null : " (à reconnecter sur Zernio)"}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-2">
              <span className="flex items-center gap-2 text-sm font-medium">
                <Dices className="size-4" />
                Légendes
              </span>
              <p className="text-muted-foreground text-xs">
                Une est tirée au sort juste avant chaque envoi, jamais la même que le vendredi d’avant.{" "}
                {filled ? `${filled} légende${filled > 1 ? "s" : ""} remplie${filled > 1 ? "s" : ""}.` : "Aucune remplie : le Reel part sans légende."}
              </p>
              {form.captions.map((c, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="text-muted-foreground w-4 pt-2 text-xs">{i + 1}</span>
                  <Textarea
                    ref={(el) => {
                      captionRefs.current[i] = el;
                    }}
                    rows={2}
                    maxLength={2200}
                    aria-label={`Légende ${i + 1}`}
                    placeholder="Bonjour, c’est vendredi."
                    value={c}
                    onFocus={() => setFocused(i)}
                    onChange={(e) => setCaption(i, e.target.value)}
                  />
                  <div className="flex flex-col">
                    <Button variant="ghost" size="icon" title="Insérer la date du vendredi" aria-label={`Insérer la date du vendredi dans la légende ${i + 1}`} onClick={() => insertDate(i)}>
                      <CalendarDays />
                    </Button>
                    <Button variant="ghost" size="icon" title="Retirer" aria-label={`Retirer la légende ${i + 1}`} onClick={() => setForm((f) => ({ ...f, captions: f.captions.filter((_, j) => j !== i) }))}>
                      <X />
                    </Button>
                  </div>
                </div>
              ))}
              <Button variant="outline" size="sm" className="self-start" onClick={() => setForm((f) => ({ ...f, captions: [...f.captions, ""] }))}>
                <Plus />
                Ajouter une légende
              </Button>
            </div>
            <div className="flex flex-col gap-2">
              <span className="flex items-center gap-2 text-sm font-medium">
                <CalendarDays className="size-4" />
                Date du vendredi dans la légende
              </span>
              <Select value={form.date_caption} onValueChange={(v) => setForm((f) => ({ ...f, date_caption: v as PafDateMode }))}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PAF_DATE_MODES.map((m) => (
                    <SelectItem key={m.value} value={m.value}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-muted-foreground text-xs">
                Écrite toute seule à chaque envoi : « {pafDateLabel(overview.nextFriday)} », puis « {pafDateLabel(fridayAfter)} »… Le bouton calendrier d’une légende y
                place {PAF_DATE_TAG} à l’endroit du curseur.
              </p>
              {preview ? (
                <div className="bg-muted flex flex-col gap-1 rounded-md p-3 text-xs">
                  <span className="text-muted-foreground">
                    Aperçu pour le {pafDateLabel(overview.nextFriday)}
                    {form.date_caption !== "only" && previewIndex >= 0 ? ` (légende ${previewIndex + 1})` : ""}
                  </span>
                  <span className="whitespace-pre-line">{preview}</span>
                </div>
              ) : null}
            </div>
            <div className="flex items-center justify-between gap-4 rounded-lg border p-3">
              <label htmlFor="paf-feed" className="text-sm">
                Aussi dans la grille du profil
              </label>
              <Switch id="paf-feed" checked={form.share_to_feed} onCheckedChange={(v) => setForm((f) => ({ ...f, share_to_feed: v }))} />
            </div>
            <div className="flex flex-col gap-2">
              <Button
                className="self-start"
                disabled={pending}
                onClick={() => startTransition(async () => setFormNotice(await savePafSettings({ ...form, username })))}
              >
                Enregistrer
              </Button>
              <NoticeLine result={formNotice} />
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Les vendredis</CardTitle>
          <CardDescription>Chaque envoi, préparé 2 jours avant et programmé chez Zernio pour {pafHourLabel(settings.hour)}.</CardDescription>
        </CardHeader>
        <CardContent>
          {posts.length ? (
            <ul className="divide-y">
              {posts.map((p) => (
                <li key={p.friday} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                  <span className="w-44 font-medium">
                    Vendredi {formatDate(`${p.friday}T12:00:00Z`, "d MMM yyyy")}
                    {p.scheduled_for ? <span className="text-muted-foreground font-normal"> · {pafHourLabel(formatTime(p.scheduled_for))}</span> : null}
                  </span>
                  <ToneBadge tone={TONES[p.status] ?? "neutral"}>{PAF_STATUS_LABELS[p.status] ?? p.status}</ToneBadge>
                  {p.username ? <Badge variant="outline">@{p.username}</Badge> : null}
                  {p.file_name ? <span className="text-muted-foreground text-xs">{p.file_name}</span> : null}
                  {p.caption ? <span className="text-muted-foreground basis-full text-xs italic">« {p.caption} »</span> : null}
                  {p.url ? (
                    <a className="inline-flex items-center gap-1 text-xs underline" href={p.url} target="_blank" rel="noreferrer noopener">
                      Voir le Reel
                      <ExternalLink className="size-3" />
                    </a>
                  ) : null}
                  {p.error ? <span className="text-destructive text-xs">{p.error}</span> : null}
                  {p.status === "failed" ? (
                    <Button variant="outline" size="sm" disabled={pending} onClick={() => startTransition(async () => setToggleNotice(await retryPaf(p.friday)))}>
                      <RotateCcw />
                      Relancer
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-sm">Aucun vendredi envoyé pour l’instant.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
