import type { Metadata } from "next";

import { AlertsList } from "@/components/alerts/alerts-list";
import { PageHeader } from "@/components/page-header";
import { listAlerts } from "@/lib/data";

export const metadata: Metadata = { title: "Alertes" };

export default async function AlertsPage() {
  const alerts = await listAlerts();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader description="Événements remontés par les workers et les synchronisations YouTube. Acquittez une alerte une fois traitée." />
      <AlertsList alerts={alerts} />
    </div>
  );
}
