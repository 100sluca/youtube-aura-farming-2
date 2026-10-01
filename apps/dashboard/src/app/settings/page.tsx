import type { Metadata } from "next";
import Link from "next/link";
import { Bot, CircleCheck, CircleX } from "lucide-react";

import { ChannelBadge } from "@/components/channel-badge";
import { PageHeader } from "@/components/page-header";
import { ChannelsSettings } from "@/components/settings/channels-settings";
import { GeminiSettingsCard } from "@/components/settings/gemini-settings";
import { GenerationSettingsCard } from "@/components/settings/generation-settings";
import { LlmSettingsCard } from "@/components/settings/llm-settings";
import { NotificationsSettingsCard } from "@/components/settings/notifications-settings";
import { InstagramSettingsCard } from "@/components/settings/instagram-settings";
import { TikTokSettingsCard } from "@/components/settings/tiktok-settings";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { getPromptStates } from "@/lib/agents";
import { getChannels } from "@/lib/data";
import { clampPct, formatNumber, formatPercent } from "@/lib/format";
import { getGeminiBrowserInfo, getGeminiSettings, getGeminiStatus } from "@/lib/gemini";
import { getGenerationCatalog, getGenerationSettings } from "@/lib/generation-data";
import { getNotificationSettings, getNotifyStatus } from "@/lib/notify";
import { PRESET_MODELS, getChannelVideoCounts, getLlmSettings, getQuotaToday, getSecretHints } from "@/lib/settings-data";
import { getInstagramSettings } from "@/lib/instagram";
import { getTikTokBacklog, getTikTokSettings, getZernioKeyHint } from "@/lib/tiktok";

export const metadata: Metadata = { title: "Réglages" };

const QUOTA_MAX = 10_000;
const UPLOADS_PER_DAY = 100; // videos.insert : compteur séparé, 100 appels par jour à 1 unité (vérifié le 2026-09-21)

export default async function SettingsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const [channels, llm, hints, prompts, quota, generation, catalog, gemini, geminiStatus, geminiBrowser, notifications, notifyStatus, tiktok, zernioHint, tiktokBacklog, instagram] = await Promise.all([
    getChannels(),
    getLlmSettings(),
    getSecretHints(),
    getPromptStates(),
    getQuotaToday(),
    getGenerationSettings(),
    getGenerationCatalog(),
    getGeminiSettings(),
    getGeminiStatus(),
    getGeminiBrowserInfo(),
    getNotificationSettings(),
    getNotifyStatus(),
    getTikTokSettings(),
    getZernioKeyHint(),
    getTikTokBacklog(),
    getInstagramSettings(),
  ]);
  const connected = typeof params.connected === "string" ? params.connected : null;
  const oauthError = typeof params.oauth_error === "string" ? params.oauth_error : null;
  const counts = await getChannelVideoCounts(channels.map((c) => c.id));
  const promptStates = Object.values(prompts);
  const customPrompts = promptStates.filter((p) => p.active && p.active.origin !== "code").length;
  const codeUpdates = promptStates.filter((p) => p.codeUpdate).length;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader description="Chaînes YouTube (ajout, connexion, historique), publication sur TikTok et Instagram (Zernio), modèles de génération (images, vidéo, voix), Gemini en ligne, intelligence artificielle (clés et modèles), notifications par e-mail, prompts des agents et quota de l’API YouTube Data." />

      {connected ? (
        <p className="flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm" role="status">
          <CircleCheck className="size-4 text-emerald-600" />
          Chaîne « {connected} » connectée à YouTube : son historique s’importe dans la Bibliothèque (quelques minutes, avec le worker lancé).
        </p>
      ) : null}
      {oauthError ? (
        <p className="border-destructive/40 bg-destructive/10 flex items-center gap-2 rounded-lg border p-3 text-sm" role="alert">
          <CircleX className="text-destructive size-4" />
          Connexion YouTube refusée : {oauthError}
        </p>
      ) : null}

      <ChannelsSettings channels={channels} counts={counts} openAdd={params.add_channel === "1"} />

      <TikTokSettingsCard initial={tiktok} keyHint={zernioHint} channels={channels} backlog={tiktokBacklog} />

      <InstagramSettingsCard initial={instagram} hasKey={Boolean(zernioHint)} channels={channels} />

      <GenerationSettingsCard initial={generation} catalog={catalog} />

      <GeminiSettingsCard initial={gemini} status={geminiStatus} browser={geminiBrowser} />

      <LlmSettingsCard initial={llm} hints={hints} presets={PRESET_MODELS} />

      <NotificationsSettingsCard initial={notifications} status={notifyStatus} />

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Prompts des agents</CardTitle>
            <CardDescription>
              Les agents, leurs prompts système, les consignes communes qu’ils reçoivent et la chaîne de production complète se lisent et se modifient dans
              l’onglet Agents (docs/22). Le worker lit la version en service à chaque tâche.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <p className="text-sm">
              {promptStates.length} prompts en base · {customPrompts === 0 ? "tous suivent le texte du code" : `${customPrompts} version${customPrompts > 1 ? "s" : ""} choisie${customPrompts > 1 ? "s" : ""} dans le dashboard`}
              {codeUpdates ? ` · ${codeUpdates} nouveau${codeUpdates > 1 ? "x" : ""} texte${codeUpdates > 1 ? "s" : ""} du code à regarder` : ""}
            </p>
            <Button asChild variant="outline" className="w-fit">
              <Link href="/agents">
                <Bot />
                Ouvrir l’onglet Agents
              </Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quota YouTube Data API</CardTitle>
            <CardDescription>
              Unités consommées aujourd’hui par chaîne, sur {formatNumber(QUOTA_MAX)} par jour ; les envois ont leur propre compteur de {UPLOADS_PER_DAY} par jour.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            {channels.map((channel) => {
              const used = quota[channel.id]?.units ?? 0;
              const uploads = quota[channel.id]?.uploads ?? 0;
              const pct = clampPct((used / QUOTA_MAX) * 100);
              return (
                <div key={channel.id} className="flex flex-col gap-2">
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <ChannelBadge channel={channel} />
                    <span className="text-muted-foreground tabular-nums">
                      {formatNumber(used)} / {formatNumber(QUOTA_MAX)} · {formatPercent(pct)}
                    </span>
                  </div>
                  <Progress value={pct} aria-label={`Quota ${channel.name}`} className={pct >= 80 ? "[&_[data-slot=progress-indicator]]:bg-amber-500" : undefined} />
                  <p className="text-muted-foreground text-xs">
                    {uploads} envoi{uploads > 1 ? "s" : ""} aujourd’hui, {UPLOADS_PER_DAY - uploads} encore possible{UPLOADS_PER_DAY - uploads > 1 ? "s" : ""}.
                  </p>
                </div>
              );
            })}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
