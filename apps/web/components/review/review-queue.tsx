"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { Table, Td, Th } from "@/components/data/table";
import { Button } from "@/components/ui/button";
import type { ClaimPage } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { getModule, resolveView } from "@/lib/navigation";
import { useApi } from "@/lib/use-api";

/**
 * Lines from an upload that may be a changed version of a claim already in the system.
 * Each one is decided by a person: the same claim (fold it in) or a separate claim (keep both).
 */
export function ReviewQueue() {
  const router = useRouter();
  const view = resolveView(
    getModule("review"),
    useSearchParams().get("view"),
  ).slug;
  const merged = view === "merged";
  const page = useApi<ClaimPage>(
    `/claims?view=${merged ? "merged" : "needs-review"}&limit=200`,
  );

  return (
    <>
      <p className="mb-3 text-[12px] text-muted">
        {merged
          ? "Lines a reviewer decided were the same claim as an earlier one. The earlier claim took their uploaded values; the line itself stays here for the record."
          : "When a sheet has a line for a patient, subscriber and service date that already has a claim, the line is held here. Compare it with the earlier claim and decide."}
      </p>
      <Panel flush>
        {page.error ? (
          <EmptyState
            title="The review queue could not be loaded"
            description={page.error}
          />
        ) : !page.data ? (
          <p className="p-6 text-muted">Loading…</p>
        ) : page.data.claims.length === 0 ? (
          <EmptyState
            title={merged ? "No merged lines yet" : "Nothing to review"}
            description={
              merged ? undefined : "Every uploaded line has been decided."
            }
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="pl-[15px]">Line</Th>
                <Th>Patient</Th>
                <Th>Practice</Th>
                <Th>Service date</Th>
                <Th>Insurance carrier</Th>
                <Th className="text-right">Billed</Th>
                <Th className="pr-[15px] text-right">
                  {merged ? "Merged into" : "Decision"}
                </Th>
              </tr>
            </thead>
            <tbody>
              {page.data.claims.map((c) => (
                <tr key={c.id}>
                  <Td className="pl-[15px] font-bold">
                    <Link href={`/claims/${c.id}`} className="hover:text-brand">
                      {c.number}
                    </Link>
                  </Td>
                  <Td>{c.patient_name}</Td>
                  <Td>{c.practice.name}</Td>
                  <Td className="whitespace-nowrap">
                    {formatDate(c.service_date)}
                  </Td>
                  <Td className="max-w-[240px] truncate">
                    {c.insurance_carrier}
                  </Td>
                  <Td className="text-right">{formatMoney(c.billed)}</Td>
                  <Td className="pr-[15px] text-right">
                    {merged ? (
                      c.merged_into && (
                        <Link
                          href={`/claims/${c.merged_into.id}`}
                          className="font-semibold text-brand"
                        >
                          {c.merged_into.number}
                        </Link>
                      )
                    ) : (
                      <Button
                        variant="primary"
                        onClick={() => router.push(`/review/${c.id}`)}
                      >
                        Review
                      </Button>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
    </>
  );
}
