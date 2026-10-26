import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { ActivityList } from "@/components/data/activity-list";
import { EmptyState } from "@/components/data/empty-state";
import { MetricCard } from "@/components/data/metric-card";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Table, Td, Th } from "@/components/data/table";
import { PageBody, PageHeader } from "@/components/shell/page-header";
import { LinkButton } from "@/components/ui/button";
import { formatCount, formatDate, formatMoney } from "@/lib/format";
import { getModule, resolveView } from "@/lib/navigation";
import {
  SAMPLE_ACTIVITY,
  SAMPLE_CLAIMS,
  SAMPLE_TODAY,
  SAMPLE_UPLOADS,
  isOpen,
  isOverdue,
} from "@/lib/sample-data";
import { CLAIM_STATUSES, UPLOAD_STATUSES, type ClaimStatus } from "@/lib/status";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage({ searchParams }: PageProps<"/dashboard">) {
  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="AR operations at a glance"
        actions={
          <LinkButton href="/uploads" variant="primary">
            New upload
          </LinkButton>
        }
      />
      <PageBody>
        <Suspense>
          {searchParams.then((params) => {
            const view = resolveView(getModule("dashboard"), typeof params.view === "string" ? params.view : null);
            return view.slug === "overview" ? (
              <Overview />
            ) : (
              <Panel>
                <EmptyState
                  title={`${view.label} is built with reporting in M6`}
                  description="This view will list the claims and uploads that need attention for the selected period."
                />
              </Panel>
            );
          })}
        </Suspense>
      </PageBody>
    </>
  );
}

function Overview() {
  const open = SAMPLE_CLAIMS.filter(isOpen);
  const unassigned = SAMPLE_CLAIMS.filter((c) => c.status === "unassigned");
  const dueToday = open.filter((c) => c.followUp === SAMPLE_TODAY);
  const overdue = SAMPLE_CLAIMS.filter((c) => isOverdue(c));

  const byStatus = (Object.keys(CLAIM_STATUSES) as ClaimStatus[]).map((status) => {
    const claims = SAMPLE_CLAIMS.filter((c) => c.status === status);
    return { status, count: claims.length, balance: claims.reduce((sum, c) => sum + c.balance, 0) };
  });

  return (
    <>
      <div className="mb-3 grid grid-cols-4 gap-2.5 max-[1100px]:grid-cols-2 max-[560px]:grid-cols-1">
        <MetricCard label="Open claims" value={formatCount(open.length)} meta={`${formatMoney(open.reduce((s, c) => s + c.balance, 0))} outstanding`} />
        <MetricCard label="Unassigned claims" value={formatCount(unassigned.length)} meta="Waiting for a manager to assign" />
        <MetricCard label="Follow-ups due today" value={formatCount(dueToday.length)} meta="Across all associates" />
        <MetricCard label="Overdue follow-ups" value={formatCount(overdue.length)} meta="Requires management attention" />
      </div>

      <div className="grid grid-cols-[1.5fr_1fr] gap-3 max-[1100px]:grid-cols-1">
        <Panel title="Claims by status">
          <Table>
            <thead>
              <tr>
                <Th>Status</Th>
                <Th className="text-right">Claims</Th>
                <Th className="text-right">Outstanding</Th>
              </tr>
            </thead>
            <tbody>
              {byStatus.map((row) => (
                <tr key={row.status}>
                  <Td>
                    <StatusPill label={CLAIM_STATUSES[row.status].label} tone={CLAIM_STATUSES[row.status].tone} />
                  </Td>
                  <Td className="text-right font-bold">{row.count}</Td>
                  <Td className="text-right">{formatMoney(row.balance)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>

        <Panel title="Recent activity">
          <ActivityList items={SAMPLE_ACTIVITY} />
        </Panel>
      </div>

      <Panel
        title="Recent uploads"
        flush
        className="mt-3"
        action={
          <Link href="/uploads" className="font-semibold text-brand hover:underline">
            View all uploads
          </Link>
        }
      >
        <Table>
          <thead>
            <tr>
              <Th className="pl-[15px]">Upload</Th>
              <Th>Practice</Th>
              <Th>File</Th>
              <Th className="text-right">Rows</Th>
              <Th>Uploaded by</Th>
              <Th>Date</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody>
            {SAMPLE_UPLOADS.map((u) => (
              <tr key={u.id}>
                <Td className="pl-[15px] font-bold">{u.id}</Td>
                <Td>{u.practice}</Td>
                <Td className="text-muted">{u.fileName}</Td>
                <Td className="text-right">{formatCount(u.rows)}</Td>
                <Td>{u.uploadedBy}</Td>
                <Td>{formatDate(u.uploadedOn)}</Td>
                <Td>
                  <StatusPill label={UPLOAD_STATUSES[u.status].label} tone={UPLOAD_STATUSES[u.status].tone} />
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>
    </>
  );
}
