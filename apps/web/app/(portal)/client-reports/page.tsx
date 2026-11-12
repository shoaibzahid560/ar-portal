import type { Metadata } from "next";
import { Suspense } from "react";
import { ClientReportsSection } from "@/components/clients/client-reports";
import { Panel } from "@/components/data/panel";
import { PageBody, PageHeader } from "@/components/shell/page-header";

export const metadata: Metadata = { title: "Client Reports" };

export default function ClientReportsPage() {
  return (
    <>
      <PageHeader
        title="Client Reports"
        subtitle="Your approved reports and downloads"
      />
      <PageBody>
        <Suspense fallback={<Panel>Loading…</Panel>}>
          <ClientReportsSection />
        </Suspense>
      </PageBody>
    </>
  );
}
