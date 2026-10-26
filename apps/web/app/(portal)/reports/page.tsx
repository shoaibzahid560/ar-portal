import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/shell/module-placeholder";

export const metadata: Metadata = { title: "Reports" };

export default function ReportsPage() {
  return (
    <ModulePlaceholder
      moduleKey="reports"
      subtitle="Performance, data quality and exports"
      milestone="M6"
      description="Dashboards and downloadable XLSX, CSV and PDF reports, each logged when exported."
    />
  );
}
