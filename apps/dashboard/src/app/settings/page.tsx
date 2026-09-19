import type { Metadata } from "next";
import { Cpu, Link2, Mail, Mic, Video } from "lucide-react";

import { ChannelBadge } from "@/components/channel-badge";
import { PageHeader } from "@/components/page-header";
import { AutoPublishSwitch } from "@/components/settings/auto-publish-switch";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getChannels } from "@/lib/data";
import { NOW, clampPct, formatDateTime, formatNumber, formatPercent } from "@/lib/format";

export const metadata: Metadata = { title: "Réglages" };

const ALERT_EMAIL = "adresse@example.com";
const QUOTA_MAX = 10_000;
const UPLOAD_COST = 1_600;

const QUOTAS: Record<string, number> = { fr: 8_200, en: 3_400 };

const PROVIDERS = [
  { label: "LLM (idéation, script, QA)", value: "anthropic", detail: "claude-sonnet-4-5", icon: Cpu },
  { label: "Génération vidéo", value: "comfy_ltx", detail: "ComfyUI · LTX-Video 2, GPU local", icon: Video },
  { label: "Voix off (TTS)", value: "kokoro", detail: "Kokoro 82M · voix fr_siwis / af_heart", icon: Mic },
];

const hoursAgo = (h: number) => new Date(NOW.getTime() - h * 3_600_000).toISOString();

const PROMPTS = [
  { agent: "ideate", version: 3, active: true, updated_at: hoursAgo(72) },
  { agent: "script", version: 4, active: true, updated_at: hoursAgo(26) },
  { agent: "script", version: 3, active: false, updated_at: hoursAgo(9 * 24) },
  { agent: "qa", version: 2, active: true, updated_at: hoursAgo(5 * 24) },
  { agent: "improve", version: 1, active: true, updated_at: hoursAgo(14 * 24) },
];

export default async function SettingsPage() {
  const channels = await getChannels();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader description="Chaînes YouTube, prompts des agents, fournisseurs IA, notifications et quota de l’API YouTube Data." />

      <section className="grid gap-4 lg:grid-cols-2">
        {channels.map((channel) => (
          <Card key={channel.id}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ChannelBadge lang={channel.lang} />
                {channel.name}
              </CardTitle>
              <CardDescription>
                Langue {channel.lang.toUpperCase()} · fuseau {channel.timezone} · {channel.is_active ? "active" : "inactive"}
              </CardDescription>
              <CardAction>
                <Button variant={channel.youtube_channel_id ? "outline" : "default"} size="sm" asChild>
                  <a href={`/api/youtube/connect?channel=${channel.slug}`}>
                    <Link2 />
                    {channel.youtube_channel_id ? "Reconnecter YouTube" : "Connecter YouTube"}
                  </a>
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex flex-col gap-1 text-sm">
                <span className="text-muted-foreground text-xs">Chaîne YouTube</span>
                {channel.youtube_channel_id ? (
                  <code className="bg-muted w-fit rounded px-1.5 py-0.5 font-mono text-xs">{channel.youtube_channel_id}</code>
                ) : (
                  <Badge variant="outline" className="w-fit border-amber-500/50 text-amber-700 dark:text-amber-400">
                    Non connectée
                  </Badge>
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-muted-foreground text-xs">Créneaux de publication</span>
                <div className="flex flex-wrap gap-1.5">
                  {channel.publish_slots.map((slot) => (
                    <Badge key={slot} variant="secondary" className="tabular-nums">
                      {slot}
                    </Badge>
                  ))}
                </div>
              </div>
              <AutoPublishSwitch id={`auto-publish-${channel.slug}`} defaultChecked={channel.auto_publish} />
            </CardContent>
          </Card>
        ))}
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card className="gap-0 overflow-hidden py-0">
          <CardHeader className="border-b py-5">
            <CardTitle>Prompts des agents</CardTitle>
            <CardDescription>Versions actives des instructions système de chaque agent.</CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-6">Agent</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Actif</TableHead>
                  <TableHead className="pr-6 text-right">Mis à jour</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {PROMPTS.map((prompt) => (
                  <TableRow key={`${prompt.agent}-${prompt.version}`}>
                    <TableCell className="pl-6 font-mono text-xs">{prompt.agent}</TableCell>
                    <TableCell className="tabular-nums">v{prompt.version}</TableCell>
                    <TableCell>
                      {prompt.active ? (
                        <Badge className="bg-emerald-600 text-white dark:bg-emerald-500">Actif</Badge>
                      ) : (
                        <Badge variant="outline">Archivé</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground pr-6 text-right text-xs tabular-nums">{formatDateTime(prompt.updated_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Fournisseurs</CardTitle>
              <CardDescription>Services utilisés par le worker.</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="flex flex-col gap-3">
                {PROVIDERS.map((provider) => {
                  const Icon = provider.icon;
                  return (
                    <li key={provider.label} className="flex items-center gap-3">
                      <span className="bg-muted text-muted-foreground flex size-8 shrink-0 items-center justify-center rounded-md">
                        <Icon className="size-4" />
                      </span>
                      <div className="flex min-w-0 flex-1 flex-col">
                        <span className="text-sm font-medium">{provider.label}</span>
                        <span className="text-muted-foreground text-xs">{provider.detail}</span>
                      </div>
                      <code className="bg-muted rounded px-1.5 py-0.5 font-mono text-xs">{provider.value}</code>
                    </li>
                  );
                })}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Notifications</CardTitle>
              <CardDescription>Destinataire des alertes de sévérité « erreur » et « avertissement ».</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3 rounded-lg border p-3 text-sm">
                <Mail className="text-muted-foreground size-4 shrink-0" />
                <div className="flex flex-col">
                  <span className="text-muted-foreground text-xs">E-mail d’alerte</span>
                  <span className="font-medium">{ALERT_EMAIL}</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Quota YouTube Data API</CardTitle>
          <CardDescription>
            Unités consommées aujourd’hui par chaîne, sur {formatNumber(QUOTA_MAX)} par projet et par jour (remise à zéro à minuit, heure du Pacifique).
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          {channels.map((channel) => {
            const used = QUOTAS[channel.slug] ?? 0;
            const pct = clampPct((used / QUOTA_MAX) * 100);
            const uploadsLeft = Math.floor((QUOTA_MAX - used) / UPLOAD_COST);
            return (
              <div key={channel.id} className="flex flex-col gap-2">
                <div className="flex items-center justify-between gap-2 text-sm">
                  <span className="flex items-center gap-2">
                    <ChannelBadge lang={channel.lang} />
                    {channel.name}
                  </span>
                  <span className="text-muted-foreground tabular-nums">
                    {formatNumber(used)} / {formatNumber(QUOTA_MAX)} · {formatPercent(pct)}
                  </span>
                </div>
                <Progress
                  value={pct}
                  aria-label={`Quota ${channel.name}`}
                  className={pct >= 80 ? "[&_[data-slot=progress-indicator]]:bg-amber-500" : undefined}
                />
                <p className="text-muted-foreground text-xs">
                  Encore {uploadsLeft} envoi{uploadsLeft > 1 ? "s" : ""} possible{uploadsLeft > 1 ? "s" : ""} aujourd’hui.
                </p>
              </div>
            );
          })}
          <p className="text-muted-foreground text-xs">
            Rappel : un appel <code className="font-mono">videos.insert</code> coûte {formatNumber(UPLOAD_COST)} unités ; les lectures de
            statistiques coûtent 1 unité.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
