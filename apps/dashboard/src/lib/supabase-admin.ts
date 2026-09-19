import { createServerClient } from "@supabase/ssr";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";

/** Client service role : routes serveur uniquement (jamais importé côté client). */
export function supabaseAdmin(): SupabaseClient {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error("NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY manquants");
  return createClient(url, key, { auth: { persistSession: false } });
}

/** Client lié à la session du navigateur (cookies) : respecte la RLS. */
export async function supabaseServer(): Promise<SupabaseClient> {
  const store = await cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => store.getAll(),
        setAll: (all) => {
          try {
            for (const { name, value, options } of all) store.set(name, value, options);
          } catch {
            // appelé depuis un Server Component : les cookies sont posés par le middleware
          }
        },
      },
    },
  );
}

/**
 * Retourne l'identité autorisée, sinon null.
 * `DASHBOARD_AUTH=none` (défaut, usage local sur le PC) : pas de connexion, tout est autorisé.
 * `DASHBOARD_AUTH=supabase` (hébergement public) : session Supabase Auth + e-mail présent dans `app_users`.
 */
export async function currentAppUser(): Promise<string | null> {
  if (process.env.DASHBOARD_AUTH !== "supabase") return "local";
  const supabase = await supabaseServer();
  const { data } = await supabase.auth.getUser();
  const email = data.user?.email;
  if (!email) return null;
  const { data: row } = await supabaseAdmin().from("app_users").select("email").eq("email", email).maybeSingle();
  return row ? email : null;
}
