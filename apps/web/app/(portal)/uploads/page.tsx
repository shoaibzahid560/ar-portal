import type { Metadata } from "next";
import { Suspense } from "react";
import { Panel } from "@/components/data/panel";
import { PageBody, PageHeader } from "@/components/shell/page-header";
import { UploadsView } from "@/components/uploads/uploads-view";

export const metadata: Metadata = { title: "Uploads" };

export default function UploadsPage() {
  return (
    <>
      <PageHeader
        title="Uploads"
        subtitle="AR sheets uploaded per practice, and what came of each one"
      />
      <PageBody>
        <Suspense fallback={<Panel>Loading uploads…</Panel>}>
          <UploadsView />
        </Suspense>
      </PageBody>
    </>
  );
}
