import type { Metadata } from "next";
import { Suspense } from "react";
import { AuditLog } from "@/components/admin/audit-log";
import { Panel } from "@/components/data/panel";
import { PageBody, PageHeader } from "@/components/shell/page-header";

export const metadata: Metadata = { title: "Audit" };

export default function AuditPage() {
  return (
    <>
      <PageHeader
        title="Audit"
        subtitle="Every sign-in and every change, with who made it and when"
      />
      <PageBody>
        <Suspense fallback={<Panel>Loading…</Panel>}>
          <AuditLog />
        </Suspense>
      </PageBody>
    </>
  );
}
