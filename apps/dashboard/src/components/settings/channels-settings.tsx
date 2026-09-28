"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { CircleCheck, CircleX, DownloadCloud, Link2, LoaderCircle, Pencil, Plus, Trash2 } from "lucide-react";

import { createChannel, deleteChannel, importChannelHistory, updateChannel } from "@/app/settings/actions";
import { ChannelAvatar } from "@/components/channel-badge";
import { ConfirmButton } from "@/components/confirm-button";
import { AutoPublishSwitch } from "@/components/settings/auto-publish-switch";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatDateTime } from "@/lib/format";
import { LANG_LABELS } from "@/lib/labels";
import type { ChannelVideoCounts } from "@/lib/settings-data";
import type { Channel, ChannelLang } from "@/lib/types";
import { cn } from "@/lib/utils";

type Notice = { ok: boolean; message: string };

/** Nom + langue d'une chaîne : formulaire commun à « Ajouter » et « Modifier ». */
function ChannelDialog({
  open,
  onOpenChange,
  title,
  description,
  initial,
  submitLabel,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  initial: { name: string; lang: ChannelLang };
  submitLabel: string;
  onSubmit: (name: string, lang: ChannelLang) => Promise<Notice>;
}) {
  const [name, setName] = React.useState(initial.name);
  const [lang, setLang] = React.useState<ChannelLang>(initial.lang);
  const [error, setError] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            startTransition(async () => {
              const res = await onSubmit(name, lang);
              if (res.ok) onOpenChange(false);
              else setError(res.message);
            });
          }}
        >
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium">Nom</span>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex. Maisons incroyables" autoFocus maxLength={80} />
          </label>
          <div className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium">Langue des vidéos</span>
            <Select value={lang} onValueChange={(v) => setLang(v as ChannelLang)}>
              <SelectTrigger className="w-full" aria-label="Langue des vidéos">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(LANG_LABELS) as ChannelLang[]).map((l) => (
                  <SelectItem key={l} value={l}>
                    {LANG_LABELS[l]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-muted-foreground text-xs">Voix off, sous-titres, titre et description YouTube.</span>
          </div>
          {error ? <p className="text-destructive text-sm">{error}</p> : null}
          <DialogFooter>
            <Button type="submit" disabled={pending || name.trim().length < 2}>
              {pending ? <LoaderCircle className="animate-spin" /> : null}
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ChannelCard({ channel, counts, onNotice }: { channel: Channel; counts: ChannelVideoCounts | undefined; onNotice: (n: Notice) => void }) {
  const router = useRouter();
  const [editing, setEditing] = React.useState(false);
  const [pending, startTransition] = React.useTransition();
  const connected = Boolean(channel.youtube_channel_id);
  const run = (fn: () => Promise<Notice>) =>
    startTransition(async () => {
      onNotice(await fn());
      router.refresh();
    });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ChannelAvatar channel={channel} className="size-7 text-[11px]" />
          <span className="truncate">{channel.name}</span>
        </CardTitle>
        <CardDescription>
          {LANG_LABELS[channel.lang]} · fuseau {channel.timezone}
          {counts ? ` · ${counts.app} vidéo${counts.app > 1 ? "s" : ""} produite${counts.app > 1 ? "s" : ""}` : ""}
        </CardDescription>
        <CardAction className="flex gap-1.5">
          <Button variant="ghost" size="icon" aria-label="Modifier le nom ou la langue" onClick={() => setEditing(true)}>
            <Pencil />
          </Button>
          <Button variant={connected ? "outline" : "default"} size="sm" asChild>
            <a href={`/api/youtube/connect?channel=${channel.slug}`}>
              <Link2 />
              {connected ? "Reconnecter" : "Connecter YouTube"}
            </a>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-1 text-sm">
          <span className="text-muted-foreground text-xs">Chaîne YouTube</span>
          {connected ? (
            <span className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{channel.youtube_title ?? "Connectée"}</span>
              <code className="bg-muted rounded px-1.5 py-0.5 font-mono text-xs">{channel.youtube_channel_id}</code>
            </span>
          ) : (
            <Badge variant="outline" className="w-fit border-amber-500/50 text-amber-700 dark:text-amber-400">
              Pas encore connectée : rien ne sera publié
            </Badge>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
          <div className="flex flex-col gap-0.5 text-sm">
            <span className="font-medium">Historique de la chaîne</span>
            <span className="text-muted-foreground text-xs">
              {counts?.importing
                ? "Import en cours…"
                : channel.history_imported_at
                  ? `${counts?.imported ?? 0} vidéo${(counts?.imported ?? 0) > 1 ? "s" : ""} importée${(counts?.imported ?? 0) > 1 ? "s" : ""} · mis à jour le ${formatDateTime(channel.history_imported_at)}`
                  : connected
                    ? "Pas encore importé"
                    : "Disponible une fois la chaîne connectée"}
            </span>
          </div>
          <Button variant="outline" size="sm" disabled={!connected || pending || counts?.importing} onClick={() => run(() => importChannelHistory(channel.id))}>
            {counts?.importing ? <LoaderCircle className="animate-spin" /> : <DownloadCloud />}
            {channel.history_imported_at ? "Mettre à jour" : "Importer"}
          </Button>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-muted-foreground text-xs">Créneaux de publication (heure de Paris)</span>
          <div className="flex flex-wrap gap-1.5">
            {channel.publish_slots.map((slot) => (
              <Badge key={slot} variant="secondary" className="tabular-nums">
                {slot}
              </Badge>
            ))}
          </div>
        </div>

        <AutoPublishSwitch id={`auto-publish-${channel.slug}`} slug={channel.slug} defaultChecked={channel.auto_publish} />

        {(counts?.app ?? 0) === 0 ? (
          <ConfirmButton variant="ghost" size="sm" className="text-destructive w-fit" disabled={pending} onConfirm={() => run(() => deleteChannel(channel.id))} confirmLabel="Confirmer la suppression">
            <Trash2 />
            Supprimer la chaîne
          </ConfirmButton>
        ) : null}
      </CardContent>

      <ChannelDialog
        key={editing ? "open" : "closed"}
        open={editing}
        onOpenChange={setEditing}
        title="Modifier la chaîne"
        description="La langue s’applique aux prochaines vidéos ; celles déjà faites ne changent pas."
        initial={{ name: channel.name, lang: channel.lang }}
        submitLabel="Enregistrer"
        onSubmit={async (name, lang) => {
          const res = await updateChannel(channel.id, name, lang);
          onNotice(res);
          router.refresh();
          return res;
        }}
      />
    </Card>
  );
}

/** Réglages → Chaînes : les chaînes YouTube de l'usine, leur connexion et leur historique. */
export function ChannelsSettings({
  channels,
  counts,
  openAdd,
}: {
  channels: Channel[];
  counts: Record<string, ChannelVideoCounts>;
  openAdd: boolean;
}) {
  const router = useRouter();
  const [adding, setAdding] = React.useState(openAdd);
  const [notice, setNotice] = React.useState<Notice | null>(null);

  return (
    <section id="chaines" className="flex scroll-mt-20 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold tracking-tight">Chaînes YouTube</h2>
        <span className="text-muted-foreground text-sm tabular-nums">{channels.length}</span>
        <Button size="sm" className="ml-auto" onClick={() => setAdding(true)}>
          <Plus />
          Ajouter une chaîne
        </Button>
      </div>
      <p className="text-muted-foreground -mt-1 text-sm">
        Une chaîne = un nom, une langue et un compte YouTube. À la connexion, ses vidéos déjà en ligne sont importées dans la Bibliothèque (marquées « Importée »), à
        côté de celles produites ici.
      </p>
      {notice ? (
        <p className={cn("flex items-center gap-1.5 text-sm", notice.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")} role="status">
          {notice.ok ? <CircleCheck className="size-4" /> : <CircleX className="size-4" />}
          {notice.message}
        </p>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2">
        {channels.map((channel) => (
          <ChannelCard key={channel.id} channel={channel} counts={counts[channel.id]} onNotice={setNotice} />
        ))}
      </div>
      <ChannelDialog
        key={adding ? "open" : "closed"}
        open={adding}
        onOpenChange={setAdding}
        title="Ajouter une chaîne"
        description="Donne-lui un nom et une langue, puis connecte-la à son compte YouTube. Tu pourras la choisir dans Création et en haut de chaque page."
        initial={{ name: "", lang: "fr" }}
        submitLabel="Ajouter"
        onSubmit={async (name, lang) => {
          const res = await createChannel(name, lang);
          setNotice(res);
          router.refresh();
          return res;
        }}
      />
    </section>
  );
}
