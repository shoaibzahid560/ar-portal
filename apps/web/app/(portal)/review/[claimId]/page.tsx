import type { Metadata } from "next";
import { Suspense } from "react";
import { Panel } from "@/components/data/panel";
import { ReviewCompare } from "@/components/review/review-compare";
import { PageBody, PageHeader } from "@/components/shell/page-header";

export const metadata: Metadata = { title: "Review a line" };

export default function ReviewLinePage() {
  return (
    <>
      <PageHeader
        title="Review a line"
        subtitle="Same claim, or a separate claim?"
      />
      <PageBody>
        <Suspense fallback={<Panel>Loading…</Panel>}>
          <ReviewCompare />
        </Suspense>
      </PageBody>
    </>
  );
}
