"use client";

import * as React from "react";
import { CircleCheck, CircleX, ExternalLink, KeyRound, Music2, RefreshCw, Trash2 } from "lucide-react";

import { deleteZernioKey, refreshTikTokAccounts, saveTikTokSettings, saveZernioKey } from "@/app/settings/tiktok-actions";
import { ConfirmButton } from "@/components/confirm-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { formatDateTime } from "@/lib/format";
import type { Channel } from "@/lib/types";
import type { TikTokAccount, TikTokBacklogVideo, TikTokSettings } from "@/lib/tiktok-types";

const NONE = "none";

function Notice({ result }: { result: { ok: boolean; message: string } | null }) {
  if (!result) return null;
  return (
    <p className={`flex items-center gap-1.5 text-xs ${result.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`} role="status">
      {result.ok ? <CircleCheck className="size-3.5 shrink-0" /> : <CircleX className="size-3.5 shrink-0" />}
      {result.message}
    </p>
  );
}

function Toggle({ id, label, help, checked, onChange }: { id: string; label: string; help: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
      <div className="flex flex-col gap-0.5">
        <label htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
        <p className="text-muted-foreground text-xs">{help}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} aria-label={label} />
    </div>
  );
}

/** Réglages → TikTok : Zernio publie les Shorts sur TikTok ; l'envoi YouTube, lui, ne change pas (docs/36). Rattrapage des
 * vidéos déjà sorties sur YouTube, chaîne par chaîne (docs/39). */
