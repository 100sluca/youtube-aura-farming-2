/** Onglet Argent : revenus réels, valeur estimée des vues, seuils de monétisation. Taux : docs/61-ou-est-l-argent.md. */
import { Meter, PlatformDot, PlatformIcon } from "@/components/shared";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { compact, euros, fmt, sum } from "@/lib/format";
import { PLATFORM_LABEL, PLATFORMS, type Platform, type Snapshot } from "@/lib/snapshot";

/** Ce que vaudraient 1 000 vues si la plateforme payait déjà (relevés du 04/10/2026). */
const RATES: Record<Platform, { per1000: number; note: string }> = {
  youtube: { per1000: 0.09, note: "Shorts : ≈ 0,10 $ (0,09 €) pour 1 000 vues en France" },
  tiktok: { per1000: 0.35, note: "Creator Rewards : 0,30 à 0,40 € pour 1 000 vues, vidéos de plus d’1 min" },
  instagram: { per1000: 0, note: "Pas de bonus Reels en France" },
};

export function ArgentView({ s }: { s: Snapshot }) {
  const nets = (s.networks ?? []).filter((a) => a.connected);
  const by = (p: Platform, f: "views_28d" | "views_7d") => sum(nets.filter((a) => a.platform === p).map((a) => a[f]));
  const worth = (p: Platform) => (by(p, "views_28d") / 1000) * RATES[p].per1000;
  const k = s.youtube?.kpis;
  const ytSubs = s.youtube?.subscribers ?? k?.subscribers ?? null;
  const shorts90 = k?.ypp?.views_90d ?? null;
  const perDay = by("youtube", "views_7d") / 7;
  const years = perDay > 0 ? (10_000_000 - (shorts90 ?? 0)) / perDay / 365 : null;

  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardDescription>Revenus réels</CardDescription>
            <CardTitle className="text-3xl font-semibold tabular-nums">0 €</CardTitle>
          </CardHeader>
          <CardFooter className="text-muted-foreground text-sm">Aucune plateforme ne paie encore : les seuils plus bas ne sont pas atteints.</CardFooter>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Si les vues des 28 derniers jours étaient payées</CardDescription>
            <CardTitle className="text-3xl font-semibold tabular-nums">≈ {euros(sum(PLATFORMS.map(worth)))}</CardTitle>
          </CardHeader>
          <CardFooter className="text-muted-foreground text-sm">Estimation, pas un relevé. Une vue américaine vaut à peu près le double d’une vue française.</CardFooter>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Valeur des vues · 28 jours</CardTitle>
          <CardDescription>Taux moyens de docs/61, par réseau</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Réseau</TableHead>
                <TableHead className="text-right">Vues</TableHead>
                <TableHead className="text-right">Estimation</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {PLATFORMS.map((p) => (
                <TableRow key={p}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <PlatformDot platform={p} />
                      {PLATFORM_LABEL[p]}
                    </div>
                    <div className="text-muted-foreground mt-0.5 text-xs whitespace-normal">{RATES[p].note}</div>
                  </TableCell>
                  <TableCell className="text-right align-top tabular-nums">{fmt(by(p, "views_28d"))}</TableCell>
                  <TableCell className="text-right align-top tabular-nums">{euros(worth(p))}</TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell>Total</TableCell>
                <TableCell className="text-right tabular-nums">{fmt(sum(PLATFORMS.map((p) => by(p, "views_28d"))))}</TableCell>
                <TableCell className="text-right tabular-nums">{euros(sum(PLATFORMS.map(worth)))}</TableCell>
              </TableRow>
            </TableFooter>
          </Table>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>YouTube · Programme Partenaire</CardTitle>
            <CardDescription>1 000 abonnés et 10 M de vues de Shorts sur 90 jours</CardDescription>
            <CardAction>
              <PlatformIcon platform="youtube" className="size-5" />
            </CardAction>
          </CardHeader>
          <CardContent className="grid gap-5">
            <Meter label="Abonnés" value={ytSubs} target={1000} format={fmt} />
            <Meter label="Vues de Shorts sur 90 jours" value={shorts90} target={10_000_000} format={compact} accent />
          </CardContent>
          <CardFooter className="text-muted-foreground flex-col items-start gap-1 text-xs">
            {years !== null ? (
              <p>
                Au rythme des 7 derniers jours ({fmt(perDay)} vues par jour), 10 M de vues prendraient {years > 10 ? "plus de 10 ans" : `≈ ${years.toFixed(1).replace(".", ",")} ans`}.
              </p>
            ) : null}
            <p>Ou 4 000 h de vidéos longues sur 12 mois. Dès le 01/02/2027, un nouveau candidat aura besoin de 8 000 h.</p>
          </CardFooter>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>TikTok · Creator Rewards</CardTitle>
            <CardDescription>10 000 abonnés et 100 000 vues sur 30 jours</CardDescription>
            <CardAction>
              <PlatformIcon platform="tiktok" className="size-5" />
            </CardAction>
          </CardHeader>
          <CardContent className="grid gap-5">
            <Meter label="Abonnés" value={s.tiktok?.followers} target={10_000} format={fmt} />
            <Meter label="Vues sur 28 jours" value={by("tiktok", "views_28d")} target={100_000} format={compact} />
          </CardContent>
          <CardFooter className="text-muted-foreground text-xs">Seules les vidéos de plus d’1 minute sont payées. La France est éligible.</CardFooter>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Instagram</CardTitle>
          <CardDescription>Pas de bonus Reels en France : Instagram sert à faire venir du monde.</CardDescription>
          <CardAction>
            <PlatformIcon platform="instagram" className="size-5" />
          </CardAction>
        </CardHeader>
        <CardContent className="text-sm">
          <span className="font-semibold tabular-nums">{fmt(by("instagram", "views_28d"))}</span> <span className="text-muted-foreground">vues sur 28 jours</span>
        </CardContent>
      </Card>
    </div>
  );
}
