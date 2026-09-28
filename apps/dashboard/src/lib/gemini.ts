/**
 * Gemini en ligne, côté serveur du dashboard (docs/17-gemini-en-ligne.md) : réglages et dernier résultat
 * (app_settings « gemini » et « gemini_status »), et le Chrome dédié que le worker pilote.
 *
 * Le Chrome dédié est un Chrome ordinaire lancé avec son propre profil (DATA_DIR/gemini-chrome) et un port DevTools
 * local (127.0.0.1:9333) : Luca s'y connecte une fois à son compte Google AI, le worker s'y branche ensuite
 * (Playwright). Mêmes options que worker/providers/gemini_web.py (chrome_command) : qui le lance en premier, le
 * dashboard ou le worker, n'a pas d'importance. On ne lit jamais la valeur d'un cookie, seulement sa présence.
 */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

import { IS_MOCK } from "@/lib/data";
import { dataRoot } from "@/lib/files";
import { DEFAULT_GEMINI, GEMINI_DURATIONS, type GeminiBrowserInfo, type GeminiDuration, type GeminiSettings, type GeminiStatus } from "@/lib/gemini-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

const PORT = Number(process.env.GEMINI_CDP_PORT ?? 9333);
const SESSION_COOKIES = new Set(["SID", "__Secure-1PSID", "__Secure-3PSID"]);

export async function getGeminiSettings(): Promise<GeminiSettings> {
  if (IS_MOCK) return DEFAULT_GEMINI;
  const { data } = await supabaseAdmin().from("app_settings").select("value").eq("key", "gemini").maybeSingle();
  const v = (data?.value ?? {}) as Partial<Record<keyof GeminiSettings, unknown>>;
  const duration = String(v.duration ?? DEFAULT_GEMINI.duration);
  const authuser = Number(v.authuser);
  return {
    authuser: Number.isInteger(authuser) && authuser >= 0 ? authuser : DEFAULT_GEMINI.authuser,
    model: typeof v.model === "string" ? v.model : DEFAULT_GEMINI.model,
    duration: (GEMINI_DURATIONS as readonly string[]).includes(duration) ? (duration as GeminiDuration) : "auto",
  };
}

export async function getGeminiStatus(): Promise<GeminiStatus> {
  const empty: GeminiStatus = { at: null, ok: null, message: null, quota_until: null, last_clip_at: null };
  if (IS_MOCK) return empty;
  const { data } = await supabaseAdmin().from("app_settings").select("value").eq("key", "gemini_status").maybeSingle();
  const v = (data?.value ?? {}) as Record<string, unknown>;
  const str = (x: unknown) => (typeof x === "string" && x ? x : null);
  const until = str(v.quota_until);
  return {
    at: str(v.at),
    ok: typeof v.ok === "boolean" ? v.ok : null,
    message: str(v.message),
    quota_until: until && new Date(until).getTime() > Date.now() ? until : null,
    last_clip_at: str(v.last_clip_at),
  };
}

function chromePath(): string | null {
  const candidates = [
    process.env.GEMINI_CHROME_PATH,
    ...["PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"].map((env) => (process.env[env] ? path.join(process.env[env]!, "Google", "Chrome", "Application", "chrome.exe") : undefined)),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
  ];
  return candidates.find((c): c is string => Boolean(c) && existsSync(c!)) ?? null;
}

/** Profil dédié : GEMINI_PROFILE_DIR, sinon <dossier de données du worker>/gemini-chrome (comme le worker). */
async function profileDir(): Promise<string | null> {
  if (process.env.GEMINI_PROFILE_DIR) return process.env.GEMINI_PROFILE_DIR;
  const root = process.env.DATA_DIR ?? (await dataRoot());
  return root ? path.join(root, "gemini-chrome") : null;
}

