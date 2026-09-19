import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { AppHeader } from "@/components/app-header";
import { AppSidebar } from "@/components/app-sidebar";
import { THEME_INIT_SCRIPT } from "@/components/theme-toggle";
import { TooltipProvider } from "@/components/ui/tooltip";
import { listAlerts } from "@/lib/data";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "YouTube 2.0",
    template: "%s · YouTube 2.0",
  },
  description: "Pilotage de l’usine à Shorts : production, calendrier, métriques.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const alerts = await listAlerts();
  const openAlerts = alerts.filter((a) => !a.acknowledged_at).length;

  return (
    <html
      lang="fr"
      className={`dark ${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-full font-sans">
        <TooltipProvider>
          <div className="flex min-h-svh">
            <AppSidebar openAlerts={openAlerts} />
            <div className="flex min-w-0 flex-1 flex-col">
              <AppHeader openAlerts={openAlerts} />
              <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-6 lg:px-8">{children}</main>
            </div>
          </div>
        </TooltipProvider>
      </body>
    </html>
  );
}
