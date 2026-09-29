import Link from "next/link";

import { TikTokMark, YouTubeMark } from "@/components/platform-marks";
import type { StatsPeriod } from "@/lib/stats-types";
import { cn } from "@/lib/utils";

export type StatsPlatform = "youtube" | "tiktok";

export function isStatsPlatform(value: unknown): value is StatsPlatform {
  return value === "youtube" || value === "tiktok";
}

/** Adresse du Dashboard pour une plateforme et une période (défauts : YouTube, 28 jours) ; `extra` garde le compte choisi. */
export function dashboardHref(platform: StatsPlatform, period: StatsPeriod, extra: Record<string, string | null | undefined> = {}): string {
  const q = new URLSearchParams();
  if (platform === "tiktok") q.set("plateforme", "tiktok");
  if (period !== "28") q.set("periode", period);
  for (const [k, v] of Object.entries(extra)) if (v) q.set(k, v);
  const s = q.toString();
  return s ? `/dashboard?${s}` : "/dashboard";
}

/** Onglets YouTube | TikTok du Dashboard (docs/39) : la période choisie suit d'un onglet à l'autre. */
export function PlatformTabs({ platform, period, counts }: { platform: StatsPlatform; period: StatsPeriod; counts?: Partial<Record<StatsPlatform, string>> }) {
  const tabs: { id: StatsPlatform; label: string; mark: React.ReactNode }[] = [
    { id: "youtube", label: "YouTube", mark: <YouTubeMark /> },
    { id: "tiktok", label: "TikTok", mark: <TikTokMark /> },
  ];
  return (
    <nav aria-label="Plateforme" className="bg-muted inline-flex w-fit rounded-lg p-[3px] text-sm">
      {tabs.map((t) => (
        <Link
          key={t.id}
          href={dashboardHref(t.id, period)}
          scroll={false}
          aria-current={platform === t.id ? "page" : undefined}
          className={cn(
            "flex h-9 items-center gap-2 rounded-md px-4 font-medium whitespace-nowrap transition-colors",
            platform === t.id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {t.mark}
          {t.label}
          {counts?.[t.id] ? <span className="text-muted-foreground text-xs tabular-nums">{counts[t.id]}</span> : null}
        </Link>
      ))}
    </nav>
  );
}
