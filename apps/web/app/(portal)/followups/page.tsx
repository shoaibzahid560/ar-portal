import type { Metadata } from "next";
import { Suspense } from "react";
import { ClaimsTable } from "@/components/claims/claims-table";
import { Panel } from "@/components/data/panel";
import { PageBody, PageHeader } from "@/components/shell/page-header";

export const metadata: Metadata = { title: "Follow-ups" };

export default function FollowUpsPage() {
  return (
    <>
      <PageHeader
        title="Follow-ups"
        subtitle="Claims by their Follow-Up Date"
      />
      <PageBody>
        <Suspense fallback={<Panel>Loading follow-ups…</Panel>}>
          <ClaimsTable moduleKey="followups" />
        </Suspense>
      </PageBody>
    </>
  );
}
