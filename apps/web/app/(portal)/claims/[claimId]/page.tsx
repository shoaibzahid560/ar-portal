import type { Metadata } from "next";
import { Suspense } from "react";
import { ClaimWork } from "@/components/claims/claim-work";
import { Panel } from "@/components/data/panel";
import { PageBody, PageHeader } from "@/components/shell/page-header";

export const metadata: Metadata = { title: "Claim" };

export default function ClaimPage() {
  return (
    <>
      <PageHeader
        title="Claim"
        subtitle="Uploaded details, work fields, notes, EOB and history"
      />
      <PageBody>
        <Suspense fallback={<Panel>Loading the claim…</Panel>}>
          <ClaimWork />
        </Suspense>
      </PageBody>
    </>
  );
}
