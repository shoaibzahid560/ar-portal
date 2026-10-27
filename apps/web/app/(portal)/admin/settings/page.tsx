import type { Metadata } from "next";
import { Suspense } from "react";
import { SettingsAdmin } from "@/components/admin/settings-admin";
import { Panel } from "@/components/data/panel";
import { PageBody, PageHeader } from "@/components/shell/page-header";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        title="Settings"
        subtitle="Roles, permissions and system configuration"
      />
      <PageBody>
        <Suspense fallback={<Panel>Loading…</Panel>}>
          <SettingsAdmin />
        </Suspense>
      </PageBody>
    </>
  );
}
