import type { Metadata } from "next";
import { Suspense } from "react";
import { ClaimsTable } from "@/components/claims/claims-table";
import { Panel } from "@/components/data/panel";
import { PageBody, PageHeader } from "@/components/shell/page-header";

export const metadata: Metadata = { title: "Claims" };

export default function ClaimsPage() {
  return (
    <>
      <PageHeader
        title="Claims"
        subtitle="Every claim from the uploaded AR sheets, within your scope"
      />
      <PageBody>
        <Suspense fallback={<Panel>Loading claims…</Panel>}>
          <ClaimsTable moduleKey="claims" />
        </Suspense>
      </PageBody>
    </>
  );
}
