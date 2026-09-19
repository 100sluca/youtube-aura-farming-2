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

/** Retourne l'e-mail de l'utilisateur connecté s'il figure dans `app_users`, sinon null. */
export async function currentAppUser(): Promise<string | null> {
  const supabase = await supabaseServer();
  const { data } = await supabase.auth.getUser();
  const email = data.user?.email;
  if (!email) return null;
  const { data: row } = await supabaseAdmin().from("app_users").select("email").eq("email", email).maybeSingle();
  return row ? email : null;
}
