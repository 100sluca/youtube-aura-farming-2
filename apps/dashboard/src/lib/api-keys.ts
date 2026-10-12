/**
 * Suivi des clés API (docs/49 §9) : pour chaque liste de clés et chaque modèle, la clé en service, celles qui sont tombées
 * aujourd'hui (quota du jour, refus) et la limite par jour que Google annonce. Lu par le gestionnaire des tâches et
 * Réglages → Quotas. Serveur uniquement (clé service role) ; les clés elles-mêmes ne sont jamais lues.
 */
import { EMPTY_KEY_BOARD, type KeyBoard, type KeyGroup, type KeyPool, type KeySlot, type KeyStatus } from "@/lib/api-key-types";
import { supabaseAdmin } from "@/lib/supabase-admin";

const PACIFIC = "America/Los_Angeles";

/** Date du jour à Los Angeles (AAAA-MM-JJ) : le jour de quota de Google. */
export function quotaDay(now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: PACIFIC, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

/** Prochain minuit à Los Angeles. */
export function nextReset(now = new Date()): Date {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", { timeZone: PACIFIC, hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })
      .formatToParts(now)
      .map((p) => [p.type, p.value]),
  );
  const elapsed = ((Number(parts.hour) % 24) * 3600 + Number(parts.minute) * 60 + Number(parts.second)) * 1000;
  return new Date(now.getTime() - elapsed + 86_400_000 - (now.getTime() % 1000));
}

type Row = {
  fingerprint: string;
  model: string;
  provider: string;
  pool: KeyPool;
  slot: number;
  slots: number;
  calls: number;
  ok: number;
  failed: number;
  status: KeyStatus;
  daily_limit: number | null;
  last_error: string | null;
  last_ok_at: string | null;
  blocked_until: string | null;
};

const VOICE_SECRET = /^gemini_voice_api_key(?:_(\d+))?$/;
const IA_SECRET = /^(gemini|anthropic|mistral)_api_key(?:_(\d+))?$/;

/** Derniers caractères de chaque clé enregistrée, par liste et dans l'ordre (Réglages). */
async function hints(): Promise<Map<string, (string | null)[]>> {
  const { data } = await supabaseAdmin().from("app_secrets").select("name, hint");
  const lists = new Map<string, { slot: number; hint: string | null }[]>();
  for (const r of data ?? []) {
    const name = String(r.name);
    const voice = VOICE_SECRET.exec(name);
    const ia = voice ? null : IA_SECRET.exec(name);
    const key = voice ? "voix:gemini" : ia ? `ia:${ia[1]}` : null;
    if (!key) continue;
    const slot = Number((voice ?? ia)?.[voice ? 1 : 2] ?? 1);
    (lists.get(key) ?? lists.set(key, []).get(key)!).push({ slot, hint: (r.hint as string | null) ?? null });
  }
  return new Map([...lists].map(([k, v]) => [k, v.sort((a, b) => a.slot - b.slot).map((x) => x.hint)]));
}

export async function getKeyBoard(): Promise<KeyBoard> {
  const db = supabaseAdmin();
  const day = quotaDay();
  const [{ data: rows, error }, { data: limits }, known] = await Promise.all([
    db.from("api_key_usage").select("*").eq("day", day),
    db.from("api_key_usage").select("model, daily_limit").not("daily_limit", "is", null),
    hints(),
  ]);
  if (error) return { ...EMPTY_KEY_BOARD, day }; // migration 0044 absente
  const limitOf = new Map<string, number>();
  for (const l of limits ?? []) limitOf.set(String(l.model), Math.max(limitOf.get(String(l.model)) ?? 0, Number(l.daily_limit)));

  const groups = new Map<string, Row[]>();
  for (const r of (rows ?? []) as Row[]) {
    const k = `${r.pool}|${r.provider}|${r.model}`;
    (groups.get(k) ?? groups.set(k, []).get(k)!).push(r);
  }
  const out: KeyGroup[] = [...groups.values()].map((list) => {
    const { pool, provider, model } = list[0];
    const names = known.get(`${pool}:${provider}`) ?? [];
    const size = Math.max(names.length, ...list.map((r) => r.slots), ...list.map((r) => r.slot));
    const bySlot = new Map(list.map((r) => [r.slot, r]));
    const slots: KeySlot[] = Array.from({ length: size }, (_, i) => {
      const r = bySlot.get(i + 1);
      // une limite par minute passée ou un quota du jour d'hier : la clé est de nouveau en service
      const blocked = r?.blocked_until ? new Date(r.blocked_until).getTime() > Date.now() : false;
      const status: KeyStatus = !r ? "unused" : r.status === "quota_minute" && !blocked ? "ok" : r.status;
      return {
        slot: i + 1,
        hint: names[i] ?? null,
        status,
        calls: r?.calls ?? 0,
        ok: r?.ok ?? 0,
        failed: r?.failed ?? 0,
        blockedUntil: r?.blocked_until ?? null,
        lastOkAt: r?.last_ok_at ?? null,
        lastError: r?.last_error ?? null,
      };
    });
    const last = [...slots].filter((s) => s.lastOkAt).sort((a, b) => (b.lastOkAt ?? "").localeCompare(a.lastOkAt ?? ""))[0];
    return {
      pool,
      provider,
      model,
      slots,
      current: last?.slot ?? null,
      down: slots.filter((s) => s.status === "quota_day" || s.status === "invalid").length,
      limit: limitOf.get(model) ?? null,
      okToday: slots.reduce((n, s) => n + s.ok, 0),
    };
  });
  out.sort((a, b) => (a.pool === b.pool ? a.model.localeCompare(b.model) : a.pool === "voix" ? -1 : 1));
  return { day, resetAt: nextReset().toISOString(), groups: out };
}
