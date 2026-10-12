/** Appels au Worker (apps/online/src/index.ts). */
import type { SnapshotResponse } from "@/lib/snapshot";

async function call<T>(path: string, init?: RequestInit): Promise<{ status: number; body: T }> {
  const res = await fetch(path, { credentials: "same-origin", headers: { "content-type": "application/json" }, ...init });
  return { status: res.status, body: (await res.json().catch(() => ({}))) as T };
}

export const getSnapshot = () => call<SnapshotResponse & { error?: string }>("/api/snapshot");
export const login = (password: string) => call<{ ok?: boolean; error?: string }>("/api/login", { method: "POST", body: JSON.stringify({ password }) });
export const logout = () => call("/api/logout", { method: "POST" });
