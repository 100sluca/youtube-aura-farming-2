import { NextResponse, type NextRequest } from "next/server";

import { encryptSecret, sign } from "@/lib/crypto";
import { currentAppUser, supabaseAdmin } from "@/lib/supabase-admin";
import { redirectUri, YOUTUBE_SCOPES } from "@/lib/youtube-oauth";

export const runtime = "nodejs";

/**
 * GET /api/youtube/callback?code=…&state=…
 * Échange le code contre un refresh token, le chiffre dans `channel_credentials`,
 * renseigne `channels.youtube_channel_id` et renvoie vers /settings.
 */
export async function GET(req: NextRequest) {
  if (!(await currentAppUser())) return new NextResponse("Non autorisé", { status: 401 });
  const params = req.nextUrl.searchParams;
  const error = params.get("error");
  if (error) return NextResponse.redirect(new URL(`/settings?oauth_error=${encodeURIComponent(error)}`, req.url));

  const code = params.get("code");
  const state = params.get("state");
  const secret = process.env.OAUTH_STATE_SECRET;
  if (!code || !state || !secret) return new NextResponse("Paramètres manquants", { status: 400 });

  const [payload, signature] = state.split(".");
  if (!payload || signature !== (await sign(payload, secret))) return new NextResponse("state invalide", { status: 400 });
  const { channel, nonce, ts } = JSON.parse(Buffer.from(payload, "base64url").toString()) as {
    channel: string; nonce: string; ts: number;
  };
  if (req.cookies.get("yt_oauth_nonce")?.value !== nonce || Date.now() - ts > 10 * 60_000) {
    return new NextResponse("state expiré", { status: 400 });
  }

  // 1) code → tokens
  const tokenRes = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code,
      client_id: process.env.GOOGLE_CLIENT_ID!,
      client_secret: process.env.GOOGLE_CLIENT_SECRET!,
      redirect_uri: redirectUri(req),
      grant_type: "authorization_code",
    }),
  });
  if (!tokenRes.ok) return new NextResponse(`Échange OAuth refusé : ${await tokenRes.text()}`, { status: 502 });
  const tokens = (await tokenRes.json()) as {
    access_token: string; refresh_token?: string; expires_in: number; scope: string;
  };
  if (!tokens.refresh_token) {
    return new NextResponse("Pas de refresh_token : révoquer l'accès dans le compte Google puis réessayer", { status: 400 });
  }

  // 2) identité de la chaîne
  const chRes = await fetch("https://www.googleapis.com/youtube/v3/channels?part=id,snippet&mine=true", {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  });
  const ch = (await chRes.json()) as {
    items?: { id: string; snippet: { title: string; thumbnails?: Record<string, { url?: string }> } }[];
  };
  const yt = ch.items?.[0];
  if (!yt) return new NextResponse("Aucune chaîne YouTube sur ce compte Google", { status: 400 });
  const thumbs = yt.snippet.thumbnails ?? {};
  const avatar = thumbs.medium?.url ?? thumbs.high?.url ?? thumbs.default?.url ?? null;

  // 3) persistance (service role : channel_credentials n'a pas de policy RLS)
  const admin = supabaseAdmin();
  const { data: channelRow, error: chErr } = await admin.from("channels").select("id, name").eq("slug", channel).single();
  if (chErr || !channelRow) return new NextResponse(`Chaîne ${channel} inconnue`, { status: 404 });
  const granted = tokens.scope.split(" ");
  const missing = YOUTUBE_SCOPES.filter((s) => !granted.includes(s));
  if (missing.length) return new NextResponse(`Scopes manquants : ${missing.join(", ")}`, { status: 400 });
  // Une chaîne YouTube ne se relie qu'à une seule chaîne de l'appli
  const { data: other } = await admin.from("channels").select("name").eq("youtube_channel_id", yt.id).neq("id", channelRow.id).maybeSingle();
  if (other) {
    const why = `la chaîne YouTube « ${yt.snippet.title} » est déjà reliée à « ${other.name} »`;
    return NextResponse.redirect(new URL(`/settings?oauth_error=${encodeURIComponent(why)}#chaines`, req.url));
  }

  await admin.from("channel_credentials").upsert({
    channel_id: channelRow.id,
    refresh_token_encrypted: await encryptSecret(tokens.refresh_token),
    access_token: tokens.access_token,
    access_token_expires_at: new Date(Date.now() + tokens.expires_in * 1000).toISOString(),
    scopes: granted,
    updated_at: new Date().toISOString(),
  });
  await admin
    .from("channels")
    .update({ youtube_channel_id: yt.id, youtube_title: yt.snippet.title, youtube_thumbnail_url: avatar })
    .eq("id", channelRow.id);
  // 4) historique : les vidéos déjà en ligne rejoignent la bibliothèque (marquées « Importée », job import_channel)
  const { data: pending } = await admin.from("jobs").select("id").eq("type", "import_channel").eq("channel_id", channelRow.id).in("status", ["queued", "running"]).limit(1);
  if (!pending?.length) await admin.from("jobs").insert({ type: "import_channel", channel_id: channelRow.id, priority: 70 });

  const res = NextResponse.redirect(new URL(`/settings?connected=${encodeURIComponent(channelRow.name)}#chaines`, req.url));
  res.cookies.delete("yt_oauth_nonce");
  return res;
}
