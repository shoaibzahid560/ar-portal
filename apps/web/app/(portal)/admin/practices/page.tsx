import type { Metadata } from "next";
import { Suspense } from "react";
import { PracticesAdmin } from "@/components/admin/practices-admin";
import { Panel } from "@/components/data/panel";
import { PageBody, PageHeader } from "@/components/shell/page-header";

export const metadata: Metadata = { title: "Practices" };

export default function PracticesPage() {
  return (
    <>
      <PageHeader
        title="Practices"
        subtitle="Practices and teams decide what each person can see"
      />
      <PageBody>
        <Suspense fallback={<Panel>Loading…</Panel>}>
          <PracticesAdmin />
        </Suspense>
      </PageBody>
    </>
  );
}
