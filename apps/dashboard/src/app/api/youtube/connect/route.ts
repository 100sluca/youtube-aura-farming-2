import { NextResponse, type NextRequest } from "next/server";

import { sign } from "@/lib/crypto";
import { currentAppUser } from "@/lib/supabase-admin";
import { redirectUri, YOUTUBE_SCOPES } from "@/lib/youtube-oauth";

export const runtime = "nodejs";

/**
 * GET /api/youtube/connect?channel=fr
 * Démarre le flux OAuth Google pour relier une chaîne (docs/05-youtube-api.md §1).
 */
export async function GET(req: NextRequest) {
  if (!(await currentAppUser())) return new NextResponse("Non autorisé", { status: 401 });
  const channel = req.nextUrl.searchParams.get("channel");
  if (!channel || !/^[a-z0-9_-]{1,32}$/.test(channel)) return new NextResponse("channel invalide", { status: 400 });
  const clientId = process.env.GOOGLE_CLIENT_ID;
  const secret = process.env.OAUTH_STATE_SECRET;
  if (!clientId || !secret) return new NextResponse("GOOGLE_CLIENT_ID / OAUTH_STATE_SECRET manquants", { status: 500 });

  const nonce = crypto.randomUUID();
  const payload = Buffer.from(JSON.stringify({ channel, nonce, ts: Date.now() })).toString("base64url");
  const state = `${payload}.${await sign(payload, secret)}`;

  const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  url.searchParams.set("client_id", clientId);
  url.searchParams.set("redirect_uri", redirectUri(req));
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", YOUTUBE_SCOPES.join(" "));
  url.searchParams.set("access_type", "offline");
  url.searchParams.set("prompt", "consent"); // force un refresh_token à chaque connexion
  url.searchParams.set("include_granted_scopes", "true");
  url.searchParams.set("state", state);

  const res = NextResponse.redirect(url);
  res.cookies.set("yt_oauth_nonce", nonce, { httpOnly: true, sameSite: "lax", secure: true, maxAge: 600, path: "/" });
  return res;
}
