import type { Metadata } from "next";
import { Suspense } from "react";
import { Panel } from "@/components/data/panel";
import { PageBody, PageHeader } from "@/components/shell/page-header";
import { UploadReport } from "@/components/uploads/upload-report";

export const metadata: Metadata = { title: "Upload" };

export default function UploadPage() {
  return (
    <>
      <PageHeader title="Upload report" subtitle="Every row accounted for" />
      <PageBody>
        <Suspense fallback={<Panel>Loading…</Panel>}>
          <UploadReport />
        </Suspense>
      </PageBody>
    </>
  );
}
