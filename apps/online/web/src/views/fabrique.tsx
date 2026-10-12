/** Onglet Fabrique : la machine et chaque vidéo en route, avec son avancement et son heure de fin estimée. */
import { Empty, Meter } from "@/components/shared";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ago, eta, isNum } from "@/lib/format";
import type { Production, Snapshot } from "@/lib/snapshot";
import { cn } from "@/lib/utils";

const GROUPS: [Production["group"], string][] = [
  ["running", "En cours"],
  ["preparing", "Script et storyboard"],
  ["queued", "En file"],
  ["waiting", "Storyboard à valider"],
  ["paused", "En pause"],
  ["failed", "En échec"],
];

const gb = (n: number) => `${n.toFixed(1).replace(".", ",")} Go`;
const since = (iso: string | null) => (iso ? ago(iso).replace("il y a ", "") : null);

export function FabriqueView({ s }: { s: Snapshot }) {
  const p = s.production;
  const m = s.machine;
  const active = (p?.items ?? []).filter((i) => i.group !== "failed").length;

  return (
    <div className="grid grid-cols-1 gap-4">
      <Card>
        <CardHeader>
          <CardTitle>{active ? `${active} vidéo${active > 1 ? "s" : ""} en route` : "Rien en route"}</CardTitle>
          <CardDescription>{p?.queue_end_at ? `Toute la file finie ${eta(p.queue_end_at)}` : "Pas de fin estimée"}</CardDescription>
        </CardHeader>
        {p?.review_videos || p?.failed_jobs ? (
          <CardContent className="flex flex-wrap gap-2">
            {p.review_videos ? (
              <Badge variant="secondary">
                {p.review_videos} vidéo{p.review_videos > 1 ? "s" : ""} finie{p.review_videos > 1 ? "s" : ""} à valider
              </Badge>
            ) : null}
            {p.failed_jobs ? (
              <Badge variant="outline" className="text-destructive">
                {p.failed_jobs} tâche{p.failed_jobs > 1 ? "s" : ""} en échec sur 7 jours
              </Badge>
            ) : null}
          </CardContent>
        ) : null}
      </Card>

      {m ? (
        <Card>
          <CardHeader>
            <CardTitle>Machine</CardTitle>
            <CardDescription>
              {m.gpu_job ? `La carte graphique fait « ${m.gpu_job.label} »${m.gpu_job.started_at ? ` depuis ${since(m.gpu_job.started_at)}` : ""}` : "Carte graphique au repos"}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5">
            <div className="flex flex-wrap gap-2">
              <ServiceBadge ok={m.worker === "ok"} label="Worker" detail={isNum(m.worker_beat_s) ? `signe de vie il y a ${Math.round(m.worker_beat_s)} s` : null} />
              <ServiceBadge ok={m.comfy === "ok"} label="ComfyUI" detail={isNum(m.comfy_queue) ? `${m.comfy_queue} en file` : null} />
            </div>
            <div className="grid gap-5 sm:grid-cols-2">
              <Meter label="Mémoire" value={m.ram_total_gb - m.ram_free_gb} target={m.ram_total_gb} format={gb} />
              {isNum(m.vram_total_mb) && isNum(m.vram_used_mb) ? <Meter label="Carte graphique" value={m.vram_used_mb / 1024} target={m.vram_total_mb / 1024} format={gb} /> : null}
            </div>
            {m.warnings?.length ? (
              <ul className="text-warning ml-4 list-disc space-y-1 text-sm">
                {m.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {GROUPS.map(([group, label]) => {
        const items = (p?.items ?? []).filter((i) => i.group === group);
        if (!items.length) return null;
        return (
          <Card key={group}>
            <CardHeader>
              <CardTitle>{label}</CardTitle>
              <CardDescription>
                {items.length} vidéo{items.length > 1 ? "s" : ""}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="divide-y">
                {items.map((i) => (
                  <ProductionRow key={i.id} i={i} />
                ))}
              </ul>
            </CardContent>
          </Card>
        );
      })}
      {!p?.items.length ? (
        <Card>
          <CardContent>
            <Empty>Aucune vidéo en fabrication.</Empty>
          </CardContent>
        </Card>
      ) : null}

      {p?.retouches?.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Retouches</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {p.retouches.map((r, n) => (
                <li key={`${r.title}-${n}`} className="grid gap-1.5 py-3 first:pt-0 last:pb-0">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="line-clamp-1 text-sm font-medium">{r.title}</span>
                    <span className="text-muted-foreground shrink-0 text-sm whitespace-nowrap tabular-nums">{Math.round(r.progress_pct)} %</span>
                  </div>
                  <Progress value={r.progress_pct} />
                  <span className="text-muted-foreground text-xs">
                    {r.what} · {r.stage}
                    {r.eta_at ? ` · fin ${eta(r.eta_at)}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {p?.other_jobs?.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Autres tâches</CardTitle>
            <CardDescription>Stats, idées, recherche…</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {p.other_jobs.map((j, n) => (
                <li key={`${j.label}-${n}`} className="flex items-start justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{j.label}</p>
                    {j.detail ? <p className="text-muted-foreground text-xs">{j.detail}</p> : null}
                  </div>
                  <span className="text-muted-foreground shrink-0 text-xs tabular-nums">{j.status === "running" ? `${Math.round(j.progress ?? 0)} %` : "en file"}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function ServiceBadge({ ok, label, detail }: { ok: boolean; label: string; detail: string | null }) {
  return (
    <Badge variant="outline" className="gap-1.5 font-normal">
      <span className={cn("size-1.5 rounded-full", ok ? "bg-success" : "bg-destructive")} />
      {label} {ok ? "actif" : "arrêté"}
      {ok && detail ? <span className="text-muted-foreground">· {detail}</span> : null}
    </Badge>
  );
}

function ProductionRow({ i }: { i: Production }) {
  const live = i.group === "running";
  // Vidéo longue (docs/63) : pas d'avancement global, celui de l'étape en cours le remplace
  const stepOnly = live && !i.progress_pct && isNum(i.step_progress);
  const value = stepOnly ? (i.step_progress ?? 0) : i.progress_pct;
  const meta = [
    i.stage,
    i.clips_total && !/clip/i.test(i.stage) ? `${i.clips_done} / ${i.clips_total} clips` : null,
    live && i.step_started_at ? `étape commencée il y a ${since(i.step_started_at)}` : null,
    i.queue_position ? `n° ${i.queue_position} dans la file` : null,
    eta(i.eta_at) ? `fin ${eta(i.eta_at)}` : null,
  ].filter(Boolean);
  return (
    <li className="grid gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm leading-snug font-medium">{i.title}</p>
          {i.series ? <p className="text-muted-foreground text-xs">{i.series}</p> : null}
        </div>
        <span className="shrink-0 text-lg font-semibold whitespace-nowrap tabular-nums">{Math.round(value)} %</span>
      </div>
      <Progress value={value} className={live ? "[&>[data-slot=progress-indicator]]:bg-signal" : undefined} />
      <p className="text-muted-foreground text-xs">{meta.join(" · ")}</p>
      {stepOnly ? <p className="text-muted-foreground text-xs">Vidéo longue : le pourcentage est celui de l’étape en cours.</p> : null}
      {i.error ? <p className="text-destructive text-xs">{i.error}</p> : null}
    </li>
  );
}
