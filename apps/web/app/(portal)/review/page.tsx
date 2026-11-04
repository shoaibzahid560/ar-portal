import type { Metadata } from "next";
import { Suspense } from "react";
import { Panel } from "@/components/data/panel";
import { ReviewQueue } from "@/components/review/review-queue";
import { PageBody, PageHeader } from "@/components/shell/page-header";

export const metadata: Metadata = { title: "Review Queue" };

export default function ReviewPage() {
  return (
    <>
      <PageHeader
        title="Review Queue"
        subtitle="Uploaded lines that may belong to a claim already in the system"
      />
      <PageBody>
        <Suspense fallback={<Panel>Loading…</Panel>}>
          <ReviewQueue />
        </Suspense>
      </PageBody>
    </>
  );
}
