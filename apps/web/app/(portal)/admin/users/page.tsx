import type { Metadata } from "next";
import { Suspense } from "react";
import { UsersAdmin } from "@/components/admin/users-admin";
import { Panel } from "@/components/data/panel";
import { PageBody, PageHeader } from "@/components/shell/page-header";

export const metadata: Metadata = { title: "Users" };

export default function UsersPage() {
  return (
    <>
      <PageHeader
        title="Users"
        subtitle="Employee access, roles, practices and teams"
      />
      <PageBody>
        <Suspense fallback={<Panel>Loading users…</Panel>}>
          <UsersAdmin />
        </Suspense>
      </PageBody>
    </>
  );
}