export function TikTokSettingsCard({
  initial,
  keyHint,
  channels,
  backlog = {},
}: {
  initial: TikTokSettings;
  keyHint: string | null;
  channels: Channel[];
  /** Vidéos à rattraper par chaîne, dans l'ordre où elles partiront. */
  backlog?: Record<string, TikTokBacklogVideo[]>;
}) {
  const [hint, setHint] = React.useState(keyHint);
  const [editingKey, setEditingKey] = React.useState(!keyHint);
  const [keyValue, setKeyValue] = React.useState("");
  const [accounts, setAccounts] = React.useState<TikTokAccount[] | null>(null);
  const [links, setLinks] = React.useState(() =>
    Object.fromEntries(
      channels.map((c) => [
        c.id,
        { account_id: initial.channels[c.id]?.account_id ?? "", enabled: initial.channels[c.id]?.enabled ?? false, backlog: initial.channels[c.id]?.backlog ?? false },
      ]),
    ),
  );
  const [options, setOptions] = React.useState({
    allow_comment: initial.allow_comment,
    allow_duet: initial.allow_duet,
    allow_stitch: initial.allow_stitch,
    ai_label: initial.ai_label,
  });
  const [pending, startTransition] = React.useTransition();
  const [keyNotice, setKeyNotice] = React.useState<{ ok: boolean; message: string } | null>(null);
  const [accountsNotice, setAccountsNotice] = React.useState<{ ok: boolean; message: string } | null>(null);
  const [notice, setNotice] = React.useState<{ ok: boolean; message: string } | null>(null);

  const loadAccounts = React.useCallback(
    () =>
      startTransition(async () => {
        const res = await refreshTikTokAccounts();
        setAccounts(res.accounts);
        setAccountsNotice(res.ok ? null : { ok: false, message: res.message });
      }),
    [],
  );
  React.useEffect(() => {
    if (keyHint) loadAccounts();
  }, [keyHint, loadAccounts]);

  const saveKey = () =>
    startTransition(async () => {
      const res = await saveZernioKey(keyValue);
      setKeyNotice(res);
      if (res.ok) {
        setHint(res.hint ?? "…");
        setKeyValue("");
        setEditingKey(false);
        setAccounts(res.accounts ?? []);
      }
    });
  const removeKey = () =>
    startTransition(async () => {
      const res = await deleteZernioKey();
      setKeyNotice(res);
      if (res.ok) {
        setHint(null);
        setEditingKey(true);
        setAccounts(null);
      }
    });

  // Comptes connus : ceux de Zernio, sinon ceux déjà enregistrés (Zernio injoignable ou pas encore lu)
  const known: TikTokAccount[] =
    accounts ??
    Object.values(initial.channels).map((c) => ({ id: c.account_id, username: c.username, displayName: c.username, avatar: null, active: true }));
  const nameOf = (id: string) => known.find((a) => a.id === id)?.username ?? Object.values(initial.channels).find((c) => c.account_id === id)?.username ?? "";

  const save = () =>
    startTransition(async () =>
      setNotice(
        await saveTikTokSettings({
          links: channels.map((c) => ({
            channel_id: c.id,
            account_id: links[c.id]?.account_id ?? "",
            username: nameOf(links[c.id]?.account_id ?? ""),
            enabled: Boolean(links[c.id]?.account_id) && Boolean(links[c.id]?.enabled),
            backlog: Boolean(links[c.id]?.account_id) && Boolean(links[c.id]?.backlog),
          })),
          ...options,
        }),
      ),
    );

  return (
    <Card id="tiktok">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Music2 className="size-5" />
          TikTok (par Zernio)
        </CardTitle>
        <CardDescription>
          Chaque Short programmé sur YouTube part aussi sur TikTok, à la même heure. Zernio sert seulement à TikTok : son appli TikTok est validée par TikTok,
          donc les vidéos sortent en public. L’envoi sur YouTube ne change pas. Les chiffres de chaque vidéo arrivent dans Dashboard → TikTok (relevés chaque
          heure) et les publications prévues dans le Calendrier.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">Clé API Zernio</span>
            {hint ? <Badge className="bg-emerald-600 text-white dark:bg-emerald-500">enregistrée · …{hint}</Badge> : <Badge variant="outline">absente</Badge>}
          </div>
          {editingKey ? (
            <div className="flex flex-wrap items-center gap-2">
              <Input
                type="password"
                autoComplete="off"
                value={keyValue}
                onChange={(e) => setKeyValue(e.target.value)}
                placeholder="sk_…"
                className="max-w-md font-mono"
                aria-label="Clé API Zernio"
              />
              <Button disabled={pending || keyValue.trim().length < 16} onClick={saveKey}>
                <KeyRound />
                Vérifier et enregistrer
              </Button>
              {hint ? (
                <Button variant="ghost" disabled={pending} onClick={() => setEditingKey(false)}>
                  Annuler
                </Button>
              ) : null}
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" disabled={pending} onClick={() => setEditingKey(true)}>
                <KeyRound />
                Remplacer la clé
              </Button>
              <ConfirmButton variant="ghost" disabled={pending} onConfirm={removeKey} confirmLabel="Confirmer : retirer la clé">
                <Trash2 />
                Retirer
              </ConfirmButton>
            </div>
          )}
          <Notice result={keyNotice} />
          <p className="text-muted-foreground text-xs">
            Clé à créer sur zernio.com (API Keys). Elle est chiffrée en base, le navigateur n’en voit que les 4 derniers caractères, et elle ne va jamais dans le dépôt
            GitHub.{" "}
            <a className="inline-flex items-center gap-1 underline" href="https://zernio.com/dashboard" target="_blank" rel="noreferrer noopener">
              Ouvrir Zernio
              <ExternalLink className="size-3" />
            </a>
          </p>
        </section>

        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">Comptes TikTok connectés à Zernio</span>
            <Button variant="ghost" size="sm" disabled={pending || !hint} onClick={loadAccounts}>
              <RefreshCw />
              Actualiser
            </Button>
          </div>
          {accounts && accounts.length === 0 ? (
            <p className="text-muted-foreground text-xs">Aucun compte : sur zernio.com, Accounts → Connect → TikTok, puis Actualiser.</p>
          ) : null}
          {accounts?.length ? (
            <ul className="flex flex-wrap gap-2">
              {accounts.map((a) => (
                <li key={a.id} className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
                  {a.avatar ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={a.avatar} alt="" className="size-6 rounded-full" />
                  ) : (
                    <Music2 className="size-4" />
                  )}
                  <span className="font-medium">@{a.username}</span>
                  {a.active ? null : (
                    <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-400">
                      à reconnecter sur Zernio
                    </Badge>
                  )}
                </li>
              ))}
            </ul>
          ) : null}
          <Notice result={accountsNotice} />
        </section>

        <section className="flex flex-col gap-3">
          <span className="text-sm font-medium">Chaînes YouTube → TikTok</span>
          {channels.map((c) => {
            const link = links[c.id] ?? { account_id: "", enabled: false, backlog: false };
            const since = initial.channels[c.id]?.enabled && initial.channels[c.id]?.account_id === link.account_id ? initial.channels[c.id]?.enabled_at : null;
            const pendingOld = backlog[c.id] ?? [];
            return (
              <div key={c.id} className="flex flex-col gap-3 rounded-lg border p-3">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div className="flex flex-col gap-1">
                    <span className="text-sm font-medium">{c.name}</span>
                    <span className="text-muted-foreground text-xs">
                      {link.account_id && link.enabled
                        ? `Publication automatique${since ? ` depuis le ${formatDateTime(since)}` : " dès l’enregistrement"} : les Shorts programmés ensuite partent aussi sur TikTok.`
                        : "Pas de publication automatique : « Publier sur TikTok » reste possible dans la Bibliothèque."}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <Select value={link.account_id || NONE} onValueChange={(v) => setLinks((l) => ({ ...l, [c.id]: { ...link, account_id: v === NONE ? "" : v } }))}>
                      <SelectTrigger className="w-52" aria-label={`Compte TikTok de ${c.name}`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NONE}>Aucun compte TikTok</SelectItem>
                        {known.map((a) => (
                          <SelectItem key={a.id} value={a.id}>
                            @{a.username}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <div className="flex items-center gap-2">
                      <Switch
                        id={`tiktok-auto-${c.id}`}
                        checked={Boolean(link.account_id) && link.enabled}
                        disabled={!link.account_id}
                        onCheckedChange={(v) => setLinks((l) => ({ ...l, [c.id]: { ...link, enabled: v } }))}
                      />
                      <label htmlFor={`tiktok-auto-${c.id}`} className="text-sm">
                        Automatique
                      </label>
                    </div>
                  </div>
                </div>
                {link.account_id ? (
                  <div className="flex flex-col gap-3 border-t pt-3 md:flex-row md:items-start md:justify-between">
                    <div className="flex min-w-0 flex-col gap-1">
                      <span className="text-sm font-medium">Rattrapage des vidéos déjà sorties sur YouTube</span>
                      <span className="text-muted-foreground text-xs">
                        {pendingOld.length
                          ? `${pendingOld.length} vidéo${pendingOld.length > 1 ? "s" : ""} jamais envoyée${pendingOld.length > 1 ? "s" : ""} sur TikTok. Activé, chaque créneau resté vide (aucune nouvelle vidéo à cette heure-là) en reçoit une, la plus ancienne d’abord, une demi-heure avant l’heure : jamais de rafale.`
                          : "Rien à rattraper : chaque vidéo déjà sortie sur YouTube est aussi partie sur TikTok (ou y attend son créneau)."}
                      </span>
                      {pendingOld.length ? (
                        <ol className="text-muted-foreground list-inside list-decimal text-xs">
                          {pendingOld.slice(0, 5).map((v) => (
                            <li key={v.id} className="truncate">
                              {v.title ?? "Sans titre"}
                              {v.published_at ? ` · sortie sur YouTube le ${formatDateTime(v.published_at)}` : ""}
                            </li>
                          ))}
                          {pendingOld.length > 5 ? <li className="list-none">… et {pendingOld.length - 5} autres</li> : null}
                        </ol>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Switch
                        id={`tiktok-backlog-${c.id}`}
                        checked={link.backlog}
                        onCheckedChange={(v) => setLinks((l) => ({ ...l, [c.id]: { ...link, backlog: v } }))}
                      />
                      <label htmlFor={`tiktok-backlog-${c.id}`} className="text-sm">
                        Rattrapage
                      </label>
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })}
        </section>

        <section className="grid gap-3 md:grid-cols-2">
          <Toggle id="tiktok-comment" label="Commentaires" help="Les spectateurs peuvent commenter." checked={options.allow_comment} onChange={(v) => setOptions((o) => ({ ...o, allow_comment: v }))} />
          <Toggle id="tiktok-duet" label="Duo" help="Ils peuvent faire un duo avec la vidéo." checked={options.allow_duet} onChange={(v) => setOptions((o) => ({ ...o, allow_duet: v }))} />
          <Toggle id="tiktok-stitch" label="Collage" help="Ils peuvent reprendre un extrait (Stitch)." checked={options.allow_stitch} onChange={(v) => setOptions((o) => ({ ...o, allow_stitch: v }))} />
          <Toggle
            id="tiktok-ai"
            label="Étiquette « contenu généré par IA »"
            help="Coupée par défaut : TikTok repère lui-même les contenus IA. À activer si tu veux la cocher sur chaque vidéo."
            checked={options.ai_label}
            onChange={(v) => setOptions((o) => ({ ...o, ai_label: v }))}
          />
        </section>
        <p className="text-muted-foreground text-xs">
          Visibilité : publique. Un compte relié par l’appli TikTok for Business ne publie une vidéo qu’en public. La légende reprend le titre et la description YouTube
          (hashtags et sources compris), sans #shorts.
        </p>

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
