"use client";

import * as React from "react";
import { Camera, CircleCheck, CircleX, ExternalLink, RefreshCw } from "lucide-react";

import { refreshInstagramAccounts, saveInstagramSettings } from "@/app/settings/instagram-actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { formatDateTime } from "@/lib/format";
import type { InstagramAccount, InstagramSettings } from "@/lib/instagram-types";
import type { Channel } from "@/lib/types";

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

const KINDS: Record<string, string> = { MEDIA_CREATOR: "Créateur", BUSINESS: "Entreprise", PERSONAL: "personnel : ne peut pas publier" };

/** Réglages → Instagram (docs/48) : chaque Short programmé sur YouTube part aussi en Reel, par Zernio (même clé que TikTok). */
export function InstagramSettingsCard({ initial, hasKey, channels }: { initial: InstagramSettings; hasKey: boolean; channels: Channel[] }) {
  const [accounts, setAccounts] = React.useState<InstagramAccount[] | null>(null);
  const [links, setLinks] = React.useState(() =>
    Object.fromEntries(channels.map((c) => [c.id, { account_id: initial.channels[c.id]?.account_id ?? "", enabled: initial.channels[c.id]?.enabled ?? false }])),
  );
  const [options, setOptions] = React.useState({ share_to_feed: initial.share_to_feed, ai_label: initial.ai_label });
  const [pending, startTransition] = React.useTransition();
  const [accountsNotice, setAccountsNotice] = React.useState<{ ok: boolean; message: string } | null>(null);
  const [notice, setNotice] = React.useState<{ ok: boolean; message: string } | null>(null);

  const loadAccounts = React.useCallback(
    () =>
      startTransition(async () => {
        const res = await refreshInstagramAccounts();
        setAccounts(res.accounts);
        setAccountsNotice(res.ok ? null : { ok: false, message: res.message });
      }),
    [],
  );
  React.useEffect(() => {
    if (hasKey) loadAccounts();
  }, [hasKey, loadAccounts]);

  const known: InstagramAccount[] =
    accounts ?? Object.values(initial.channels).map((c) => ({ id: c.account_id, username: c.username, displayName: c.username, avatar: null, active: true, kind: null }));
  const nameOf = (id: string) => known.find((a) => a.id === id)?.username ?? Object.values(initial.channels).find((c) => c.account_id === id)?.username ?? "";

  const save = () =>
    startTransition(async () =>
      setNotice(
        await saveInstagramSettings({
          links: channels.map((c) => ({
            channel_id: c.id,
            account_id: links[c.id]?.account_id ?? "",
            username: nameOf(links[c.id]?.account_id ?? ""),
            enabled: Boolean(links[c.id]?.account_id) && Boolean(links[c.id]?.enabled),
          })),
          ...options,
        }),
      ),
    );

  return (
    <Card id="instagram">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Camera className="size-5" />
          Instagram (par Zernio)
        </CardTitle>
        <CardDescription>
          Chaque Short programmé sur YouTube part aussi en Reel sur Instagram, à la même heure, comme sur TikTok. Même clé Zernio que TikTok (carte ci-dessus). Le
          compte doit être professionnel (Créateur ou Entreprise) et connecté sur zernio.com.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">Comptes Instagram connectés à Zernio</span>
            <Button variant="ghost" size="sm" disabled={pending || !hasKey} onClick={loadAccounts}>
              <RefreshCw />
              Actualiser
            </Button>
          </div>
          {!hasKey ? <p className="text-muted-foreground text-xs">Enregistrer d’abord la clé Zernio dans la carte TikTok.</p> : null}
          {accounts && accounts.length === 0 ? (
            <p className="text-muted-foreground text-xs">
              Aucun compte : sur zernio.com, Accounts → Connect → Instagram, puis Actualiser.{" "}
              <a className="inline-flex items-center gap-1 underline" href="https://zernio.com/dashboard" target="_blank" rel="noreferrer noopener">
                Ouvrir Zernio
                <ExternalLink className="size-3" />
              </a>
            </p>
          ) : null}
          {accounts?.length ? (
            <ul className="flex flex-wrap gap-2">
              {accounts.map((a) => (
                <li key={a.id} className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
                  {a.avatar ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={a.avatar} alt="" className="size-6 rounded-full" />
                  ) : (
                    <Camera className="size-4" />
                  )}
                  <span className="font-medium">@{a.username}</span>
                  {a.kind ? <Badge variant="outline">{KINDS[a.kind] ?? a.kind}</Badge> : null}
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
          <span className="text-sm font-medium">Chaînes YouTube → Instagram</span>
          {channels.map((c) => {
            const link = links[c.id] ?? { account_id: "", enabled: false };
            const since = initial.channels[c.id]?.enabled && initial.channels[c.id]?.account_id === link.account_id ? initial.channels[c.id]?.enabled_at : null;
            return (
              <div key={c.id} className="flex flex-col gap-3 rounded-lg border p-3 md:flex-row md:items-center md:justify-between">
                <div className="flex flex-col gap-1">
                  <span className="text-sm font-medium">{c.name}</span>
                  <span className="text-muted-foreground text-xs">
                    {link.account_id && link.enabled
                      ? `Publication automatique${since ? ` depuis le ${formatDateTime(since)}` : " dès l’enregistrement"} : les Shorts programmés ensuite partent aussi en Reel.`
                      : "Pas de publication automatique : « Publier sur Instagram » reste possible dans la Bibliothèque."}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <Select value={link.account_id || NONE} onValueChange={(v) => setLinks((l) => ({ ...l, [c.id]: { ...link, account_id: v === NONE ? "" : v } }))}>
                    <SelectTrigger className="w-52" aria-label={`Compte Instagram de ${c.name}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NONE}>Aucun compte Instagram</SelectItem>
                      {known.map((a) => (
                        <SelectItem key={a.id} value={a.id}>
                          @{a.username}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <div className="flex items-center gap-2">
                    <Switch
                      id={`instagram-auto-${c.id}`}
                      checked={Boolean(link.account_id) && link.enabled}
                      disabled={!link.account_id}
                      onCheckedChange={(v) => setLinks((l) => ({ ...l, [c.id]: { ...link, enabled: v } }))}
                    />
                    <label htmlFor={`instagram-auto-${c.id}`} className="text-sm">
                      Automatique
                    </label>
                  </div>
                </div>
              </div>
            );
          })}
        </section>

        <section className="grid gap-3 md:grid-cols-2">
          <Toggle
            id="instagram-feed"
            label="Aussi dans la grille du profil"
            help="Le Reel apparaît dans la grille du profil, pas seulement dans l’onglet Reels."
            checked={options.share_to_feed}
            onChange={(v) => setOptions((o) => ({ ...o, share_to_feed: v }))}
          />
          <Toggle
            id="instagram-ai"
            label="Étiquette « IA » de Meta"
            help="Coupée par défaut, comme sur TikTok : Meta repère lui-même une partie des contenus IA."
            checked={options.ai_label}
            onChange={(v) => setOptions((o) => ({ ...o, ai_label: v }))}
          />
        </section>
        <p className="text-muted-foreground text-xs">
          Un Reel dure 90 s au plus : une vidéo plus longue est refusée. La légende reprend le titre et la description YouTube, sans #shorts et avec 5 hashtags au
          plus (limite d’Instagram).
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
