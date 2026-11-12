import type { Metadata } from "next";
import { Suspense } from "react";
import { Panel } from "@/components/data/panel";
import { ReportsSection } from "@/components/reports/reports-section";
import { PageBody, PageHeader } from "@/components/shell/page-header";

export const metadata: Metadata = { title: "Reports" };

export default function ReportsPage() {
  return (
    <>
      <PageHeader
        title="Reports"
        subtitle="Performance, productivity, data quality and downloads, within your scope"
      />
      <PageBody>
        <Suspense fallback={<Panel>Loading…</Panel>}>
          <ReportsSection />
        </Suspense>
      </PageBody>
    </>
  );
}
