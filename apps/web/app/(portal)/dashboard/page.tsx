import type { Metadata } from "next";
import { Suspense } from "react";
import {
  DashboardActions,
  DashboardOverview,
} from "@/components/dashboard/overview";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { ApiStatus } from "@/components/shell/api-status";
import { PageBody, PageHeader } from "@/components/shell/page-header";
import { getModule, resolveView } from "@/lib/navigation";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage({
  searchParams,
}: PageProps<"/dashboard">) {
  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="AR operations at a glance"
        actions={
          <>
            <ApiStatus />
            <DashboardActions />
          </>
        }
      />
      <PageBody>
        <Suspense>
          {searchParams.then((params) => {
            const view = resolveView(
              getModule("dashboard"),
              typeof params.view === "string" ? params.view : null,
            );
            return view.slug === "overview" ? (
              <DashboardOverview />
            ) : (
              <Panel>
                <EmptyState
                  title={`${view.label} is built with reporting in M6`}
                  description="The Overview shows live numbers now."
                />
              </Panel>
            );
          })}
        </Suspense>
      </PageBody>
    </>
  );
}
