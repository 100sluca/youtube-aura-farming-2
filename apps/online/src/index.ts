/**
 * Site en ligne de YouTube 2.0 (docs/65-site-en-ligne.md).
 *
 * - POST /api/ingest   : le dashboard du PC envoie son instantané (jeton INGEST_TOKEN) ; gardé tel quel dans KV.
 * - POST /api/login    : mot de passe (PASSWORD) → cookie de session signé, 30 jours.
 * - POST /api/logout   : efface le cookie.
 * - GET  /api/snapshot : le dernier instantané et son heure d'arrivée (session obligatoire).
 * Le reste (public/) est la page, sans aucune donnée : tout passe par /api/snapshot.
 *
 * Changer PASSWORD ou SESSION_SECRET déconnecte toutes les sessions ouvertes (la clé du cookie en dépend).
 * Trop d'essais ratés depuis une même adresse : 15 minutes de blocage.
 */

interface Env {
  ASSETS: Fetcher;
  DATA: KVNamespace;
  PASSWORD: string;
  INGEST_TOKEN: string;
  SESSION_SECRET: string;
}

const COOKIE = "aura_session";
const SESSION_DAYS = 30;
const MAX_FAILURES = 8;
const LOCK_S = 15 * 60;
const MAX_BODY = 5 * 1024 * 1024;

const enc = new TextEncoder();

const json = (data: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", "x-robots-tag": "noindex", ...headers },
  });

function hex(buf: ArrayBuffer): string {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function sha256(text: string): Promise<string> {
  return hex(await crypto.subtle.digest("SHA-256", enc.encode(text)));
}

async function hmac(key: string, message: string): Promise<string> {
  const k = await crypto.subtle.importKey("raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", k, enc.encode(message)));
}

/** Comparaison à temps constant de deux chaînes (hachées d'abord : même longueur). */
async function same(a: string, b: string): Promise<boolean> {
  const [x, y] = await Promise.all([sha256(a), sha256(b)]);
  let diff = 0;
  for (let i = 0; i < x.length; i++) diff |= x.charCodeAt(i) ^ y.charCodeAt(i);
  return diff === 0;
}

const sessionKey = (env: Env) => `${env.SESSION_SECRET}|${env.PASSWORD}`;

async function newSession(env: Env): Promise<string> {
  const payload = `v1.${Date.now() + SESSION_DAYS * 86_400_000}`;
  return `${payload}.${await hmac(sessionKey(env), payload)}`;
}

function readCookie(request: Request, name: string): string | null {
  for (const part of (request.headers.get("cookie") ?? "").split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return null;
}

async function authenticated(request: Request, env: Env): Promise<boolean> {
  const value = readCookie(request, COOKIE);
  if (!value) return false;
  const [version, exp, sig] = value.split(".");
  if (version !== "v1" || !exp || !sig || !(Number(exp) > Date.now())) return false;
  return same(sig, await hmac(sessionKey(env), `${version}.${exp}`));
}

const cookie = (value: string, maxAge: number) => `${COOKIE}=${value}; Path=/; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Lax`;

async function login(request: Request, env: Env): Promise<Response> {
  const ip = request.headers.get("cf-connecting-ip") ?? "inconnue";
  const failKey = `fail:${await sha256(ip)}`;
  const failures = Number((await env.DATA.get(failKey)) ?? 0);
  if (failures >= MAX_FAILURES) return json({ error: "Trop d’essais. Réessaie dans 15 minutes." }, 429);

  const body = (await request.json().catch(() => null)) as { password?: unknown } | null;
  const password = typeof body?.password === "string" ? body.password : "";
  if (!env.PASSWORD || !(await same(password, env.PASSWORD))) {
    await env.DATA.put(failKey, String(failures + 1), { expirationTtl: LOCK_S });
    await new Promise((r) => setTimeout(r, 400));
    return json({ error: "Mot de passe incorrect." }, 401);
  }
  return json({ ok: true }, 200, { "set-cookie": cookie(await newSession(env), SESSION_DAYS * 86_400) });
}

async function ingest(request: Request, env: Env): Promise<Response> {
  const auth = request.headers.get("authorization") ?? "";
  if (!env.INGEST_TOKEN || !auth.startsWith("Bearer ") || !(await same(auth.slice(7), env.INGEST_TOKEN))) return json({ error: "jeton refusé" }, 401);
  const length = Number(request.headers.get("content-length") ?? 0);
  if (length > MAX_BODY) return json({ error: "trop gros" }, 413);
  const text = await request.text();
  if (text.length > MAX_BODY) return json({ error: "trop gros" }, 413);
  let data: { version?: unknown; generated_at?: unknown };
  try {
    data = JSON.parse(text);
  } catch {
    return json({ error: "JSON illisible" }, 400);
  }
  if (typeof data?.version !== "number" || typeof data?.generated_at !== "string") return json({ error: "instantané invalide" }, 400);
  const receivedAt = new Date().toISOString();
  await env.DATA.put("snapshot", text, { metadata: { received_at: receivedAt } });
  return json({ ok: true, received_at: receivedAt, bytes: text.length });
}

async function snapshot(env: Env): Promise<Response> {
  const { value, metadata } = await env.DATA.getWithMetadata<{ received_at?: string }>("snapshot");
  if (!value) return json({ received_at: null, snapshot: null });
  return new Response(`{"received_at":${JSON.stringify(metadata?.received_at ?? null)},"snapshot":${value}}`, {
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", "x-robots-tag": "noindex" },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);
    const method = request.method;

    if (pathname === "/api/ingest" && method === "POST") return ingest(request, env);
    if (pathname === "/api/login" && method === "POST") return login(request, env);
    if (pathname === "/api/logout" && method === "POST") return json({ ok: true }, 200, { "set-cookie": cookie("", 0) });
    if (pathname === "/api/session" && method === "GET") return json({ authenticated: await authenticated(request, env) });
    if (pathname === "/api/snapshot" && method === "GET") {
      if (!(await authenticated(request, env))) return json({ error: "connexion requise" }, 401);
      return snapshot(env);
    }
    if (pathname.startsWith("/api/")) return json({ error: "introuvable" }, 404);
    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;
