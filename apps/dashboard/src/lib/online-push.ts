/**
 * Envoi de l'instantané au site en ligne (docs/65-site-en-ligne.md) : POST <ONLINE_URL>/api/ingest avec le jeton
 * ONLINE_INGEST_TOKEN (même valeur que le secret INGEST_TOKEN du Worker Cloudflare). Sans ces deux lignes dans
 * apps/dashboard/.env.local, rien ne part (PC du frère de Luca, sessions de développement). Serveur uniquement.
 */
import { buildOnlineSnapshot } from "@/lib/online-snapshot";

export interface OnlinePushResult {
  ok: boolean;
  at: string;
  status: number | null;
  bytes: number;
  error: string | null;
}

export function onlineTarget(): { url: string; token: string } | null {
  const url = process.env.ONLINE_URL?.trim().replace(/\/+$/, "");
  const token = process.env.ONLINE_INGEST_TOKEN?.trim();
  return url && token ? { url, token } : null;
}

export async function pushOnlineSnapshot(): Promise<OnlinePushResult> {
  const at = new Date().toISOString();
  const target = onlineTarget();
  if (!target) return { ok: false, at, status: null, bytes: 0, error: "ONLINE_URL ou ONLINE_INGEST_TOKEN absent de .env.local" };
  const body = JSON.stringify(await buildOnlineSnapshot());
  try {
    const res = await fetch(`${target.url}/api/ingest`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${target.token}` },
      body,
      signal: AbortSignal.timeout(30_000),
    });
    const error = res.ok ? null : `${res.status} ${(await res.text().catch(() => "")).slice(0, 200)}`;
    return { ok: res.ok, at, status: res.status, bytes: body.length, error };
  } catch (e) {
    return { ok: false, at, status: null, bytes: body.length, error: e instanceof Error ? e.message : String(e) };
  }
}