async function devtools(): Promise<{ webSocketDebuggerUrl?: string } | null> {
  try {
    const res = await fetch(`http://127.0.0.1:${PORT}/json/version`, { cache: "no-store", signal: AbortSignal.timeout(1000) });
    return res.ok ? ((await res.json()) as { webSocketDebuggerUrl?: string }) : null;
  } catch {
    return null;
  }
}

/** Session Google présente dans le Chrome dédié ? (noms des cookies de google.com, jamais leurs valeurs) */
async function signedInViaCdp(wsUrl: string): Promise<boolean | null> {
  return new Promise((resolve) => {
    let done = false;
    const finish = (value: boolean | null, ws?: WebSocket) => {
      if (done) return;
      done = true;
      try {
        ws?.close();
      } catch {}
      resolve(value);
    };
    try {
      const ws = new WebSocket(wsUrl);
      const timer = setTimeout(() => finish(null, ws), 3000);
      ws.onopen = () => ws.send(JSON.stringify({ id: 1, method: "Storage.getCookies" }));
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(String(event.data)) as { id?: number; result?: { cookies?: { name: string; domain: string }[] } };
          if (msg.id !== 1) return;
          clearTimeout(timer);
          const cookies = msg.result?.cookies ?? [];
          finish(cookies.some((c) => SESSION_COOKIES.has(c.name) && /(^|\.)google\.com$/.test(c.domain)), ws);
        } catch {
          finish(null, ws);
        }
      };
      ws.onerror = () => finish(null, ws);
    } catch {
      finish(null);
    }
  });
}

export async function getGeminiBrowserInfo(): Promise<GeminiBrowserInfo> {
  const [profile, version] = await Promise.all([profileDir(), devtools()]);
  const running = Boolean(version);
  return {
    chrome: chromePath(),
    profile,
    profileExists: Boolean(profile && existsSync(profile)),
    port: PORT,
    running,
    signedIn: running && version?.webSocketDebuggerUrl ? await signedInViaCdp(version.webSocketDebuggerUrl) : null,
  };
}

/** Ouvre Gemini dans le Chrome dédié : nouvel onglet s'il tourne déjà, sinon lancement (fenêtre normale). */
export async function openGeminiWindow(authuser: number): Promise<{ ok: boolean; message: string }> {
  const url = `https://gemini.google.com/u/${authuser}/app`;
  if (await devtools()) {
    const res = await fetch(`http://127.0.0.1:${PORT}/json/new?${url}`, { method: "PUT", cache: "no-store", signal: AbortSignal.timeout(5000) });
    if (!res.ok) return { ok: false, message: `Chrome dédié : ouverture de l’onglet refusée (${res.status})` };
    const target = (await res.json()) as { id?: string };
    if (target.id) await fetch(`http://127.0.0.1:${PORT}/json/activate/${target.id}`, { cache: "no-store", signal: AbortSignal.timeout(5000) }).catch(() => null);
    return { ok: true, message: "Gemini ouvert dans le Chrome dédié (déjà lancé)" };
  }
  const chrome = chromePath();
  if (!chrome) return { ok: false, message: "Chrome introuvable : installer Google Chrome ou renseigner GEMINI_CHROME_PATH" };
  const profile = await profileDir();
  if (!profile) return { ok: false, message: "Dossier de données du worker inconnu : renseigner GEMINI_PROFILE_DIR (ex. C:\\YouTube2\\data\\gemini-chrome)" };
  const args = [
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--no-first-run", "--no-default-browser-check",
    "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding", url,
  ];
  spawn(chrome, args, { detached: true, stdio: "ignore", windowsHide: false }).unref();
  for (let i = 0; i < 20; i++) {
    await new Promise((r) => setTimeout(r, 500));
    if (await devtools()) return { ok: true, message: "Chrome dédié ouvert sur Gemini : connecte-toi à ton compte Google AI Pro dans cette fenêtre" };
  }
  return {
    ok: false,
    message: "Chrome ne répond pas sur son port de pilotage : si une fenêtre Chrome utilise déjà ce profil, la fermer puis réessayer",
  };
}
