/** Onglet Recherche (docs/60, 63, 64) : le stratège, les niches, les vidéos à reproduire, la Découverte, les questions. */
import { ExternalLink } from "lucide-react";

import { Empty, PlatformIcon, Sparkline } from "@/components/shared";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { compact, dayLabel, duration, euros, fmt, isNum, safeUrl } from "@/lib/format";
import type { Research, ResearchVideo, Snapshot } from "@/lib/snapshot";
import { cn } from "@/lib/utils";

const ACTIONS: Record<string, string> = {
  scan: "relevé des niches",
  explore: "exploration",
  watch: "Gemini regarde",
  adapt: "adaptation",
  reproduce: "reproduction",
  brief: "rapport du stratège",
  ask: "question au stratège",
  discover_shorts: "découverte de Shorts",
  discover: "découverte",
};
const VERDICT_TONE: Record<string, string> = { "à lancer": "text-success", "à tester": "text-tiktok", "à surveiller": "text-warning", "à éviter": "text-destructive" };
const PHASE_TONE: Record<string, string> = { émergente: "text-signal", "en hausse": "text-success", installée: "text-tiktok", "en baisse": "text-destructive" };

export function RechercheView({ s }: { s: Snapshot }) {
  const r = s.research;
  if (!r) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>La veille arrive au prochain envoi</CardTitle>
          <CardDescription>Le PC n’a pas encore envoyé la page Recherche.</CardDescription>
        </CardHeader>
      </Card>
    );
  }
  const rep = r.report;
  const byId = new Map(r.videos.map((v) => [v.id, v]));
  const next = rep?.next_video ?? null;
  const nextVideo = next?.video_id ? byId.get(next.video_id) : undefined;
  const names = new Map(r.niches.flatMap((n) => [[n.slug, n.label] as const, [n.label, n.label] as const]));
  const nicheName = (slug: string) => names.get(slug) ?? slug.replace(/_/g, " ");

  return (
    <div className="grid grid-cols-1 gap-4">
      {r.running?.length ? (
        <Alert>
          <AlertDescription>En cours sur le PC : {r.running.map((x) => ACTIONS[x] ?? x).join(", ")}</AlertDescription>
        </Alert>
      ) : null}

      {rep ? (
        <Card>
          <CardHeader>
            <CardDescription>Le stratège · {dayLabel(rep.created_at)}</CardDescription>
            <CardTitle className="text-base leading-snug">{rep.headline}</CardTitle>
          </CardHeader>
          {next ? (
            <CardContent className="grid gap-3">
              <div className="bg-muted/50 grid gap-3 rounded-lg border p-3">
                <p className="text-signal text-xs font-medium">La vidéo à faire maintenant</p>
                <div className="flex gap-3">
                  {safeUrl(nextVideo?.thumbnail) ? (
                    <img src={safeUrl(nextVideo?.thumbnail)} alt="" loading="lazy" referrerPolicy="no-referrer" className="h-20 w-14 shrink-0 rounded-md object-cover" />
                  ) : null}
                  <div className="min-w-0 text-sm">
                    <p className="font-medium">{nextVideo?.title ?? next.ref}</p>
                    {nextVideo ? (
                      <p className="text-muted-foreground text-xs">
                        {compact(nextVideo.views)} vues · {nextVideo.channel}
                      </p>
                    ) : null}
                  </div>
                </div>
                <p className="text-sm">{next.why}</p>
                {next.how ? <p className="text-muted-foreground text-sm">{next.how}</p> : null}
              </div>
              {rep.warnings?.length ? (
                <ul className="text-warning ml-4 list-disc space-y-1 text-sm">
                  {rep.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              ) : null}
            </CardContent>
          ) : null}
        </Card>
      ) : null}

      {rep?.niches?.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Verdict par niche</CardTitle>
            <CardDescription>Ce que le stratège conseille de lancer, tester ou éviter</CardDescription>
          </CardHeader>
          <CardContent>
            <Accordion type="single" collapsible>
              {rep.niches.map((n) => (
                <AccordionItem key={n.niche} value={n.niche}>
                  <AccordionTrigger className="items-center hover:no-underline">
                    <span className="flex min-w-0 flex-1 items-center justify-between gap-3">
                      <span className="truncate">{nicheName(n.niche)}</span>
                      <Badge variant="outline" className={VERDICT_TONE[n.verdict]}>
                        {n.verdict}
                      </Badge>
                    </span>
                  </AccordionTrigger>
                  <AccordionContent className="grid gap-2">
                    <p>{n.why}</p>
                    {n.how ? <p className="text-muted-foreground">{n.how}</p> : null}
                    {n.first_videos?.length ? (
                      <ul className="ml-4 list-disc space-y-1">
                        {n.first_videos.map((x) => (
                          <li key={x}>{x}</li>
                        ))}
                      </ul>
                    ) : null}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </CardContent>
        </Card>
      ) : null}

      {r.videos.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Vidéos à reproduire</CardTitle>
            <CardDescription>Les meilleures des 4 derniers mois, celles du stratège d’abord</CardDescription>
          </CardHeader>
          <CardContent>
            <Accordion type="single" collapsible>
              {r.videos.map((v) => (
                <ReferenceRow key={v.id} v={v} />
              ))}
            </Accordion>
          </CardContent>
        </Card>
      ) : null}

      {r.niches.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Niches suivies</CardTitle>
            <CardDescription>{r.niches.length} niches, de la mieux notée à la moins bien notée</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {r.niches.map((n) => (
                <li key={n.id} className="grid gap-1.5 py-3 first:pt-0 last:pb-0">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{n.label}</p>
                      {n.description ? <p className="text-muted-foreground line-clamp-2 text-xs">{n.description}</p> : null}
                    </div>
                    {isNum(n.score) ? <span className="shrink-0 text-lg font-semibold tabular-nums">{Math.round(n.score)}</span> : null}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {n.phase ? (
                      <Badge variant="outline" className={cn(PHASE_TONE[n.phase])}>
                        {n.phase}
                      </Badge>
                    ) : null}
                    {n.status === "proposed" ? <Badge variant="secondary">proposée</Badge> : null}
                    {isNum(n.median_views_month) ? <Badge variant="secondary">{compact(n.median_views_month)} vues médianes</Badge> : null}
                    {isNum(n.hits_month) ? <Badge variant="secondary">{fmt(n.hits_month)} tubes ce mois</Badge> : null}
                    {isNum(n.effort) ? <Badge variant="secondary">effort {n.effort}/5</Badge> : null}
                  </div>
                  {n.curve.filter((c) => isNum(c.median_views)).length > 1 ? <Sparkline values={n.curve.map((c) => c.median_views)} color="var(--signal)" className="h-8" /> : null}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {rep?.fast_formats?.length || rep?.new_niches?.length ? (
        <div className="grid gap-4 md:grid-cols-2">
          {rep?.fast_formats?.length ? (
            <Card>
              <CardHeader>
                <CardTitle>Formats rapides</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="divide-y">
                  {rep.fast_formats.map((f) => (
                    <li key={f.format} className="py-2.5 text-sm first:pt-0 last:pb-0">
                      <p className="font-medium">{f.format}</p>
                      <p className="text-muted-foreground text-xs">{f.why}</p>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
          {rep?.new_niches?.length ? (
            <Card>
              <CardHeader>
                <CardTitle>Niches à explorer</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="divide-y">
                  {rep.new_niches.map((n) => (
                    <li key={n.label} className="py-2.5 text-sm first:pt-0 last:pb-0">
                      <p className="font-medium">{n.label}</p>
                      <p className="text-muted-foreground text-xs">{n.description}</p>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : null}

      {r.discovery?.length ? <Discovery list={r.discovery} /> : null}

      {r.asks?.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Tes questions au stratège</CardTitle>
          </CardHeader>
          <CardContent>
            <Accordion type="single" collapsible>
              {r.asks.map((a, n) => (
                <AccordionItem key={`${a.at}-${n}`} value={`${n}`}>
                  <AccordionTrigger>{a.question}</AccordionTrigger>
                  <AccordionContent className="text-muted-foreground whitespace-pre-wrap">
                    {a.answer ?? (a.status === "failed" ? "Échec." : "Réponse en cours…")}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function ReferenceRow({ v }: { v: ResearchVideo }) {
  const thumb = safeUrl(v.thumbnail);
  return (
    <AccordionItem value={v.id}>
      <AccordionTrigger className="items-center gap-3 py-3 hover:no-underline">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          {thumb ? <img src={thumb} alt="" loading="lazy" referrerPolicy="no-referrer" className="bg-muted h-16 w-11 shrink-0 rounded-md object-cover" /> : <div className="bg-muted h-16 w-11 shrink-0 rounded-md" />}
          <div className="grid min-w-0 gap-1">
            <span className="line-clamp-2 text-sm leading-snug font-medium">{v.title}</span>
            <span className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-normal">
              <span className="text-foreground tabular-nums">{compact(v.views)} vues</span>
              {isNum(v.outlier) ? <span className="text-signal tabular-nums">×{v.outlier.toFixed(1).replace(".", ",")}</span> : null}
              {v.niche ? <span className="truncate">{v.niche}</span> : null}
              {v.status === "shortlisted" ? <Badge variant="secondary">retenue</Badge> : null}
            </span>
          </div>
        </div>
      </AccordionTrigger>
      <AccordionContent className="grid gap-3">
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="secondary">{compact(v.views_per_day)} vues par jour</Badge>
          {isNum(v.outlier) ? <Badge variant="secondary">×{v.outlier.toFixed(1).replace(".", ",")} la normale de la chaîne</Badge> : null}
          {v.published_at ? <Badge variant="secondary">sortie {dayLabel(v.published_at)}</Badge> : null}
          {isNum(v.duration_s) ? <Badge variant="secondary">{duration(v.duration_s)}</Badge> : null}
          <Badge variant="secondary">score {fmt(v.remake_score)}</Badge>
        </div>
        <p className="text-muted-foreground text-xs">
          {v.channel}
          {isNum(v.channel_subs) ? ` · ${compact(v.channel_subs)} abonnés` : ""}
        </p>
        {v.summary ? <p>{v.summary}</p> : null}
        {v.hook ? <p className="text-muted-foreground border-l-2 pl-3">Accroche : {v.hook}</p> : null}
        {v.why?.length ? (
          <div>
            <p className="mb-1 font-medium">Pourquoi ça marche</p>
            <ul className="text-muted-foreground ml-4 list-disc space-y-1">
              {v.why.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {v.remake ? (
          <div className="bg-muted/50 rounded-lg border p-3">
            <p className="text-signal text-xs font-medium">Notre version</p>
            <p className="mt-1 font-medium">{v.remake.title}</p>
            <p className="text-muted-foreground mt-1">{v.remake.premise}</p>
          </div>
        ) : null}
        {v.adaptation ? <p className="text-muted-foreground text-xs">Version fidèle en français prête : {v.adaptation}</p> : null}
        {safeUrl(v.url) ? (
          <Button variant="outline" size="sm" className="w-fit" asChild>
            <a href={safeUrl(v.url)} target="_blank" rel="noopener noreferrer">
              <PlatformIcon platform="youtube" />
              Regarder
              <ExternalLink className="text-muted-foreground" />
            </a>
          </Button>
        ) : null}
      </AccordionContent>
    </AccordionItem>
  );
}

function Discovery({ list }: { list: Research["discovery"] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Découverte</CardTitle>
        <CardDescription>Les chaînes qui percent, par niche, argent estimé par mois</CardDescription>
      </CardHeader>
      <CardContent>
        {list.length ? (
          <Accordion type="single" collapsible>
            {list.map((n) => (
              <AccordionItem key={n.niche} value={n.niche}>
                <AccordionTrigger className="items-center hover:no-underline">
                  <span className="flex min-w-0 flex-1 items-center justify-between gap-3">
                    <span className="truncate">{n.niche}</span>
                    <span className="text-muted-foreground shrink-0 font-normal tabular-nums">{euros(n.revenue)} / mois</span>
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <p className="text-muted-foreground mb-2 text-xs">
                    {n.category}
                    {n.langs?.length ? ` · ${n.langs.join(", ")}` : ""}
                  </p>
                  <ul className="divide-y">
                    {n.channels.map((c) => (
                      <li key={c.url} className="grid gap-1 py-2.5 first:pt-0 last:pb-0">
                        <div className="flex items-baseline justify-between gap-3">
                          <a href={safeUrl(c.url)} target="_blank" rel="noopener noreferrer" className="truncate font-medium underline-offset-4 hover:underline">
                            {c.title}
                          </a>
                          <span className="text-muted-foreground shrink-0 tabular-nums">{euros(c.revenue)}</span>
                        </div>
                        <p className="text-muted-foreground text-xs">
                          {[
                            c.format,
                            isNum(c.subs) ? `${compact(c.subs)} abonnés` : null,
                            isNum(c.monthly_views) ? `${compact(c.monthly_views)} vues / mois` : null,
                            isNum(c.months) ? `${String(c.months).replace(".", ",")} mois` : null,
                            isNum(c.rpm) ? `RPM ${c.rpm.toFixed(2).replace(".", ",")} $` : null,
                            c.lang,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                        {c.why ? <p className="text-xs">{c.why}</p> : null}
                      </li>
                    ))}
                  </ul>
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        ) : (
          <Empty>Rien de découvert pour l’instant.</Empty>
        )}
      </CardContent>
    </Card>
  );
}
