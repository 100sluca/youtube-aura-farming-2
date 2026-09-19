import type { NextRequest } from "next/server";

/** Scopes demandés à Google (docs/05-youtube-api.md §1). */
export const YOUTUBE_SCOPES = [
  "https://www.googleapis.com/auth/youtube.upload",
  "https://www.googleapis.com/auth/youtube",
  "https://www.googleapis.com/auth/yt-analytics.readonly",
];

export function redirectUri(req: NextRequest): string {
  const base = process.env.NEXT_PUBLIC_APP_URL ?? req.nextUrl.origin;
  return `${base}/api/youtube/callback`;
}
