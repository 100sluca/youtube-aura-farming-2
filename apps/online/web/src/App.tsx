/**
 * Site en ligne de YouTube 2.0 (docs/65-site-en-ligne.md) : lit le dernier instantané envoyé par le dashboard du PC et
 * l'affiche en cinq onglets. Connexion par mot de passe (cookie posé par le Worker). Relecture chaque minute.
 */
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { LogOut, RefreshCw, TriangleAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getSnapshot, login, logout } from "@/lib/api";
import { ago, minutesSince, when } from "@/lib/format";
import type { SnapshotResponse } from "@/lib/snapshot";
import { cn } from "@/lib/utils";
import { ArgentView } from "@/views/argent";
import { DirectView } from "@/views/direct";
import { FabriqueView } from "@/views/fabrique";
import { RechercheView } from "@/views/recherche";
import { VideosView } from "@/views/videos";

const TABS = [
  { id: "direct", label: "Direct" },
  { id: "videos", label: "Vidéos" },
  { id: "fabrique", label: "Fabrique" },
  { id: "argent", label: "Argent" },
  { id: "recherche", label: "Recherche" },
] as const;
type TabId = (typeof TABS)[number]["id"];

/** L'envoi part toutes les 5 min : au-delà de 15, le PC ne répond plus. */
export type Freshness = { level: "ok" | "late" | "off"; text: string };
function freshness(receivedAt: string | null): Freshness {
  const m = minutesSince(receivedAt);
  if (!receivedAt) return { level: "off", text: "Rien reçu du PC pour l’instant." };
  if (m <= 15) return { level: "ok", text: `Chiffres reçus ${ago(receivedAt)}.` };
  if (m <= 60) return { level: "late", text: `Le PC n’a rien envoyé depuis ${Math.round(m)} min : chiffres du ${when(receivedAt)}.` };
  return { level: "off", text: `Derniers chiffres du ${when(receivedAt)}. Le PC est peut-être éteint ou le dashboard arrêté.` };
}

const initialTab = (): TabId => {
  const h = location.hash.slice(1);
  return TABS.some((t) => t.id === h) ? (h as TabId) : "direct";
};

export function App() {
  const [state, setState] = useState<"loading" | "login" | "ready">("loading");
  const [data, setData] = useState<SnapshotResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<TabId>(initialTab);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const { status, body } = await getSnapshot();
      if (status === 401) return setState("login");
      if (status !== 200) throw new Error(body.error ?? `Erreur ${status}`);
      setData(body);
      setError(null);
      setState("ready");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setState((s) => (s === "loading" ? "ready" : s));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => document.visibilityState === "visible" && void load(), 60_000);
    const onVisible = () => document.visibilityState === "visible" && void load();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load]);

  useEffect(() => {
    const onHash = () => setTab(initialTab());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const changeTab = (value: string) => {
    setTab(value as TabId);
    history.replaceState(null, "", `#${value}`);
    window.scrollTo({ top: 0 });
  };

  if (state === "loading") return <Loading />;
  if (state === "login") return <Login onDone={load} />;

  const snapshot = data?.snapshot ?? null;
  const fresh = freshness(data?.received_at ?? null);

  return (
    <Tabs value={tab} onValueChange={changeTab} className="min-h-svh gap-0">
      <header className="bg-background/90 sticky top-0 z-20 border-b pt-[env(safe-area-inset-top)] backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-3 px-4">
          <div className="flex items-center gap-2">
            <img src="/icon.svg" alt="" className="size-6 rounded-md" />
            <span className="font-semibold">Aura</span>
          </div>
          <Badge variant="outline" className="ml-auto gap-1.5 font-normal" title={fresh.text}>
            <span className={cn("size-1.5 rounded-full", { ok: "bg-success", late: "bg-warning", off: "bg-destructive" }[fresh.level])} />
            {data?.received_at ? ago(data.received_at) : "rien reçu"}
          </Badge>
          <Button variant="ghost" size="icon" aria-label="Actualiser" onClick={() => void load()} disabled={busy}>
            <RefreshCw className={cn(busy && "animate-spin")} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Se déconnecter"
            onClick={async () => {
              await logout();
              setData(null);
              setState("login");
            }}
          >
            <LogOut />
          </Button>
        </div>
        <div className="mx-auto max-w-5xl px-4 pb-3">
          <TabsList className="grid h-9 w-full grid-cols-5">
            {TABS.map((t) => (
              <TabsTrigger key={t.id} value={t.id} className="px-1 text-xs sm:text-sm">
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl px-4 pt-4 pb-[calc(2rem+env(safe-area-inset-bottom))]">
        {error ? (
          <Alert variant="destructive" className="mb-4">
            <TriangleAlert />
            <AlertTitle>Lecture impossible</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        {fresh.level !== "ok" ? (
          <Alert className="mb-4">
            <TriangleAlert className={fresh.level === "late" ? "text-warning" : "text-destructive"} />
            <AlertTitle>{fresh.level === "late" ? "Le PC est en retard" : "Le PC n’envoie plus rien"}</AlertTitle>
            <AlertDescription>{fresh.text}</AlertDescription>
          </Alert>
        ) : null}

        {snapshot ? (
          <>
            <TabsContent value="direct">
              <DirectView s={snapshot} goTo={changeTab} />
            </TabsContent>
            <TabsContent value="videos">
              <VideosView s={snapshot} />
            </TabsContent>
            <TabsContent value="fabrique">
              <FabriqueView s={snapshot} />
            </TabsContent>
            <TabsContent value="argent">
              <ArgentView s={snapshot} />
            </TabsContent>
            <TabsContent value="recherche">
              <RechercheView s={snapshot} />
            </TabsContent>
            <p className="text-muted-foreground mt-8 text-center text-xs">
              Instantané fait {when(snapshot.generated_at)}
              {snapshot.errors?.length ? ` · parties manquantes : ${snapshot.errors.join(" · ")}` : ""}
            </p>
          </>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>En attente du premier envoi</CardTitle>
              <CardDescription>Le dashboard du PC envoie ses chiffres toutes les 5 minutes. Rien n’est encore arrivé.</CardDescription>
            </CardHeader>
          </Card>
        )}
      </main>
    </Tabs>
  );
}

function Loading() {
  return (
    <div className="mx-auto grid max-w-5xl gap-4 p-4">
      <Skeleton className="h-9 w-full" />
      <div className="grid grid-cols-2 gap-4">
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}

function Login({ onDone }: { onDone: () => Promise<void> }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setPending(true);
    const { status, body } = await login(password);
    setPending(false);
    if (status === 200) return onDone();
    setError(body.error ?? "Connexion impossible.");
  };

  return (
    <div className="flex min-h-svh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="mb-2 flex items-center gap-2">
            <img src="/icon.svg" alt="" className="size-7 rounded-md" />
            <span className="text-lg font-semibold">Aura</span>
          </div>
          <CardTitle>Connexion</CardTitle>
          <CardDescription>Les stats, la fabrication et la veille de YouTube 2.0.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="password">Mot de passe</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                autoFocus
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={error ? true : undefined}
              />
              {error ? <p className="text-destructive text-sm">{error}</p> : null}
            </div>
            <Button type="submit" className="w-full" disabled={pending}>
              {pending ? "Connexion…" : "Se connecter"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
