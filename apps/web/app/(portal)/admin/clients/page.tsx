import type { Metadata } from "next";
import { Suspense } from "react";
import { ClientsAdmin } from "@/components/clients/clients-admin";
import { Panel } from "@/components/data/panel";
import { PageBody, PageHeader } from "@/components/shell/page-header";

export const metadata: Metadata = { title: "Clients" };

export default function ClientsPage() {
  return (
    <>
      <PageHeader
        title="Clients"
        subtitle="Client organisations, their practices, approved reports and accounts"
      />
      <PageBody>
        <Suspense fallback={<Panel>Loading…</Panel>}>
          <ClientsAdmin />
        </Suspense>
      </PageBody>
    </>
  );
}
