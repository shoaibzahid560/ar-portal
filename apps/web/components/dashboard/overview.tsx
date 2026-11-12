"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import Link from "next/link";
import { ACTIONS } from "@/components/admin/audit-log";
import { ActivityList } from "@/components/data/activity-list";
import { EmptyState } from "@/components/data/empty-state";
import { MetricCard } from "@/components/data/metric-card";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Table, Td, Th } from "@/components/data/table";
import type { AuditPage, ClaimSummary, Upload } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, formatMoney } from "@/lib/format";
import { claimStatusTone, UPLOAD_STATUSES } from "@/lib/status";
import { useApi } from "@/lib/use-api";

/** Real numbers, each limited to what the signed-in person may see. */
export function DashboardOverview() {
  const { permissions } = useAuth();
  const router = useRouter();
  const clientAccount =
    permissions.includes("client_reports.view") &&
    !permissions.includes("dashboard.view");
  // Client accounts have no internal dashboard: everyone lands on /dashboard after sign-in, clients move on.
  useEffect(() => {
    if (clientAccount) router.replace("/client-reports");
  }, [clientAccount, router]);
  const canClaims = [
    "claims.view",
    "claims.view_team",
    "claims.view_practice",
  ].some((p) => permissions.includes(p));
  const canUploads = permissions.includes("uploads.view");
  const canAudit = permissions.includes("audit.view");
  const summary = useApi<ClaimSummary>(canClaims ? "/claims/summary" : null);
  const uploads = useApi<Upload[]>(canUploads ? "/uploads?limit=5" : null);
  const activity = useApi<AuditPage>(canAudit ? "/audit-events?limit=8" : null);
  const own =
    !permissions.includes("claims.view_practice") &&
    !permissions.includes("claims.view_team");

  if (!canClaims) {
    return (
      <Panel>
        <EmptyState
          title="Nothing to show yet"
          description="Your role doesn’t include claims or uploads."
        />
      </Panel>
    );
  }
  const s = summary.data;

  return (
    <>
      <section className="mb-3 grid grid-cols-4 gap-2.5 max-[1000px]:grid-cols-2">
        <MetricCard
          label={own ? "Your claims" : "Claims"}
          value={s ? String(s.total) : "…"}
          meta={s ? `${formatMoney(s.billed_total)} billed` : undefined}
        />
        <MetricCard
          label="Unassigned"
          value={s ? String(s.unassigned) : "…"}
          meta="Waiting to be assigned"
        />
        <MetricCard
          label="Follow-ups due today"
          value={s ? String(s.due_today) : "…"}
          meta="By Follow-Up Date"
        />
        <MetricCard
          label="Overdue follow-ups"
          value={s ? String(s.overdue) : "…"}
          meta="Follow-Up Date has passed"
        />
      </section>
      {s &&
        s.awaiting_completion > 0 &&
        permissions.includes("claims.close") && (
          <p className="mb-3 rounded-[9px] bg-info-soft px-3 py-2.5 text-[12px]">
            {s.awaiting_completion} claim(s) marked complete and waiting for
            your review.{" "}
            <Link
              href="/claims?view=awaiting-completion"
              className="font-bold text-brand underline"
            >
              Review them
            </Link>
          </p>
        )}
      {s && s.returned > 0 && !permissions.includes("claims.close") && (
        <p className="mb-3 rounded-[9px] bg-danger-soft px-3 py-2.5 text-[12px] text-danger-ink">
          {s.returned} claim(s) returned for correction.{" "}
          <Link href="/claims?view=returned" className="font-bold underline">
            See them
          </Link>
        </p>
      )}
      {s && s.needs_review > 0 && (
        <p className="mb-3 rounded-[9px] bg-warn-soft px-3 py-2.5 text-[12px] text-warn-ink">
          {s.needs_review} claim(s) need review: they may be changed lines of
          claims already in the system.{" "}
          <Link
            href="/claims?view=needs-review"
            className="font-bold underline"
          >
            Review them
          </Link>
        </p>
      )}

      <section
        className={
          canAudit
            ? "mb-3 grid grid-cols-[minmax(0,1.6fr)_minmax(300px,1fr)] items-start gap-3 max-[1000px]:grid-cols-1"
            : "mb-3"
        }
      >
        <Panel title="Claims by claim status" flush>
          {!s ? (
            <p className="p-4 text-muted">Loading…</p>
          ) : s.by_status.length === 0 ? (
            <EmptyState
              title="No claims yet"
              description="Claims appear once an AR sheet is uploaded."
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th className="pl-[15px]">Claim status</Th>
                  <Th className="text-right">Claims</Th>
                  <Th className="pr-[15px] text-right">Billed</Th>
                </tr>
              </thead>
              <tbody>
                {s.by_status.map((row) => (
                  <tr key={row.status}>
                    <Td className="pl-[15px]">
                      <StatusPill
                        label={row.status}
                        tone={claimStatusTone(
                          row.status === "No status yet" ? null : row.status,
                        )}
                      />
                    </Td>
                    <Td className="text-right">{row.count}</Td>
                    <Td className="pr-[15px] text-right">
                      {formatMoney(row.billed)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
        {canAudit && (
          <Panel title="Recent activity">
            <ActivityList
              items={(activity.data?.events ?? []).map((e) => ({
                id: e.id,
                title: ACTIONS[e.action]?.label ?? e.action,
                detail: `${e.actor?.name ?? "System"} · ${e.entity_type}`,
                when: formatDateTime(e.occurred_at),
                pill: {
                  label: e.entity_type,
                  tone: ACTIONS[e.action]?.tone ?? "neutral",
                },
              }))}
            />
          </Panel>
        )}
      </section>

      {canUploads && (
        <Panel
          title="Recent uploads"
          flush
          action={
            <Link href="/uploads" className="font-semibold text-brand">
              View all uploads
            </Link>
          }
        >
          {(uploads.data ?? []).length === 0 ? (
            <EmptyState title="No uploads yet" />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th className="pl-[15px]">Upload</Th>
                  <Th>Practice</Th>
                  <Th>File</Th>
                  <Th className="text-right">New claims</Th>
                  <Th>Uploaded by</Th>
                  <Th>Date</Th>
                  <Th className="pr-[15px]">Status</Th>
                </tr>
              </thead>
              <tbody>
                {uploads.data?.map((u) => (
                  <tr key={u.id}>
                    <Td className="pl-[15px] font-bold">
                      <Link
                        href={`/uploads/${u.id}`}
                        className="hover:text-brand"
                      >
                        {u.number}
                      </Link>
                    </Td>
                    <Td>{u.practice.name}</Td>
                    <Td className="max-w-[220px] truncate text-muted">
                      {u.file_name}
                    </Td>
                    <Td className="text-right">{u.created_claims}</Td>
                    <Td>{u.uploaded_by.name}</Td>
                    <Td className="whitespace-nowrap">
                      {formatDateTime(u.created_at)}
                    </Td>
                    <Td className="pr-[15px]">
                      <StatusPill
                        label={UPLOAD_STATUSES[u.status].label}
                        tone={UPLOAD_STATUSES[u.status].tone}
                      />
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
      )}
    </>
  );
}

/** "New upload" only for people who can upload. */
export function DashboardActions() {
  const { permissions } = useAuth();
  if (!permissions.includes("uploads.create")) return null;
  return (
    <Link
      href="/uploads"
      className="inline-flex h-9 items-center rounded-[7px] border border-brand bg-brand px-3 text-[12px] font-semibold text-white"
    >
      New upload
    </Link>
  );
}
